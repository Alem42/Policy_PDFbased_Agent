"""Write one ledger row per paid request; recording never breaks the request itself."""

import logging
from urllib.parse import urlsplit

from langchain_core.callbacks import BaseCallbackHandler

from app.core.database import get_connection
from app.modules.usage import budget
from app.modules.usage.context import current

logger = logging.getLogger(__name__)

_HOSTS = {"open.bigmodel.cn": "zhipu", "api.deepseek.com": "deepseek"}


def provider_for_url(url: str, fallback: str = "custom") -> str:
    host = (urlsplit(url).hostname or "").lower()
    for suffix, name in _HOSTS.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return host or fallback


def record(
    provider: str,
    model: str,
    kind: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    requests: int = 1,
) -> None:
    scope = current()
    try:
        cost = budget.cost_of(provider, model, input_tokens, output_tokens, requests)
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO api_usage_events (
                    provider, model, kind, area, operation, user_id, session_id, document_id,
                    input_tokens, output_tokens, requests, cost_cny
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    COALESCE(%s::uuid, (SELECT id FROM app_users WHERE uid = %s)),
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    provider,
                    model,
                    kind,
                    scope.area,
                    scope.operation,
                    scope.user_id,
                    scope.user_uid,
                    scope.session_id,
                    scope.document_id,
                    max(int(input_tokens or 0), 0),
                    max(int(output_tokens or 0), 0),
                    requests,
                    cost,
                ),
            )
        budget.add_to_spend_cache(cost)
    except Exception:  # noqa: BLE001 - e.g. migration 032 not applied yet
        logger.warning("API usage was not recorded: %s/%s %s", provider, model, kind, exc_info=True)


def _usage_from(response) -> tuple[int, int]:
    """Token counts from a LangChain LLMResult (both streamed and non-streamed)."""
    for generations in response.generations or []:
        for generation in generations:
            usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
            if usage:
                return usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    token_usage = (response.llm_output or {}).get("token_usage") or {}
    return token_usage.get("prompt_tokens", 0), token_usage.get("completion_tokens", 0)


class UsageCallback(BaseCallbackHandler):
    """Attached to every chat client: budget check before, ledger row after."""

    raise_error = True  # let ApiBudgetExceeded abort the call instead of being logged

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model

    def on_chat_model_start(self, serialized, messages, **kwargs) -> None:
        budget.ensure_within_budget()

    def on_llm_end(self, response, **kwargs) -> None:
        input_tokens, output_tokens = _usage_from(response)
        record(self.provider, self.model, "chat", input_tokens, output_tokens)
