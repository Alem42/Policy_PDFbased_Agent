from uuid import UUID


def string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        for separator in ("\n", ";", ","):
            if separator in value:
                return [item.strip() for item in value.split(separator) if item.strip()]
        return [value.strip()] if value.strip() else []
    return [str(value)]


def looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def iso_value(value: object) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def row_to_metadata(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["original_filename"],
        "original_filename": row["original_filename"],
        "stored_filename": row["stored_filename"],
        "relative_path": row["file_path"],
        "file_path": row["file_path"],
        "size": row["file_size"],
        "file_size": row["file_size"],
        "modified_at": row["uploaded_at"].timestamp(),
        "status": row["status"],
        "approved": row.get("approved", True),
        "access_level": row.get("access_level", "public"),
        "uploaded_at": iso_value(row.get("uploaded_at")),
        "processed_at": iso_value(row.get("processed_at")),
        "error_message": row.get("error_message"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "source_type": row.get("source_type"),
        "source_organisation": row.get("source_organisation"),
        "country_region": row.get("country_region"),
        "language": row.get("language"),
        "publication_date": iso_value(row.get("publication_date")),
        "keywords": string_list(row.get("keywords")),
        "policy_areas": string_list(row.get("policy_areas")),
        "year": row.get("year"),
        "page_count": row.get("page_count") or 0,
        "chunk_count": row.get("chunk_count") or 0,
        "source_url": row.get("source_url"),
        "canonical_url": row.get("canonical_url"),
        "imported_by": row.get("imported_by") and str(row["imported_by"]),
        "imported_via": row.get("imported_via"),
    }
