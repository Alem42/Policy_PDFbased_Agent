from __future__ import annotations

import hashlib
import json
import re
import shutil
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from pypdf import PdfReader

from app.core.config import BACKEND_ROOT, get_settings, resolve_backend_path
from app.core.database import get_connection, init_db
from app.ingestion.metadata_extractor import generate_document_metadata
from app.rag.embeddings import (
    EMBEDDING_MODEL_NAME,
    embed_text,
    estimate_token_count,
    vector_literal,
)

MAX_CHUNK_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 120


def _pdf_dir() -> Path:
    path = resolve_backend_path(get_settings().document_storage_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _legacy_pdf_dir() -> Path:
    return resolve_backend_path(get_settings().legacy_document_storage_dir)


def safe_filename(filename: str) -> str:
    cleaned = Path(filename).name.strip()
    if not cleaned or not cleaned.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")
    return cleaned


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _relative_path(path: Path) -> str:
    return str(path.resolve().relative_to(BACKEND_ROOT.resolve()))


def _pdf_roots() -> list[Path]:
    pdf_dir = _pdf_dir()
    legacy_pdf_dir = _legacy_pdf_dir()
    roots = [pdf_dir]
    if legacy_pdf_dir.exists() and legacy_pdf_dir.resolve() != pdf_dir.resolve():
        roots.append(legacy_pdf_dir)
    return roots


def discover_pdf_paths() -> list[Path]:
    paths: list[Path] = []
    for root in _pdf_roots():
        if root.exists():
            paths.extend(root.rglob("*.pdf"))
    return sorted(set(paths), key=lambda item: str(item).lower())


def _start_job(document_id: str, job_type: str) -> str:
    job_id = str(uuid4())
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO processing_jobs (id, document_id, job_type, status)
            VALUES (%s, %s, %s, 'running')
            """,
            (job_id, document_id, job_type),
        )
        connection.commit()
    return job_id


def _finish_job(
    job_id: str,
    status: str = "completed",
    error_message: str | None = None,
    details: dict | None = None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE processing_jobs
            SET status = %s,
                finished_at = now(),
                error_message = %s,
                details_json = %s::jsonb
            WHERE id = %s
            """,
            (status, error_message, json.dumps(details or {}), job_id),
        )
        connection.commit()


