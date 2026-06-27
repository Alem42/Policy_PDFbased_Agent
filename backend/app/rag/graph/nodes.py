from app.rag.generation import format_context, generate_answer
from app.rag.graph.state import PDFQAState
from app.services.document_service import read_documents, retrieve_relevant_chunks


def _identifiers(state: PDFQAState) -> list[str]:
    return state.get("document_ids") or state.get("filenames") or []


def load_documents_node(state: PDFQAState) -> dict:
    """Load page-level text as a fallback for selected local PDF files."""
    return {
        "pages": read_documents(
            _identifiers(state),
            include_restricted=state.get("include_restricted", False),
        )
    }


def retrieve_context_node(state: PDFQAState) -> dict:
    """Build model context.

    This uses vector retrieval over pre-computed document chunks. If no chunks
    are available yet, it falls back to page-level extracted text.
    """
    chunks = retrieve_relevant_chunks(
        question=state["question"],
        identifiers=_identifiers(state),
        limit=state.get("top_k", 8),
        include_restricted=state.get("include_restricted", False),
    )
    context_source = chunks or state["pages"]
    context, truncated = format_context(context_source)
    if not context:
        raise ValueError("No extractable text was found in the selected PDFs.")
    citations = [
        {
            "document_id": chunk["document_id"],
            "title": chunk["file"],
            "chunk_id": chunk["chunk_id"],
            "page": chunk["page_start"],
            "quote": chunk["text"][:500],
        }
        for chunk in chunks
    ]
    return {"context": context, "truncated": truncated, "chunks": chunks, "citations": citations}


def generate_answer_node(state: PDFQAState) -> dict:
    """Generate the final answer from the prepared document context."""
    return {
        "answer": generate_answer(
            question=state["question"],
            context=state["context"],
            model=state.get("model"),
        )
    }
