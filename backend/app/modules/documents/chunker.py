import re

from app.modules.documents.embeddings import estimate_token_count

# Must stay safely under the embedding model's real limit (512 WordPiece
# tokens for bge-small-en-v1.5) since estimate_token_count now counts in
# that tokenizer's own units. The margin below 512 covers [CLS]/[SEP] and
# rounding from sentence-level splitting.
MAX_CHUNK_TOKENS = 480
CHUNK_OVERLAP_TOKENS = 72

# Any single paragraph-level item (natural paragraph, sentence-split piece,
# or hard-sliced fragment) must leave room for CHUNK_OVERLAP_TOKENS worth of
# carry-over from the previous chunk, otherwise overlap + one full-budget
# item can exceed MAX_CHUNK_TOKENS on its own.
_ITEM_BUDGET = MAX_CHUNK_TOKENS - CHUNK_OVERLAP_TOKENS

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")


class DocumentChunker:
    """Builds overlapping, paragraph-aligned retrieval chunks."""

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
                    "token_count": estimate_token_count(text),
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

    @staticmethod
    def _paragraphs(pages: list[dict]) -> list[dict]:
        paragraphs: list[dict] = []
        for page in pages:
            for raw_paragraph in re.split(r"\n\s*\n+", page["text"]):
                clean = re.sub(r"\s+", " ", raw_paragraph).strip()
                if not clean:
                    continue
                token_count = estimate_token_count(clean)
                if token_count <= _ITEM_BUDGET:
                    paragraphs.append(
                        {"page": page["page"], "text": clean, "token_count": token_count}
                    )
                else:
                    paragraphs.extend(_split_oversized_paragraph(page["page"], clean))
        return paragraphs


def _split_oversized_paragraph(page: int, text: str) -> list[dict]:
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
        sentence_tokens = estimate_token_count(sentence)
        if sentence_tokens > _ITEM_BUDGET:
            flush_piece()
            pieces.extend(_hard_slice(page, sentence))
            continue
        if piece_text and piece_tokens + sentence_tokens > _ITEM_BUDGET:
            flush_piece()
        piece_text = f"{piece_text} {sentence}".strip()
        piece_tokens += sentence_tokens
    flush_piece()
    return pieces


def _hard_slice(page: int, text: str) -> list[dict]:
    """Cut unpunctuated text into _ITEM_BUDGET-sized pieces via binary search."""
    pieces: list[dict] = []
    remaining = text
    while remaining:
        if estimate_token_count(remaining) <= _ITEM_BUDGET:
            pieces.append(
                {"page": page, "text": remaining, "token_count": estimate_token_count(remaining)}
            )
            break
        low, high = 1, len(remaining)
        while low < high:
            mid = (low + high + 1) // 2
            if estimate_token_count(remaining[:mid]) <= _ITEM_BUDGET:
                low = mid
            else:
                high = mid - 1
        cut = max(low, 1)
        piece_text = remaining[:cut].strip()
        pieces.append(
            {"page": page, "text": piece_text, "token_count": estimate_token_count(piece_text)}
        )
        remaining = remaining[cut:].strip()
    return pieces


document_chunker = DocumentChunker()
