from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from app.core.database import get_connection


class UserRepository:
    """Persistence boundary for application users."""

    def create(self, username: str, email: str, password_hash: str, role: str) -> dict:
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
                INSERT INTO app_users (
                    id, uid, username, email, email_verified_at, password_hash, role
                )
                VALUES (%s, %s, %s, %s, now(), %s, %s)
                RETURNING id, uid, username, email, email_verified_at, role, created_at
                """,
                (str(uuid4()), next_uid, username, email, password_hash, role),
            ).fetchone()
            connection.commit()
        return dict(row)

    def find_for_authentication(self, username: str) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT id, uid, username, email, email_verified_at,
                       password_hash, role, created_at
                FROM app_users
                WHERE username = %s OR lower(email) = lower(%s)
                """,
                (username, username),
            ).fetchone()
        return dict(row) if row else None

    def find_by_uid(self, uid: str) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT id, uid, username, email, email_verified_at, role, created_at
                FROM app_users
                WHERE uid = %s
                """,
                (uid,),
            ).fetchone()
        return dict(row) if row else None


user_repository = UserRepository()


class VerificationCodeRepository:
    """Short-lived registration-code persistence boundary."""

    def latest(self, email: str) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT id, email, code_hash, expires_at, consumed_at,
                       attempt_count, created_at
                FROM email_verification_codes
                WHERE lower(email) = lower(%s)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (email,),
            ).fetchone()
        return dict(row) if row else None

    def create(self, email: str, code_hash: str, expires_at: datetime) -> dict:
        with get_connection() as connection:
            row = connection.execute(
                """
                INSERT INTO email_verification_codes (id, email, code_hash, expires_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id, email, expires_at, created_at
                """,
                (str(uuid4()), email, code_hash, expires_at),
            ).fetchone()
            connection.commit()
        return dict(row)

    def record_failed_attempt(self, code_id: UUID | str) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE email_verification_codes
                SET attempt_count = attempt_count + 1
                WHERE id = %s
                """,
                (str(code_id),),
            )
            connection.commit()

    def consume(self, code_id: UUID | str) -> bool:
        with get_connection() as connection:
            row = connection.execute(
                """
                UPDATE email_verification_codes
                SET consumed_at = now()
                WHERE id = %s AND consumed_at IS NULL AND expires_at > now()
                RETURNING id
                """,
                (str(code_id),),
            ).fetchone()
            connection.commit()
        return row is not None

    def revoke(self, code_id: UUID | str) -> None:
        with get_connection() as connection:
            connection.execute(
                "DELETE FROM email_verification_codes WHERE id = %s",
                (str(code_id),),
            )
            connection.commit()


verification_code_repository = VerificationCodeRepository()
