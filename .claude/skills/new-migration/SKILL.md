---
description: Create an Alembic migration for the vector DB
argument-hint: <what the migration does>
disable-model-invocation: true
---
Migration: $ARGUMENTS

1. Read `docs/conventions.md` (Vector DB) and ADR-0002. Look at existing files in `migrations/`.
2. Create it with `uv run alembic revision -m "<description>"` and write upgrade + downgrade.
3. Scope columns indexed, HNSW on embeddings, no FKs to anything outside this database.
4. Show me the migration before running it. Then run it against the local vector DB and run the tests.
