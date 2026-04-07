"""Sync conflict resolution strategies."""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ConflictStrategy(Enum):
    LAST_WRITE_WINS = "last_write_wins"
    KEEP_LOCAL = "keep_local"
    KEEP_REMOTE = "keep_remote"


class ConflictResolver:
    """Determines which version to keep when both local and remote changed."""

    def __init__(self, strategy: ConflictStrategy = ConflictStrategy.LAST_WRITE_WINS) -> None:
        self._strategy = strategy

    @property
    def strategy(self) -> ConflictStrategy:
        return self._strategy

    @strategy.setter
    def strategy(self, value: ConflictStrategy) -> None:
        self._strategy = value

    def resolve(
        self,
        local_modified: float | None,
        remote_modified: float | None,
    ) -> str:
        """Return 'local' or 'remote' based on the strategy.

        Parameters are timestamps (epoch seconds). None means unknown.
        """
        if self._strategy == ConflictStrategy.KEEP_LOCAL:
            return "local"
        if self._strategy == ConflictStrategy.KEEP_REMOTE:
            return "remote"

        # LAST_WRITE_WINS
        if local_modified is None and remote_modified is None:
            return "local"
        if local_modified is None:
            return "remote"
        if remote_modified is None:
            return "local"

        if remote_modified > local_modified:
            logger.info("Conflict resolved: remote is newer")
            return "remote"
        else:
            logger.info("Conflict resolved: local is newer or equal")
            return "local"
