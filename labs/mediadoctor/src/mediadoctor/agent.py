"""The seed agent: retrieve, then one Claude call."""

from __future__ import annotations

from typing import Any

from evalkit import LLM, load_models, text_of
from mediadoctor.kb import KnowledgeBase, load_kb
from mediadoctor.prompts import PROMPTS

AGENT_NAMESPACE = "mediadoctor-seed"


def format_context(docs) -> str:
    return "\n\n".join(f"[kb:{d.id}]\n{d.text}" for d in docs)


def build_request(
    query: str, prompt_version: str = "v1", kb: KnowledgeBase | None = None
) -> dict[str, Any]:
    """Build the exact Messages API request. Its SHA-256 is the fixture key."""
    kb = kb or load_kb()
    role = load_models()["agent"]
    context = format_context(kb.search(query, k=2))
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": PROMPTS[prompt_version],
        "messages": [
            {
                "role": "user",
                "content": f"Knowledge base context:\n\n{context}\n\nQuestion: {query}",
            }
        ],
    }


def answer(
    query: str,
    prompt_version: str = "v1",
    llm: LLM | None = None,
    kb: KnowledgeBase | None = None,
) -> str:
    llm = llm or LLM(namespace=AGENT_NAMESPACE)
    return text_of(llm.create(**build_request(query, prompt_version, kb)))
