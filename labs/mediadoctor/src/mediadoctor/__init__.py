"""MediaDoctor: the course's running agent.

Module 1 ships a deliberately simple "seed" version: naive keyword retrieval over the
knowledge base plus a single Claude call. Module 2 turns it into a traced, tool-using agent.
"""

from mediadoctor.agent import AGENT_NAMESPACE, answer, build_request
from mediadoctor.kb import KnowledgeBase, load_kb
from mediadoctor.prompts import PROMPTS

__all__ = ["AGENT_NAMESPACE", "PROMPTS", "KnowledgeBase", "answer", "build_request", "load_kb"]
