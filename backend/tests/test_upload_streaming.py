import asyncio
import hashlib
import io
from datetime import UTC, datetime
from threading import Event
from typing import Annotated

import pytest
from fastapi import FastAPI, File, UploadFile
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.upload_limits import UploadBodyLimitMiddleware
from app.modules.documents.exceptions import DuplicateDocumentError, UploadTooLargeError
from app.modules.documents.file_store import document_file_store
from app.modules.documents.service import pipeline


@pytest.fixture
def upload_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(document_file_store, "_document_dir", lambda: tmp_path)
    monkeypatch.setattr(
        document_file_store, "relative_path", lambda path: f"{path.parent.name}/{path.name}"
    )
    return tmp_path


class BoundedReader(io.BytesIO):
    def __init__(self, value, chunk_size):
        super().__init__(value)
        self.chunk_size = chunk_size
        self.reads = []

    def read(self, size=-1):
        assert 0 < size <= self.chunk_size
        self.reads.append(size)
        return super().read(size)


def test_staging_handles_split_utf8_and_hashes_without_unbounded_reads(upload_storage):
    data = ("政策研究🚀" * 500).encode()
    reader = BoundedReader(data, 7)
    staged = document_file_store.stage_upload(
        "policy.txt", reader, max_bytes=len(data), chunk_bytes=7
    )
    assert staged.file_size == len(data)
    assert staged.checksum == hashlib.sha256(data).hexdigest()
    assert staged.path.read_bytes() == data
    assert len(reader.reads) > 1


@pytest.mark.parametrize(
    ("name", "content", "max_bytes", "exception"),
    [
        ("large.txt", b"x" * 101, 100, UploadTooLargeError),
        ("bad.txt", b"valid\xff", 100, ValueError),
        ("nul.md", b"# heading\x00", 100, ValueError),
        ("truncated.txt", b"hello\xe4\xb8", 100, ValueError),
        ("bad.pdf", b"not a pdf", 100, ValueError),
        ("bad.docx", b"not a zip", 100, ValueError),
    ],
)
def test_rejected_staging_files_are_cleaned(upload_storage, name, content, max_bytes, exception):
    with pytest.raises(exception):
        document_file_store.stage_upload(
            name, io.BytesIO(content), max_bytes=max_bytes, chunk_bytes=3
        )
    assert not list(upload_storage.rglob("*.part"))


def test_read_error_cleans_staged_file(upload_storage):
    class FailingSource(io.BytesIO):
        def read(self, size=-1):
            raise OSError("interrupted disk read")

    with pytest.raises(OSError):
        document_file_store.stage_upload(
            "notes.txt", FailingSource(b"text"), max_bytes=100, chunk_bytes=8
        )
    assert not list(upload_storage.rglob("*.part"))


@pytest.mark.parametrize("failure", ["duplicate", "database"])
async def test_failed_registration_never_leaves_new_files(upload_storage, monkeypatch, failure):
    class Repository:
        def find_by_checksum(self, _checksum):
            if failure == "duplicate":
                return {"id": "existing", "original_filename": "existing.txt"}
            return None

        def create(self, **_kwargs):
            raise RuntimeError("database write failed")

    monkeypatch.setattr(pipeline, "document_repository", Repository())
    with pytest.raises(DuplicateDocumentError if failure == "duplicate" else RuntimeError):
        await pipeline.save_upload(UploadFile(filename="notes.txt", file=io.BytesIO(b"content")))
    assert not [path for path in upload_storage.rglob("*") if path.is_file()]


async def test_sync_registration_does_not_block_event_loop(upload_storage, monkeypatch):
    entered = asyncio.Event()
    released = Event()
    captured = {}
    loop = asyncio.get_running_loop()

    class Repository:
        def find_by_checksum(self, _checksum):
            loop.call_soon_threadsafe(entered.set)
            assert released.wait(timeout=2), "Event loop could not run while SQL was waiting"
            return None

        def create(self, **kwargs):
            captured.update(kwargs)

        def get_record(self, document_id):
            return {
                **captured,
                "id": document_id,
                "uploaded_at": datetime.now(UTC),
                "status": "uploaded",
            }

    monkeypatch.setattr(pipeline, "document_repository", Repository())
    task = asyncio.create_task(
        pipeline.save_upload(UploadFile(filename="notes.txt", file=io.BytesIO(b"content")))
    )
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        released.set()
        saved = await task
    finally:
        released.set()
    assert saved["file_size"] == 7
    assert "content" not in captured


async def test_known_oversize_is_rejected_before_copy(upload_storage, monkeypatch):
    monkeypatch.setattr(
        pipeline, "get_settings", lambda: Settings(_env_file=None, upload_max_bytes=10)
    )
    with pytest.raises(UploadTooLargeError):
        await pipeline.save_upload(
            UploadFile(filename="notes.txt", file=io.BytesIO(b"x" * 11), size=11)
        )
    assert not list(upload_storage.iterdir())


def make_upload_app(max_bytes=128, overhead=128):
    app = FastAPI()
    app.add_middleware(
        UploadBodyLimitMiddleware,
        upload_path="/upload",
        max_file_bytes=max_bytes,
        overhead_bytes=overhead,
    )

    @app.post("/upload")
    async def upload(file: Annotated[UploadFile, File()]):
        return {"bytes": len(await file.read())}

    return app


def test_content_length_rejected_before_parsing():
    with TestClient(make_upload_app()) as client:
        response = client.post("/upload", content=b"x" * 257)
    assert response.status_code == 413
    assert "Maximum file size" in response.json()["detail"]


def test_public_upload_limits_are_reachable_before_uuid_route():
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/v1/documents/upload-limits")
    assert response.status_code == 200
    assert response.json()["max_file_bytes"] == 20 * 1024 * 1024


async def test_chunked_oversize_closes_multipart_temporary_file(monkeypatch):
    from starlette import formparsers

    original = formparsers.SpooledTemporaryFile
    opened = []

    def tracked_file(*args, **kwargs):
        handle = original(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked_file)
    first = (
        b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="x.txt"'
        b"\r\nContent-Type: text/plain\r\n\r\nsmall"
    )
    messages = iter(
        [
            {"type": "http.request", "body": first, "more_body": True},
            {"type": "http.request", "body": b"x" * 200, "more_body": True},
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"multipart/form-data; boundary=boundary")],
        "client": ("127.0.0.1", 1),
        "server": ("localhost", 80),
    }
    await make_upload_app()(scope, receive, send)
    assert sent[0]["status"] == 413
    assert opened and all(handle.closed for handle in opened)


@pytest.mark.integration
async def test_concurrent_real_uploads_preserve_unique_document(
    postgres_repository,
    upload_storage,
    monkeypatch,
):
    from app.modules.documents.repositories.documents import document_repository

    content = b"Unique step1 concurrent upload " + str(upload_storage).encode()
    uploads = [
        UploadFile(filename=f"policy-{index}.txt", file=io.BytesIO(content)) for index in range(2)
    ]
    results = await asyncio.gather(
        *(pipeline.save_upload(upload) for upload in uploads), return_exceptions=True
    )
    successes = [value for value in results if isinstance(value, dict)]
    duplicates = [value for value in results if isinstance(value, DuplicateDocumentError)]
    try:
        assert len(successes) == len(duplicates) == 1, results
        assert duplicates[0].existing_id == successes[0]["id"]
        assert successes[0]["file_size"] == len(content)
        assert not list(upload_storage.rglob("*.part"))
        assert len([path for path in upload_storage.rglob("*") if path.is_file()]) == 1
    finally:
        for row in successes:
            document_repository.delete(row["id"])