def _set_document_status(
    document_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    processed_sql = ", processed_at = now()" if status == "ready" else ""
    with get_connection() as connection:
        connection.execute(
            f"""
            UPDATE documents
            SET status = %s,
                error_message = %s
                {processed_sql}
            WHERE id = %s
            """,
            (status, error_message, document_id),
        )
        connection.commit()


def _create_document_record(
    path: Path,
    original_filename: str,
    content: bytes,
) -> str:
    document_id = str(uuid4())
    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO documents (
                id,
                original_filename,
                stored_filename,
                file_path,
                file_size,
                sha256,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'uploaded')
            ON CONFLICT (file_path) DO UPDATE
            SET original_filename = EXCLUDED.original_filename,
                stored_filename = EXCLUDED.stored_filename,
                file_size = EXCLUDED.file_size,
                sha256 = EXCLUDED.sha256
            RETURNING id
            """,
            (
                document_id,
                original_filename,
                path.name,
                _relative_path(path),
                len(content),
                _sha256(content),
            ),
        ).fetchone()
        connection.commit()
    return str(row["id"])


def _read_pdf_pages_from_path(path: Path) -> list[dict]:
    reader = PdfReader(BytesIO(path.read_bytes()))
    pages = [
        {
            "file": path.name,
            "page": page_number,
            "text": (page.extract_text() or "").strip(),
        }
        for page_number, page in enumerate(reader.pages, start=1)
    ]
    return _clean_extracted_pages(pages)


def _normalise_noise_line(line: str) -> str:
    clean = re.sub(r"\s+", " ", line).strip().lower()
    clean = re.sub(r"\d+", "#", clean)
    return clean


def _repeated_margin_lines(pages: list[dict]) -> set[str]:
    counts: dict[str, int] = {}
    for page in pages:
        lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
        margin_lines = lines[:3] + lines[-3:]
        for line in margin_lines:
            normalised = _normalise_noise_line(line)
            if 4 <= len(normalised) <= 120:
                counts[normalised] = counts.get(normalised, 0) + 1
    threshold = max(3, len(pages) // 4)
    return {line for line, count in counts.items() if count >= threshold}


def _looks_like_table_of_contents(text: str) -> bool:
    lower = text.lower()
    dot_leaders = len(re.findall(r"\.{3,}\s*\d+", text))
    numbered_entries = len(re.findall(r"^\s*\d+(\.\d+)*\s+.+\s+\d+\s*$", text, re.MULTILINE))
    return ("table of contents" in lower or "contents" in lower) and (
        dot_leaders >= 4 or numbered_entries >= 6
    )


def _clean_extracted_pages(pages: list[dict]) -> list[dict]:
    repeated_lines = _repeated_margin_lines(pages)
    cleaned_pages: list[dict] = []
    in_references = False

    for index, page in enumerate(pages):
        text = page["text"]
        if in_references:
            cleaned_pages.append({**page, "text": ""})
            continue
        if _looks_like_table_of_contents(text):
            cleaned_pages.append({**page, "text": ""})
            continue

        lines = []
        for line in text.splitlines():
            if _normalise_noise_line(line) in repeated_lines:
                continue
            lines.append(line)
        text = "\n".join(lines).strip()

        # Only trim references near the end of the file; policy references are
        # usually useful metadata but rarely useful retrieval evidence.
        if index > len(pages) * 0.7:
            match = re.search(
                r"(?im)^\s*(references|bibliography|works cited)\s*$",
                text,
            )
            if match:
                text = text[: match.start()].strip()
                in_references = True

        cleaned_pages.append({**page, "text": text})

    return cleaned_pages


def _save_pages(document_id: str, pages: list[dict]) -> None:
    with get_connection() as connection:
        connection.execute(
            "DELETE FROM document_pages WHERE document_id = %s",
            (document_id,),
        )
        for page in pages:
            text = page["text"]
            connection.execute(
                """
                INSERT INTO document_pages (id, document_id, page_number, text, char_count)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (str(uuid4()), document_id, page["page"], text, len(text)),
            )
        connection.commit()


