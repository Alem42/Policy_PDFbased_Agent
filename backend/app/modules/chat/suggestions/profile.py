"""User suggestion-click log + soft personalization.

Records which suggested questions a user actually clicks, so future suggestions
can lean toward the topics they engage with.

Currently minimal: log clicks + surface the user's recent clicked questions as a
one-line hint injected into the candidate prompt (only when personalize is on).

TODO(profile): build a real profile — embed each clicked question, maintain a
running topic centroid per user, and re-rank/seed candidates by cosine similarity
to that centroid. Store centroids alongside the active embedding model id so a
model switch invalidates them (same rule as policy_matcher / chunk embeddings).
"""

from __future__ import annotations

import logging
from uuid import uuid4

from app.core.database import get_connection

logger = logging.getLogger(__name__)


def log_click(user_id: str, session_id: str | None, question: str) -> None:
    """Record that a user clicked a suggested question. Best-effort (never raises)."""
    text = (question or "").strip()
    if not text:
        return
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO suggestion_clicks (id, user_id, session_id, question)
                VALUES (%s, %s, %s, %s)
                """,
                (str(uuid4()), user_id, session_id, text[:500]),
            )
            conn.commit()
    except Exception as exc:
        # A missing table (pre-migration) or any write error must not break the UX.
        logger.warning("suggestion click not logged: %s", exc)


def recent_click_questions(user_id: str, limit: int = 10) -> list[str]:
    """The user's most recently clicked suggestions (newest first)."""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT question FROM suggestion_clicks
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            ).fetchall()
        return [r["question"] for r in rows]
    except Exception:
        return []


def personalization_hint(user_id: str | None) -> str:
    """One-line hint for the candidate prompt, or '' when there's nothing to add."""
    if not user_id:
        return ""
    questions = recent_click_questions(user_id, limit=8)
    if not questions:
        return ""
    joined = "; ".join(q[:80] for q in questions[:5])
    return (
        "The user has previously shown interest in questions like: "
        f"{joined}. Gently prefer follow-ups in similar directions when the "
        "documents support them, but never at the expense of answerability."
    )
