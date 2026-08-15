from __future__ import annotations

from app.modules.chat.domain.modes import ChatExecutionProfile
from app.modules.chat.rag.agent import tools as agent_tools
from app.modules.chat.rag.agent.policy import tools_for
from app.modules.retrieval.contracts import EvidenceDecision, RetrievalResult


def _tool_names(profile: ChatExecutionProfile) -> set[str]:
    return {
        tool.name
        for tool in tools_for(
            False,
            "chat",
            limits={tool.name: 10 for tool in agent_tools.ALL_TOOLS},
            source_policy=profile.source_policy,
        )
    }


def test_output_format_cannot_expand_selected_source_permissions() -> None:
    adaptive = ChatExecutionProfile("research", "selected_only", "adaptive")
    policy_brief = ChatExecutionProfile("research", "selected_only", "policy_brief")

    expected = {"search_internal_documents", "prepare_final_answer"}
    assert _tool_names(adaptive) == expected
    assert _tool_names(policy_brief) == expected


def test_source_policy_controls_escalation_tools() -> None:
    selected = ChatExecutionProfile("research", "selected_only", "adaptive")
    library = ChatExecutionProfile("research", "library_allowed", "adaptive")
    web = ChatExecutionProfile("research", "web_with_approval", "adaptive")

    assert "search_full_corpus" not in _tool_names(selected)
    assert "search_full_corpus" in _tool_names(library)
    assert "search_web" not in _tool_names(library)
    assert "search_web" in _tool_names(web)


def test_legacy_tool_adapter_preserves_capability_result(monkeypatch) -> None:
    expected = RetrievalResult(
        chunks=({"text": "Evidence", "document_id": "doc-1"},),
        citations=({"document_id": "doc-1", "quote": "Evidence"},),
        evidence=EvidenceDecision(True, "supported"),
        context="Evidence",
        filter_applied=True,
    )

    class StubCapability:
        def search(self, request):
            return expected

    monkeypatch.setattr(agent_tools, "policy_search_capability", StubCapability())

    state = agent_tools._run_retrieval_pipeline(
        "question",
        ["doc-1"],
        top_k=8,
        include_restricted=False,
    )

    assert state == expected.as_state()