def _save_metadata(
    document_id: str,
    metadata: dict,
    generated_by_model: str | None,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO document_metadata (
                document_id,
                title,
                summary,
                source_type,
                source_organisation,
                country_region,
                language,
                year,
                publication_date,
                policy_areas,
                keywords,
                stakeholders,
                implementation_risks,
                metadata_json,
                generated_by_model,
                generated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, now())
            ON CONFLICT (document_id) DO UPDATE
            SET title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                source_type = EXCLUDED.source_type,
                source_organisation = EXCLUDED.source_organisation,
                country_region = EXCLUDED.country_region,
                language = EXCLUDED.language,
                year = EXCLUDED.year,
                publication_date = EXCLUDED.publication_date,
                policy_areas = EXCLUDED.policy_areas,
                keywords = EXCLUDED.keywords,
                stakeholders = EXCLUDED.stakeholders,
                implementation_risks = EXCLUDED.implementation_risks,
                metadata_json = EXCLUDED.metadata_json,
                generated_by_model = EXCLUDED.generated_by_model,
                generated_at = now()
            """,
            (
                document_id,
                metadata.get("title"),
                metadata.get("summary"),
                metadata.get("source_type"),
                metadata.get("source_organisation"),
                metadata.get("country_region"),
                metadata.get("language"),
                metadata.get("year"),
                metadata.get("publication_date"),
                metadata.get("policy_areas", []),
                metadata.get("keywords", []),
                metadata.get("stakeholders", []),
                metadata.get("implementation_risks", []),
                json.dumps(metadata.get("metadata_json", {})),
                generated_by_model,
            ),
        )
        connection.commit()


def _paragraphs_for_chunking(pages: list[dict]) -> list[dict]:
    # Split on blank lines first so chunks preserve natural paragraph boundaries
    # instead of cutting through sentences whenever possible.
    paragraphs: list[dict] = []
    for page in pages:
        chunks = re.split(r"\n\s*\n+", page["text"])
        for paragraph in chunks:
            clean = re.sub(r"\s+", " ", paragraph).strip()
            if clean:
                paragraphs.append(
                    {
                        "page": page["page"],
                        "text": clean,
                        "token_count": estimate_token_count(clean),
                    }
                )
    return paragraphs


def chunk_pages(pages: list[dict]) -> list[dict]:
    paragraphs = _paragraphs_for_chunking(pages)
    chunks: list[dict] = []
    current: list[dict] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if not current:
            return
        text = "\n\n".join(item["text"] for item in current)
        chunks.append(
            {
                "chunk_index": len(chunks),
                "page_start": current[0]["page"],
                "page_end": current[-1]["page"],
                "section_title": None,
                "text": text,
                "token_count": estimate_token_count(text),
            }
        )

        # Carry a small paragraph overlap into the next chunk so retrieval does
        # not lose context at chunk boundaries.
        overlap: list[dict] = []
        overlap_tokens = 0
        for item in reversed(current):
            if overlap_tokens >= CHUNK_OVERLAP_TOKENS:
                break
            overlap.insert(0, item)
            overlap_tokens += item["token_count"]
        current = overlap
        current_tokens = overlap_tokens

    for paragraph in paragraphs:
        if current and current_tokens + paragraph["token_count"] > MAX_CHUNK_TOKENS:
            flush()
        current.append(paragraph)
        current_tokens += paragraph["token_count"]

    if current:
        flush()

    return chunks


def _save_chunks_and_embeddings(
    document_id: str,
    chunks: list[dict],
    language: str | None,
) -> None:
    with get_connection() as connection:
        # Reprocessing replaces chunks and embeddings atomically for this
        # document; the FK cascade removes old embedding rows.
        connection.execute(
            "DELETE FROM document_chunks WHERE document_id = %s",
            (document_id,),
        )
        for chunk in chunks:
            chunk_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO document_chunks (
                    id,
                    document_id,
                    chunk_index,
                    page_start,
                    page_end,
                    section_title,
                    language,
                    text,
                    token_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    chunk_id,
                    document_id,
                    chunk["chunk_index"],
                    chunk["page_start"],
                    chunk["page_end"],
                    chunk["section_title"],
                    language,
                    chunk["text"],
                    chunk["token_count"],
                ),
            )
            connection.execute(
                """
                INSERT INTO chunk_embeddings (chunk_id, embedding, embedding_model)
                VALUES (%s, %s::vector, %s)
                """,
                (
                    chunk_id,
                    vector_literal(embed_text(chunk["text"])),
                    EMBEDDING_MODEL_NAME,
                ),
            )
        connection.commit()


def process_document(document_id: str) -> None:
    job_id = _start_job(document_id, "ingest_pdf")
    try:
        document = get_document(document_id)
        path = BACKEND_ROOT / document["file_path"]

        # Ingestion stages are reflected in document.status so the UI can show
        # progress and failures without reading processing job internals.
        pages = _read_pdf_pages_from_path(path)
        _save_pages(document_id, pages)
        _set_document_status(document_id, "parsed")

        try:
            metadata, model_name = generate_document_metadata(
                filename=document["original_filename"],
                pages=pages,
            )
        except Exception as exc:
            metadata = {
                "title": document["original_filename"],
                        "summary": None,
                        "source_type": None,
                        "source_organisation": None,
                        "country_region": None,
                        "language": None,
                        "year": None,
                        "publication_date": None,
                        "policy_areas": [],
                "keywords": [],
                "stakeholders": [],
                "implementation_risks": [],
                "metadata_json": {"metadata_error": str(exc)},
            }
            model_name = None
        _save_metadata(document_id, metadata, model_name)
        _set_document_status(document_id, "annotated")

        chunks = chunk_pages(pages)
        _save_chunks_and_embeddings(document_id, chunks, metadata.get("language"))
        _set_document_status(document_id, "ready")

        _finish_job(
            job_id,
            details={
                "page_count": len(pages),
                "chunk_count": len(chunks),
                "metadata_model": model_name,
            },
        )
    except Exception as exc:
        _set_document_status(document_id, "failed", str(exc))
        _finish_job(job_id, status="failed", error_message=str(exc))
        raise


async def save_upload(upload: UploadFile) -> dict:
    init_db()
    filename = safe_filename(upload.filename or "")
    content = await upload.read()

    if not content.startswith(b"%PDF"):
        raise ValueError(f"{filename} is not a valid PDF file.")

    document_id = str(uuid4())
    folder = _pdf_dir() / document_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_bytes(content)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO documents (
                id,
                original_filename,
                stored_filename,
                file_path,
                file_size,
                sha256,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, 'uploaded')
            """,
            (
                document_id,
                filename,
                path.name,
                _relative_path(path),
                len(content),
                _sha256(content),
            ),
        )
        connection.commit()

    process_document(document_id)
    return document_metadata(get_document(document_id))


