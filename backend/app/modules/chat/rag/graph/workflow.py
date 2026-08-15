from langgraph.graph import END, START, StateGraph

from app.modules.chat.rag.graph.nodes import (
    check_evidence_node,
    generate_answer_node,
    insufficient_evidence_node,
    load_documents_node,
    retrieve_context_node,
    route_after_evidence_check,
)
from app.modules.chat.rag.graph.state import (
    AnswerMode,
    PDFQAState,
    ResponseMode,
    normalize_answer_mode,
)
from app.modules.retrieval.contracts import MetadataFilters, RetrievalRequest
from app.modules.retrieval.service import retrieval_service


def build_pdf_qa_graph():
    """Compile the PDF question-answering workflow."""
    builder = StateGraph(PDFQAState)

    builder.add_node("load_documents", load_documents_node)
    builder.add_node("retrieve_context", retrieve_context_node)
    builder.add_node("check_evidence", check_evidence_node)
    builder.add_node("insufficient_evidence", insufficient_evidence_node)
    builder.add_node("generate_answer", generate_answer_node)

    builder.add_edge(START, "load_documents")
    builder.add_edge("load_documents", "retrieve_context")
    builder.add_edge("retrieve_context", "check_evidence")
    builder.add_conditional_edges(
        "check_evidence",
        route_after_evidence_check,
        {
            "generate_answer": "generate_answer",
            "insufficient_evidence": "insufficient_evidence",
        },
    )
    builder.add_edge("generate_answer", END)
    builder.add_edge("insufficient_evidence", END)

    return builder.compile()


pdf_qa_graph = build_pdf_qa_graph()


def run_retrieval(
    question: str,
    document_ids: list[str] | None = None,
    filenames: list[str] | None = None,
    model: str | None = None,
    response_mode: ResponseMode = "researcher",
    answer_mode: AnswerMode = "analysis",
    top_k: int = 8,
    include_restricted: bool = False,
    history: list[dict] | None = None,
    metadata_filters: dict | None = None,
    run_context: dict | None = None,
) -> dict:
    """Run load → retrieve → evidence-check and return the raw graph state.

    Stops before calling the LLM so the caller can stream generation separately.
    """
    effective_answer_mode = normalize_answer_mode(response_mode, answer_mode)
    state: PDFQAState = {
        "question": question,
        "document_ids": document_ids or [],
        "filenames": filenames or [],
        "model": model,
        "response_mode": response_mode,
        "answer_mode": effective_answer_mode,
        "top_k": top_k,
        "include_restricted": include_restricted,
        "metadata_filters": metadata_filters or {},
        "history": history or [],
        "run_context": run_context or {},
        "context": "",
        "truncated": False,
        "chunks": [],
        "raw_chunks": [],
        "citations": [],
        "pages": [],
        "used_vector_retrieval": False,
        "evidence_sufficient": False,
        "evidence_reason": None,
        "answer": "",
    }
    result = retrieval_service.retrieve(
        RetrievalRequest(
            question=question,
            scope="selected",
            identifiers=tuple(document_ids or filenames or []),
            top_k=top_k,
            include_restricted=include_restricted,
            metadata_filters=MetadataFilters.from_mapping(metadata_filters),
        )
    )
    state.update(result.as_state())
    return dict(state)


def run_pdf_qa(
    question: str,
    document_ids: list[str] | None = None,
    filenames: list[str] | None = None,
    model: str | None = None,
    response_mode: ResponseMode = "researcher",
    answer_mode: AnswerMode = "analysis",
    top_k: int = 8,
    include_restricted: bool = False,
    history: list[dict] | None = None,
    metadata_filters: dict | None = None,
    run_context: dict | None = None,
) -> dict:
    """Invoke the compiled graph and return its final state."""
    effective_answer_mode = normalize_answer_mode(response_mode, answer_mode)
    return pdf_qa_graph.invoke(
        {
            "question": question,
            "document_ids": document_ids or [],
            "filenames": filenames or [],
            "model": model,
            "response_mode": response_mode,
            "answer_mode": effective_answer_mode,
            "top_k": top_k,
            "include_restricted": include_restricted,
            "metadata_filters": metadata_filters or {},
            "history": history or [],
            "run_context": run_context or {},
        }
    )
