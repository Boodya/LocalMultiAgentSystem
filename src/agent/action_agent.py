from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional

from . import config
from .llm import make_chat_client
from .tools import run_powershell, write_text_file, read_text_file, list_dir, ensure_dir


PLAN_SCHEMA = (
    '{"steps": ['
    '{"type":"cmd","description":"...","command":"..."},'
    '{"type":"write","description":"...","path":"file.py","content":"..."}'
    '], "reason":"short", "done": false}'
)


class ActionAgent:
    """A minimal autonomous agent that plans steps and executes them via PowerShell and file ops."""
    def __init__(self, workspace: Optional[str] = None, printer=None, verbose: bool = False):
        self.print = printer or (lambda *_a, **_k: None)
        self.verbose = verbose
        self.llm = make_chat_client()
        base = Path(workspace or config.TOOLS_WORKING_DIR)
        ensure_dir(base)
        self.workspace = base
        self.max_steps = config.TOOLS_MAX_STEPS
        self.timeout_s = config.TOOLS_CMD_TIMEOUT_S

    def _say(self, msg: str):
        self.print(msg)

    def plan(self, goal: str, transcript: List[Dict]) -> Dict:
        sys = (
            "You are an autonomous developer agent. Plan the next 1-3 concrete steps to progress the task. "
            "Use types: 'cmd' (PowerShell command) or 'write' (write file with content). "
            "Important: Each 'cmd' runs in a fresh PowerShell; do not rely on prior activation state. "
            "Always use .venv\\Scripts\\python.exe and .venv\\Scripts\\pip.exe (not 'python' or 'pip'). "
            "All file paths are relative to the workspace root; do NOT prefix with 'workspace/' or '.\\workspace\\'. "
            "When the goal is achieved (e.g., a smoke test ran successfully), set done=true and return an empty steps list. "
            "Use recent tool outputs (stdout/stderr/exit code) to decide completion. "
            "Return ONLY JSON matching this example schema: " + PLAN_SCHEMA
        )
        ctx = "\n".join([f"- {m.get('role')}: {m.get('content')[:400]}" for m in transcript[-6:]])
        user = (
            f"Goal: {goal}\n\nWorkspace: {self.workspace}\nRecent log:\n{ctx}\n\n"
            "Constraints: PowerShell only; keep commands idempotent; prefer relative paths under workspace. "
            "On Windows, prefer .venv as the virtual environment name."
        )
        try:
            plan = self.llm.chat_json([
                {"role": "user", "content": user}
            ], schema_hint=PLAN_SCHEMA, temperature=0.2)
        except Exception as e:
            self._say(f"act.plan.parse_error: {e}")
            # Fallback: request a minimal plan without large code blocks
            MIN_SCHEMA = '{"steps":[{"type":"cmd","description":"...","command":"..."}],"reason":"short","done":false}'
            mini_user = user + "\n\nReturn minimal JSON: only 'cmd' steps. If you think a file must be written, include a 'write' step with just the 'path' and a short 'description' (omit 'content')."
            try:
                plan = self.llm.chat_json([
                    {"role": "user", "content": mini_user}
                ], schema_hint=MIN_SCHEMA, temperature=0.0)
            except Exception as e2:
                self._say(f"act.plan.minimal_parse_error: {e2}")
                return {"steps": [], "reason": "parse_error"}
        # normalize
        steps = plan.get("steps") or []
        if isinstance(steps, dict):
            steps = [steps]
        clean = []
        for s in steps[:3]:
            if not isinstance(s, dict):
                continue
            t = s.get("type")
            if t not in ("cmd", "write"):
                continue
            clean.append(s)
        if self.verbose:
            try:
                import json as _json
                self._say("act.plan.response: " + _json.dumps({"steps": clean, "reason": plan.get("reason", "")}, ensure_ascii=False))
            except Exception:
                pass
        return {"steps": clean, "reason": plan.get("reason", ""), "done": bool(plan.get("done", False))}

    def run_step(self, step: Dict) -> Dict:
        t = step.get("type")
        if t == "cmd":
            cmd = step.get("command", "").strip()
            if not cmd:
                return {"ok": False, "error": "empty command"}
            # Rewrite to use venv tools explicitly if present
            cmd = self._rewrite_cmd_for_venv(cmd)
            if self.verbose:
                self._say(f"act.cmd: {cmd}")
            res = run_powershell(cmd, cwd=self.workspace, timeout_s=self.timeout_s)
            if self.verbose:
                if res.stdout:
                    self._say("act.out:\n" + res.stdout)
                if res.stderr:
                    self._say("act.err:\n" + res.stderr)
                self._say(f"act.code: {res.code} t={res.duration_s:.2f}s")
            return {"ok": res.code == 0, "code": res.code, "stdout": res.stdout, "stderr": res.stderr, "t": res.duration_s}
        if t == "write":
            path = step.get("path", "").strip()
            content = step.get("content", "")
            if not path:
                return {"ok": False, "error": "empty path"}
            path = self._normalize_rel(path)
            if not content:
                # Generate content if the plan omitted it
                content = self._gen_file_content(goal=self._current_goal, path=path)
            full = write_text_file(self.workspace, path, content)
            return {"ok": True, "path": full, "bytes": len(content.encode('utf-8'))}
        return {"ok": False, "error": f"unknown step type {t}"}

    def run_task(self, goal: str) -> str:
        transcript: List[Dict] = []
        summary: List[str] = []
        last_sig: Optional[str] = None
        stagnation = 0
        # make goal available to content generator
        self._current_goal = goal
        for i in range(1, self.max_steps + 1):
            self._say(f"act.plan step={i}")
            try:
                plan = self.plan(goal, transcript)
            except Exception as e:
                self._say(f"act.plan.error: {e}")
                break
            if plan.get("done"):
                summary.append("Goal achieved. Stopping.")
                break
            steps = plan.get("steps", [])
            if not steps:
                summary.append(f"No further steps at iteration {i}.")
                break
            # Stagnation detection: if identical plan repeats, stop
            sig = "|".join([f"{s.get('type')}::{s.get('path') or ''}::{s.get('command') or ''}" for s in steps])
            if sig == last_sig:
                stagnation += 1
            else:
                stagnation = 0
            last_sig = sig
            if stagnation >= 1:
                summary.append("No progress detected (repeated plan). Stopping.")
                break
            for s in steps:
                desc = s.get('description','')
                suffix = f" | {s.get('command','')}" if (self.verbose and s.get('type') == 'cmd') else ""
                self._say(f"act.exec: {s.get('type')} - {desc}{suffix}")
                result = self.run_step(s)
                transcript.append({"role": "tool", "content": json.dumps({"step": s, "result": result}, ensure_ascii=False)})
                if not result.get("ok"):
                    self._say(f"act.fail: {result}")
                    summary.append(f"Failed: {result}")
                    # continue planning to recover
                else:
                    self._say("act.ok")
                    # Success heuristic: pygame smoke test succeeded
                    if s.get('type') == 'cmd':
                        out = (result.get('stdout') or '') + (result.get('stderr') or '')
                        low = out.lower()
                        if ("pygame" in low) and ("hello from the pygame community" in low):
                            summary.append("Smoke test output detected (pygame). Stopping.")
                            return "\n".join(summary)
        return "\n".join(summary) or "Task complete (see logs)."

    def _normalize_rel(self, p: str) -> str:
        # Strip leading workspace/ or .\workspace\ prefixes
        p = p.replace("\\", "/").lstrip("/.")
        if p.lower().startswith("workspace/"):
            p = p[len("workspace/"):]
        return p

    def _rewrite_cmd_for_venv(self, cmd: str) -> str:
        """Rewrite leading python/pip in each segment to venv executables if they exist."""
        vpy = (self.workspace / ".venv" / "Scripts" / "python.exe")
        vpip = (self.workspace / ".venv" / "Scripts" / "pip.exe")
        segments = [c.strip() for c in cmd.split(";")]
        new_segments = []
        for seg in segments:
            low = seg.lower().lstrip()
            if low.startswith("python ") and vpy.exists():
                seg = f'"{vpy}"' + seg[6:]  # replace leading 'python'
            elif low.startswith("pip ") and vpip.exists():
                seg = f'"{vpip}"' + seg[3:]  # replace leading 'pip'
            # Normalize workspace path prefixes inside commands when running from workspace cwd
            seg = seg.replace(".\\workspace\\", ".\\").replace("./workspace/", "./").replace("workspace\\", "").replace("workspace/", "")
            new_segments.append(seg)
        return "; ".join(new_segments)

    def _gen_file_content(self, goal: str, path: str) -> str:
        """Ask the LLM to generate file content when the plan omitted it."""
        prompt = (
            f"Goal: {goal}\nCreate the file '{path}' content. Return ONLY the raw file content without any wrapper or explanations. "
            "Keep it minimal but runnable. If it's a pygame smoke test 'snake.py', make it auto-exit after a short time (e.g., 3 seconds)."
        )
        try:
            text = self.llm.chat([{"role": "user", "content": prompt}], temperature=0.1)
            return text
        except Exception as e:
            self._say(f"act.gen_content.error: {e}")
            return ""
