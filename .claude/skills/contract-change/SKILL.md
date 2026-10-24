---
description: Change the internal API contract as its own PR (contracts/ only)
argument-hint: <what operation/field and why>
disable-model-invocation: true
---
Contract change: $ARGUMENTS

1. Read `contracts/README.md` and `docs/conventions.md` (API section).
2. Edit ONLY `contracts/ai-service.yaml`. No implementation.
3. Every search/chat/generation request keeps a required `scope`. Long work returns 202 + job ID. Deletes are idempotent.
4. Bump `info.version`: additive → minor. Removal/rename → only if a previous release deprecated it, then major.
5. Lint: `npx @redocly/cli lint contracts/ai-service.yaml`.
6. Give me a PR title (`contract: ...`), a list of changed operations, and a note for the backend team on what they must change after upgrading.
