"""CRUD operations for Snippets and SnippetPackages."""

from __future__ import annotations

import logging

from termplus.core.database import Database
from termplus.core.models.snippet import Snippet, SnippetPackage

logger = logging.getLogger(__name__)


class SnippetManager:
    """Manages snippets and snippet packages in the database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # --- Packages ---

    def create_package(self, package: SnippetPackage) -> int:
        """Insert a new package and return its id."""
        cursor = self._db.execute(
            "INSERT INTO snippet_packages (vault_id, name, icon, sort_order) VALUES (?, ?, ?, ?)",
            (package.vault_id, package.name, package.icon, package.sort_order),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def update_package(self, package: SnippetPackage) -> None:
        """Update an existing package."""
        self._db.execute(
            "UPDATE snippet_packages SET vault_id=?, name=?, icon=?, sort_order=? WHERE id=?",
            (package.vault_id, package.name, package.icon, package.sort_order, package.id),
        )

    def delete_package(self, package_id: int) -> None:
        """Delete a package by id."""
        self._db.execute("DELETE FROM snippet_packages WHERE id=?", (package_id,))

    def list_packages(self, vault_id: int = 1) -> list[SnippetPackage]:
        """List all packages in a vault."""
        rows = self._db.fetchall(
            "SELECT * FROM snippet_packages WHERE vault_id=? ORDER BY sort_order, name",
            (vault_id,),
        )
        return [
            SnippetPackage(
                id=r["id"], vault_id=r["vault_id"], name=r["name"],
                icon=r["icon"], sort_order=r["sort_order"],
            )
            for r in rows
        ]

    # --- Snippets ---

    def create_snippet(self, snippet: Snippet) -> int:
        """Insert a new snippet and return its id."""
        cursor = self._db.execute(
            """INSERT INTO snippets
                (vault_id, package_id, name, script, description, run_as_sudo, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                snippet.vault_id, snippet.package_id, snippet.name,
                snippet.script, snippet.description, snippet.run_as_sudo,
                snippet.sort_order,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def update_snippet(self, snippet: Snippet) -> None:
        """Update an existing snippet."""
        self._db.execute(
            """UPDATE snippets SET
                vault_id=?, package_id=?, name=?, script=?, description=?,
                run_as_sudo=?, sort_order=?
            WHERE id=?""",
            (
                snippet.vault_id, snippet.package_id, snippet.name,
                snippet.script, snippet.description, snippet.run_as_sudo,
                snippet.sort_order, snippet.id,
            ),
        )

    def delete_snippet(self, snippet_id: int) -> None:
        """Delete a snippet by id."""
        self._db.execute("DELETE FROM snippets WHERE id=?", (snippet_id,))

    def get_snippet(self, snippet_id: int) -> Snippet | None:
        """Fetch a single snippet by id."""
        row = self._db.fetchone("SELECT * FROM snippets WHERE id=?", (snippet_id,))
        if row is None:
            return None
        return self._row_to_snippet(row)

    def list_snippets(
        self,
        vault_id: int = 1,
        package_id: int | None = None,
        search: str | None = None,
    ) -> list[Snippet]:
        """List snippets with optional filtering."""
        sql = "SELECT * FROM snippets WHERE vault_id=?"
        params: list = [vault_id]

        if package_id is not None:
            sql += " AND package_id=?"
            params.append(package_id)

        if search:
            sql += " AND (name LIKE ? OR script LIKE ? OR description LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like, like])

        sql += " ORDER BY sort_order, name"
        rows = self._db.fetchall(sql, tuple(params))
        return [self._row_to_snippet(r) for r in rows]

    @staticmethod
    def _row_to_snippet(row: dict | object) -> Snippet:
        return Snippet(
            id=row["id"],
            vault_id=row["vault_id"],
            package_id=row["package_id"],
            name=row["name"],
            script=row["script"],
            description=row["description"],
            run_as_sudo=bool(row["run_as_sudo"]),
            sort_order=row["sort_order"],
            created_at=row["created_at"],
        )
