from __future__ import annotations
from typing import Dict, List, Optional

from .llm import make_chat_client
from .web_search import search_and_fetch
from . import config


PLANNER_SCHEMA_HINT = (
    '{"need_search": true, "queries": ["q1", "q2"], "answer": "string", '
    '"reason": "short reason (<=1 sentence)", "steps": ["step1", "step2"]}'
)

PLANNER_USER_PROMPT = (
    "You are a planner for a helpful assistant. If answering requires internet search, return need_search=true and propose 1–3 precise search queries in 'queries'. "
    "If search is not needed, return need_search=false and provide a short direct answer in 'answer'. "
    "Also return a short 'reason' (<=1 sentence, no chain-of-thought) and an array 'steps' with 1–3 short step names. "
    "Use the user's language for any natural text fields."
)

ANSWER_SYSTEM = (
    "You are an assistant that answers strictly based on the provided sources. If sources conflict, point it out. "
    "Always add a final 'Sources' section (use the user's language for the section title) listing the URLs. "
    "Answer in a structured way: 5 bullet points if possible."
)


def _has_cyrillic(text: str) -> bool:
    try:
        return any('а' <= ch <= 'я' or 'А' <= ch <= 'Я' for ch in text)
    except Exception:
        return False


def _sources_label_for(text: str) -> str:
    return "Источники" if _has_cyrillic(text or "") else "Sources"


