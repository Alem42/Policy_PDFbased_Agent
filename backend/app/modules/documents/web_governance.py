"""Application service for permanent web-document lifecycle governance."""

from __future__ import annotations

from datetime import datetime

from app.modules.documents.repositories.web_governance import (
    WebGovernanceRepository,
    web_governance_repository,
)

LIFECYCLE_STATUSES = {"active", "stale", "archived"}


class WebGovernanceService:
    def __init__(
        self,
        repository: WebGovernanceRepository = web_governance_repository,
    ) -> None:
        self.repository = repository

    def register_import(self, document_id: str, *, created_by: str | None) -> dict:
        return self.repository.register_import(document_id, created_by=created_by)

    def list(
        self,
        *,
        lifecycle_status: str | None = None,
        due_only: bool = False,
    ) -> list[dict]:
        if lifecycle_status and lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError("Unknown web document lifecycle status.")
        return self.repository.list_records(
            lifecycle_status=lifecycle_status,
            due_only=due_only,
        )

    def update(
        self,
        document_id: str,
        *,
        lifecycle_status: str | None = None,
        refresh_interval_days: int | None = None,
        next_review_at: datetime | None = None,
    ) -> dict:
        if lifecycle_status and lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError("Unknown web document lifecycle status.")
        if refresh_interval_days is not None and not 1 <= refresh_interval_days <= 3650:
            raise ValueError("refresh_interval_days must be between 1 and 3650.")
        return self.repository.update(
            document_id,
            lifecycle_status=lifecycle_status,
            refresh_interval_days=refresh_interval_days,
            next_review_at=next_review_at,
        )


web_governance_service = WebGovernanceService()
