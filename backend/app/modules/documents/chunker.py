from app.modules.documents.embeddings import estimate_token_count

MAX_CHUNK_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 120


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

    @staticmethod
    def _paragraphs(pages: list[dict]) -> list[dict]:
        import re

        paragraphs: list[dict] = []
        for page in pages:
            for paragraph in re.split(r"\n\s*\n+", page["text"]):
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


document_chunker = DocumentChunker()
