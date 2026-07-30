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

# Document Analysis mode only has the selected-document search and the final
# answer hand-off (see graph.py::_tools_for). No full-corpus/web escalation
# tools exist in this mode.
ANALYSIS_STRATEGY_PROMPT = (
    """Tools and strategy (Document Analysis mode):
You must act through tools; never write the user-facing answer directly.
1. Call search_internal_documents once for the user's question.
2. Then call prepare_final_answer:
   - If evidence_sufficient=true, give it a concise plan for an answer using
     only the returned sources and their exact citation numbers.
   - If evidence_sufficient=false, give it a plan to explain plainly that the
     selected documents do not contain enough information. Do not guess,
     offer web/full-library search (not available in this mode), or fall back
     on general knowledge.
prepare_final_answer is only a hand-off. Do not put the answer itself in its
arguments; the final writer will generate and stream it.

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
You must act through tools on every turn; never write a user-facing answer
or question directly. Call tools in a loop, and stop as soon as you have
enough evidence. The sequence below is a strong default, not a fixed
script — use judgement about what the question actually needs, subject to
one hard rule: never call search_web on your own initiative without either
the user's explicit request or their confirmation via ask_user.

The evidence_sufficient field is a retrieval heuristic, not an instruction
you must obey blindly. Inspect the returned titles and excerpts against the
user's actual question. If a critical requested subject, country,
organisation, or time period is missing, treat the evidence as insufficient
even when evidence_sufficient=true.

Tool call budgets apply only to the current user question. Every new user
question starts with fresh budgets. Never infer that a tool is unavailable
now because an earlier question in this chat exhausted its budget.

For every search or ask_user tool call, include `decision_reason`: one short,
user-readable sentence explaining why that action is the appropriate next
step. Do not include private chain-of-thought or a long reasoning transcript.

- If the user's own message already explicitly asked you to search the web
  (phrases like "search the web", "look it up online", "check online"), you
  do not need to try search_internal_documents/search_full_corpus first, and
  you do not need ask_user either — the user's request is itself the
  authorisation. Go straight to search_web.
- Otherwise, start with search_internal_documents.
  - If evidence_sufficient=true, you very likely have what you need: call
    prepare_final_answer with a concise writing plan and the exact citation
    numbers. Do not search further just because more sources might exist.
  - If evidence_sufficient=false, call search_full_corpus (the rest of the
    shared library, not just this conversation's selected documents).
    - If that returns evidence_sufficient=true, call prepare_final_answer
      with a plan grounded in those sources and their exact citation
      numbers, but only if the excerpts really cover the user's critical
      constraints.
    - You may use search_full_corpus at most twice to materially reformulate
      the query. If it is no longer offered, choose ask_user, search_web
      when already authorised, or prepare_final_answer; never try to call
      it again.
  - If still insufficient, call the ask_user TOOL to confirm whether to
    search the web.
- Once confirmed (or already requested): call search_web.
  - If evidence_sufficient=true, call prepare_final_answer with a plan that
    uses those results as web sources.
- import_web_page (admin users only, when the tool is available to you):
  only call this if the user explicitly asks to save/import a specific web
  page into the knowledge base. It is a separate, permanent action from
  search_web and asks its own confirmation via that same tool — never call
  it just because you already ran search_web.
- If none of the above produced sufficient evidence, you may still answer
  from your own general knowledge per the Open Discussion boundary below,
  clearly labelled as such, by calling prepare_final_answer with that plan.
  But if you haven't already asked whether to search the web, call ask_user
  first rather than putting an offer in the final answer.

CRITICAL: any time you want to ask the user whether to search the web — for
insufficient evidence, or as a follow-up offer after already answering from
what you found — you MUST call the ask_user tool to ask it. Never write that
question as plain text in your answer: the chat interface can only turn an
actual ask_user tool call into an actionable prompt the user can respond to;
a question written as prose is not clickable and just stalls the
conversation.

If retrieved results are topically similar but fail a critical constraint
from the user's question, ask_user is valid even if a retrieval tool reported
evidence_sufficient=true.

When the research loop is complete, your final action MUST be
prepare_final_answer. It is a hand-off to a separate streaming writer, so
give it only a concise answer plan and exact citation numbers — never the
full prose answer.

"""
    + CITATION_NUMBERING_RULE
)

FINAL_ANSWER_WRITER_PROMPT = """Final answer phase:
The ReAct research loop is complete. The conversation contains the search
tool results and ends with a prepare_final_answer tool result containing the
approved answer plan and citation numbers.

Write the final user-facing answer now. Follow the requested persona, style,
knowledge boundary, and the approved plan. Use only exact citation `number`
values present in tool results; never renumber or invent citations.

Return only the answer body. Do not call or describe tools, expose the
research trace, ask whether to search the web, or offer an action that would
require another user confirmation. Those decisions belong to the completed
ReAct phase.
"""


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


def get_final_answer_system_prompt(
    response_mode: ResponseMode = "researcher",
    answer_mode: AnswerMode = "analysis",
) -> str:
    """Prompt for the tool-free writer that runs after prepare_final_answer."""
    if response_mode == "policymaker":
        parts = [
            POLICYMAKER_BASE_SYSTEM_PROMPT,
            POLICYMAKER_STYLE_PROMPT,
            POLICYMAKER_BOUNDARY_PROMPT,
            FINAL_ANSWER_WRITER_PROMPT,
            CITATION_NUMBERING_RULE,
        ]
        return "\n".join(part.strip() for part in parts if part.strip())

    style = STUDENT_STYLE_PROMPT if response_mode == "student" else RESEARCHER_STYLE_PROMPT
    is_chat_mode = answer_mode == "chat"
    boundary = CHAT_BOUNDARY_PROMPT if is_chat_mode else ANALYSIS_BOUNDARY_PROMPT
    parts = [BASE_SYSTEM_PROMPT, style]
    if not is_chat_mode:
        structure = (
            STUDENT_STRUCTURE_PROMPT if response_mode == "student" else RESEARCHER_STRUCTURE_PROMPT
        )
        parts.append(structure)
    parts.extend([boundary, FINAL_ANSWER_WRITER_PROMPT, CITATION_NUMBERING_RULE])
    return "\n".join(part.strip() for part in parts if part.strip())
