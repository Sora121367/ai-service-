---
description: Check the branch before opening a PR
disable-model-invocation: true
---
1. `git fetch origin && git diff --stat origin/main...HEAD`. Warn if over ~400 lines or touching more than one area.
2. Check every search path takes a Scope, and new endpoints match `contracts/ai-service.yaml`.
3. Search the diff for secrets, cloud AI calls, logging of content/prompts/answers, and fetches without SSRF protection.
4. Run `uv run ruff check . && uv run ruff format --check . && uv run pytest`.
5. Draft the PR title (Conventional Commits) and fill in `.github/pull_request_template.md`.
