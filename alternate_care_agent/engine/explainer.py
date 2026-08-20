"""
The ONLY LLM-backed step in this agent. Everything upstream (classification,
provider discovery, ranking) is deterministic and rule-based on purpose —
per your reference doc's own recommendation (Section 26/31): don't put the
core care decision behind an LLM call, use the LLM only to turn a
structured decision into plain-language explanation.

This is what actually justifies LangChain in this codebase: a prompt
template + structured parsing around a real generation task, not
LangChain wrapping code that doesn't need an LLM at all.
"""

from __future__ import annotations
from typing import Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from models.schemas import CareDecision

# _PROMPT is pure data — safe to build at module level (no network, no auth).
_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are explaining a non-emergency care routing decision to a "
            "patient in plain, reassuring language. Do not add clinical "
            "advice beyond what's given. Do not mention rule IDs, priority "
            "numbers, or internal system details. 2-3 sentences max. If "
            "status is not DOCUMENT_SUPPORTED, don't state the recommendation "
            "with false certainty — use softer language like 'likely' or "
            "'a reasonable next step'.",
        ),
        (
            "human",
            "destination: {destination}\n"
            "specialty: {specialty}\n"
            "status: {status}\n"
            "clinical_reasoning: {explanation}",
        ),
    ]
)

# Lazy-initialised so importing this module never triggers a Google SDK
# initialisation, network call, or auth check.  The chain is built on first
# use of explain_decision(); tests that mock explain_decision() are therefore
# never affected by this module-level state.
#
# Runtime configuration:
#   GOOGLE_API_KEY=<your_key>   — required when explain_decision() is called.
#   Get a free API key (no credit card) at https://aistudio.google.com/apikey
#
# Model choice / temperature are the only things you should need to tune here.
_chain: Any = None


def _get_chain() -> Any:
    """Return the compiled LangChain chain, creating it on first call."""
    global _chain
    if _chain is None:
        _llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.3,
            max_tokens=200,
        )
        _chain = _PROMPT | _llm
    return _chain


def explain_decision(decision: CareDecision) -> str:
    result = _get_chain().invoke(
        {
            "destination": decision.destination,
            "specialty": decision.specialty or "n/a",
            "status": decision.status,
            "explanation": decision.explanation,
        }
    )
    return result.content
