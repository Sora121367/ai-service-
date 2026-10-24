# Conventions

Short and binding. Change only by PR + ADR.

## Git
- Branches: `feat/<area>-<short-name>`, `fix/...`, `contract/...`, `chore/...`. Short-lived (≤ 3 days).
- Rebase on `main` at least daily. Squash-merge PRs.
- Commits: Conventional Commits — `feat(ingestion): pptx slide anchors`, `fix(rag): ...`, `contract: ...`.
- PR size: aim for < 400 changed lines. Every PR: tests pass, CI green, one human approval (two for `contracts/`, `migrations/`, `app/prompts/`).
- Releases: tag `vX.Y.Z` on `main` = contract version. The release workflow publishes the contract and the Java client.

## Python
- Python 3.12, uv, ruff (format + lint), pytest. Type hints everywhere; pydantic models for all API input/output.
- Layout: `app/api` (FastAPI routers) → `app/<area>` (logic) → `app/clients` (Ollama, embeddings, S3, web search, backend callback).
- Config only from environment (pydantic-settings). No hard-coded URLs, buckets or model names.

## API (contracts/ai-service.yaml)
- JSON fields `camelCase` on the wire (pydantic aliases), IDs are UUID strings, dates ISO-8601 UTC.
- Errors: RFC 9457 Problem Details with a `code` field.
- Long work: `202 Accepted` + job ID; progress reported by callback to the backend, `GET /jobs/{id}` as fallback (ADR-0003).
- Delete endpoints are idempotent.
- Versioning: additive = minor; removal/rename = major, after a deprecation release.

## Vector DB (pgvector)
- Alembic only. Scope columns indexed: `scope_type, classroom_id, course_id, workspace_id, owner_id, document_id`. HNSW on the embedding.
- `document_id` is a plain UUID (the documents table lives in the backend's database).

## Logging and privacy
- Never log tokens, file contents, chunk text, prompts with user content, chat messages or answers. Log IDs, timings, model names and token counts.
