from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_ROOT.parent


def test_token_usage_is_present_in_fresh_database_schema() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    assert '"token_usage"' in init_sql


def test_every_migration_file_is_mounted_by_compose() -> None:
    """Every migration under database/migrations/ must be mounted in
    compose.yaml, or a fresh volume silently skips it. Checks the whole
    directory (not a hardcoded filename) so this stays correct as new
    migrations are added."""
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    migrations_dir = BACKEND_ROOT / "database" / "migrations"
    migration_files = sorted(p.name for p in migrations_dir.glob("*.sql"))
    assert migration_files, "Expected at least one migration file."
    missing = [name for name in migration_files if name not in compose]
    assert not missing, f"Migrations not mounted in compose.yaml: {missing}"


def test_agent_run_observability_schema_is_available_to_fresh_databases() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    migration_sql = (
        BACKEND_ROOT / "database" / "migrations" / "028_add_agent_run_events.sql"
    ).read_text(encoding="utf-8")

    for table in ("agent_runs", "agent_run_events"):
        assert table in init_sql
        assert table in migration_sql


def test_email_verification_schema_is_removed() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert '"email_verification_codes"' not in init_sql
    assert '"email_verified_at"' not in init_sql
    assert "026_remove_email_verification.sql" in compose


def test_admin_invitation_schema_and_migration_are_available() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert '"admin_invites"' in init_sql
    assert '"code_hash"' in init_sql
    assert "025_add_admin_invites.sql" in compose


def test_email_is_not_a_unique_account_identifier() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    migration = (
        BACKEND_ROOT / "database" / "migrations" / "027_allow_shared_admin_emails.sql"
    ).read_text(encoding="utf-8")
    assert "app_users_email_lower_key" not in init_sql
    assert "DROP INDEX" in migration
    assert "027_allow_shared_admin_emails.sql" in compose


def test_legacy_crawling_schema_is_removed() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    legacy_tables = (
        "crawl_sources",
        "crawl_jobs",
        "crawl_errors",
        "crawled_documents",
        "crawled_document_versions",
        "crawled_document_assets",
    )
    assert all(f'"{table}"' not in init_sql for table in legacy_tables)
    assert "022_remove_legacy_crawling.sql" in compose
