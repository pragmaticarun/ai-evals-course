"""Knowledge base loading and a deliberately naive keyword retriever.

Module 7 replaces this with a measured retriever; keeping it naive here gives the
later modules real retrieval failures to find.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from evalkit import repo_root

_STOP = frozenset(
    "a an and are as at be but by can do does for from how i in is it my of on or our "
    "should so that the their then there this to we what when where which why will with "
    "you your any after over about every some only one".split()
)


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOP and len(t) > 1]


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    text: str


@dataclass
class KnowledgeBase:
    docs: dict[str, Doc]

    def search(self, query: str, k: int = 2) -> list[Doc]:
        q = set(tokens(query))
        scored = []
        for doc in self.docs.values():
            title_hits = len(q & set(tokens(doc.title)))
            body_hits = len(q & set(tokens(doc.text)))
            score = 3 * title_hits + body_hits
            scored.append((score, doc.id, doc))
        scored.sort(key=lambda s: (-s[0], s[1]))  # deterministic tie-break on id
        return [d for score, _, d in scored[:k] if score > 0]


def load_kb(directory: Path | None = None) -> KnowledgeBase:
    directory = directory or repo_root() / "data" / "kb"
    docs = {}
    for path in sorted(directory.glob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8").strip()
        first = text.splitlines()[0]
        title = first.removeprefix("# ").strip()
        docs[path.stem] = Doc(id=path.stem, title=title, text=text)
    return KnowledgeBase(docs)