def sync_existing_pdfs() -> None:
    init_db()
    with get_connection() as connection:
        rows = connection.execute("SELECT file_path FROM documents").fetchall()
    known_paths = {row["file_path"] for row in rows}

    for path in discover_pdf_paths():
        relative = _relative_path(path)
        if relative in known_paths:
            continue
        content = path.read_bytes()
        if not content.startswith(b"%PDF"):
            continue
        document_id = _create_document_record(path, path.name, content)
        try:
            process_document(document_id)
        except Exception:
            continue


def rescan_library(reprocess_existing: bool = True) -> dict:
    init_db()
    sync_existing_pdfs()

    if not reprocess_existing:
        return {"rescanned": True, "reprocessed": 0}

    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id FROM documents ORDER BY uploaded_at"
        ).fetchall()

    reprocessed = 0
    for row in rows:
        process_document(str(row["id"]))
        reprocessed += 1

    return {"rescanned": True, "reprocessed": reprocessed}


def document_metadata(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["original_filename"],
        "original_filename": row["original_filename"],
        "stored_filename": row["stored_filename"],
        "relative_path": row["file_path"],
        "size": row["file_size"],
        "modified_at": row["uploaded_at"].timestamp(),
        "status": row["status"],
        "approved": row.get("approved", True),
        "access_level": row.get("access_level", "public"),
        "uploaded_at": row["uploaded_at"].isoformat(),
        "processed_at": row["processed_at"].isoformat()
        if row.get("processed_at")
        else None,
        "error_message": row.get("error_message"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "source_type": row.get("source_type"),
        "source_organisation": row.get("source_organisation"),
        "country_region": row.get("country_region"),
        "language": row.get("language"),
        "publication_date": row["publication_date"].isoformat()
        if row.get("publication_date")
        else None,
        "keywords": row.get("keywords") or [],
        "policy_areas": row.get("policy_areas") or [],
        "year": row.get("year"),
        "page_count": row.get("page_count") or 0,
        "chunk_count": row.get("chunk_count") or 0,
    }


def _list_where_clause(include_restricted: bool, filters: dict) -> tuple[str, list]:
    clauses = []
    values = []
    if not include_restricted:
        clauses.append("d.approved = true AND d.access_level = 'public'")
    if filters.get("policy_area"):
        clauses.append("%s = ANY(m.policy_areas)")
        values.append(filters["policy_area"])
    if filters.get("country_or_region"):
        clauses.append("m.country_region = %s")
        values.append(filters["country_or_region"])
    if filters.get("source_organisation"):
        clauses.append("m.source_organisation = %s")
        values.append(filters["source_organisation"])
    if filters.get("tag"):
        clauses.append("%s = ANY(m.keywords)")
        values.append(filters["tag"])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, values


def list_documents(
    include_restricted: bool = False,
    policy_area: str | None = None,
    country_or_region: str | None = None,
    source_organisation: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    sync_existing_pdfs()
    where_sql, values = _list_where_clause(
        include_restricted,
        {
            "policy_area": policy_area,
            "country_or_region": country_or_region,
            "source_organisation": source_organisation,
            "tag": tag,
        },
    )
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                d.*,
                m.title,
                m.summary,
                m.source_type,
                m.source_organisation,
                m.country_region,
                m.language,
                m.publication_date,
                m.keywords,
                m.policy_areas,
                m.year,
                COALESCE(p.page_count, 0) AS page_count,
                COALESCE(c.chunk_count, 0) AS chunk_count
            FROM documents d
            LEFT JOIN document_metadata m ON m.document_id = d.id
            LEFT JOIN (
                SELECT document_id, count(*) AS page_count
                FROM document_pages
                GROUP BY document_id
            ) p ON p.document_id = d.id
            LEFT JOIN (
                SELECT document_id, count(*) AS chunk_count
                FROM document_chunks
                GROUP BY document_id
            ) c ON c.document_id = d.id
            {where_sql}
            ORDER BY d.uploaded_at DESC, d.original_filename ASC
            """,
            tuple(values),
        ).fetchall()
    return [document_metadata(row) for row in rows]


def get_document_detail(identifier: str, include_restricted: bool = False) -> dict:
    document = get_document(identifier, include_restricted=include_restricted)
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                d.*,
                m.title,
                m.summary,
                m.source_type,
                m.source_organisation,
                m.country_region,
                m.language,
                m.publication_date,
                m.year,
                m.policy_areas,
                m.keywords,
                m.stakeholders,
                m.implementation_risks,
                m.metadata_json,
                m.generated_by_model,
                m.generated_at,
                COALESCE(p.page_count, 0) AS page_count,
                COALESCE(c.chunk_count, 0) AS chunk_count
            FROM documents d
            LEFT JOIN document_metadata m ON m.document_id = d.id
            LEFT JOIN (
                SELECT document_id, count(*) AS page_count
                FROM document_pages
                GROUP BY document_id
            ) p ON p.document_id = d.id
            LEFT JOIN (
                SELECT document_id, count(*) AS chunk_count
                FROM document_chunks
                GROUP BY document_id
            ) c ON c.document_id = d.id
            WHERE d.id = %s
            """,
            (document["id"],),
        ).fetchone()

        jobs = connection.execute(
            """
            SELECT job_type, status, started_at, finished_at, error_message, details_json
            FROM processing_jobs
            WHERE document_id = %s
            ORDER BY started_at DESC
            LIMIT 10
            """,
            (document["id"],),
        ).fetchall()

    detail = document_metadata(row)
    detail.update(
        {
            "sha256": row["sha256"],
            "mime_type": row["mime_type"],
            "stakeholders": row.get("stakeholders") or [],
            "implementation_risks": row.get("implementation_risks") or [],
            "metadata_json": row.get("metadata_json") or {},
            "generated_by_model": row.get("generated_by_model"),
            "generated_at": row["generated_at"].isoformat()
            if row.get("generated_at")
            else None,
            "jobs": [
                {
                    "job_type": job["job_type"],
                    "status": job["status"],
                    "started_at": job["started_at"].isoformat(),
                    "finished_at": job["finished_at"].isoformat()
                    if job.get("finished_at")
                    else None,
                    "error_message": job.get("error_message"),
                    "details_json": job.get("details_json") or {},
                }
                for job in jobs
            ],
        }
    )
    return detail


def get_document_chunks(identifier: str, include_restricted: bool = False) -> list[dict]:
    document = get_document(identifier, include_restricted=include_restricted)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.chunk_index,
                c.page_start,
                c.page_end,
                c.section_title,
                c.language,
                c.text,
                c.token_count,
                c.keywords,
                c.metadata_json,
                c.created_at,
                e.embedding_model
            FROM document_chunks c
            LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id
            WHERE c.document_id = %s
            ORDER BY c.chunk_index
            """,
            (document["id"],),
        ).fetchall()

    return [
        {
            "id": str(row["id"]),
            "chunk_id": str(row["id"]),
            "document_id": str(document["id"]),
            "chunk_index": row["chunk_index"],
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "section_title": row.get("section_title"),
            "language": row.get("language"),
            "text": row["text"],
            "token_count": row["token_count"],
            "keywords": row.get("keywords") or [],
            "metadata_json": row.get("metadata_json") or {},
            "created_at": row["created_at"].isoformat(),
            "embedding_model": row.get("embedding_model"),
            "text_preview": row["text"][:500],
        }
        for row in rows
    ]


def get_document(identifier: str, include_restricted: bool = True) -> dict:
    init_db()
    with get_connection() as connection:
        visibility_sql = (
            ""
            if include_restricted
            else "AND approved = true AND access_level = 'public'"
        )
        if _looks_like_uuid(identifier):
            row = connection.execute(
                f"SELECT * FROM documents WHERE id = %s {visibility_sql}",
                (identifier,),
            ).fetchone()
        else:
            row = connection.execute(
                f"""
                SELECT *
                FROM documents
                WHERE (original_filename = %s OR stored_filename = %s OR file_path = %s)
                {visibility_sql}
                ORDER BY uploaded_at DESC
                LIMIT 1
                """,
                (identifier, identifier, identifier),
            ).fetchone()
    if not row:
        raise FileNotFoundError(f"PDF not found: {identifier}")
    return row


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def resolve_pdf(identifier: str, include_restricted: bool = False) -> Path:
    document = get_document(identifier, include_restricted=include_restricted)
    path = BACKEND_ROOT / document["file_path"]
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {identifier}")
    return path


def delete_document(identifier: str) -> None:
    document = get_document(identifier)
    path = BACKEND_ROOT / document["file_path"]
    with get_connection() as connection:
        connection.execute("DELETE FROM documents WHERE id = %s", (document["id"],))
        connection.commit()
    if path.is_file():
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass


def update_document_governance(
    identifier: str,
    approved: bool | None = None,
    access_level: str | None = None,
) -> dict:
    if access_level is not None and access_level not in {"public", "private"}:
        raise ValueError("access_level must be public or private.")
    document = get_document(identifier, include_restricted=True)
    with get_connection() as connection:
        row = connection.execute(
            """
            UPDATE documents
            SET approved = COALESCE(%s, approved),
                access_level = COALESCE(%s, access_level)
            WHERE id = %s
            RETURNING *
            """,
            (approved, access_level, document["id"]),
        ).fetchone()
        connection.commit()
    return get_document_detail(str(row["id"]), include_restricted=True)


def update_document_metadata(identifier: str, payload: dict) -> dict:
    document = get_document(identifier, include_restricted=True)
    metadata_fields = {
        "title": payload.get("title"),
        "summary": payload.get("summary"),
        "source_organisation": payload.get("source_organisation"),
        "country_region": payload.get("country_or_region"),
        "year": payload.get("published_year"),
        "policy_areas": [payload["policy_area"]] if payload.get("policy_area") else None,
        "keywords": payload.get("tags"),
    }
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO document_metadata (
                document_id,
                title,
                summary,
                source_organisation,
                country_region,
                year,
                policy_areas,
                keywords
            )
            VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                COALESCE(%s::text[], '{}'),
                COALESCE(%s::text[], '{}')
            )
            ON CONFLICT (document_id) DO UPDATE
            SET title = COALESCE(EXCLUDED.title, document_metadata.title),
                summary = COALESCE(EXCLUDED.summary, document_metadata.summary),
                source_organisation = COALESCE(
                    EXCLUDED.source_organisation,
                    document_metadata.source_organisation
                ),
                country_region = COALESCE(
                    EXCLUDED.country_region,
                    document_metadata.country_region
                ),
                year = COALESCE(EXCLUDED.year, document_metadata.year),
                policy_areas = CASE
                    WHEN EXCLUDED.policy_areas = '{}' THEN document_metadata.policy_areas
                    ELSE EXCLUDED.policy_areas
                END,
                keywords = CASE
                    WHEN EXCLUDED.keywords = '{}' THEN document_metadata.keywords
                    ELSE EXCLUDED.keywords
                END,
                reviewed_at = now()
            """,
            (
                document["id"],
                metadata_fields["title"],
                metadata_fields["summary"],
                metadata_fields["source_organisation"],
                metadata_fields["country_region"],
                metadata_fields["year"],
                metadata_fields["policy_areas"],
                metadata_fields["keywords"],
            ),
        )
        connection.commit()

    if payload.get("approved") is not None or payload.get("access_level") is not None:
        return update_document_governance(
            str(document["id"]),
            approved=payload.get("approved"),
            access_level=payload.get("access_level"),
        )
    return get_document_detail(str(document["id"]), include_restricted=True)


