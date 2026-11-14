"""Text processing and LLM content normalization utilities."""

from __future__ import annotations

from typing import Any


def extract_text_content(content: Any) -> str:
    """Extract clean string text from various LLM content representations.
    
    Handles:
    - Pure string: "Xin chào"
    - List of parts: [{"type": "text", "text": "Xin chào"}, ...]
    - Nested objects or tuples
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
            elif hasattr(part, "text"):
                parts.append(str(part.text))
        return "\n".join(parts).strip()
    return str(content)
