from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent


def test_token_usage_is_present_in_fresh_database_schema() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    assert '"token_usage"' in init_sql


def test_latest_migration_is_mounted_by_compose() -> None:
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "018_add_token_usage_to_chat_messages.sql" in compose


def test_email_verification_schema_and_migration_are_available() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert '"email_verification_codes"' in init_sql
    assert '"email_verified_at"' in init_sql
    assert "021_add_email_verification.sql" in compose
