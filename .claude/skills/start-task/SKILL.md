---
description: Start an AI service task with a plan first
argument-hint: <area> <what to build>
disable-model-invocation: true
---
Task: $ARGUMENTS

1. Read `CLAUDE.md`, the spec sections in `docs/project-instructions.md` that cover this task (usually 2, 5, 6, 9), and the related operations in `contracts/ai-service.yaml`.
2. Check: does this need a contract change, a migration, a new dependency, or a prompt change? If yes, list exactly what and STOP.
3. Otherwise write a short plan: files, scope handling, tests (including isolation tests if it touches search), open questions. Wait for my approval.
4. Implement, add tests, run `uv run pytest` and ruff, and summarize what changed.
