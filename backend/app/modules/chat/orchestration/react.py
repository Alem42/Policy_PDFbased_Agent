from app.modules.chat.rag.agent.graph import get_agent_graph


class ReactOrchestrator:
    """Access the persisted multi-step tool-calling graph.

    The compiled graph is intentionally exposed through a facade so HTTP,
    CLI, and future background-job adapters do not depend on its package path.
    Use a stable conversation/session id as LangGraph ``thread_id``.
    """

    def graph(self):
        return get_agent_graph()


react_orchestrator = ReactOrchestrator()
