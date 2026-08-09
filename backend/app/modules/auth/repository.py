from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from app.core.database import get_connection


class UserRepository:
    """Persistence boundary for application users."""

    def create(self, username: str, email: str, password_hash: str, role: str) -> dict:
        with get_connection() as connection:
            connection.execute("LOCK TABLE app_users IN EXCLUSIVE MODE")
            next_uid = self._next_uid(connection)
            row = connection.execute(
                """
                INSERT INTO app_users (id, uid, username, email, password_hash, role)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, uid, username, email, role, created_at
                """,
                (str(uuid4()), next_uid, username, email, password_hash, role),
            ).fetchone()
            connection.commit()
        return dict(row)

    @staticmethod
    def _next_uid(connection) -> str:
        latest = connection.execute(
            """
            SELECT uid FROM app_users
            WHERE uid ~ '^[0-9]+$'
            ORDER BY uid::bigint DESC LIMIT 1
            """
        ).fetchone()
        return f"{int(latest['uid']) + 1 if latest else 0:05d}"

    def create_admin_with_invite(
        self,
        username: str,
        email: str,
        password_hash: str,
        invite_hash: str,
    ) -> dict:
        """Create an admin and consume one invite in the same transaction."""
        with get_connection() as connection:
            invite = connection.execute(
                """
                SELECT id
                FROM admin_invites
                WHERE code_hash = %s
                  AND consumed_at IS NULL
                  AND revoked_at IS NULL
                  AND expires_at > now()
                FOR UPDATE
                """,
                (invite_hash,),
            ).fetchone()
            if not invite:
                raise ValueError("Invitation code is invalid, expired, revoked, or already used.")

            connection.execute("LOCK TABLE app_users IN EXCLUSIVE MODE")
            user_id = uuid4()
            row = connection.execute(
                """
                INSERT INTO app_users (id, uid, username, email, password_hash, role)
                VALUES (%s, %s, %s, %s, %s, 'admin')
                RETURNING id, uid, username, email, role, created_at
                """,
                (
                    str(user_id),
                    self._next_uid(connection),
                    username,
                    email,
                    password_hash,
                ),
            ).fetchone()
            connection.execute(
                """
                UPDATE admin_invites
                SET consumed_at = now(), consumed_by_user_id = %s
                WHERE id = %s
                """,
                (str(user_id), str(invite["id"])),
            )
            connection.commit()
        return dict(row)

    def admin_exists(self) -> bool:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT EXISTS (SELECT 1 FROM app_users WHERE role = 'admin') AS present"
            ).fetchone()
        return bool(row["present"])

    def find_for_authentication(self, username: str) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT id, uid, username, email, password_hash, role, created_at
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
                SELECT id, uid, username, email, role, created_at
                FROM app_users
                WHERE uid = %s
                """,
                (uid,),
            ).fetchone()
        return dict(row) if row else None


user_repository = UserRepository()


class AdminInviteRepository:
    """Persistence boundary for single-use administrator invitations."""

    def create(
        self,
        *,
        code_hash: str,
        code_prefix: str,
        expires_at: datetime,
        created_by_user_id: UUID | str | None,
        replace_bootstrap: bool = False,
    ) -> dict:
        with get_connection() as connection:
            if replace_bootstrap:
                connection.execute(
                    """
                    UPDATE admin_invites
                    SET revoked_at = now()
                    WHERE created_by_user_id IS NULL
                      AND consumed_at IS NULL
                      AND revoked_at IS NULL
                    """
                )
            row = connection.execute(
                """
                INSERT INTO admin_invites (
                    id, code_hash, code_prefix, created_by_user_id, expires_at
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, code_prefix, created_by_user_id, expires_at,
                          consumed_at, revoked_at, created_at
                """,
                (
                    str(uuid4()),
                    code_hash,
                    code_prefix,
                    str(created_by_user_id) if created_by_user_id else None,
                    expires_at,
                ),
            ).fetchone()
            connection.commit()
        return dict(row)

    def list_all(self) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT i.id, i.code_prefix, i.expires_at, i.consumed_at,
                       i.revoked_at, i.created_at,
                       creator.username AS created_by_username,
                       consumer.username AS consumed_by_username
                FROM admin_invites i
                LEFT JOIN app_users creator ON creator.id = i.created_by_user_id
                LEFT JOIN app_users consumer ON consumer.id = i.consumed_by_user_id
                ORDER BY i.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke(self, invite_id: UUID | str) -> bool:
        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE admin_invites
                SET revoked_at = now()
                WHERE id = %s AND consumed_at IS NULL AND revoked_at IS NULL
                RETURNING id
                """,
                (str(invite_id),),
            ).fetchone()
            connection.commit()
        return row is not None


admin_invite_repository = AdminInviteRepository()
