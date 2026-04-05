"""Snippet and SnippetPackage data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class SnippetPackage:
    """A folder/category for organizing snippets."""

    id: int | None = None
    vault_id: int = 1
    name: str = ""
    icon: str | None = None
    sort_order: int = 0


@dataclass
class Snippet:
    """A saved command/script."""

    id: int | None = None
    vault_id: int = 1
    package_id: int | None = None
    name: str = ""
    script: str = ""
    description: str | None = None
    run_as_sudo: bool = False
    color_label: str | None = None
    sort_order: int = 0
    created_at: datetime | None = None
    tags: list[str] | None = None
