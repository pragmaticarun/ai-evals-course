"""Tool schemas for the module 2 agent (skeleton).

Module 1 does not call tools. Module 2 implements these and runs them in a Claude
tool-use loop, with each call traced. The schemas are here now so the shape of the
agent is visible from the start.
"""

from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "search_kb",
        "description": "Search the MediaDoctor knowledge base and return the best matching documents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ffprobe",
        "description": "Inspect a sample media file (streams, codecs, timestamps, container atoms).",
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Name of a file under data/media/."}
            },
            "required": ["file"],
        },
    },
    {
        "name": "codec_caps",
        "description": "Look up decoder capabilities (MIME, profiles, max size, hardware or software) for a device profile.",
        "input_schema": {
            "type": "object",
            "properties": {"device": {"type": "string"}, "mime": {"type": "string"}},
            "required": ["device", "mime"],
        },
    },
    {
        "name": "logcat_grep",
        "description": "Search a captured logcat file for lines matching a pattern.",
        "input_schema": {
            "type": "object",
            "properties": {"log": {"type": "string"}, "pattern": {"type": "string"}},
            "required": ["log", "pattern"],
        },
    },
]


def run_tool(name: str, arguments: dict) -> str:
    raise NotImplementedError(f"Tool {name!r} is implemented in module 2.")
