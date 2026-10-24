# ADR-0003: Long-running jobs: HTTP in, callback out, queue stays internal

- Status: Proposed — confirm with the backend lead (mirrors backend ADR-0004)
- Date: 2026-10-24

## Decision (proposed)
- Backend → AI: HTTP request with an idempotency key; long work returns `202` + job ID.
- AI → backend: callback to `BACKEND_CALLBACK_URL` on progress, success or failure, authenticated with this service's client-credentials token. `GET /jobs/{id}` is the polling fallback.
- The internal queue (Redis + arq or Celery, to choose) is an implementation detail of this repo.

## Consequences
Callback schema and retry rules are part of `contracts/ai-service.yaml`. Failed callbacks retry with backoff; the backend may also poll.
