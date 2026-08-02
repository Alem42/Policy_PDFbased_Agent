from app.core.config import get_settings


def format_context(items: list[dict]) -> tuple[str, bool]:
    """Format retrieved pages/chunks within the configured context limit."""

    sections: list[str] = []
    used_characters = 0
    truncated = False
    for index, item in enumerate(items):
        text = item.get("text", "")
        if not text:
            continue
        page_num = item.get("page") or item.get("page_start") or "?"
        filename = item.get("file") or item.get("doc_title") or "Unknown document"
        section = f"[{index + 1}] {filename}, page {page_num}\n{text}"
        remaining = get_settings().max_context_characters - used_characters
        if remaining <= 0:
            truncated = True
            break
        if len(section) > remaining:
            sections.append(section[:remaining])
            truncated = True
            break
        sections.append(section)
        used_characters += len(section)
    return "\n\n---\n\n".join(sections), truncated
