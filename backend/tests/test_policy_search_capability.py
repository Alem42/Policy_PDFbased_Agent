import ast
from pathlib import Path

from app.modules.chat.capabilities import PolicySearchCapability, PolicySearchRequest
from app.modules.retrieval.contracts import EvidenceDecision, MetadataFilters, RetrievalResult


class RecordingRetriever:
    def __init__(self, result: RetrievalResult) -> None:
        self.result = result
        self.requests = []

    def retrieve(self, request):
        self.requests.append(request)
        return self.result


def test_selected_policy_search_translates_to_retrieval_contract() -> None:
    expected = RetrievalResult(evidence=EvidenceDecision(True, "supported"))
    retriever = RecordingRetriever(expected)
    capability = PolicySearchCapability(retriever)
    filters = MetadataFilters(country_regions=("Australia",), freshness_requested=True)

    result = capability.search(
        PolicySearchRequest(
            query="What does the policy require?",
            scope="selected",
            identifiers=("doc-1", "doc-2"),
            top_k=7,
            include_restricted=True,
            metadata_filters=filters,
        )
    )

    assert result is expected
    request = retriever.requests[0]
    assert request.question == "What does the policy require?"
    assert request.scope == "selected"
    assert request.identifiers == ("doc-1", "doc-2")
    assert request.top_k == 7
    assert request.include_restricted is True
    assert request.metadata_filters is filters


def test_library_policy_search_translates_to_full_corpus_scope() -> None:
    retriever = RecordingRetriever(RetrievalResult())
    capability = PolicySearchCapability(retriever)

    capability.search(PolicySearchRequest(query="carbon policy", scope="library"))

    assert retriever.requests[0].scope == "full_corpus"


def test_capability_package_has_no_langgraph_dependency() -> None:
    capability_root = Path(__file__).parents[1] / "app/modules/chat/capabilities"
    imported_modules: set[str] = set()
    for path in capability_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    assert not any(module.startswith("langgraph") for module in imported_modules)
