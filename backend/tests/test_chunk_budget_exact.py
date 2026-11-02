import pytest

from app.modules.documents.chunker import DocumentChunker


@pytest.mark.parametrize("overlap", [0, 8, 16, 32])
def test_budget_counts_join_separators_and_keeps_source_content(overlap):
    paragraphs = ["a" * 19, "b" * 19, "c" * 19, "d" * 19, "e" * 19, "f" * 19]
    chunks = DocumentChunker(token_counter=len).chunk(
        [{"page": 1, "text": "\n\n".join(paragraphs)}], max_tokens=64, overlap=overlap
    )
    assert all(len(c["text"]) <= 64 and c["token_count"] == len(c["text"]) for c in chunks)
    assert all(any(p in c["text"] for c in chunks) for p in paragraphs)


def test_overlap_is_trimmed_to_fit_actual_joined_tokens():
    chunks = DocumentChunker(token_counter=len).chunk(
        [{"page": 1, "text": "x" * 32 + "\n\n" + "y" * 32 + "\n\n" + "z" * 32}],
        max_tokens=64,
        overlap=32,
    )
    assert all(c["token_count"] <= 64 for c in chunks)
    assert any("y" * 32 in c["text"] for c in chunks)
    assert any("z" * 32 in c["text"] for c in chunks)


def test_oversized_paragraph_sentence_joins_count_actual_tokens():
    # Joining two independently tokenized sentences can cost extra tokens.
    def counter(text):
        return len(text) + 2 * text.count(". ")

    text = ". ".join(["a" * 18, "b" * 18, "c" * 18, "d" * 18]) + "."
    chunks = DocumentChunker(token_counter=counter).chunk(
        [{"page": 1, "text": text}],
        max_tokens=64,
        overlap=8,
    )
    assert all(c["token_count"] == counter(c["text"]) <= 64 for c in chunks)
    assert all(any(letter * 18 in c["text"] for c in chunks) for letter in "abcd")
