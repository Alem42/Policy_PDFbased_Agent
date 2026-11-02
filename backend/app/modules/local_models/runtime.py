"""One serialized GPU worker; weights stay on disk, idle processes release CUDA."""

from __future__ import annotations

import multiprocessing
import sys
from functools import lru_cache
from importlib.util import find_spec
from threading import RLock, Timer

from app.core.config import get_settings, resolve_backend_path

EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
RERANKER_MODEL = "Qwen/Qwen3-Reranker-0.6B"
QUERY_INSTRUCTION = "Given a policy research question, retrieve passages that answer the question."


def _require_local_dependencies():
    missing = [name for name in ("torch", "transformers") if find_spec(name) is None]
    if missing:
        raise RuntimeError(
            f"Local Qwen dependencies missing: {', '.join(missing)}. "
            f"Backend Python: {sys.executable}. "
            "Start the backend from its directory with `python -m scripts.run_backend` "
            "to use the project .venv; for a new environment, install the backend "
            "[local-models] extra with that environment's Python."
        )


@lru_cache(maxsize=2)
def tokenizer(model: str):
    _require_local_dependencies()
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise RuntimeError("Install the backend local-models extra before selecting Qwen.") from exc
    cache = resolve_backend_path(get_settings().model_cache_dir) / "huggingface"
    return AutoTokenizer.from_pretrained(model, cache_dir=str(cache), padding_side="left")


def count_tokens(text: str, model: str = EMBEDDING_MODEL) -> int:
    return len(tokenizer(model).encode(text, add_special_tokens=False))


class LocalModelRuntime:
    """Process boundary prevents model references/CUDA contexts surviving unload."""

    def __init__(self, *, context=None, timeout: float = 900):
        self._context = context or multiprocessing.get_context("spawn")
        self._timeout = timeout
        self._lock = RLock()
        self._process = None
        self._connection = None
        self._timer = None
        self._generation = 0
        self._last_status: dict = {}

    def _start(self):
        _require_local_dependencies()
        from app.modules.local_models.worker import worker_main

        parent, child = self._context.Pipe()
        cache = str(resolve_backend_path(get_settings().model_cache_dir) / "huggingface")
        process = self._context.Process(target=worker_main, args=(child, cache), daemon=True)
        process.start()
        child.close()
        self._process, self._connection = process, parent

    def call(self, operation: str, *, idle_seconds: float = 120, **payload):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._generation += 1
            generation = self._generation
            if self._process is None or not self._process.is_alive():
                self._release()
                self._start()
            try:
                self._connection.send({"operation": operation, **payload})
                if not self._connection.poll(self._timeout):
                    raise TimeoutError("Local inference timed out; GPU worker was released.")
                result = self._connection.recv()
                if not result.get("ok"):
                    raise RuntimeError(result.get("error", "Local inference failed."))
                self._last_status = result.get("status", {})
                return result["result"]
            except (EOFError, BrokenPipeError, OSError, TimeoutError, RuntimeError):
                self._release()
                raise
            finally:
                if idle_seconds <= 0:
                    self._release()
                elif self._process:
                    self._timer = Timer(idle_seconds, self._expire, args=(generation,))
                    self._timer.daemon = True
                    self._timer.start()

    def _expire(self, generation):
        with self._lock:
            if generation == self._generation:
                self._release()

    def _release(self):
        if self._timer:
            self._timer.cancel()
            self._timer = None
        if self._connection:
            self._connection.close()
            self._connection = None
        if self._process:
            if self._process.is_alive():
                self._process.terminate()
            self._process.join(timeout=10)
            self._process = None

    def unload(self):
        with self._lock:
            self._generation += 1
            self._release()

    def status(self):
        acquired = self._lock.acquire(blocking=False)
        try:
            process = self._process
            running = bool(process and process.is_alive())
            return {
                **self._last_status,
                "loaded": running,
                "pid": process.pid if running else None,
                "busy": not acquired,
                "allocated_bytes": self._last_status.get("allocated_bytes", 0) if running else 0,
                "models": self._last_status.get("models", []) if running else [],
            }
        finally:
            if acquired:
                self._lock.release()


local_model_runtime = LocalModelRuntime()
