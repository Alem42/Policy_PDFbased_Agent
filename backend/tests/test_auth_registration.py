from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.auth import service, verification
from app.modules.auth.schemas import RegistrationRequest


class FakeVerificationRepository:
    def __init__(self) -> None:
        self.row = None
        self.failed_attempts = 0
        self.consumed = False

    def latest(self, email):
        return self.row

    def create(self, email, code_hash, expires_at):
        self.row = {
            "id": uuid4(),
            "email": email,
            "code_hash": code_hash,
            "expires_at": expires_at,
            "consumed_at": None,
            "attempt_count": 0,
            "created_at": datetime.now(UTC),
        }
        return self.row

    def record_failed_attempt(self, code_id):
        self.failed_attempts += 1
        self.row["attempt_count"] += 1

    def consume(self, code_id):
        self.consumed = True
        self.row["consumed_at"] = datetime.now(UTC)
        return True

    def revoke(self, code_id):
        self.row = None


def _settings(**overrides):
    values = {
        "app_secret": "test-secret",
        "email_verification_mode": "development",
        "email_verification_code_ttl_seconds": 600,
        "email_verification_resend_seconds": 60,
        "email_verification_max_attempts": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_registration_schema_requires_matching_passwords_and_valid_email():
    valid = {
        "username": "researcher",
        "email": "Researcher@Example.com",
        "password": "Policy123",
        "password_confirmation": "Policy123",
        "verification_code": "123456",
    }
    payload = RegistrationRequest(**valid)
    assert payload.email == "researcher@example.com"

    with pytest.raises(ValidationError, match="Passwords do not match"):
        RegistrationRequest(**{**valid, "password_confirmation": "Different1"})
    with pytest.raises(ValidationError, match="valid email"):
        RegistrationRequest(**{**valid, "email": "not-an-email"})


def test_development_code_is_issued_and_can_only_be_consumed_once(monkeypatch):
    repository = FakeVerificationRepository()
    monkeypatch.setattr(verification, "verification_code_repository", repository)
    monkeypatch.setattr(verification, "get_settings", lambda: _settings())
    monkeypatch.setattr(verification.secrets, "randbelow", lambda limit: 123456)

    result = verification.issue_verification_code("User@Example.com")
    assert result["development_code"] == "123456"

    verification.consume_verification_code("user@example.com", "123456")
    assert repository.consumed is True
    with pytest.raises(ValueError, match="Request a new"):
        verification.consume_verification_code("user@example.com", "123456")


def test_incorrect_code_records_attempt_without_consuming(monkeypatch):
    repository = FakeVerificationRepository()
    monkeypatch.setattr(verification, "verification_code_repository", repository)
    monkeypatch.setattr(verification, "get_settings", lambda: _settings())
    monkeypatch.setattr(verification.secrets, "randbelow", lambda limit: 123456)
    verification.issue_verification_code("user@example.com")

    with pytest.raises(ValueError, match="incorrect"):
        verification.consume_verification_code("user@example.com", "000000")
    assert repository.failed_attempts == 1
    assert repository.consumed is False


def test_expired_code_is_rejected(monkeypatch):
    repository = FakeVerificationRepository()
    repository.row = {
        "id": uuid4(),
        "email": "user@example.com",
        "code_hash": "unused",
        "expires_at": datetime.now(UTC) - timedelta(seconds=1),
        "consumed_at": None,
        "attempt_count": 0,
        "created_at": datetime.now(UTC) - timedelta(minutes=11),
    }
    monkeypatch.setattr(verification, "verification_code_repository", repository)
    monkeypatch.setattr(verification, "get_settings", lambda: _settings())

    with pytest.raises(ValueError, match="expired"):
        verification.consume_verification_code("user@example.com", "123456")


def test_delivery_failure_revokes_unusable_code(monkeypatch):
    repository = FakeVerificationRepository()
    monkeypatch.setattr(verification, "verification_code_repository", repository)
    monkeypatch.setattr(
        verification, "get_settings", lambda: _settings(email_verification_mode="smtp")
    )
    monkeypatch.setattr(
        verification,
        "_send_smtp_code",
        lambda email, code: (_ for _ in ()).throw(OSError("mail server unavailable")),
    )

    with pytest.raises(verification.EmailDeliveryError):
        verification.issue_verification_code("user@example.com")
    assert repository.row is None


def test_admin_secret_remains_a_non_enforced_placeholder(monkeypatch):
    captured = {}

    def create(username, email, password_hash, role):
        captured.update(username=username, email=email, role=role)
        return {
            "id": uuid4(),
            "uid": "00001",
            "username": username,
            "email": email,
            "email_verified_at": datetime.now(UTC),
            "role": role,
            "created_at": datetime.now(UTC),
        }

    monkeypatch.setattr(service.user_repository, "create", create)
    user = service.create_user(
        "admin-user", "admin@example.com", "Password1", "admin", secret="anything"
    )
    assert captured["role"] == "admin"
    assert user["email_verified"] is True
