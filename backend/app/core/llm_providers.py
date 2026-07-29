from __future__ import annotations

DEFAULT_PROVIDER = "deepseek"


def get_provider_config(provider: str | None) -> dict:
    """Build one chat-provider config exclusively from the endpoint catalog."""
    from app.modules.catalog.service import get_catalog

    provider_id = provider or DEFAULT_PROVIDER
    catalog = get_catalog("chat")
    entries = [
        entry for entry in catalog["entries"] if entry["provider"] == provider_id
    ]
    if not entries:
        raise ValueError(
            f"Provider '{provider_id}' has no chat endpoint in the model catalog."
        )

    provider_row = next(
        (item for item in catalog.get("providers", []) if item["id"] == provider_id),
        None,
    )
    base_url = (provider_row or {}).get("base_url") or entries[0]["base_url"]
    if not base_url:
        raise ValueError(f"Provider '{provider_id}' has no chat base URL.")

    return {
        "label": (provider_row or {}).get("label", entries[0]["provider_label"]),
        "base_url": base_url,
        "default_model": entries[0]["model"],
        # The application consumes final answer text only. DeepSeek V4 supports
        # thinking and non-thinking modes, so disable thinking for this RAG path.
        "extra_body": (
            {"thinking": {"type": "disabled"}}
            if provider_id == "deepseek"
            else {}
        ),
    }


def resolve_provider_and_model(
    model: str | None,
    default_provider: str,
) -> tuple[str, str | None]:
    """Resolve an optional ``provider/model`` chat selection."""
    if model and "/" in model:
        provider, _, model_id = model.partition("/")
        get_provider_config(provider)  # validates that the provider supports chat
        return provider, model_id or None
    return default_provider, model
