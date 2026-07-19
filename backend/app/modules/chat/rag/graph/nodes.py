from app.modules.chat.rag.evidence import MAX_VECTOR_DISTANCE, assess_evidence_sufficiency
from app.modules.chat.rag.generation import format_context, generate_answer
from app.modules.chat.rag.graph.state import AnswerMode, PDFQAState, ResponseMode
from app.modules.chat.rag.prompts import get_insufficient_evidence_message
from app.modules.documents.service import read_documents, retrieve_relevant_chunks


def _identifiers(state: PDFQAState) -> list[str]:
    return state.get("document_ids") or state.get("filenames") or []


def _response_mode(state: PDFQAState) -> ResponseMode:
    mode = state.get("response_mode", "researcher")
    return "student" if mode == "student" else "researcher"


def _answer_mode(state: PDFQAState) -> AnswerMode:
    mode = state.get("answer_mode", "analysis")
    return "chat" if mode == "chat" else "analysis"


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
    # Only treat as vector retrieval when at least one chunk meets the distance threshold.
    # Avoids blocking generic questions when embeddings are weak or non-semantic.
    relevant_chunks = [c for c in chunks if float(c.get("distance", 1.0)) <= MAX_VECTOR_DISTANCE]
    used_vector_retrieval = bool(relevant_chunks)
    context_source = relevant_chunks or state["pages"]
    context, truncated = format_context(context_source)
    if not context:
        return {
            "context": "",
            "truncated": truncated,
            "chunks": relevant_chunks,
            "citations": [],
            "used_vector_retrieval": used_vector_retrieval,
        }

    if used_vector_retrieval:
        # Vector path: one citation per retrieved chunk (has document_id and quote).
        citations = [
            {
                "document_id": chunk["document_id"],
                "title": chunk["file"],
                "chunk_id": chunk["chunk_id"],
                "page": chunk["page_start"],
                "quote": chunk["text"][:500],
            }
            for chunk in relevant_chunks
        ]
    else:
        # Page-level fallback: one citation per page so the [N] markers the LLM
        # writes for page N map to citations[N-1] in the drawer.
        # Pages don't carry document_id, so that field is omitted (optional in schema).
        citations = [
            {
                "title": p["file"],
                "page": p.get("page"),
                "quote": (p.get("text") or "")[:300],
            }
            for p in state["pages"]
        ]
    return {
        "context": context,
        "truncated": truncated,
        "chunks": relevant_chunks,
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
            history=state.get("history", []),
            citations=state.get("citations", []),
            answer_mode=_answer_mode(state),
        )
    }


def route_after_evidence_check(state: PDFQAState) -> str:
    if state.get("evidence_sufficient", False):
        return "generate_answer"
    # Open discussion may continue even when selected documents are thin.
    if _answer_mode(state) == "chat":
        return "generate_answer"
    return "insufficient_evidence"
