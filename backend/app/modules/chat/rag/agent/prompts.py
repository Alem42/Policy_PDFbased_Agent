from __future__ import annotations

from app.modules.chat.rag.graph.state import AnswerMode, ResponseMode
from app.modules.chat.rag.prompts import (
    ANALYSIS_BOUNDARY_PROMPT,
    BASE_SYSTEM_PROMPT,
    CHAT_BOUNDARY_PROMPT,
    POLICYMAKER_BASE_SYSTEM_PROMPT,
    POLICYMAKER_BOUNDARY_PROMPT,
    POLICYMAKER_STYLE_PROMPT,
    RESEARCHER_STRUCTURE_PROMPT,
    RESEARCHER_STYLE_PROMPT,
    STUDENT_STRUCTURE_PROMPT,
    STUDENT_STYLE_PROMPT,
)

# The decision procedure itself (2.1/2.3 of the product spec): a strategy for
# the LLM to follow inside the tool-calling loop, not a hardcoded Python
# router. Only the evidence-sufficiency GATE is deterministic code (reused
# from evidence.py via the tools); which tool to call next is always the
# model's call.
AGENT_STRATEGY_PROMPT = """Tools and strategy:
You answer by calling tools in a loop, then writing a final answer. Follow
this order and stop as soon as you have enough evidence — don't call tools
you don't need:

1. search_internal_documents — ALWAYS call this first.
   - If evidence_sufficient=true, you very likely have what you need: write
     the answer now, citing the returned sources. Do not search further just
     because more sources might exist.
2. If evidence_sufficient=false: call search_full_corpus (the rest of the
   shared library, not just this conversation's selected documents).
   - If that returns evidence_sufficient=true, answer from it, citing its
     sources.
3. If still insufficient, decide whether the user's own message already
   asked you to search the web (phrases like "search the web", "look it up
   online", "check online"). If they did, skip straight to search_web.
   Otherwise call ask_user to confirm whether to search the web — do not
   search the web on your own initiative without either the user's explicit
   request or their confirmation.
4. If confirmed (or already requested): call search_web.
   - If evidence_sufficient=true, you may answer using those results,
     citing them as web sources.
5. import_web_page (admin users only, when the tool is available to you):
   only call this if the user explicitly asks to save/import a specific web
   page into the knowledge base. It is a separate, permanent action from
   search_web and asks its own confirmation — never call it just because you
   already ran search_web.
6. If none of the above produced sufficient evidence, say plainly that you
   could not find enough information — do not guess or fill the gap from
   unsupported general knowledge (unless the mode's knowledge boundary below
   explicitly allows drawing on general knowledge).

Citations: cite sources inline using numbered markers [1], [2], matching the
order sources were returned to you across all tool calls in this
conversation turn. Use exactly one number per marker, placed right after the
sentence that uses that source, before punctuation. Do not invent a source
number that wasn't actually returned by a tool.
"""


def get_agent_system_prompt(
    response_mode: ResponseMode = "researcher",
    answer_mode: AnswerMode = "analysis",
    *,
    is_admin: bool = False,
) -> str:
    if response_mode == "policymaker":
        parts = [
            POLICYMAKER_BASE_SYSTEM_PROMPT,
            POLICYMAKER_STYLE_PROMPT,
            POLICYMAKER_BOUNDARY_PROMPT,
            AGENT_STRATEGY_PROMPT,
        ]
    else:
        style = STUDENT_STYLE_PROMPT if response_mode == "student" else RESEARCHER_STYLE_PROMPT
        boundary = CHAT_BOUNDARY_PROMPT if answer_mode == "chat" else ANALYSIS_BOUNDARY_PROMPT
        parts = [BASE_SYSTEM_PROMPT, style]
        if answer_mode == "analysis":
            structure = (
                STUDENT_STRUCTURE_PROMPT
                if response_mode == "student"
                else RESEARCHER_STRUCTURE_PROMPT
            )
            parts.append(structure)
        parts.extend([boundary, AGENT_STRATEGY_PROMPT])

    if not is_admin:
        parts.append(
            "You do not have the import_web_page tool available — you cannot "
            "import pages into the knowledge base. Do not claim you imported "
            "anything."
        )
    return "\n".join(part.strip() for part in parts if part.strip())
