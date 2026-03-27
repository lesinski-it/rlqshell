"""Vault — unified access point for all core managers."""

from __future__ import annotations

import logging

from termplus.core.database import Database
from termplus.core.host_manager import HostManager
from termplus.core.snippet_manager import SnippetManager

logger = logging.getLogger(__name__)


class Vault:
    """Central container that owns the database and delegates to managers.

    Usage:
        vault = Vault(db_path)
        vault.initialize()
        hosts = vault.hosts.list_hosts()
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._hosts = HostManager(db)
        self._snippets = SnippetManager(db)

    def initialize(self) -> None:
        """Initialize the database schema and seed defaults."""
        self._db.initialize()
        logger.info("Vault initialized")

    @property
    def db(self) -> Database:
        return self._db

    @property
    def hosts(self) -> HostManager:
        return self._hosts

    @property
    def snippets(self) -> SnippetManager:
        return self._snippets

    def close(self) -> None:
        """Close the underlying database."""
        self._db.close()
