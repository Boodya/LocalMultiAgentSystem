from __future__ import annotations
from typing import Dict

from .llm import make_chat_client


DECISION_SCHEMA = (
    '{"need_action": false, "need_search": false, '
    '"clarify": null, "goal": "refined goal or empty", "reason": "short"}'
)


PROMPT = (
    "You are a router for a local assistant on Windows. Decide the next mode: "
    "- If the request implies creating/editing files or running commands (like venv, pip, running scripts), set need_action=true. "
    "- If answering requires web information, set need_search=true. "
    "- If the instruction is ambiguous, set clarify to ONE concise question to the user (and keep need_action=false until clarified). "
    "- Optionally provide a refined 'goal' string for action mode. "
    "Return ONLY JSON per the schema."
)


class Orchestrator:
    def __init__(self):
        self.llm = make_chat_client()

    def decide(self, user_input: str) -> Dict:
        messages = [
            {"role": "user", "content": f"User: {user_input}\n\n{PROMPT}"}
        ]
        plan = self.llm.chat_json(messages, schema_hint=DECISION_SCHEMA, temperature=0.1)
        # normalize
        need_action = bool(plan.get("need_action", False))
        need_search = bool(plan.get("need_search", False))
        clarify = plan.get("clarify")
        if isinstance(clarify, str):
            clarify = clarify.strip() or None
        else:
            clarify = None
        goal = plan.get("goal") or ""
        reason = plan.get("reason") or ""
        return {
            "need_action": need_action,
            "need_search": need_search,
            "clarify": clarify,
            "goal": goal,
            "reason": reason,
        }
