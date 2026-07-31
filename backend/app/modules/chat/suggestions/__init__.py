"""Follow-up question suggestions.

After each answer, propose a few next questions the user might ask (Approach A:
LLM proposes from the answer + retrieved context), then validate each candidate
against the corpus with the existing evidence gate (Approach D) so we never
suggest a question the selected documents cannot actually answer.
"""
