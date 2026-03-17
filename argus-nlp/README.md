# ARGUS NLP Assistant (Purple Column)

This service implements the purple-column NLP assistant requirements:

- State-grounded prompt construction
- Query intent routing and classification
- Response formatting and recommended actions
- Latency optimization via prompt caching
- Operator chat endpoint and query history

## Structure

- `app/main.py` — FastAPI app
- `app/schemas.py` — request/response Pydantic models
- `app/prompt.py` — state-grounded prompt templates
- `app/router.py` — query routing logic + model call
- `app/history.py` — in-memory chat history

## Run

```bash
cd argus-nlp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8004
```

## Example

```
POST /nlp/query
{
  "user_id": "u1",
  "query": "What is the current alert status?",
  "intent": "status"
}
```

Response includes `assistant`, `detail`, and `recommended_actions`.

## Ollama/Mistral Setup

1. Start Ollama (if not installed, install from ollama.com).
2. Pull model:
```bash
docker compose run ollama ollama pull mistral:7b-instruct
```
3. Start Ollama server:
```bash
docker compose up -d ollama
```
4. Set environment variables:
```bash
set OLLAMA_URL=http://127.0.0.1:11434
set OLLAMA_MODEL=mistral:7b-instruct
```
5. Run the service and API test.

If Ollama isn't running, fallback logic still returns a safe stub response for demo mode.

