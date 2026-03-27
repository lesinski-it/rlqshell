"""Tests for cloud sync components."""

from __future__ import annotations

from pathlib import Path

import pytest

from termplus.core.sync.conflict_resolver import ConflictResolver, ConflictStrategy
from termplus.core.sync.sync_state import SyncState


# === ConflictResolver ===

def test_last_write_wins_remote_newer():
    resolver = ConflictResolver(ConflictStrategy.LAST_WRITE_WINS)
    result = resolver.resolve(local_modified=1000.0, remote_modified=2000.0)
    assert result == "remote"


def test_last_write_wins_local_newer():
    resolver = ConflictResolver(ConflictStrategy.LAST_WRITE_WINS)
    result = resolver.resolve(local_modified=3000.0, remote_modified=2000.0)
    assert result == "local"


def test_keep_local_strategy():
    resolver = ConflictResolver(ConflictStrategy.KEEP_LOCAL)
    result = resolver.resolve(local_modified=1000.0, remote_modified=9999.0)
    assert result == "local"


def test_keep_remote_strategy():
    resolver = ConflictResolver(ConflictStrategy.KEEP_REMOTE)
    result = resolver.resolve(local_modified=9999.0, remote_modified=1000.0)
    assert result == "remote"


def test_lww_none_timestamps():
    resolver = ConflictResolver(ConflictStrategy.LAST_WRITE_WINS)
    assert resolver.resolve(None, None) == "local"
    assert resolver.resolve(None, 1000.0) == "remote"
    assert resolver.resolve(1000.0, None) == "local"


# === SyncState ===

def test_sync_state_persistence(tmp_path: Path):
    state_file = tmp_path / "sync_state.json"

    state = SyncState(state_file)
    assert state.status == "idle"
    assert state.provider == ""
    assert state.device_id  # should be generated

    state.set_provider("OneDrive")
    state.update_after_sync("abc123", "abc123")

    # Reload from disk
    state2 = SyncState(state_file)
    assert state2.provider == "OneDrive"
    assert state2.last_sync is not None
    assert state2.device_id == state.device_id


def test_sync_state_needs_sync(tmp_path: Path):
    state = SyncState(tmp_path / "sync_state.json")

    # Create a test file
    db_file = tmp_path / "test.db"
    db_file.write_bytes(b"test data")

    assert state.needs_sync(db_file)  # never synced

    file_hash = SyncState.compute_file_hash(db_file)
    state.update_after_sync(file_hash, file_hash)

    assert not state.needs_sync(db_file)  # hash matches

    db_file.write_bytes(b"changed data")
    assert state.needs_sync(db_file)  # hash changed


def test_compute_file_hash(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_bytes(b"hello world")
    h = SyncState.compute_file_hash(f)
    assert len(h) == 64  # SHA256 hex
    assert h == SyncState.compute_file_hash(f)  # deterministic


def test_compute_hash_nonexistent(tmp_path: Path):
    assert SyncState.compute_file_hash(tmp_path / "nope") == ""


def test_build_meta(tmp_path: Path):
    state = SyncState(tmp_path / "sync_state.json")
    meta = state.build_meta("0.1.0", "abc123")
    assert meta.app_version == "0.1.0"
    assert meta.db_hash == "abc123"
    assert meta.device_id == state.device_id
    assert meta.last_modified  # should be non-empty
