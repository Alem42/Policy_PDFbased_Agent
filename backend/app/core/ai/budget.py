"""Opt-in evaluation budgets shared across asyncio tasks and worker threads.

Reservations use UTF-8 byte length plus framing and the output cap. This is
deliberately conservative, not the provider's tokenizer or billing statement.
No reservation is refunded; retries must reserve again before sending.
"""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock


class BudgetExceeded(RuntimeError):
    pass


class LLMBudget:
    def __init__(self, *, token_limit=100_000, call_limit=40, input_limit=20_000):
        self.token_limit = token_limit
        self.call_limit = call_limit
        self.input_limit = input_limit
        self.reserved = 0
        self.calls = 0
        self.exhausted = False
        self.actual = {}
        self._lock = Lock()

    def reserve(self, messages, max_output):
        prompt = json.dumps(
            [getattr(m, "content", m) for m in messages], ensure_ascii=False, default=str
        )
        estimate = len(prompt.encode("utf8")) + 256 + 16 * len(messages)
        cost = estimate + max_output
        with self._lock:
            if (
                self.exhausted
                or estimate > self.input_limit
                or self.calls >= self.call_limit
                or self.reserved + cost > self.token_limit
            ):
                self.exhausted = True
                raise BudgetExceeded("Evaluation API budget reached; no further request was sent.")
            self.reserved += cost
            self.calls += 1

    def record(self, model, usage):
        with self._lock:
            row = self.actual.setdefault(
                model, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            )
            for key in row:
                row[key] += (usage or {}).get(key, 0)

    def snapshot(self):
        with self._lock:
            return {
                "estimated_token_limit": self.token_limit,
                "api_call_limit": self.call_limit,
                "reserved_tokens": self.reserved,
                "api_calls": self.calls,
                "budget_exhausted": self.exhausted,
                "reported_usage": {k: dict(v) for k, v in self.actual.items()},
            }


_active = ContextVar("evaluation_llm_budget", default=None)


def active():
    return _active.get()


def reserve(messages, max_output):
    if value := active():
        value.reserve(messages, max_output)


def record(model, usage):
    if value := active():
        value.record(model, usage)


@contextmanager
def scope(config):
    value = LLMBudget(
        token_limit=config.get("token_budget", 100_000),
        call_limit=config.get("max_api_calls", 40),
        input_limit=config.get("max_input_tokens", 20_000),
    )
    token = _active.set(value)
    try:
        yield value
    finally:
        _active.reset(token)
