from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.auth import invites, service
from app.modules.auth.schemas import RegistrationRequest


def test_registration_schema_requires_matching_passwords_and_valid_email():
    valid = {
        "username": "researcher",
        "email": "Researcher@Example.com",
        "password": "Policy123",
        "password_confirmation": "Policy123",
    }
    payload = RegistrationRequest(**valid)
    assert payload.email == "researcher@example.com"

    with pytest.raises(ValidationError, match="Passwords do not match"):
        RegistrationRequest(**{**valid, "password_confirmation": "Different1"})
    with pytest.raises(ValidationError, match="valid email"):
        RegistrationRequest(**{**valid, "email": "not-an-email"})


def test_registration_does_not_require_an_email_verification_code():
    payload = RegistrationRequest(
        username="researcher",
        email="researcher@example.com",
        password="!",
        password_confirmation="!",
    )

    assert payload.email == "researcher@example.com"
    assert "verification_code" not in payload.model_dump()


def test_admin_registration_requires_and_consumes_an_invite(monkeypatch):
    captured = {}

    def create_admin(username, email, password_hash, invite_hash):
        captured.update(
            username=username,
            email=email,
            role="admin",
            invite_hash=invite_hash,
        )
        return {
            "id": uuid4(),
            "uid": "00001",
            "username": username,
            "email": email,
            "role": "admin",
            "created_at": datetime.now(UTC),
        }

    monkeypatch.setattr(service.user_repository, "create_admin_with_invite", create_admin)
    with pytest.raises(ValueError, match="invitation code"):
        service.create_user("admin-user", "admin@example.com", "Password1", "admin")

    user = service.create_user(
        "admin-user",
        "admin@example.com",
        "Password1",
        "admin",
        invite_code="a-secure-single-use-invitation",
    )
    assert captured["role"] == "admin"
    assert len(captured["invite_hash"]) == 64
    assert user["email"] == "admin@example.com"


def test_invitation_plaintext_is_returned_once_and_only_hash_is_persisted(monkeypatch):
    captured = {}

    def create(**values):
        captured.update(values)
        return {
            "id": uuid4(),
            "code_prefix": values["code_prefix"],
            "created_by_user_id": values["created_by_user_id"],
            "expires_at": values["expires_at"],
            "consumed_at": None,
            "revoked_at": None,
            "created_at": datetime.now(UTC),
        }

    monkeypatch.setattr(invites.admin_invite_repository, "create", create)
    monkeypatch.setattr(
        invites.secrets,
        "token_urlsafe",
        lambda length: "invite-code-with-high-entropy",
    )

    result = invites.create_invite(created_by_user_id="admin-id", expires_in_days=7)

    assert result["invite_code"] == "invite-code-with-high-entropy"
    assert captured["code_hash"] == invites.hash_invite_code(result["invite_code"])
    assert captured["code_hash"] != result["invite_code"]
    assert "code_hash" not in result


def test_bootstrap_invitation_is_disabled_after_first_admin(monkeypatch):
    monkeypatch.setattr(invites.user_repository, "admin_exists", lambda: True)

    with pytest.raises(ValueError, match="already exists"):
        invites.create_bootstrap_invite()


def test_generated_app_secret_is_persisted_and_reused(tmp_path, monkeypatch):
    settings = type(
        "Settings",
        (),
        {"app_secret": None, "app_secret_file": tmp_path / "app_secret"},
    )()
    monkeypatch.setattr(service, "get_settings", lambda: settings)

    first = service.application_secret_key()
    second = service.application_secret_key()

    assert first == second
    assert len(first) >= 32
    assert (tmp_path / "app_secret").read_bytes() == first
