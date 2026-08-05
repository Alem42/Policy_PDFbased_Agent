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


def test_email_verification_schema_and_migration_are_available() -> None:
    init_sql = (BACKEND_ROOT / "database" / "init.sql").read_text(encoding="utf-8")
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert '"email_verification_codes"' in init_sql
    assert '"email_verified_at"' in init_sql
    assert "021_add_email_verification.sql" in compose


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
