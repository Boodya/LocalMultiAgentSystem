from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any, Dict


# Load config from appconfig.json at repo root, with environment overrides for sensitive fields
def _default_config() -> Dict[str, Any]:
    return {
        "llm": {
            "provider": "ollama",  # ollama | azure
            "ollama": {
                "baseUrl": "http://127.0.0.1:11434",
                "model": "gpt-oss:20b",
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 8192,
                    "timeout_s": 60,
                    "max_retries": 2,
                    "retry_backoff_s": 1.5
                }
            },
            "azure": {
                "endpoint": "",
                "apiKey": None,  # set via env AZURE_API_KEY or in this file
                "deployment": "",
                "apiVersion": "2024-05-01-preview",
                "options": {
                    "temperature": 0.2,
                    "timeout_s": 60,
                    "max_retries": 2,
                    "retry_backoff_s": 1.5
                }
            }
        },
        "search": {
            "provider": os.getenv("SEARCH_PROVIDER", "ddg"),  # ddg | google
            "ddg": {
                "maxResults": 5,
                "fetchMaxPages": 3,
                "requestTimeoutS": 20,
                "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            },
            "google": {
                "apiKey": os.getenv("GOOGLE_CSE_API_KEY"),
                "cx": os.getenv("GOOGLE_CSE_CX"),
                "dateRestrict": os.getenv("GOOGLE_CSE_DATE_RESTRICT", "d1")
            },
            "maxContextDocChars": 8000
        },
        "summarization": {
            "retryIfShort": True,
            "minChars": 120
        },
        "verbose": {
            "plannerRequest": True,
            "plannerResponse": True,
            "maxDocPreviewChars": 300
        }
    }


def _load_json_config() -> Dict[str, Any]:
    # repo root assumed two levels up from this file: src/agent/config.py -> repo/
    root = Path(__file__).resolve().parents[2]
    cfg_path = root / "appconfig.json"
    data = _default_config()
    if cfg_path.exists():
        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                user = json.load(f)
            # shallow merge (top-level keys and known nested maps)
            def merge(dst: Dict[str, Any], src: Dict[str, Any]):
                for k, v in src.items():
                    if isinstance(v, dict) and isinstance(dst.get(k), dict):
                        merge(dst[k], v)
                    else:
                        dst[k] = v
            merge(data, user)
        except Exception:
            # If config broken, keep defaults
            pass
    # env override for Azure key if present
    ak = os.getenv("AZURE_API_KEY")
    if ak:
        data.setdefault("llm", {}).setdefault("azure", {})["apiKey"] = ak
    # env override for Azure endpoint if present
    ae = os.getenv("AZURE_ENDPOINT")
    if ae:
        data.setdefault("llm", {}).setdefault("azure", {})["endpoint"] = ae
    # env override for Azure deployment if present
    ad = os.getenv("AZURE_DEPLOYMENT")
    if ad:
        data.setdefault("llm", {}).setdefault("azure", {})["deployment"] = ad
    # env override for Azure api version if present
    av = os.getenv("AZURE_API_VERSION")
    if av:
        data.setdefault("llm", {}).setdefault("azure", {})["apiVersion"] = av
    return data


CONFIG: Dict[str, Any] = _load_json_config()


def cfg(path: str, default: Any = None) -> Any:
    cur: Any = CONFIG
    for p in path.split('.'):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


# Backward-compatible module-level constants mapped from CONFIG
OLLAMA_BASE_URL = cfg("llm.ollama.baseUrl", "http://127.0.0.1:11434")
MODEL_NAME = cfg("llm.ollama.model", "gpt-oss:20b")
TEMPERATURE = float(cfg("llm.ollama.options.temperature", 0.2))
OLLAMA_TIMEOUT_S = int(cfg("llm.ollama.options.timeout_s", 60))
OLLAMA_MAX_RETRIES = int(cfg("llm.ollama.options.max_retries", 2))
OLLAMA_RETRY_BACKOFF_S = float(cfg("llm.ollama.options.retry_backoff_s", 1.5))
OLLAMA_NUM_CTX = int(cfg("llm.ollama.options.num_ctx", 8192))

REQUEST_TIMEOUT_S = int(cfg("search.ddg.requestTimeoutS", 20))
SEARCH_MAX_RESULTS = int(cfg("search.ddg.maxResults", 5))
FETCH_MAX_PAGES = int(cfg("search.ddg.fetchMaxPages", 3))
USER_AGENT = cfg("search.ddg.userAgent")
MAX_CONTEXT_DOC_CHARS = int(cfg("search.maxContextDocChars", 8000))

SUMMARY_RETRY_IF_SHORT = bool(cfg("summarization.retryIfShort", True))
SUMMARY_MIN_CHARS = int(cfg("summarization.minChars", 120))

VERBOSE_SHOW_PLANNER_REQUEST = bool(cfg("verbose.plannerRequest", True))
VERBOSE_SHOW_PLANNER_RESPONSE = bool(cfg("verbose.plannerResponse", True))
VERBOSE_MAX_DOC_PREVIEW_CHARS = int(cfg("verbose.maxDocPreviewChars", 300))

SEARCH_PROVIDER = (cfg("search.provider", os.getenv("SEARCH_PROVIDER", "ddg")) or "ddg").lower()
GOOGLE_CSE_API_KEY = cfg("search.google.apiKey", os.getenv("GOOGLE_CSE_API_KEY"))
GOOGLE_CSE_CX = cfg("search.google.cx", os.getenv("GOOGLE_CSE_CX"))
GOOGLE_CSE_DATE_RESTRICT = cfg("search.google.dateRestrict", os.getenv("GOOGLE_CSE_DATE_RESTRICT", "d1"))
AZURE_ENDPOINT = cfg("llm.azure.endpoint", os.getenv("AZURE_ENDPOINT"))
AZURE_DEPLOYMENT = cfg("llm.azure.deployment", os.getenv("AZURE_DEPLOYMENT"))
AZURE_API_VERSION = cfg("llm.azure.apiVersion", os.getenv("AZURE_API_VERSION", "2024-05-01-preview"))


def reload_config() -> None:
    global CONFIG
    CONFIG = _load_json_config()
