from __future__ import annotations

import pytest

from app.modules.documents import chunker as chunker_module


def _word_count(text: str) -> int:
    return max(1, len(text.split()))


def _double_word_count(text: str) -> int:
    return max(1, len(text.split()) * 2)


def test_chunkers_share_splitting_logic_with_independent_token_counters() -> None:
    text = ("policy " * 250).strip()
    pages = [{"page": 1, "text": text}]

    legacy_chunks = chunker_module.DocumentChunker(_word_count).chunk(pages)
    model_chunks = chunker_module.DocumentChunker(_double_word_count).chunk(pages)

    assert len(legacy_chunks) == 1
    assert len(model_chunks) == 2
    assert all(chunk["token_count"] <= chunker_module.MAX_CHUNK_TOKENS for chunk in model_chunks)


def test_embedding_model_chunker_uses_model_token_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counted_texts: list[str] = []

    def fake_model_count(text: str) -> int:
        counted_texts.append(text)
        return _word_count(text)

    monkeypatch.setattr(chunker_module, "estimate_embedding_token_count", fake_model_count)
    model_chunker = chunker_module.EmbeddingModelDocumentChunker()

    chunks = model_chunker.chunk([{"page": 1, "text": "policy response"}])

    assert counted_texts
    assert chunks[0]["token_count"] == 2


def test_default_chunker_uses_embedding_model_tokenizer() -> None:
    assert isinstance(
        chunker_module.document_chunker,
        chunker_module.EmbeddingModelDocumentChunker,
    )
    assert isinstance(
        chunker_module.TiktokenDocumentChunker(),
        chunker_module.DocumentChunker,
    )
