"""Admin-tunable per-tool call budgets for the ReAct agent.

Every tool the agent can call (search_internal_documents, search_full_corpus,
ask_user, search_web, import_web_page, prepare_final_answer) has a per-turn
call budget. Once a tool hits its budget, chat.rag.agent.policy.tools_for
stops offering it to the LLM. This module makes those budgets admin-tunable
instead of hardcoded, following the same one-JSON-row pattern as
reranking/embedding/suggestion settings.
"""
