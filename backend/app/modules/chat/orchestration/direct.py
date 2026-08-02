from app.modules.chat.rag.graph.workflow import run_pdf_qa, run_retrieval


class DirectOrchestrator:
    """Fixed one-pass retrieval/evidence/answer black box.

    ``retrieve`` stops before the LLM writer and is suitable for SSE callers.
    ``answer`` runs the complete synchronous workflow. Call both from a worker
    thread when used by an async application.
    """

    def retrieve(self, **kwargs) -> dict:
        return run_retrieval(**kwargs)

    def answer(self, **kwargs) -> dict:
        return run_pdf_qa(**kwargs)


direct_orchestrator = DirectOrchestrator()
