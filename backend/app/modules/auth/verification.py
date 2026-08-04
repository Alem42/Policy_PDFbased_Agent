"""Email verification with an explicit development and SMTP delivery boundary."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from app.core.config import get_settings
from app.modules.auth.repository import verification_code_repository


class EmailDeliveryError(RuntimeError):
    """A code was created but could not be delivered."""


def _normalise_email(email: str) -> str:
    return email.strip().lower()


def _code_hash(email: str, code: str) -> str:
    message = f"{_normalise_email(email)}:{code}".encode()
    return hmac.new(get_settings().app_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _send_smtp_code(email: str, code: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL must be configured.")

    message = EmailMessage()
    message["Subject"] = "Your Policy in Action verification code"
    message["From"] = settings.smtp_from_email
    message["To"] = email
    message.set_content(
        f"Your registration verification code is {code}. "
        f"It expires in {settings.email_verification_code_ttl_seconds // 60} minutes."
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        if settings.smtp_use_tls:
            client.starttls()
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)


def issue_verification_code(email: str) -> dict:
    """Create and deliver one six-digit registration code."""
    settings = get_settings()
    clean_email = _normalise_email(email)
    now = datetime.now(UTC)
    latest = verification_code_repository.latest(clean_email)
    if latest and latest["consumed_at"] is None:
        retry_at = latest["created_at"] + timedelta(
            seconds=settings.email_verification_resend_seconds
        )
        if retry_at > now:
            seconds = max(1, int((retry_at - now).total_seconds()))
            raise ValueError(f"Please wait {seconds} seconds before requesting another code.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = now + timedelta(seconds=settings.email_verification_code_ttl_seconds)
    row = verification_code_repository.create(
        clean_email, _code_hash(clean_email, code), expires_at
    )

    mode = settings.email_verification_mode.strip().lower()
    try:
        if mode == "smtp":
            _send_smtp_code(clean_email, code)
            development_code = None
        elif mode == "development":
            development_code = code
        else:
            raise RuntimeError("EMAIL_VERIFICATION_MODE must be 'development' or 'smtp'.")
    except Exception as exc:
        verification_code_repository.revoke(row["id"])
        raise EmailDeliveryError("Verification email could not be delivered.") from exc

    return {
        "message": "Verification code sent.",
        "expires_in": settings.email_verification_code_ttl_seconds,
        "retry_after": settings.email_verification_resend_seconds,
        "development_code": development_code,
    }


def consume_verification_code(email: str, code: str) -> None:
    """Validate and atomically consume the latest code for an email address."""
    settings = get_settings()
    clean_email = _normalise_email(email)
    row = verification_code_repository.latest(clean_email)
    now = datetime.now(UTC)
    if not row or row["consumed_at"] is not None:
        raise ValueError("Request a new verification code.")
    if row["expires_at"] <= now:
        raise ValueError("The verification code has expired. Request a new one.")
    if row["attempt_count"] >= settings.email_verification_max_attempts:
        raise ValueError("Too many incorrect attempts. Request a new verification code.")
    if not hmac.compare_digest(row["code_hash"], _code_hash(clean_email, code)):
        verification_code_repository.record_failed_attempt(row["id"])
        raise ValueError("The verification code is incorrect.")
    if not verification_code_repository.consume(row["id"]):
        raise ValueError("The verification code is no longer valid.")
