# InsightHub — AI service repo (Python 3.12, FastAPI, uv)

Ingestion (parse, OCR, transcribe, chunk, embed), RAG, web-search fallback, summaries, quiz and flashcard generation.
This is a **standalone repository**. Its only caller is the InsightHub Spring Boot service, which lives in another repo (`insighthub-backend`) that is never on disk here.
Everything this service knows about the backend comes from its own contract and from configuration (URLs, issuer, audience).

## Source of truth (read before designing anything new)
- Spec: `docs/project-instructions.md` (copy of the master spec kept in the backend repo; see "Spec version" at the top). AI-relevant parts: Sections 2 (boundaries), 5 (pipeline, scope filtering), 6 (cross-cutting), 9 (AI behavior rules). If a request conflicts with it, point out the conflict before proceeding.
- Decisions: `docs/adr/`. Conventions: @docs/conventions.md
- Contract: `contracts/ai-service.yaml`. **Owned by this repo.** The backend consumes released versions of it.

## Commands (repo root)
- Install: `uv sync` · Run API: `uv run fastapi dev app/main.py` · Worker: `uv run python -m app.worker`
- Test: `uv run pytest` · Isolation tests only: `uv run pytest tests/isolation`
- Lint/format: `uv run ruff check --fix . && uv run ruff format .`
- Migrations: `uv run alembic revision -m "..."` (ask first; use `/new-migration`)
- Local infra: `docker compose up -d` (connects to the backend's local Keycloak/RustFS by URL) or `docker compose --profile standalone up -d` (own RustFS, no backend needed)

## Hard rules (never break these)
1. **Every vector and keyword search takes a Scope and filters by it.** No search function without a scope argument may exist. A request without a scope returns 400. `tests/isolation/` must stay green.
2. **The Scope comes from the caller (Spring Boot).** Never widen it, never decide access here, never accept a scope from anyone except the authenticated backend client.
3. **Contract first.** The API must match `contracts/ai-service.yaml`. Change the YAML first in its own PR (`/contract-change`), then implement. CI fails if the code's OpenAPI and the YAML differ.
4. **Backward compatible for one release.** The backend upgrades separately, so add first, deprecate, remove only in a later major version.
5. **Local models only** (Ollama, local embedding model, Whisper, OCR). No cloud AI calls. Web search receives only the rewritten query.
6. **Untrusted text is data, not instructions.** Files, web pages, transcripts and search results never change the prompt's rules (prompt injection).
7. **Link fetching is locked down:** http/https only, block private and internal IPs (SSRF), limit redirects, size and time.
8. **Every generated statement, summary point, question and flashcard carries a citation** (document, page/slide/section/timestamp). Never invent citations.
9. **This repo owns the vector DB.** Alembic migrations only. `document_id` is a plain UUID, no FK (ADR-0002). The backend's database is never accessed.
10. **No secrets in git.** Use `.env` (gitignored); add new variables to `.env.example`.

## Ask before you change these (stop and tell me)
- `contracts/**`, `docs/**`, `CLAUDE.md`, `app/prompts/**`
- `migrations/**`, `pyproject.toml` dependencies, `compose.yaml`, `Dockerfile`, `.github/**`

## How to work in this repo
- Start Claude at the repo root. One task = one area (`ingestion`, `rag`, `generation`, `api`). Plan first and wait for approval.
- Write or update tests with every change and run them before saying you're done. Retrieval or prompt changes also run `tests/eval`.
- Small PRs (under ~400 changed lines). Conventional commits (`feat(rag): ...`).
- The embedding model fixes the vector dimension: don't create the chunks table until the model is decided (spec Section 11).
