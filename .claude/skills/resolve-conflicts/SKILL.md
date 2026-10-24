---
description: Resolve git rebase/merge conflicts safely and explain each choice
disable-model-invocation: true
---
1. Run `git status` and list every conflicted file.
2. If any conflicted file is in `contracts/`, `migrations/`, `app/prompts/`, `docs/`, `CLAUDE.md` or `uv.lock`: STOP and tell me which. A human decides those (for `uv.lock`: take main's version, then `uv lock`).
3. For each other file: read both sides and the commits behind them (`git log --merge -p -- <file>`), keep both intents, explain each resolution in one line.
4. Run `uv run pytest`. Don't continue the rebase until I confirm.
