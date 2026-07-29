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

# Shared citation rule, reused by both strategy prompts below. Every tool
# result carries an explicit `number` field per citation (see
# agent/tools.py::_number_citations) — the model has no way to know the
# running [N] total across earlier tool calls in the turn on its own, and
# letting it guess is exactly what caused citation markers to point at the
# wrong source in testing (a web-search citation landing on an unrelated PDF
# page number instead).
CITATION_NUMBERING_RULE = """Citations: cite sources inline using numbered markers [1], [2], using
EXACTLY the `number` field given in each tool result for that source —
never renumber, recount, or guess. If the same source is returned again
with the same number, reuse that number. Use exactly one number per marker,
placed right after the sentence that uses that source, before punctuation.
Do not invent a source number that wasn't actually given to you by a tool.
"""

# Document Analysis mode: only search_internal_documents is bound (see
# graph.py::_tools_for) -- no full-corpus/web escalation tools exist in this
# mode, so the strategy is just "search once, answer or refuse."
ANALYSIS_STRATEGY_PROMPT = (
    """Tools and strategy (Document Analysis mode):
You have exactly one tool: search_internal_documents. Call it once for the
user's question.
- If evidence_sufficient=true, answer using only the returned sources.
- If evidence_sufficient=false, say plainly that the selected documents
  don't contain enough information to answer this — do not guess, do not
  offer to search the web or the wider library (not available in this
  mode), and do not fall back on general knowledge.

"""
    + CITATION_NUMBERING_RULE
)

# The decision procedure itself (2.1/2.3 of the product spec): a strategy for
# the LLM to follow inside the tool-calling loop, not a hardcoded Python
# router. Only the evidence-sufficiency GATE is deterministic code (reused
# from evidence.py via the tools); which tool to call next is always the
# model's call. Only bound in Open Discussion mode (answer_mode == "chat") —
# Document Analysis mode uses ANALYSIS_STRATEGY_PROMPT above instead, since
# going beyond the selected documents (full corpus, web, general knowledge)
# is something only Open Discussion's knowledge boundary already permits.
AGENT_STRATEGY_PROMPT = (
    """Tools and strategy (Open Discussion mode):
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
   Otherwise call the ask_user TOOL to confirm whether to search the web —
   do not search the web on your own initiative without either the user's
   explicit request or their confirmation via that tool.
4. If confirmed (or already requested): call search_web.
   - If evidence_sufficient=true, you may answer using those results,
     citing them as web sources.
5. import_web_page (admin users only, when the tool is available to you):
   only call this if the user explicitly asks to save/import a specific web
   page into the knowledge base. It is a separate, permanent action from
   search_web and asks its own confirmation via that same tool — never call
   it just because you already ran search_web.
6. If none of the above produced sufficient evidence, you may still answer
   from your own general knowledge per the Open Discussion boundary below,
   clearly labelled as such — but if you haven't already asked (via
   ask_user) whether to search the web, offer that too.

CRITICAL: any time you want to ask the user whether to search the web — for
insufficient evidence, or as a follow-up offer after already answering from
what you found — you MUST call the ask_user tool to ask it. Never write that
question as plain text in your answer: the chat interface can only turn an
actual ask_user tool call into an actionable prompt the user can respond to;
a question written as prose is not clickable and just stalls the
conversation.

"""
    + CITATION_NUMBERING_RULE
)


def get_agent_system_prompt(
    response_mode: ResponseMode = "researcher",
    answer_mode: AnswerMode = "analysis",
    *,
    is_admin: bool = False,
) -> str:
    # Policymaker is always forced to answer_mode="analysis" upstream
    # (normalize_answer_mode) — strategy is hardcoded to match rather than
    # trusting the caller passed the already-normalized value.
    if response_mode == "policymaker":
        return "\n".join(
            part.strip()
            for part in [
                POLICYMAKER_BASE_SYSTEM_PROMPT,
                POLICYMAKER_STYLE_PROMPT,
                POLICYMAKER_BOUNDARY_PROMPT,
                ANALYSIS_STRATEGY_PROMPT,
            ]
            if part.strip()
        )

    style = STUDENT_STYLE_PROMPT if response_mode == "student" else RESEARCHER_STYLE_PROMPT
    is_chat_mode = answer_mode == "chat"
    boundary = CHAT_BOUNDARY_PROMPT if is_chat_mode else ANALYSIS_BOUNDARY_PROMPT
    strategy = AGENT_STRATEGY_PROMPT if is_chat_mode else ANALYSIS_STRATEGY_PROMPT
    parts = [BASE_SYSTEM_PROMPT, style]
    if not is_chat_mode:
        structure = (
            STUDENT_STRUCTURE_PROMPT if response_mode == "student" else RESEARCHER_STRUCTURE_PROMPT
        )
        parts.append(structure)
    parts.extend([boundary, strategy])

    if is_chat_mode and not is_admin:
        parts.append(
            "You do not have the import_web_page tool available — you cannot "
            "import pages into the knowledge base. Do not claim you imported "
            "anything."
        )
    return "\n".join(part.strip() for part in parts if part.strip())
