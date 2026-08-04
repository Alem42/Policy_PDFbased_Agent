from __future__ import annotations

import asyncio

from app.modules.chat.application.models import StartedTurn, StartTurnRequest
from app.modules.chat.history_repository import ChatHistoryRepository, chat_history_repository
from app.modules.chat.schemas import MAX_HISTORY_TURNS


class SessionNotFoundError(LookupError):
    """The requested session does not exist for the current user."""


class ChatTurnService:
    """Own the database lifecycle for starting and failing a chat turn.

    Prior history is always read before inserting the new question, so callers
    can safely append that question once when constructing model input.
    """

    def __init__(self, repository: ChatHistoryRepository = chat_history_repository) -> None:
        self.repository = repository

    async def start(self, request: StartTurnRequest) -> StartedTurn:
        if request.session_id:
            session_id = request.session_id
            owns = await asyncio.to_thread(
                self.repository.session_belongs_to_user,
                session_id,
                request.user_id,
            )
            if not owns:
                raise SessionNotFoundError("Session not found.")
            history = await asyncio.to_thread(
                self.repository.get_history_for_llm,
                session_id,
                MAX_HISTORY_TURNS,
            )
            if request.identifiers:
                await asyncio.to_thread(
                    self.repository.update_session_document_ids,
                    session_id,
                    list(request.identifiers),
                )
        else:
            session_id = await asyncio.to_thread(
                self.repository.create_session,
                request.user_id,
                request.question[:80],
                list(request.identifiers),
                request.response_mode,
            )
            history = []

        await asyncio.to_thread(
            self.repository.add_message,
            session_id,
            "user",
            request.question,
        )
        assistant_message_id = None
        if request.create_pending_assistant:
            assistant_message_id = await asyncio.to_thread(
                self.repository.create_pending_message,
                session_id,
                "assistant",
                request.agent_mode,
            )
        return StartedTurn(
            session_id=session_id,
            user_id=request.user_id,
            history=history,
            assistant_message_id=assistant_message_id,
        )

    async def fail(self, message_id: str, partial_answer: str = "") -> None:
        await asyncio.to_thread(
            self.repository.finalize_message,
            message_id,
            partial_answer,
            status="error",
        )

    async def add_message(self, *args, **kwargs):
        """Persist a completed user/assistant message using repository compatibility arguments."""

        return await asyncio.to_thread(self.repository.add_message, *args, **kwargs)

    async def finalize_message(self, *args, **kwargs) -> None:
        await asyncio.to_thread(self.repository.finalize_message, *args, **kwargs)

    async def touch(self, session_id: str) -> None:
        await asyncio.to_thread(self.repository.touch_session, session_id)

    async def history(self, session_id: str) -> list[dict]:
        return await asyncio.to_thread(
            self.repository.get_history_for_llm,
            session_id,
            MAX_HISTORY_TURNS,
        )

    async def message_steps(self, message_id: str) -> list[dict]:
        return await asyncio.to_thread(self.repository.get_message_steps, message_id)

    async def update_steps(self, message_id: str, steps: list[dict]) -> None:
        await asyncio.to_thread(self.repository.update_reasoning_steps, message_id, steps)

    async def update_suggestions(self, message_id: str, suggestions: list[str]) -> None:
        await asyncio.to_thread(
            self.repository.update_message_suggestions,
            message_id,
            suggestions,
        )

    async def require_session(self, session_id: str, user_id: str) -> None:
        owns = await asyncio.to_thread(
            self.repository.session_belongs_to_user,
            session_id,
            user_id,
        )
        if not owns:
            raise SessionNotFoundError("Session not found.")


chat_turn_service = ChatTurnService()
