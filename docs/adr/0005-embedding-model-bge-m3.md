# ADR-0005: Embedding model: bge-m3 (1024 dimensions)

- Status: Accepted
- Date: 2026-10-24
- Deciders: project owner

## Context
The embedding model fixes the vector dimension of the chunks table (spec Section 11, CLAUDE.md). Content is Khmer and English, retrieval must work across both languages, and all models run locally (hard rule 5).

## Decision
Use `bge-m3` (multilingual, cross-lingual, 1024-dimensional dense vectors). The chunks table uses `vector(1024)` with an HNSW index. The model name comes from `EMBEDDING_MODEL`; the dimension is a fixed constant tied to the migration, not a setting.

## Consequences
- Unblocks the `chunks` migration (next step).
- Changing the model later changes the dimension, so it needs a new migration and a full re-embed of all documents.
- Khmer retrieval quality must be checked in `tests/eval`.
- `.env.example` sets `EMBEDDING_MODEL=bge-m3`.
