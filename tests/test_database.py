"""Tests for Database, HostManager, SnippetManager, and Vault."""

from __future__ import annotations

from termplus.core.database import Database
from termplus.core.host_manager import HostManager
from termplus.core.models.host import Group, Host, Tag
from termplus.core.models.snippet import Snippet, SnippetPackage
from termplus.core.snippet_manager import SnippetManager
from termplus.core.vault import Vault


def _make_db(tmp_path) -> Database:
    db = Database(tmp_path / "test.db")
    db.initialize()
    return db


# === Database init ===

def test_database_creates_tables(tmp_path):
    db = _make_db(tmp_path)
    tables = db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {r["name"] for r in tables}
    assert "hosts" in names
    assert "vaults" in names
    assert "tags" in names
    assert "snippets" in names
    assert "sync_state" in names
    db.close()


def test_default_vault_created(tmp_path):
    db = _make_db(tmp_path)
    row = db.fetchone("SELECT * FROM vaults WHERE is_default=1")
    assert row is not None
    assert row["name"] == "Personal"
    db.close()


# === Host CRUD ===

def test_create_and_get_host(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    host = Host(label="web-1", address="10.0.1.10", protocol="ssh")
    host_id = mgr.create_host(host)
    assert host_id > 0

    fetched = mgr.get_host(host_id)
    assert fetched is not None
    assert fetched.label == "web-1"
    assert fetched.address == "10.0.1.10"
    assert fetched.ssh_port == 22
    db.close()


def test_update_host(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    host_id = mgr.create_host(Host(label="old-name", address="1.2.3.4"))
    host = mgr.get_host(host_id)
    assert host is not None

    host.label = "new-name"
    host.ssh_port = 2222
    mgr.update_host(host)

    updated = mgr.get_host(host_id)
    assert updated is not None
    assert updated.label == "new-name"
    assert updated.ssh_port == 2222
    db.close()


def test_delete_host(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    host_id = mgr.create_host(Host(label="to-delete", address="5.5.5.5"))
    mgr.delete_host(host_id)
    assert mgr.get_host(host_id) is None
    db.close()


def test_list_hosts_search(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    mgr.create_host(Host(label="web-server", address="10.0.1.1"))
    mgr.create_host(Host(label="db-server", address="10.0.1.2"))
    mgr.create_host(Host(label="nas", address="192.168.1.10"))

    results = mgr.list_hosts(search="web")
    assert len(results) == 1
    assert results[0].label == "web-server"

    results = mgr.list_hosts(search="10.0")
    assert len(results) == 2
    db.close()


# === Group CRUD ===

def test_create_and_list_groups(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    gid = mgr.create_group(Group(name="Production"))
    assert gid > 0

    groups = mgr.list_groups()
    assert len(groups) == 1
    assert groups[0].name == "Production"
    db.close()


def test_host_in_group(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    gid = mgr.create_group(Group(name="Staging"))
    mgr.create_host(Host(label="stg-1", address="10.0.2.1", group_id=gid))
    mgr.create_host(Host(label="prod-1", address="10.0.1.1"))

    in_group = mgr.list_hosts(group_id=gid)
    assert len(in_group) == 1
    assert in_group[0].label == "stg-1"
    db.close()


def test_delete_group_nullifies_hosts(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    gid = mgr.create_group(Group(name="Temp"))
    host_id = mgr.create_host(Host(label="h1", address="1.1.1.1", group_id=gid))
    mgr.delete_group(gid)

    host = mgr.get_host(host_id)
    assert host is not None
    assert host.group_id is None
    db.close()


# === Tags ===

def test_tags_crud(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    tid = mgr.create_tag(Tag(name="critical", color="#e94560"))
    assert tid > 0

    tags = mgr.list_tags()
    assert len(tags) == 1
    assert tags[0].name == "critical"

    mgr.delete_tag(tid)
    assert len(mgr.list_tags()) == 0
    db.close()


def test_host_tags(tmp_path):
    db = _make_db(tmp_path)
    mgr = HostManager(db)
    host_id = mgr.create_host(Host(label="tagged", address="2.2.2.2"))
    t1 = mgr.create_tag(Tag(name="prod", color="#22c55e"))
    t2 = mgr.create_tag(Tag(name="web", color="#3b82f6"))

    mgr.add_tag_to_host(host_id, t1)
    mgr.add_tag_to_host(host_id, t2)

    tags = mgr.get_host_tags(host_id)
    assert len(tags) == 2
    names = {t.name for t in tags}
    assert names == {"prod", "web"}

    mgr.remove_tag_from_host(host_id, t1)
    assert len(mgr.get_host_tags(host_id)) == 1
    db.close()


# === Snippets ===

def test_snippet_crud(tmp_path):
    db = _make_db(tmp_path)
    mgr = SnippetManager(db)

    pkg_id = mgr.create_package(SnippetPackage(name="Docker"))
    sid = mgr.create_snippet(Snippet(
        name="PS", script="docker ps -a", package_id=pkg_id,
    ))
    assert sid > 0

    snippet = mgr.get_snippet(sid)
    assert snippet is not None
    assert snippet.name == "PS"
    assert snippet.script == "docker ps -a"

    snippet.name = "List Containers"
    mgr.update_snippet(snippet)
    assert mgr.get_snippet(sid).name == "List Containers"

    mgr.delete_snippet(sid)
    assert mgr.get_snippet(sid) is None
    db.close()


def test_snippet_search(tmp_path):
    db = _make_db(tmp_path)
    mgr = SnippetManager(db)
    mgr.create_snippet(Snippet(name="Update", script="apt update"))
    mgr.create_snippet(Snippet(name="Restart Nginx", script="systemctl restart nginx"))

    results = mgr.list_snippets(search="nginx")
    assert len(results) == 1
    assert results[0].name == "Restart Nginx"
    db.close()


# === Vault ===

def test_vault_integration(tmp_path):
    db = Database(tmp_path / "vault.db")
    vault = Vault(db)
    vault.initialize()

    vault.hosts.create_host(Host(label="test", address="1.1.1.1"))
    vault.snippets.create_snippet(Snippet(name="uptime", script="uptime"))

    assert len(vault.hosts.list_hosts()) == 1
    assert len(vault.snippets.list_snippets()) == 1
    vault.close()
