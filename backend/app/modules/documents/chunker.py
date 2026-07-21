import re
from collections.abc import Callable

from app.modules.documents.embeddings import (
    estimate_embedding_token_count,
    estimate_token_count,
)

TokenCounter = Callable[[str], int]

MAX_CHUNK_TOKENS = 480
CHUNK_OVERLAP_TOKENS = 120

# Any single paragraph-level item (natural paragraph, sentence-split piece,
# or hard-sliced fragment) must leave room for CHUNK_OVERLAP_TOKENS worth of
# carry-over from the previous chunk, otherwise overlap + one full-budget
# item can exceed MAX_CHUNK_TOKENS on its own.
_ITEM_BUDGET = MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")


class DocumentChunker:
    """Builds overlapping, paragraph-aligned retrieval chunks."""

    def __init__(self, token_counter: TokenCounter = estimate_token_count) -> None:
        self._token_counter = token_counter

    def chunk(self, pages: list[dict]) -> list[dict]:
        paragraphs = self._paragraphs(pages)
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
                    "token_count": self._token_counter(text),
                }
            )
            overlap: list[dict] = []
            overlap_tokens = 0
            for item in reversed(current):
                if overlap_tokens + item["token_count"] > CHUNK_OVERLAP_TOKENS:
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

    def _paragraphs(self, pages: list[dict]) -> list[dict]:
        paragraphs: list[dict] = []
        for page in pages:
            for raw_paragraph in re.split(r"\n\s*\n+", page["text"]):
                clean = re.sub(r"\s+", " ", raw_paragraph).strip()
                if not clean:
                    continue
                token_count = self._token_counter(clean)
                if token_count <= _ITEM_BUDGET:
                    paragraphs.append(
                        {"page": page["page"], "text": clean, "token_count": token_count}
                    )
                else:
                    # >>> paragraph-splitting entry point: a single natural
                    # paragraph (no blank-line break) is too big on its own
                    # and would otherwise be emitted as one oversized chunk.
                    paragraphs.extend(
                        _split_oversized_paragraph(page["page"], clean, self._token_counter)
                    )
        return paragraphs


def _split_oversized_paragraph(page: int, text: str, token_counter: TokenCounter) -> list[dict]:
    """Break a paragraph that exceeds _ITEM_BUDGET into smaller pieces.

    Splits on sentence boundaries first; a "sentence" that is still too long
    on its own (e.g. unpunctuated text) falls back to a binary-searched
    character cut so no single piece ever exceeds the budget.
    """
    pieces: list[dict] = []
    piece_text = ""
    piece_tokens = 0

    def flush_piece() -> None:
        nonlocal piece_text, piece_tokens
        if piece_text:
            pieces.append({"page": page, "text": piece_text, "token_count": piece_tokens})
            piece_text, piece_tokens = "", 0

    for sentence in _SENTENCE_BOUNDARY.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_tokens = token_counter(sentence)
        if sentence_tokens > _ITEM_BUDGET:
            flush_piece()
            pieces.extend(_hard_slice(page, sentence, token_counter))
            continue
        if piece_text and piece_tokens + sentence_tokens > _ITEM_BUDGET:
            flush_piece()
        piece_text = f"{piece_text} {sentence}".strip()
        piece_tokens += sentence_tokens
    flush_piece()
    return pieces


def _hard_slice(page: int, text: str, token_counter: TokenCounter) -> list[dict]:
    """Cut unpunctuated text into _ITEM_BUDGET-sized pieces via binary search."""
    pieces: list[dict] = []
    remaining = text
    while remaining:
        if token_counter(remaining) <= _ITEM_BUDGET:
            pieces.append(
                {"page": page, "text": remaining, "token_count": token_counter(remaining)}
            )
            break
        low, high = 1, len(remaining)
        while low < high:
            mid = (low + high + 1) // 2
            if token_counter(remaining[:mid]) <= _ITEM_BUDGET:
                low = mid
            else:
                high = mid - 1
        cut = max(low, 1)
        piece_text = remaining[:cut].strip()
        pieces.append({"page": page, "text": piece_text, "token_count": token_counter(piece_text)})
        remaining = remaining[cut:].strip()
    return pieces


class TiktokenDocumentChunker(DocumentChunker):
    """Chunk documents using the legacy cl100k_base tokenizer."""

    def __init__(self) -> None:
        super().__init__(estimate_token_count)


class EmbeddingModelDocumentChunker(DocumentChunker):
    """Chunk documents using the configured embedding model's tokenizer."""

    def __init__(self) -> None:
        super().__init__(estimate_embedding_token_count)


# Legacy fallback retained for a possible future tokenizer/model change.
# document_chunker = TiktokenDocumentChunker()
document_chunker = EmbeddingModelDocumentChunker()
