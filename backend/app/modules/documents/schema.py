"""Check the required durable-task schema before accepting work."""

from contextlib import nullcontext

from app.core.database import get_connection

TASK_TABLES = ("document_tasks", "document_upload_requests")
MIGRATION_COMMAND = "python -m app.modules.documents.migrate"


class DocumentTaskSchemaError(RuntimeError):
    pass


def validate_document_task_schema(connection=None) -> None:
    context = nullcontext(connection) if connection is not None else get_connection()
    with context as conn:
        missing = [
            name
            for name in TASK_TABLES
            if conn.execute("SELECT to_regclass(%s) AS relation", (name,)).fetchone()["relation"]
            is None
        ]
    if missing:
        raise DocumentTaskSchemaError(
            f"Document task database schema is out of date: missing {', '.join(missing)}. "
            "Stop the API and document workers, then from backend/ run "
            f"`{MIGRATION_COMMAND}` using the same environment as the service. "
            "This applies database/migrations/028_durable_document_tasks.sql "
            "without resetting existing users or documents. Restart after it succeeds."
        )
