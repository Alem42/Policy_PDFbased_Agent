import re
from collections.abc import Callable

from app.modules.documents.embeddings import (
    estimate_embedding_token_count,
    estimate_token_count,
)

TokenCounter = Callable[[str], int]

# Defaults; the active budget is admin-tunable (Manage > Embedding) and passed
# into chunk() at call time. The constants keep existing callers/tests unchanged.
MAX_CHUNK_TOKENS = 480
CHUNK_OVERLAP_TOKENS = 120

# Any single paragraph-level item (natural paragraph, sentence-split piece, or
# hard-sliced fragment) must leave room for the overlap carried from the previous
# chunk, otherwise overlap + one full-budget item can exceed the max on its own.
# item_budget = max_tokens - overlap (computed per call).

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")


# TODO(structure-aware chunking): future work. Detect headings (numbering like
# "3.2"/"Article 5", ALL-CAPS lines, or larger font via PyMuPDF get_text("dict"))
# and use them as hard chunk boundaries + populate `section_title`, so a chunk
# never straddles two sections. Optionally add semantic chunking (split where
# adjacent-sentence embedding similarity drops). Deferred for now.


class DocumentChunker:
    """Builds overlapping, paragraph-aligned retrieval chunks."""

    def __init__(self, token_counter: TokenCounter = estimate_token_count) -> None:
        self._token_counter = token_counter

    def chunk(
        self,
        pages: list[dict],
        max_tokens: int = MAX_CHUNK_TOKENS,
        overlap: int = CHUNK_OVERLAP_TOKENS,
    ) -> list[dict]:
        # Keep the params sane so a small budget can't make item_budget <= 0.
        max_tokens = max(64, int(max_tokens))
        overlap = max(0, min(int(overlap), max_tokens // 2))
        item_budget = max_tokens - overlap

        paragraphs = self._paragraphs(pages, item_budget)
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
            current, current_tokens = self._overlap_tail(current, overlap)

        for paragraph in paragraphs:
            if current and current_tokens + paragraph["token_count"] > max_tokens:
                flush()
            current.append(paragraph)
            current_tokens += paragraph["token_count"]
        if current:
            flush()
        return chunks

    def _overlap_tail(self, items: list[dict], overlap: int) -> tuple[list[dict], int]:
        """Carry ~overlap tokens of trailing context into the next chunk.

        Whole trailing paragraphs first. If the last paragraph alone already
        exceeds the overlap budget, fall back to carrying its trailing SENTENCES
        so overlap is never empty (fixes the long-final-paragraph zero-overlap
        bug where two chunks shared no text at all).
        """
        tail: list[dict] = []
        tail_tokens = 0
        for item in reversed(items):
            if tail_tokens + item["token_count"] > overlap:
                break
            tail.insert(0, item)
            tail_tokens += item["token_count"]

        if not tail and items and overlap > 0:
            sentences = _tail_sentences(items[-1], overlap, self._token_counter)
            if sentences:
                return [sentences], sentences["token_count"]
        return tail, tail_tokens

    def _paragraphs(self, pages: list[dict], item_budget: int) -> list[dict]:
        paragraphs: list[dict] = []
        for page in pages:
            for raw_paragraph in re.split(r"\n\s*\n+", page["text"]):
                clean = re.sub(r"\s+", " ", raw_paragraph).strip()
                if not clean:
                    continue
                token_count = self._token_counter(clean)
                if token_count <= item_budget:
                    paragraphs.append(
                        {"page": page["page"], "text": clean, "token_count": token_count}
                    )
                else:
                    # >>> paragraph-splitting entry point: a single natural
                    # paragraph (no blank-line break) is too big on its own
                    # and would otherwise be emitted as one oversized chunk.
                    paragraphs.extend(
                        _split_oversized_paragraph(
                            page["page"], clean, self._token_counter, item_budget
                        )
                    )
        return paragraphs


def _tail_sentences(item: dict, budget: int, token_counter: TokenCounter) -> dict | None:
    """Build an overlap item from the trailing sentences of a long paragraph."""
    carried: list[str] = []
    tokens = 0
    for sentence in reversed(_SENTENCE_BOUNDARY.split(item["text"])):
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_tokens = token_counter(sentence)
        if carried and tokens + sentence_tokens > budget:
            break
        carried.insert(0, sentence)
        tokens += sentence_tokens
        if tokens >= budget:  # took at least one sentence; stop once budget reached
            break
    if not carried:
        return None
    text = " ".join(carried)
    return {"page": item["page"], "text": text, "token_count": token_counter(text)}


def _split_oversized_paragraph(
    page: int, text: str, token_counter: TokenCounter, item_budget: int
) -> list[dict]:
    """Break a paragraph that exceeds item_budget into smaller pieces.

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
        if sentence_tokens > item_budget:
            flush_piece()
            pieces.extend(_hard_slice(page, sentence, token_counter, item_budget))
            continue
        if piece_text and piece_tokens + sentence_tokens > item_budget:
            flush_piece()
        piece_text = f"{piece_text} {sentence}".strip()
        piece_tokens += sentence_tokens
    flush_piece()
    return pieces


def _hard_slice(
    page: int, text: str, token_counter: TokenCounter, item_budget: int
) -> list[dict]:
    """Cut unpunctuated text into item_budget-sized pieces via binary search."""
    pieces: list[dict] = []
    remaining = text
    while remaining:
        if token_counter(remaining) <= item_budget:
            pieces.append(
                {"page": page, "text": remaining, "token_count": token_counter(remaining)}
            )
            break
        low, high = 1, len(remaining)
        while low < high:
            mid = (low + high + 1) // 2
            if token_counter(remaining[:mid]) <= item_budget:
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
