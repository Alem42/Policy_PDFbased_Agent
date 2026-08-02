from langchain_core.messages import AIMessage, HumanMessage


def aggregate_turn_token_usage(messages: list) -> dict:
    """Sum provider-reported usage for AI messages after the latest user turn.

    Missing usage metadata is ignored because some providers and synthetic
    LangGraph messages do not report tokens. An empty dictionary means no
    trustworthy usage was available; values are never estimated here.
    """

    latest_human_index = next(
        (
            index
            for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        0,
    )
    prompt_tokens = completion_tokens = total_tokens = 0
    found = False
    for message in messages[latest_human_index:]:
        usage = getattr(message, "usage_metadata", None) if isinstance(message, AIMessage) else None
        if not usage:
            continue
        found = True
        prompt_tokens += usage.get("input_tokens") or 0
        completion_tokens += usage.get("output_tokens") or 0
        total_tokens += usage.get("total_tokens") or 0
    if not found:
        return {}
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
