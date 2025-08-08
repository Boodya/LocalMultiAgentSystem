# Локальный чат‑агент (PoC) — Ollama/Azure + веб‑поиск

Минимальный прототип локального чат‑агента на Windows с локальной LLM через Ollama (gpt-oss:20b) или облачной LLM через Azure AI Foundry, с веб‑поиском (DuckDuckGo или Google CSE) и извлечением текста страниц для ответа с источниками.

## Возможности
- Локальная LLM через Ollama (gpt-oss:20b) или облачная через Azure
- Простая логика агента (двухшаговый план):
  1) решить, нужен ли интернет-поиск; 2) при необходимости — поиск и краткое чтение страниц; 3) итоговый ответ с источниками
- Поиск DuckDuckGo (без API ключа) или Google Custom Search (при наличии ключей)
- Загрузка HTML и извлечение чистого текста (requests + BeautifulSoup)
- Интерактивный CLI

## Предварительные требования
- Windows 10/11, PowerShell
- Python 3.9–3.12
- Установленный и запущенный Ollama
  - Скачать: https://ollama.com/download
  - В терминале: `ollama pull gpt-oss:20b`

## Установка
```powershell
# В корне репозитория
python -m venv .venv
. .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Убедитесь, что сервис Ollama запущен (приложение Ollama открыто или служба работает), и модель загружена:
```powershell
ollama pull gpt-oss:20b
```

## Запуск
```powershell
python app.py
```
- Введите вопрос. Агент сам решит, нужен ли поиск.
- Чтобы запретить веб-поиск и отвечать только оффлайн:
```powershell
python app.py --no-web
```
- Команда выхода: `/exit`

### Полезные команды
- Принудительный веб‑поиск для запроса:
```powershell
python app.py --verbose
# затем в интерактиве:
/web Что нового в Python 3.13?
```
- Показ «мыслей» (план, краткая причина, шаги, поиск и загрузка страниц):
```powershell
python app.py --verbose
```

### Повторное использование контекста
- Показ последних загруженных страниц: в интерактиве введите `/ctx`
- Суммаризация последних страниц другим запросом: `/summarize Кратко подведи итоги`

## Конфигурация (appconfig.json + переменные окружения)
Все настройки вынесены в `appconfig.json` в корне репозитория. Часть чувствительных полей можно (и удобно) переопределять переменными окружения.

Основные секции:
- llm: выбор провайдера и параметры
  - provider: "ollama" или "azure"
  - ollama: baseUrl, model, options (temperature, num_ctx, timeout_s, max_retries, retry_backoff_s)
  - azure: endpoint, deployment, apiKey (может задаваться переменной окружения), apiVersion, options
- search: выбор поискового провайдера и параметры
  - provider: "ddg" (по умолчанию) или "google"
  - ddg: maxResults, fetchMaxPages, requestTimeoutS, userAgent
  - google: apiKey, cx, dateRestrict
  - maxContextDocChars: максимум символов в совокупном контексте
- summarization: retryIfShort, minChars
- verbose: флаги для подробного лога планировщика и превью документов

Пример `appconfig.json` (фрагмент):
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
  }
}
```

### Переменные окружения (override)
Вы можете переопределить часть настроек через переменные окружения (приоритетнее, чем файл):
- AZURE_API_KEY — ключ для Azure AI Foundry; при наличии подставляется в `llm.azure.apiKey`
- AZURE_ENDPOINT — адрес ресурса Azure, подставляется в `llm.azure.endpoint` (например, `https://<resource>.openai.azure.com`)
- AZURE_DEPLOYMENT — имя деплоймента модели, подставляется в `llm.azure.deployment`
- SEARCH_PROVIDER — `ddg` или `google`, переопределяет `search.provider`
- GOOGLE_CSE_API_KEY — API‑ключ для Google Custom Search
- GOOGLE_CSE_CX — идентификатор поисковой системы (cx) для Google CSE
- GOOGLE_CSE_DATE_RESTRICT — ограничение по дате (например, `d1`, `w1`, `m1`), по умолчанию `d1`

В PowerShell (только на текущую сессию):
```powershell
$env:AZURE_API_KEY = "<your_azure_key>"
$env:AZURE_ENDPOINT = "https://<resource>.openai.azure.com"
$env:AZURE_DEPLOYMENT = "<your_deployment_name>"
$env:SEARCH_PROVIDER = "google"
$env:GOOGLE_CSE_API_KEY = "<your_google_api_key>"
$env:GOOGLE_CSE_CX = "<your_cx>"
$env:GOOGLE_CSE_DATE_RESTRICT = "d1"
```

Примечание: команда `set VAR=...` — это синтаксис cmd.exe. В PowerShell используйте `$env:VAR = "..."`. Если вы укажете `set AZURE_API_KEY=...` внутри PowerShell, это не создаст переменную окружения для текущего процесса Python.

## Как работает Azure‑конфигурация
Чтобы использовать Azure AI Foundry вместо локальной Ollama:
1) В `appconfig.json` установите `llm.provider` в "azure".
2) Заполните в секции `llm.azure`:
   - `endpoint`: например, `https://<resource>.openai.azure.com`
   - `deployment`: имя вашего развертывания модели (например, `gpt-4o-mini` или другое)
   - `apiKey`: можно оставить `null` и задать через переменную окружения `AZURE_API_KEY`
   - `apiVersion`: при необходимости измените (по умолчанию `2024-05-01-preview`)
3) Запустите CLI как обычно. Если не все обязательные поля заданы, агент сообщит об ошибке конфигурации.

Примечания:
- Ключ берётся так: сначала `AZURE_API_KEY` из окружения; если его нет — поле `llm.azure.apiKey` из `appconfig.json`.
- Если `endpoint`, `deployment` или ключ не заданы — и выбран провайдер `azure` — агент выбросит понятную ошибку с подсказкой.
- Параметры ретраев/таймаутов для Azure читаются из `llm.azure.options`.

## Переключение поискового провайдера
- По умолчанию используется DuckDuckGo (без ключей).
- Для Google CSE задайте в `appconfig.json` `search.provider = "google"` и укажите `google.apiKey` и `google.cx` (или задайте через переменные окружения, см. выше).

## Советы
- Первый ответ может быть медленным из-за «прогрева» модели.
- Для вопросов, требующих актуальной информации, агент выполнит поиск и приведёт источники.
- Параметры (лимиты поиска/таймауты) настраиваются в `src/agent/config.py`.

## Структура
- `app.py` — CLI вход
- `src/agent/agent.py` — простая ReAct‑петля (планирование → поиск → ответ)
- `src/agent/llm.py` — провайдеры LLM (Ollama и Azure) + фабрика
- `src/agent/web_search.py` — поиск (DDG/Google CSE) и загрузка страниц
- `src/agent/config.py` — конфигурация (appconfig.json + env‑override)
- `appconfig.json` — файл конфигурации

## Устранение неполадок
- Ошибка соединения с Ollama: проверьте, что Ollama запущен и модель `gpt-oss:20b` загружена.
- Проблемы с установкой `lxml`: обновите pip и wheel: `pip install --upgrade pip wheel` и повторите установку.
- Некоторые сайты могут блокировать запросы — агент продолжит с доступными результатами.
- При провайдере `azure`: убедитесь, что заданы `endpoint`, `deployment` и `apiKey` (через переменную окружения или файл). В противном случае будет брошена ошибка конфигурации.
