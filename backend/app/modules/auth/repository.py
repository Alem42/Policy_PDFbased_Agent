from __future__ import annotations

from uuid import uuid4

from app.core.database import get_connection


class UserRepository:
    """Persistence boundary for application users."""

    def create(self, username: str, password_hash: str, role: str) -> dict:
        with get_connection() as connection:
            connection.execute("LOCK TABLE app_users IN EXCLUSIVE MODE")
            latest = connection.execute(
                """
                SELECT uid FROM app_users
                WHERE uid ~ '^[0-9]+$'
                ORDER BY uid::bigint DESC LIMIT 1
                """
            ).fetchone()
            next_uid = f"{int(latest['uid']) + 1 if latest else 0:05d}"
            row = connection.execute(
                """
                INSERT INTO app_users (id, uid, username, password_hash, role)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, uid, username, role, created_at
                """,
                (str(uuid4()), next_uid, username, password_hash, role),
            ).fetchone()
            connection.commit()
        return dict(row)

    def find_for_authentication(self, username: str) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT id, uid, username, password_hash, role, created_at
                FROM app_users
                WHERE username = %s
                """,
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def find_by_uid(self, uid: str) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT id, uid, username, role, created_at
                FROM app_users
                WHERE uid = %s
                """,
                (uid,),
            ).fetchone()
        return dict(row) if row else None


user_repository = UserRepository()
