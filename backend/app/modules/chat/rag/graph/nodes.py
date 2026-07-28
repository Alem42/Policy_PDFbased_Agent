from app.modules.chat.rag.evidence import (
    assess_evidence_sufficiency,
    max_vector_distance,
)
from app.modules.chat.rag.generation import (
    check_evidence_sufficiency_llm,
    format_context,
    generate_answer,
)
from app.modules.chat.rag.graph.state import (
    AnswerMode,
    PDFQAState,
    ResponseMode,
    normalize_answer_mode,
)
from app.modules.chat.rag.prompts import get_insufficient_evidence_message
from app.modules.documents.service import (
    documents_have_embeddings,
    read_documents,
    retrieve_relevant_chunks,
)


def _identifiers(state: PDFQAState) -> list[str]:
    return state.get("document_ids") or state.get("filenames") or []


def _response_mode(state: PDFQAState) -> ResponseMode:
    mode = state.get("response_mode", "researcher")
    if mode in {"researcher", "policymaker", "student"}:
        return mode
    return "researcher"


def _answer_mode(state: PDFQAState) -> AnswerMode:
    mode = state.get("answer_mode", "analysis")
    return normalize_answer_mode(_response_mode(state), mode)


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
    raw_chunks = retrieve_relevant_chunks(
        question=state["question"],
        identifiers=_identifiers(state),
        limit=state.get("top_k", 8),
        include_restricted=state.get("include_restricted", False),
    )
    # Check the DB directly — using bool(raw_chunks) is unreliable because an unusual
    # query can legitimately return 0 nearest-neighbours even when embeddings exist.
    has_embeddings = documents_have_embeddings(_identifiers(state))

    # Only use chunks that are actually close to the query (live, admin-tunable cutoff).
    threshold = max_vector_distance()
    relevant_chunks = [c for c in raw_chunks if float(c.get("distance", 1.0)) <= threshold]
    context_source = relevant_chunks or state["pages"]
    context, truncated = format_context(context_source)

    if not context:
        return {
            "context": "",
            "truncated": truncated,
            "chunks": relevant_chunks,
            "raw_chunks": raw_chunks,
            "citations": [],
            "used_vector_retrieval": has_embeddings,
        }

    if relevant_chunks:
        # Vector path: one citation per retrieved chunk (has document_id and quote).
        citations = [
            {
                "document_id": chunk["document_id"],
                "title": chunk.get("doc_title") or chunk["file"],
                "chunk_id": chunk["chunk_id"],
                "page": chunk["page_start"],
                "quote": chunk["text"][:500],
            }
            for chunk in relevant_chunks
        ]
    else:
        # Page-level fallback (no relevant chunks found): cite per page.
        citations = [
            {
                "title": p.get("title") or p["file"],
                "page": p.get("page"),
                "quote": (p.get("text") or "")[:300],
            }
            for p in state["pages"]
        ]
    return {
        "context": context,
        "truncated": truncated,
        "chunks": relevant_chunks,
        "raw_chunks": raw_chunks,
        "citations": citations,
        "used_vector_retrieval": has_embeddings,
    }


def check_evidence_node(state: PDFQAState) -> dict:
    """Decide whether retrieved material is strong enough for generation."""
    sufficient, reason = assess_evidence_sufficiency(
        question=state["question"],
        raw_chunks=state.get("raw_chunks", []),
        pages=state.get("pages", []),
        context=state.get("context", ""),
        has_embeddings=state.get("used_vector_retrieval", False),
    )
    if sufficient:
        # Second, semantic gate: the cheap vector/reranker check above only
        # measures embedding closeness, which can be deceptively high for
        # topically unrelated policy-language text. Ask the LLM itself to
        # confirm the excerpts can actually answer the question before
        # committing to a full (and more expensive) generation call.
        llm_sufficient, llm_reason = check_evidence_sufficiency_llm(
            question=state["question"],
            citations=state.get("citations", []),
            model=state.get("model"),
        )
        if not llm_sufficient:
            return {"evidence_sufficient": False, "evidence_reason": llm_reason}
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
    answer, resolved_model = generate_answer(
        question=state["question"],
        context=state["context"],
        model=state.get("model"),
        response_mode=_response_mode(state),
        answer_mode=_answer_mode(state),
        history=state.get("history", []),
        citations=state.get("citations", []),
    )
    return {"answer": answer, "resolved_model": resolved_model}


def route_after_evidence_check(state: PDFQAState) -> str:
    if state.get("evidence_sufficient", False):
        return "generate_answer"
    # Policymaker mode is always document-grounded and must stop when evidence is weak.
    if _response_mode(state) == "policymaker":
        return "insufficient_evidence"
    # Existing Researcher/Student Open Discussion behaviour remains unchanged.
    if _answer_mode(state) == "chat":
        return "generate_answer"
    return "insufficient_evidence"