def extract_pages(identifier: str, include_restricted: bool = False) -> list[dict]:
    document = get_document(identifier, include_restricted=include_restricted)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT page_number, text
            FROM document_pages
            WHERE document_id = %s
            ORDER BY page_number
            """,
            (document["id"],),
        ).fetchall()

    if not rows:
        path = BACKEND_ROOT / document["file_path"]
        pages = _read_pdf_pages_from_path(path)
        _save_pages(str(document["id"]), pages)
        return pages

    return [
        {
            "file": document["original_filename"],
            "page": row["page_number"],
            "text": row["text"],
        }
        for row in rows
    ]


def read_documents(identifiers: list[str], include_restricted: bool = False) -> list[dict]:
    pages: list[dict] = []
    for identifier in identifiers:
        pages.extend(extract_pages(identifier, include_restricted=include_restricted))
    return pages


def retrieve_relevant_chunks(
    question: str,
    identifiers: list[str],
    limit: int = 8,
    include_restricted: bool = False,
) -> list[dict]:
    documents = [
        get_document(identifier, include_restricted=include_restricted)
        for identifier in identifiers
    ]
    document_ids = [str(document["id"]) for document in documents]
    if not document_ids:
        return []

    query_vector = vector_literal(embed_text(question))
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                c.id AS chunk_id,
                c.document_id,
                d.original_filename AS file,
                c.page_start,
                c.page_end,
                c.text,
                c.token_count,
                c.language,
                e.embedding <=> %s::vector AS distance
            FROM chunk_embeddings e
            JOIN document_chunks c ON c.id = e.chunk_id
            JOIN documents d ON d.id = c.document_id
            WHERE c.document_id = ANY(%s::uuid[])
            ORDER BY e.embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vector, document_ids, query_vector, limit),
        ).fetchall()

    return [
        {
            "chunk_id": str(row["chunk_id"]),
            "document_id": str(row["document_id"]),
            "file": row["file"],
            "page": row["page_start"],
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "text": row["text"],
            "token_count": row["token_count"],
            "language": row.get("language"),
            "distance": float(row["distance"]),
        }
        for row in rows
    ]


def copy_pdf_into_library(source_path: Path) -> str:
    content = source_path.read_bytes()
    filename = safe_filename(source_path.name)
    document_id = str(uuid4())
    folder = _pdf_dir() / document_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    shutil.copy2(source_path, target)
    return _create_document_record(target, filename, content)
