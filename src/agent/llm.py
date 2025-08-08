from __future__ import annotations
import json
import time
import requests
from typing import List, Dict, Optional

from . import config


class OllamaChat:
    def __init__(self, model: str = config.MODEL_NAME, base_url: str = config.OLLAMA_BASE_URL):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(self, messages: List[Dict[str, str]], temperature: float = config.TEMPERATURE,
             system_prompt: Optional[str] = None) -> str:
        payload = {
            "model": self.model,
            "messages": ([] if not system_prompt else [{"role": "system", "content": system_prompt}]) + messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": getattr(config, "OLLAMA_NUM_CTX", 2048)
            }
        }
        url = f"{self.base_url}/api/chat"
        last_err = None
        for attempt in range(config.OLLAMA_MAX_RETRIES + 1):
            try:
                resp = requests.post(url, json=payload, timeout=config.OLLAMA_TIMEOUT_S)
                if resp.status_code != 200:
                    raise RuntimeError(f"Ollama API error {resp.status_code}: {resp.text}")
                data = resp.json()
                break
            except Exception as e:
                last_err = e
                if attempt < config.OLLAMA_MAX_RETRIES:
                    import time as _t
                    _t.sleep(config.OLLAMA_RETRY_BACKOFF_S * (attempt + 1))
                    continue
                raise last_err
        # Non-streamed chat returns: { 'message': {'role':'assistant','content':'...'}, 'done': true, ... }
        msg = data.get("message", {})
        content = msg.get("content", "")
        return content

    def chat_json(self, messages: List[Dict[str, str]], schema_hint: str, temperature: float = config.TEMPERATURE) -> dict:
        """Ask model to return strict JSON. Minimal guard via last-ditch parsing."""
        system = (
            "You are a planner. Respond with ONLY valid JSON without comments or explanations. "
            "Follow this schema (example): " + schema_hint
        )
        text = self.chat(messages, temperature=temperature, system_prompt=system)
        # try parse; if fails, attempt to extract JSON substring
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except Exception:
                    pass
            raise


class AzureChat:
    """Minimal Azure AI Foundry (Azure OpenAI) chat wrapper.
    Expects:
      - endpoint: e.g., https://<resource>.openai.azure.com
      - deployment: your chat deployment name
      - apiKey: key (from env or config)
    """
    def __init__(self,
                 endpoint: str,
                 deployment: str,
                 api_key: str,
                 api_version: str = "2024-05-01-preview"):
        self.endpoint = endpoint.rstrip("/")
        self.deployment = deployment
        self.api_key = api_key
        self.api_version = api_version

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "api-key": self.api_key,
        }

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2,
             system_prompt: Optional[str] = None) -> str:
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions?api-version={self.api_version}"
        last_err = None
        # Some Azure models only support default temperature (1). We'll retry without temperature if rejected.
        temp_to_use: Optional[float] = temperature
        for attempt in range(int(config.cfg("llm.azure.options.max_retries", 2)) + 1):
            try:
                payload = {
                    "messages": ([] if not system_prompt else [{"role": "system", "content": system_prompt}]) + messages,
                }
                if temp_to_use is not None:
                    payload["temperature"] = temp_to_use
                resp = requests.post(url, headers=self._headers(), json=payload,
                                     timeout=float(config.cfg("llm.azure.options.timeout_s", 60)))
                if resp.status_code >= 400:
                    # If temperature rejected, retry omitting it (use default)
                    try:
                        err_json = resp.json()
                    except Exception:
                        err_json = None
                    if err_json and isinstance(err_json, dict):
                        err = err_json.get("error", {})
                        param = err.get("param")
                        msg = (err.get("message") or "").lower()
                        if param == "temperature" or ("temperature" in msg and "default" in msg):
                            # Remove temperature and retry once more
                            if temp_to_use is not None and attempt < int(config.cfg("llm.azure.options.max_retries", 2)):
                                temp_to_use = None
                                time.sleep(float(config.cfg("llm.azure.options.retry_backoff_s", 1.5)) * (attempt + 1))
                                continue
                    # Include Azure error body for better diagnostics
                    raise RuntimeError(f"Azure API error {resp.status_code}: {resp.text}")
                data = resp.json()
                # Azure format: choices[0].message.content
                choices = data.get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "")
            except Exception as e:
                last_err = e
                if attempt < int(config.cfg("llm.azure.options.max_retries", 2)):
                    time.sleep(float(config.cfg("llm.azure.options.retry_backoff_s", 1.5)) * (attempt + 1))
                    continue
                raise last_err

    def chat_json(self, messages: List[Dict[str, str]], schema_hint: str, temperature: float = 0.2) -> dict:
        system = (
            "You are a planner. Respond with ONLY valid JSON without comments or explanations. "
            "Follow this schema (example): " + schema_hint
        )
        text = self.chat(messages, temperature=temperature, system_prompt=system)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except Exception:
                    pass
            raise


def make_chat_client():
    provider = (config.cfg("llm.provider", "ollama") or "ollama").lower()
    if provider == "azure":
        endpoint = config.cfg("llm.azure.endpoint", "").strip()
        api_key = config.cfg("llm.azure.apiKey") or ""
        deployment = config.cfg("llm.azure.deployment", "").strip()
        api_version = config.cfg("llm.azure.apiVersion", "2024-05-01-preview")
        if not (endpoint and api_key and deployment):
            raise RuntimeError("Azure LLM is not configured: set endpoint, apiKey, and deployment in appconfig.json or env AZURE_API_KEY")
        return AzureChat(endpoint=endpoint, deployment=deployment, api_key=api_key, api_version=api_version)
    # default: ollama
    return OllamaChat(model=config.cfg("llm.ollama.model", config.MODEL_NAME), base_url=config.cfg("llm.ollama.baseUrl", config.OLLAMA_BASE_URL))
