from langgraph.graph import END, START, StateGraph

from app.modules.chat.rag.graph.nodes import (
    generate_answer_node,
    load_documents_node,
    retrieve_context_node,
)
from app.modules.chat.rag.graph.state import PDFQAState


def build_pdf_qa_graph():
    """Compile the PDF question-answering workflow."""
    builder = StateGraph(PDFQAState)

    builder.add_node("load_documents", load_documents_node)
    builder.add_node("retrieve_context", retrieve_context_node)
    builder.add_node("generate_answer", generate_answer_node)

    builder.add_edge(START, "load_documents")
    builder.add_edge("load_documents", "retrieve_context")
    builder.add_edge("retrieve_context", "generate_answer")
    builder.add_edge("generate_answer", END)

    return builder.compile()


pdf_qa_graph = build_pdf_qa_graph()


def run_pdf_qa(
    question: str,
    document_ids: list[str] | None = None,
    filenames: list[str] | None = None,
    model: str | None = None,
    top_k: int = 8,
    include_restricted: bool = False,
) -> dict:
    """Invoke the compiled graph and return its final state."""
    return pdf_qa_graph.invoke(
        {
            "question": question,
            "document_ids": document_ids or [],
            "filenames": filenames or [],
            "model": model,
            "top_k": top_k,
            "include_restricted": include_restricted,
        }
    )
