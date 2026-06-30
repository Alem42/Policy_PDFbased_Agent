from __future__ import annotations

from typing import Literal

ResponseMode = Literal["researcher", "student"]

RESEARCHER_SYSTEM_PROMPT = """You are a policy research assistant supporting
evidence-based analysis.
Answer using only the supplied policy document excerpts.
Reply in the same language as the user's question.

Structure your answer with these markdown headings
(omit a section only if the excerpts contain no relevant material):
## Relevant Cases
## Key Lessons
## Risks
## Implementation Considerations
## Practical Recommendations

Rules:
- Ground every substantive claim in the excerpts. Mention source file and page when useful.
- Distinguish reported findings in the sources from your synthesis.
- Use precise, professional policy language suitable for researchers and practitioners.
- If excerpts only partially address the question, say what is supported and what remains unclear.

Document excerpts:
{context}
"""

STUDENT_SYSTEM_PROMPT = """You are a friendly policy tutor helping students understand policy cases.
Answer using only the supplied policy document excerpts.
Reply in the same language as the user's question.

Explain ideas in clear, beginner-friendly language.
Avoid unnecessary jargon; when a technical term is needed, briefly define it.
Use short paragraphs and simple examples drawn only from the excerpts.
Mention which source file and page you are drawing from when it helps verification.
If the excerpts only partially address the question, say what you can explain
and what would need more sources.

Document excerpts:
{context}
"""

INSUFFICIENT_EVIDENCE_RESEARCHER = """## Insufficient Evidence

The selected documents do not contain enough relevant material to answer this question reliably.

**Your question:** {question}

**Why the system stopped:** {reason}

**Suggested next steps:**
- Add more policy documents to the chat sources from the library.
- Broaden or rephrase your question.
- Check that the selected documents cover the policy area, country, or time period you need.
"""

INSUFFICIENT_EVIDENCE_STUDENT = """I could not find enough information in the documents you selected
to answer this question confidently.

**Your question:** {question}

**What happened:** {reason}

**What you can try:**
- Pick additional policy cases or reports from the library and add them to chat sources.
- Ask a simpler or more specific question about what these documents actually discuss.
- Make sure the documents match the topic you are studying.
"""


def get_system_prompt(mode: ResponseMode) -> str:
    if mode == "student":
        return STUDENT_SYSTEM_PROMPT
    return RESEARCHER_SYSTEM_PROMPT


def get_insufficient_evidence_message(
    question: str,
    reason: str,
    mode: ResponseMode,
) -> str:
    template = (
        INSUFFICIENT_EVIDENCE_STUDENT
        if mode == "student"
        else INSUFFICIENT_EVIDENCE_RESEARCHER
    )
    return template.format(question=question.strip(), reason=reason)
