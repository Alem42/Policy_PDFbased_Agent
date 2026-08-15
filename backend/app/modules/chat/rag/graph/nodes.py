from app.modules.chat.rag.generation import generate_answer
from app.modules.chat.rag.graph.state import (
    AnswerMode,
    PDFQAState,
    ResponseMode,
    normalize_answer_mode,
)
from app.modules.chat.rag.prompts import get_insufficient_evidence_message
from app.modules.retrieval.contracts import MetadataFilters, RetrievalRequest
from app.modules.retrieval.service import (
    retrieval_service,
)


def _identifiers(state: PDFQAState) -> list[str]:
    return state.get("document_ids") or state.get("filenames") or []


def _response_mode(state: PDFQAState) -> ResponseMode:
    mode = state.get("response_mode", "researcher")
    if mode in {"researcher", "policymaker"}:
        return mode
    return "researcher"


def _answer_mode(state: PDFQAState) -> AnswerMode:
    mode = state.get("answer_mode", "analysis")
    return normalize_answer_mode(_response_mode(state), mode)


def load_documents_node(state: PDFQAState) -> dict:
    """Load page-level text as a fallback for selected local PDF files."""
    return {
        "pages": retrieval_service.load_pages(
            _identifiers(state),
            include_restricted=state.get("include_restricted", False),
        )
    }


def retrieve_context_node(state: PDFQAState) -> dict:
    """Delegate selected-document retrieval to the shared black box."""
    result = retrieval_service.retrieve(
        RetrievalRequest(
            question=state["question"],
            scope="selected",
            identifiers=tuple(_identifiers(state)),
            top_k=state.get("top_k", 8),
            include_restricted=state.get("include_restricted", False),
            metadata_filters=MetadataFilters.from_mapping(state.get("metadata_filters")),
        ),
        preloaded_pages=state.get("pages", []),
    )
    return result.as_state()


def check_evidence_node(state: PDFQAState) -> dict:
    """Expose the decision already made by ``RetrievalService``."""
    return {
        "evidence_sufficient": state.get("evidence_sufficient", False),
        "evidence_reason": state.get("evidence_reason"),
    }


def insufficient_evidence_node(state: PDFQAState) -> dict:
    """Return a mode-aware refusal when evidence is too weak."""
    reason = state.get("evidence_reason") or "The retrieved excerpts are too weak."
    answer = get_insufficient_evidence_message(
        question=state["question"],
        reason=reason,
        mode=_response_mode(state),
    )
    if state.get("filter_fallback") and state.get("filter_notice"):
        answer = f"Note: {state['filter_notice']}\n\n{answer}"
    return {"answer": answer}


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
    if state.get("filter_fallback") and state.get("filter_notice"):
        answer = f"Note: {state['filter_notice']}\n\n{answer}"
    return {"answer": answer, "resolved_model": resolved_model}


def route_after_evidence_check(state: PDFQAState) -> str:
    if state.get("evidence_sufficient", False):
        return "generate_answer"
    # Policymaker mode is always document-grounded and must stop when evidence is weak.
    if _response_mode(state) == "policymaker":
        return "insufficient_evidence"
    # Researcher Open Discussion may continue without selected-document evidence.
    if _answer_mode(state) == "chat":
        return "generate_answer"
    return "insufficient_evidence"
