from __future__ import annotations
from typing import List, Dict


class ConversationMemory:
    """Keeps a rolling window of recent user/assistant messages for context."""
    def __init__(self, max_messages: int = 20):
        self.max_messages = max_messages
        self._messages: List[Dict[str, str]] = []

    def add_user(self, content: str) -> None:
        self._append({"role": "user", "content": content or ""})

    def add_assistant(self, content: str) -> None:
        self._append({"role": "assistant", "content": content or ""})

    def _append(self, msg: Dict[str, str]) -> None:
        self._messages.append(msg)
        if len(self._messages) > self.max_messages:
            # keep last N
            self._messages = self._messages[-self.max_messages :]

    def recent(self, n: int = 6) -> List[Dict[str, str]]:
        if n <= 0:
            return []
        return self._messages[-n:]

    def as_bullets(self, n: int = 6, max_chars: int = 160) -> str:
        out = []
        for m in self.recent(n):
            role = m.get("role", "")
            text = (m.get("content", "") or "").strip().replace("\n", " ")
            if len(text) > max_chars:
                text = text[: max_chars - 1] + "…"
            out.append(f"- {role}: {text}")
        return "\n".join(out)
