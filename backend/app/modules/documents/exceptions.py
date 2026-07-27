from __future__ import annotations


class DuplicateDocumentError(Exception):
    """Raised when an uploaded file's content already exists in the library.

    L1 duplicate detection: two files with identical bytes share a SHA-256, so
    an incoming file whose hash already exists is an exact duplicate.
    """

    def __init__(self, existing_id: str, existing_filename: str) -> None:
        self.existing_id = existing_id
        self.existing_filename = existing_filename
        super().__init__(f"This file is identical to an existing document: {existing_filename}")
