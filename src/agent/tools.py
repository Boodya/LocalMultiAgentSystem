from __future__ import annotations
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class CmdResult:
    code: int
    stdout: str
    stderr: str
    duration_s: float


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_powershell(command: str, cwd: Path, timeout_s: int = 180) -> CmdResult:
    """Run a PowerShell command and capture output. Uses -NoProfile for determinism."""
    start = time.time()
    proc = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        out, err = proc.communicate(timeout=timeout_s)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        code = -9
        err = (err or "") + f"\n<timeout after {timeout_s}s>"
    dur = time.time() - start
    return CmdResult(code=code, stdout=out or "", stderr=err or "", duration_s=dur)


def write_text_file(base: Path, rel_path: str, content: str) -> str:
    p = (base / rel_path).resolve()
    ensure_dir(p.parent)
    p.write_text(content, encoding="utf-8")
    return str(p)


def read_text_file(base: Path, rel_path: str) -> str:
    p = (base / rel_path).resolve()
    return p.read_text(encoding="utf-8")


def list_dir(base: Path, rel_path: str = ".") -> List[str]:
    p = (base / rel_path).resolve()
    if not p.exists():
        return []
    return [c.name + ("/" if c.is_dir() else "") for c in p.iterdir()]
