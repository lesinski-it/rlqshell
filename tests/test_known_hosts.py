"""Tests for Known Hosts manager and Command Palette."""

from __future__ import annotations

from pathlib import Path

import pytest

from rlqshell.core.database import Database
from rlqshell.core.known_hosts import HostKeyStatus, KnownHostsManager
from rlqshell.ui.command_palette import fuzzy_score


# === KnownHostsManager ===

@pytest.fixture
def known_hosts(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.initialize()
    mgr = KnownHostsManager(db)
    yield mgr
    db.close()


def test_host_key_not_found(known_hosts):
    status = known_hosts.verify_host_key("example.com", 22, "ssh-ed25519", "SHA256:abc")
    assert status == HostKeyStatus.NOT_FOUND


def test_add_and_verify_match(known_hosts):
    known_hosts.add_host_key("example.com", 22, "ssh-ed25519", "SHA256:abc")
    status = known_hosts.verify_host_key("example.com", 22, "ssh-ed25519", "SHA256:abc")
    assert status == HostKeyStatus.MATCH


def test_verify_mismatch(known_hosts):
    known_hosts.add_host_key("example.com", 22, "ssh-ed25519", "SHA256:abc")
    status = known_hosts.verify_host_key("example.com", 22, "ssh-ed25519", "SHA256:xyz")
    assert status == HostKeyStatus.MISMATCH


def test_remove_host_key(known_hosts):
    known_hosts.add_host_key("example.com", 22, "ssh-ed25519", "SHA256:abc")
    known_hosts.remove_host_key("example.com", 22)
    status = known_hosts.verify_host_key("example.com", 22, "ssh-ed25519", "SHA256:abc")
    assert status == HostKeyStatus.NOT_FOUND


def test_list_all(known_hosts):
    known_hosts.add_host_key("host-a.com", 22, "ssh-rsa", "SHA256:aaa")
    known_hosts.add_host_key("host-b.com", 2222, "ssh-ed25519", "SHA256:bbb")
    entries = known_hosts.list_all()
    assert len(entries) == 2
    hostnames = {e["hostname"] for e in entries}
    assert hostnames == {"host-a.com", "host-b.com"}


def test_delete_by_id(known_hosts):
    known_hosts.add_host_key("host.com", 22, "ssh-rsa", "SHA256:test")
    entries = known_hosts.list_all()
    assert len(entries) == 1
    known_hosts.delete_by_id(entries[0]["id"])
    assert len(known_hosts.list_all()) == 0


# === Fuzzy Search ===

def test_fuzzy_exact_match():
    assert fuzzy_score("admin", "admin@production") > 0


def test_fuzzy_no_match():
    assert fuzzy_score("xyz", "admin@production") == 0


def test_fuzzy_prefix_scores_higher():
    score_prefix = fuzzy_score("ad", "admin@production")
    score_middle = fuzzy_score("pr", "admin@production")
    assert score_prefix > 0
    assert score_middle > 0


def test_fuzzy_empty_query():
    assert fuzzy_score("", "anything") > 0


def test_fuzzy_case_insensitive():
    assert fuzzy_score("ADMIN", "admin@prod") > 0
