# Local Chat Agent (PoC) — Ollama/Azure + Web Search + Actions (PowerShell)

Minimal local chat agent for Windows. Uses a local LLM via Ollama (gpt-oss:20b) or a cloud LLM via Azure AI Foundry. Includes web search (DuckDuckGo or Google CSE) and page text extraction for answers with sources. Also includes an autonomous action mode to plan and execute PowerShell steps (create files, run commands) end-to-end.

## Features
- LLM providers: Ollama (gpt-oss:20b) or Azure AI Foundry
- Simple agent loop for Q&A:
  1) decide if web is needed; 2) search and fetch; 3) summarize with sources
- Web search: DuckDuckGo (no key) or Google Custom Search (with keys)
- HTML fetch + clean text (requests + BeautifulSoup)
- Interactive CLI
- Autonomous action mode (/task): plans steps, writes files, runs PowerShell commands, iterates up to a limit

## Requirements
- Windows 10/11, PowerShell
- Python 3.9–3.12
- Ollama installed and running (for local mode)
  - Download: https://ollama.com/download
  - In terminal: `ollama pull gpt-oss:20b`

## Setup
```powershell
# At the repo root
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Make sure Ollama service is running and model pulled:
```powershell
ollama pull gpt-oss:20b
```

## Run
```powershell
python app.py
```
- Ask your question. The agent will decide whether to search.
- Disable web usage:
```powershell
python app.py --no-web
```
- Quit: `/exit`

### Useful commands
- Force web search for a prompt:
```powershell
python app.py --verbose
# then in the interactive prompt:
/web What’s new in Python 3.13?
```
- Show “thinking” (planning/search steps):
```powershell
python app.py --verbose
```
- Reuse context:
  - List cached pages: `/ctx`
  - Summarize cached pages with a new prompt: `/summarize Summarize briefly`

### Autonomous actions (PowerShell)
- Run an end-to-end task with planning and stepwise execution:
  - `/task build a snake game in Python`
- The agent will plan 1–3 steps at a time (write files, run PowerShell commands) inside the workspace directory and iterate up to a configurable step limit.
- Logs are printed with the [act] prefix.

## Configuration (appconfig.json + environment variables)
All settings live in `appconfig.json` at the repo root. Sensitive values can be overridden via environment variables.

Main sections:
- llm: provider and options
  - provider: "ollama" or "azure"
  - ollama: baseUrl, model, options (temperature, num_ctx, timeout_s, max_retries, retry_backoff_s)
  - azure: endpoint, deployment, apiKey, apiVersion, options
- search: provider and options
  - provider: "ddg" (default) or "google"
  - ddg: maxResults, fetchMaxPages, requestTimeoutS, userAgent
  - google: apiKey, cx, dateRestrict
  - maxContextDocChars: max combined characters for context
- summarization: retryIfShort, minChars
- verbose: planner/log options
- tools: autonomous execution options
  - allow (reserved), workingDir (default "workspace"), commandTimeoutS (default 180), maxSteps (default 12)

Example appconfig.json (partial):
```json
{
  "llm": {
    "provider": "ollama",
    "ollama": { "baseUrl": "http://127.0.0.1:11434", "model": "gpt-oss:20b" },
    "azure": {
      "endpoint": "",
      "apiKey": null,
      "deployment": "",
      "apiVersion": "2024-05-01-preview"
    }
  },
  "search": {
    "provider": "ddg",
    "google": { "apiKey": null, "cx": null, "dateRestrict": "d1" }
  },
  "tools": {
    "workingDir": "workspace",
    "commandTimeoutS": 180,
    "maxSteps": 12
  }
}
```

### Environment variables (override)
You can override part of the config via env vars (they take precedence):
- AZURE_API_KEY — overrides `llm.azure.apiKey`
- AZURE_ENDPOINT — overrides `llm.azure.endpoint` (e.g., `https://<resource>.openai.azure.com`)
- AZURE_DEPLOYMENT — overrides `llm.azure.deployment`
- AZURE_API_VERSION — overrides `llm.azure.apiVersion` (default `2024-05-01-preview`)
- SEARCH_PROVIDER — `ddg` or `google`, overrides `search.provider`
- GOOGLE_CSE_API_KEY — API key for Google Custom Search
- GOOGLE_CSE_CX — Search engine id (cx) for Google CSE
- GOOGLE_CSE_DATE_RESTRICT — e.g., `d1`, `w1`, `m1` (default `d1`)

PowerShell (current session only):
```powershell
$env:AZURE_API_KEY = "<your_azure_key>"
$env:AZURE_ENDPOINT = "https://<resource>.openai.azure.com"
$env:AZURE_DEPLOYMENT = "<your_deployment_name>"
$env:AZURE_API_VERSION = "2024-05-01-preview"
$env:SEARCH_PROVIDER = "google"
$env:GOOGLE_CSE_API_KEY = "<your_google_api_key>"
$env:GOOGLE_CSE_CX = "<your_cx>"
$env:GOOGLE_CSE_DATE_RESTRICT = "d1"
```

Note: `set VAR=...` is cmd.exe syntax. In PowerShell use `$env:VAR = "..."`. Using `set` inside PowerShell won’t set env vars for the Python process.

## Azure configuration
To use Azure instead of local Ollama:
1) Set `llm.provider` to `"azure"` in `appconfig.json`.
2) Fill `llm.azure`: `endpoint`, `deployment`, `apiKey` (or set via env), and optionally `apiVersion`.
3) Run the CLI. If any required fields are missing, the agent will report a clear configuration error.

Notes:
- The API key is taken from `AZURE_API_KEY` first, then from `appconfig.json`.
- If `endpoint`, `deployment`, or key are missing (with provider `azure`), the agent will error with guidance.
- Retry/timeout settings for Azure are under `llm.azure.options`.

## Switch search provider
- Default: DuckDuckGo (no keys required).
- For Google CSE, set `search.provider = "google"` and specify `google.apiKey` and `google.cx` (or set via env vars).

## Tips
- The very first response may be slower due to model warm-up.
- For time-sensitive questions the agent will search and include sources.
- Tunables (limits/timeouts) are in `src/agent/config.py` and `appconfig.json`.

## Project structure
- `app.py` — CLI entry
- `src/agent/agent.py` — plan → (optional) search → summarize with sources
- `src/agent/llm.py` — LLM providers (Ollama/Azure) + factory
- `src/agent/web_search.py` — search (DDG/Google CSE) and page fetching
- `src/agent/config.py` — configuration (appconfig.json + env overrides)
- `src/agent/tools.py` — PowerShell runner and simple FS helpers
- `src/agent/action_agent.py` — autonomous planning/execution agent
- `appconfig.json` — configuration file

## Troubleshooting
- Ollama connection error: ensure Ollama is running and `gpt-oss:20b` is pulled.
- lxml install issues: upgrade pip and wheel (`pip install --upgrade pip wheel`) and reinstall.
- Some sites may block scraping — the agent will continue with available results.
- Azure provider: ensure `endpoint`, `deployment`, and `apiKey` are set (via env or file). Otherwise you’ll get a configuration error.
