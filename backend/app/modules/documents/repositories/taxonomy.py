from __future__ import annotations

from uuid import uuid4

from app.core.database import get_connection


class TaxonomyRepository:
    """Persistence for the admin-editable two-level policy taxonomy."""

    def load_tree(self) -> list[dict]:
        """Return groups ordered by parent_order then child_order."""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT parent, child, source_ref, parent_order, child_order
                FROM policy_taxonomy
                ORDER BY parent_order, parent, child_order, child
                """
            ).fetchall()

        groups: list[dict] = []
        index: dict[str, dict] = {}
        for row in rows:
            group = index.get(row["parent"])
            if group is None:
                group = {"parent": row["parent"], "source_ref": row["source_ref"], "children": []}
                index[row["parent"]] = group
                groups.append(group)
            group["children"].append(row["child"])
        return groups

    def is_empty(self) -> bool:
        with get_connection() as connection:
            row = connection.execute("SELECT EXISTS(SELECT 1 FROM policy_taxonomy) AS e").fetchone()
        return not (row and row["e"])

    def replace_tree(self, groups: list[dict]) -> None:
        """Atomically replace the whole taxonomy (delete-all then insert)."""
        with get_connection() as connection:
            connection.execute("DELETE FROM policy_taxonomy")
            for parent_order, group in enumerate(groups):
                for child_order, child in enumerate(group["children"]):
                    connection.execute(
                        """
                        INSERT INTO policy_taxonomy
                            (id, parent, child, parent_order, child_order, source_ref, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, now())
                        """,
                        (
                            str(uuid4()),
                            group["parent"],
                            child,
                            parent_order,
                            child_order,
                            group.get("source_ref"),
                        ),
                    )
            connection.commit()


taxonomy_repository = TaxonomyRepository()