class ChatAgent:
    def __init__(self, allow_web: bool = True, verbose: bool = False, printer=None, memory: Optional[object] = None):
        self.allow_web = allow_web
        self.verbose = verbose
        self.print = printer or (lambda *_args, **_kwargs: None)
        # Initialize chat client (Ollama or Azure) from config
        self.llm = make_chat_client()
        self._last_context_pages = []
        self.memory = memory

    def plan(self, user_query: str) -> Dict:
        # Include recent conversation context to help with follow-ups
        content = ""
        if getattr(self, "memory", None):
            try:
                bullets = self.memory.as_bullets(8)
            except Exception:
                bullets = ""
            if bullets:
                content += f"Recent conversation (most recent last):\n{bullets}\n\n"
        content += f"Question: {user_query}\n\n{PLANNER_USER_PROMPT}"
        messages = [{"role": "user", "content": content}]
        if self.verbose and getattr(config, "VERBOSE_SHOW_PLANNER_REQUEST", True):
            self.print("planner.request: JSON plan requested (need_search, queries, answer, reason, steps)")
        plan = self.llm.chat_json(messages, schema_hint=PLANNER_SCHEMA_HINT, temperature=0.1)
        # sanitize
        need_search = bool(plan.get("need_search", False))
        queries = plan.get("queries") or []
        if isinstance(queries, str):
            queries = [queries]
        queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
        answer = plan.get("answer") or ""
        reason = plan.get("reason") or ""
        steps = plan.get("steps") or []
        if isinstance(steps, str):
            steps = [steps]
        steps = [s for s in steps if isinstance(s, str) and s.strip()][:3]
        if self.verbose:
            self.print(f"plan.need_search={need_search}; queries={queries}; answer.len={len(answer)}")
            if reason:
                self.print(f"reason: {reason}")
            if steps:
                self.print("steps: " + " -> ".join(steps))
            if getattr(config, "VERBOSE_SHOW_PLANNER_RESPONSE", True):
                try:
                    import json as _json
                    self.print("planner.response: " + _json.dumps({
                        "need_search": need_search,
                        "queries": queries,
                        "answer_len": len(answer),
                        "reason": reason,
                        "steps": steps
                    }, ensure_ascii=False))
                except Exception:
                    pass
        return {"need_search": need_search, "queries": queries[:3], "answer": answer, "reason": reason, "steps": steps}

    def answer_with_sources(self, user_query: str, context_docs: List[Dict[str, str]]) -> str:
        sources_text_lines = []
        for i, doc in enumerate(context_docs, start=1):
            title = doc.get("title") or "(untitled)"
            url = doc.get("url") or ""
            content = doc.get("content") or ""
            snippet = doc.get("snippet") or ""
            sources_text_lines.append(f"[{i}] {title}\nURL: {url}\nSNIPPET: {snippet}\nCONTENT: {content}\n")
        context_text = "\n\n".join(sources_text_lines)

        messages = [
            {"role": "user", "content": (
                "Question:\n" + user_query +
                "\n\nUse the sources below to answer. Be concise and specific, include key details." +
                "\n\nSOURCES:\n" + context_text +
                "\n\nRequirements:\n- Provide a brief summary in 5 bullet points (if possible)." +
                "\n- For each bullet: 1–2 sentences of essence, numbers if available, and a short note on why it matters." +
                "\n- If sources conflict, mention it in the corresponding bullet." +
                "\n- Add a final 'Sources' section listing the URLs." +
                "\n- Respond in the user's language."
            )}
        ]
        if self.verbose:
            total_chars = sum(len((d.get("content") or "")) for d in context_docs)
            self.print(f"summarize.using docs={len(context_docs)} total_chars={total_chars}")
        final = self.llm.chat(messages, temperature=0.2, system_prompt=ANSWER_SYSTEM)

        # Retry if too short (likely the model failed to summarize)
        if getattr(config, "SUMMARY_RETRY_IF_SHORT", True) and len(final.strip()) < getattr(config, "SUMMARY_MIN_CHARS", 120):
            if self.verbose:
                self.print("summary too short, retrying with stricter instruction")
            messages[-1]["content"] += "\n\nImportant: The answer must contain a numbered list of 5 items and be at least 600 characters."
            final = self.llm.chat(messages, temperature=0.2, system_prompt=ANSWER_SYSTEM)

        # Fallback: generate a minimal summary from titles/snippets if still empty
        if not final.strip():
            bullets = []
            for i, doc in enumerate(context_docs[:5], 1):
                t = (doc.get("title") or "Untitled").strip()
                sn = (doc.get("snippet") or doc.get("content") or "").strip()
                sn = sn[:160]
                bullets.append(f"{i}. {t} — {sn}")
            final = "\n".join(bullets)
        return final

    def handle_query(self, user_query: str, force_web: bool = False) -> str:
        # Special handling: if user asks to recall conversation, summarize memory
        uq_lower = (user_query or "").strip().lower()
        recall_triggers = [
            # Russian
            "о чем мы", "что мы обсуждали", "что я тебя спрашивал", "история разговора", "из контекста",
            # English
            "what did we talk", "what have we discussed", "conversation history", "what we just talked"
        ]
        if getattr(self, "memory", None) and any(t in uq_lower for t in recall_triggers):
            try:
                bullets = self.memory.as_bullets(12, max_chars=240)  # type: ignore[attr-defined]
            except Exception:
                bullets = ""
            if bullets:
                return f"Here's a brief recap of our recent conversation:\n\n{bullets}"
            # fall through if no bullets

        # If we have recent context and the user asks to work with "these pages/sources",
        # skip planning and directly answer from the cached context.
        uq = (user_query or "").strip().lower()
        if self._last_context_pages and any(kw in uq for kw in [
            # Russian triggers
            "прочитай эти страницы", "по этим источникам", "по этим страницам", "суммаризируй",
            # English triggers
            "read these pages", "from these sources", "from these pages", "summarize"
        ]):
            if self.verbose:
                self.print("using last context for summarization")
            return self.answer_from_last_context(user_query)

        # 1) Plan — do we need web search?
        try:
            plan = self.plan(user_query)
        except Exception as e:
            return f"[Planning error: {e}]"

        if (not plan.get("need_search") or not self.allow_web) and not force_web:
            # Answer directly using the model if possible
            if plan.get("answer"):
                return plan["answer"]
            try:
                sys = None
                if getattr(self, "memory", None):
                    try:
                        bullets = self.memory.as_bullets(8)
                    except Exception:
                        bullets = ""
                    if bullets:
                        sys = "Use the following recent conversation context if it helps answer the user succinctly.\n\n" + bullets
                resp = self.llm.chat([{"role": "user", "content": user_query}], temperature=0.2, system_prompt=sys)
                return resp
            except Exception as e:
                return f"[LLM error: {e}]"

        # 2) Search and fetch
        if self.verbose:
            self.print("searching...")
        try:
            bundle = search_and_fetch(plan.get("queries", []), log=(self.print if self.verbose else None))
            pages = bundle.get("pages", [])
            if self.verbose:
                urls = [p.get("url") for p in pages]
                self.print(f"fetched {len(pages)} pages: {urls}")
        except Exception as e:
            return f"[Search/fetch error: {e}]"

        if not pages:
            return "[No sources found for the query. Try rephrasing.]"

        # Cache context for follow-ups
        self._last_context_pages = pages

        # 3) Final answer
        try:
            answer = self.answer_with_sources(user_query, pages)
            urls = [p.get("url") for p in pages if p.get("url")]
            sources_label = _sources_label_for(user_query)
            if sources_label not in answer:
                answer += f"\n\n{sources_label}:\n" + "\n".join(urls)
            return answer
        except Exception as e:
            return f"[Answer generation error: {e}]"

    def answer_from_last_context(self, user_query: str) -> str:
        if not self._last_context_pages:
            return "[No cached sources. First perform a search (e.g., /web ...).]"
        try:
            answer = self.answer_with_sources(user_query, self._last_context_pages)
            urls = [p.get("url") for p in self._last_context_pages if p.get("url")]
            sources_label = _sources_label_for(user_query)
            if sources_label not in answer:
                answer += f"\n\n{sources_label}:\n" + "\n".join(urls)
            return answer
        except Exception as e:
            return f"[Answer generation error: {e}]"
