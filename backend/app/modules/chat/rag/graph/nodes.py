from app.modules.chat.rag.evidence import assess_evidence_sufficiency
from app.modules.chat.rag.generation import format_context, generate_answer
from app.modules.chat.rag.graph.state import PDFQAState, ResponseMode
from app.modules.chat.rag.prompts import get_insufficient_evidence_message
from app.modules.documents.service import read_documents, retrieve_relevant_chunks


def _identifiers(state: PDFQAState) -> list[str]:
    return state.get("document_ids") or state.get("filenames") or []


def _response_mode(state: PDFQAState) -> ResponseMode:
    mode = state.get("response_mode", "researcher")
    return "student" if mode == "student" else "researcher"


def load_documents_node(state: PDFQAState) -> dict:
    """Load page-level text as a fallback for selected local PDF files."""
    return {
        "pages": read_documents(
            _identifiers(state),
            include_restricted=state.get("include_restricted", False),
        )
    }


def retrieve_context_node(state: PDFQAState) -> dict:
    """Build model context from vector retrieval or page-level fallback."""
    chunks = retrieve_relevant_chunks(
        question=state["question"],
        identifiers=_identifiers(state),
        limit=state.get("top_k", 8),
        include_restricted=state.get("include_restricted", False),
    )
    used_vector_retrieval = bool(chunks)
    context_source = chunks or state["pages"]
    context, truncated = format_context(context_source)
    if not context:
        return {
            "context": "",
            "truncated": truncated,
            "chunks": chunks,
            "citations": [],
            "used_vector_retrieval": used_vector_retrieval,
        }

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
    return {
        "context": context,
        "truncated": truncated,
        "chunks": chunks,
        "citations": citations,
        "used_vector_retrieval": used_vector_retrieval,
    }


def check_evidence_node(state: PDFQAState) -> dict:
    """Decide whether retrieved material is strong enough for generation."""
    sufficient, reason = assess_evidence_sufficiency(
        question=state["question"],
        chunks=state.get("chunks", []),
        pages=state.get("pages", []),
        context=state.get("context", ""),
        used_vector_retrieval=state.get("used_vector_retrieval", False),
    )
    return {
        "evidence_sufficient": sufficient,
        "evidence_reason": reason,
    }


def insufficient_evidence_node(state: PDFQAState) -> dict:
    """Return a mode-aware refusal when evidence is too weak."""
    reason = state.get("evidence_reason") or "The retrieved excerpts are too weak."
    return {
        "answer": get_insufficient_evidence_message(
            question=state["question"],
            reason=reason,
            mode=_response_mode(state),
        )
    }


def generate_answer_node(state: PDFQAState) -> dict:
    """Generate the final answer from the prepared document context."""
    return {
        "answer": generate_answer(
            question=state["question"],
            context=state["context"],
            model=state.get("model"),
            response_mode=_response_mode(state),
        )
    }


def route_after_evidence_check(state: PDFQAState) -> str:
    if state.get("evidence_sufficient", False):
        return "generate_answer"
    return "insufficient_evidence"
