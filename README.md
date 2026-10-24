# InsightHub — AI service

Python 3.12 / FastAPI service: ingestion, RAG, web-search fallback, summaries, quiz and flashcard generation.
Standalone repo. Its only caller is the InsightHub Spring Boot backend (separate repo), through `contracts/ai-service.yaml`.

| Need | Command (repo root) |
|---|---|
| Install | `uv sync` |
| Local infra, connected to the backend's local Keycloak/RustFS by URL | `docker compose up -d` |
| Local infra, no backend at all (own RustFS on :9100) | `docker compose --profile standalone up -d` |
| Ollama on this machine (GPU) | add `--profile gpu` (otherwise set `OLLAMA_URL` to the shared GPU server) |
| Run API / worker | `uv run fastapi dev app/main.py` · `uv run python -m app.worker` |
| Test / lint | `uv run pytest` · `uv run ruff check . && uv run ruff format .` |
| Release the contract + Java client | `git tag v<version> && git push origin v<version>` (version = `info.version` in the contract) |

Local ports: API :8000 · vector DB :5433 · Redis :6379 · own RustFS (standalone) :9100 / console :9101 · Ollama :11434

Claude Code: start `claude` **at this repo root**, then `/start-task <area> <task>`.
Team skills: `/start-task`, `/contract-change`, `/new-migration`, `/resolve-conflicts`, `/pre-pr`.
Setup steps: `SETUP-GUIDE.md`. Rules: `CLAUDE.md`, `docs/conventions.md`, `docs/adr/`.
