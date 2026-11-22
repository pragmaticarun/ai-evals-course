"""Chunking and retrieval over the second-edition knowledge base (module 7).

Two chunkers and two retrievers, so retrieval can be measured on its own:

    fixed_chunks     windows of N words over the raw document text; headings land wherever they fall
    section_chunks   one chunk per `##` section, prefixed with the document and section titles

    keyword          count of distinct query words in the chunk (the module 1 retriever, minus titles)
    bm25             Okapi BM25 over lightly stemmed words (decoders -> decoder, crashes -> crash)

Relevance is labelled per section (`doc#n`). A chunk is credited to the section it overlaps most,
so both chunkers are scored against the same labels.
"""

from __future__ import annotations

import csv
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from evalkit import repo_root
from mediadoctor.kb import tokens

CHUNKERS = ("fixed", "section")
RETRIEVERS = ("keyword", "bm25")
FIXED_WORDS = 40


@dataclass(frozen=True)
class Section:
    id: str  # doc#n
    doc: str
    title: str  # document title
    heading: str
    text: str
    start: int  # word offsets in the document's raw word list
    end: int


@dataclass(frozen=True)
class Chunk:
    id: str
    doc: str
    text: str
    section: str  # the section this chunk overlaps most


def kb2_dir() -> Path:
    return repo_root() / "data" / "kb_v2"


@cache
def corpus() -> dict[str, list[str]]:
    """{doc id: raw words}, in file order."""
    return {
        p.stem: p.read_text(encoding="utf-8").split()
        for p in sorted(kb2_dir().glob("*.md"))
        if p.name != "README.md"
    }


@cache
def sections() -> dict[str, Section]:
    out = {}
    for p in sorted(kb2_dir().glob("*.md")):
        if p.name == "README.md":
            continue
        title, pos, n = "", 0, 0
        current: dict | None = None
        for line in p.read_text(encoding="utf-8").splitlines():
            words = line.split()
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("## "):
                if current:
                    out[current["id"]] = Section(**current, end=pos)
                n += 1
                current = {"id": f"{p.stem}#{n}", "doc": p.stem, "title": title,
                           "heading": line[3:].strip(), "text": "", "start": pos}  # fmt: skip
            elif current is not None and words:
                current["text"] = (current["text"] + " " + line.strip()).strip()
            pos += len(words)
        if current:
            out[current["id"]] = Section(**current, end=pos)
    return out


def _primary_section(doc: str, start: int, end: int) -> str:
    best, best_overlap = "", -1
    for s in sections().values():
        if s.doc != doc:
            continue
        overlap = min(end, s.end) - max(start, s.start)
        if overlap > best_overlap:
            best, best_overlap = s.id, overlap
    return best


@cache
def chunks(chunker: str) -> tuple[Chunk, ...]:
    out = []
    if chunker == "fixed":
        for doc, words in corpus().items():
            for i in range(0, len(words), FIXED_WORDS):
                end = min(i + FIXED_WORDS, len(words))
                out.append(
                    Chunk(f"{doc}@{i}", doc, " ".join(words[i:end]), _primary_section(doc, i, end))
                )
    elif chunker == "section":
        for s in sections().values():
            out.append(Chunk(s.id, s.doc, f"{s.title}: {s.heading}. {s.text}", s.id))
    else:
        raise ValueError(f"unknown chunker {chunker!r}")
    return tuple(out)


def stem(word: str) -> str:
    """A deliberately small suffix stripper: enough to match plurals and simple verb forms."""
    for suffix, keep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3 and not word.endswith("ss"):
            return word[: -len(suffix)] + keep
    return word


def stems(text: str) -> list[str]:
    return [stem(t) for t in tokens(text)]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.docs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avg = sum(self.lens) / len(self.lens)
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.k1, self.b = k1, b

    def score(self, query: list[str], i: int) -> float:
        tf, s = self.docs[i], 0.0
        for t in set(query):
            if t not in tf:
                continue
            f = tf[t]
            s += (
                self.idf[t]
                * f
                * (self.k1 + 1)
                / (f + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
            )
        return s


@cache
def _bm25(chunker: str) -> BM25:
    return BM25([stems(c.text) for c in chunks(chunker)])


def search(query: str, chunker: str, retriever: str, k: int = 5) -> list[Chunk]:
    cs = chunks(chunker)
    q = tokens(query)
    if retriever == "keyword":
        qs = set(q)
        scores = [len(qs & set(tokens(c.text))) for c in cs]
    elif retriever == "bm25":
        bm = _bm25(chunker)
        qs = [stem(t) for t in q]
        scores = [bm.score(qs, i) for i in range(len(cs))]
    else:
        raise ValueError(f"unknown retriever {retriever!r}")
    order = sorted(range(len(cs)), key=lambda i: (-scores[i], cs[i].id))
    return [cs[i] for i in order[:k] if scores[i] > 0]


@dataclass(frozen=True)
class Query:
    id: str
    topic: str
    text: str
    grades: dict[str, int]  # section id -> 2 (answers it) or 1 (related)

    @property
    def relevant(self) -> set[str]:
        return {s for s, g in self.grades.items() if g > 0}

    @property
    def answering(self) -> set[str]:
        return {s for s, g in self.grades.items() if g >= 2}


def relevance_path() -> Path:
    return repo_root() / "data" / "labels" / "module07_relevance.csv"


@cache
def queries() -> tuple[Query, ...]:
    out = []
    with relevance_path().open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            grades = {}
            for part in r["relevant"].split(";"):
                sid, g = part.rsplit(":", 1)
                grades[sid] = int(g)
            out.append(Query(r["query_id"], r["topic"], r["query"], grades))
    unknown = {s for q in out for s in q.grades} - set(sections())
    if unknown:
        raise ValueError(f"relevance labels name unknown sections: {sorted(unknown)}")
    return tuple(out)


CITE = re.compile(r"\[kb:([^\]\s]+)\]")  # any cited id, so a malformed or invented one is caught


# --- Generation -------------------------------------------------------------------------------------

RAG_SYSTEM = """\
You are MediaDoctor, an assistant for Android and multimedia engineers. Answer the question using
only the knowledge base passages provided. Cite every passage you rely on as [kb:<id>].
If the passages do not answer the question, say so and do not guess.

Reply in exactly this format:
Answer: <two or three sentences>
Sources: <the [kb:<id>] tags you used, or none>"""

SYSTEMS = {"baseline": ("fixed", "keyword"), "improved": ("section", "bm25")}
CONTEXT_K = 3


def context_for(query: str, system: str) -> list[Chunk]:
    chunker, retriever = SYSTEMS[system]
    return search(query, chunker, retriever, CONTEXT_K)


def format_context(cs: list[Chunk]) -> str:
    return "\n\n".join(f"[kb:{c.id}]\n{c.text}" for c in cs) or "(no passages found)"


def rag_request(query: str, cs: list[Chunk]) -> dict:
    from evalkit import load_models

    role = load_models()["agent"]
    return {
        "model": role.model,
        "max_tokens": role.max_tokens,
        "system": RAG_SYSTEM,
        "messages": [
            {
                "role": "user",
                "content": f"Knowledge base passages:\n\n{format_context(cs)}\n\nQuestion: {query}",
            }
        ],
    }
