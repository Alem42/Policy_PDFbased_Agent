import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from langchain_core.runnables import RunnableLambda

from app.core.ai import chat_models
from app.modules.documents.ingestion import contextual_header as headers
from app.modules.documents.ingestion import metadata_extractor as metadata


def test_slow_optional_headers_do_not_hold_up_document_processing(monkeypatch):
    blocked = threading.Event()
    started = threading.Event()

    def model(prompt):
        if "slow excerpt" in prompt.to_string():
            started.set()
            blocked.wait(timeout=2)
            return "Late header that must be discarded."
        return "A useful header."

    monkeypatch.setattr(headers, "resolve_generation_target", lambda _: ("test", "test", {}))
    monkeypatch.setattr(headers, "create_chat_client", lambda *a, **kw: RunnableLambda(model))
    monkeypatch.setattr(headers, "_STAGE_TIMEOUT_SECONDS", 0.15)
    chunks = [{"text": "fast excerpt"}, {"text": "slow excerpt"}]
    before = time.monotonic()
    try:
        result = headers.build_contextual_headers(chunks, title="Test", summary="Policy")
        assert started.is_set()
        assert result == ["A useful header.", ""]
        assert time.monotonic() - before < 1
        assert chunks == [{"text": "fast excerpt"}, {"text": "slow excerpt"}]
    finally:
        blocked.set()


def test_metadata_deadline_reaches_existing_pipeline_fallback(monkeypatch):
    blocked = threading.Event()

    def slow_model(_prompt):
        blocked.wait(timeout=2)
        return "{}"

    monkeypatch.setattr(metadata, "get_taxonomy_tree", lambda: [])
    monkeypatch.setattr(metadata, "resolve_generation_target", lambda _: ("test", "test", {}))
    monkeypatch.setattr(metadata, "create_chat_client", lambda *a, **kw: RunnableLambda(slow_model))
    monkeypatch.setattr(metadata, "_LLM_STAGE_TIMEOUT_SECONDS", 0.1)
    before = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="metadata generation exceeded"):
            metadata.generate_document_metadata(
                filename="test.pdf", pages=[{"page": 1, "text": "Policy test content."}]
            )
        assert time.monotonic() - before < 1
    finally:
        blocked.set()


def test_real_sdk_times_out_without_retrying_optional_header(monkeypatch):
    received = []
    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            release.wait(timeout=2)
            self.close_connection = True

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(headers, "resolve_generation_target", lambda _: ("test", "test", {}))
    monkeypatch.setattr(chat_models, "get_provider_api_key", lambda _: "local-test-key")
    monkeypatch.setattr(
        chat_models,
        "get_provider_config",
        lambda _: {"base_url": f"http://127.0.0.1:{server.server_port}/v1", "extra_body": {}},
    )
    # 100ms can expire before the local server accepts the first connection on
    # Windows under load. Keep a real timeout, with room for socket scheduling.
    request_timeout = 0.5
    monkeypatch.setattr(headers, "_REQUEST_TIMEOUT_SECONDS", request_timeout)
    monkeypatch.setattr(headers, "_STAGE_TIMEOUT_SECONDS", 1.5)
    # Client construction can load the system certificate store. Measure the
    # network deadline after that one-time setup, using the real SDK client.
    client = chat_models.create_chat_client(
        "test", "test", max_tokens=128, timeout=request_timeout, max_retries=0
    )
    options = {}

    def prepared_client(*_args, **kwargs):
        options.update(kwargs)
        return client

    monkeypatch.setattr(headers, "create_chat_client", prepared_client)
    before = time.monotonic()
    try:
        result = headers.build_contextual_headers(
            [{"text": "Grant applications close in June."}], title="Grant policy", summary=None
        )
        assert result == [""]
        assert time.monotonic() - before < 2
        assert len(received) == 1
        assert options == {"max_tokens": 128, "timeout": request_timeout, "max_retries": 0}
        assert received[0].get("max_completion_tokens", received[0].get("max_tokens")) == 128
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
