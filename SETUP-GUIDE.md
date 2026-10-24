# AI service repo: setup for team work with Claude Code

This guide gets the AI service repo ready for the first feature. It doesn't include any feature implementation.
This repo stands alone: you never need the backend repo on disk. The two repos meet only through the released contract and configuration (URLs, Keycloak issuer, S3 endpoint).
**AI owner** = the person responsible for this repo. **Everyone** = every AI developer.

## Step 0. Agree with the backend lead (30 minutes)

| Decide | Write it in |
|---|---|
| Who owns this repo and who reviews contracts, migrations and prompts | `.github/CODEOWNERS` |
| ADR-0002: no cross-database references; delete endpoints + reconciliation | `docs/adr/0002-...md` (and the backend's ADR-0003) |
| ADR-0003: HTTP in, callback out; internal queue (Redis + arq or Celery) | `docs/adr/0003-...md` (and the backend's ADR-0004) |
| Keycloak clients the backend lead adds to the realm: audience `insighthub-ai-service`, callback client `insighthub-ai-callback` | backend repo, `keycloak/` |
| Bucket name shared with the backend | `.env.example` (`S3_BUCKET`) |
| Shared dev GPU server URL (for people without a GPU) | team notes / `.env` |

## Step 1. Install tools (Everyone)

- Git, Docker Desktop (Compose 2.20 or newer), `jq`, Python 3.12, [uv](https://docs.astral.sh/uv/)
- A Claude plan that includes Claude Code (Pro, Max, Team or Enterprise), and Claude Code itself (https://code.claude.com/docs/en/setup):

```bash
curl -fsSL https://claude.ai/install.sh | bash      # macOS / Linux / WSL
irm https://claude.ai/install.ps1 | iex             # Windows PowerShell
claude                                              # first run: log in through the browser
```

On Windows, use WSL or Git Bash, because the team hook is a bash script.

## Step 2. Prepare and push the repo (AI owner)

```bash
unzip insighthub-ai-service.zip && cd insighthub-ai-service
# 1. Copy the spec from the backend repo's docs/project-instructions.md (master) into docs/project-instructions.md,
#    and write its version (date or commit) on the first line.
# 2. Replace @your-org/... in .github/CODEOWNERS.
git init -b main
git add .
git commit -m "chore: initial AI service skeleton, contract, docs and Claude Code setup"
git remote add origin git@github.com:<org>/insighthub-ai-service.git     # private, empty repo
git push -u origin main
```

Check that it works:

```bash
uv sync
cp .env.example .env
docker compose --profile standalone up -d          # vector DB, Redis, own RustFS
docker compose ps                                  # all services running
```

## Step 3. Protect `main` (AI owner)

GitHub → Settings → Rules → Rulesets, target `main`:

- Require a pull request, with **1 approval** and **review from Code Owners**
- Require status checks: **only `ci-ok`**
- Block force pushes, require linear history; restrict who can push tags `v*` (releases)
- Settings → General: squash merge only, "Automatically delete head branches"

## Step 4. Set up each laptop (Everyone)

```bash
git clone git@github.com:<org>/insighthub-ai-service.git     # any folder you like
cd insighthub-ai-service && cp .env.example .env && uv sync
claude                       # ALWAYS start Claude at the repo root
```

**First-session check (5 minutes):**

| Type in Claude Code | You should see |
|---|---|
| `/memory` | `CLAUDE.md` is loaded |
| `/permissions` | The allow, ask and deny rules from `.claude/settings.json` |
| `/hooks` | The PostToolUse ruff hook |
| `/` | `/start-task`, `/contract-change`, `/new-migration`, `/resolve-conflicts`, `/pre-pr` |
| "Summarize the hard rules of this repo" | The 10 hard rules, starting with the mandatory scope filter |

Personal preferences go in `CLAUDE.local.md` (gitignored).

**Which mode to run:**

| You need | Do this |
|---|---|
| Unit tests, ingestion or RAG work without the backend | `docker compose --profile standalone up -d`, set `S3_ENDPOINT=http://localhost:9100` in `.env`. Tests use generated JWTs, no Keycloak needed. |
| Real end-to-end calls from Spring Boot | Someone runs the backend's local stack (Keycloak :8180, RustFS :9000) on this machine, or you use the shared dev servers. Keep the default URLs in `.env` (or point them at the dev servers), then `docker compose up -d` and run the API with uv. |
| LLM without a local GPU | Set `OLLAMA_URL` to the shared GPU server. With a GPU: add `--profile gpu`. |

## Step 5. Setup tasks with Claude Code (before any feature)

One PR each, in order. Use plan mode (Shift+Tab) and read the plan before approving.

| # | Who | Prompt |
|---|---|---|
| 1 | AI owner | `/start-task api Set up the FastAPI skeleton: dependencies in pyproject.toml, pydantic-settings config from .env.example, app/main.py with only /health, app/worker.py stub, Alembic config in migrations/. No business logic.` |
| 2 | AI owner | `Add to CI a check that exports app.openapi() and fails if it differs from contracts/ai-service.yaml, plus a breaking-change check against main. Plan first.` |
| 3 | AI owner + backend lead | `Complete .github/workflows/release.yml: generate the Java client (com.insighthub:ai-service-client, version from the tag) and publish it to GitHub Packages. Plan first.` |
| 4 | AI owner | `Add JWT validation middleware: issuer, JWKS URL, audience and allowed client from config; reject everything else. Tests with locally generated keys.` |
| 5 | AI owner | `/contract-change scope schema, job + callback schemas, delete-by-document/workspace/owner and list-document-ids endpoints (ADR-0002, ADR-0003)` |
| 6 | AI owner | `Write the isolation test cases listed in tests/isolation/README.md as pending tests (skipped until search exists).` |

When 1–5 are merged, release the first contract: `git tag v0.1.0 && git push origin v0.1.0`. Tell the backend team to run `/use-ai-contract 0.1.0`.

## Step 6. Daily workflow (Everyone)

```
morning    git pull  →  git switch -c feat/<area>-<short-name>
work       claude → /start-task <area> <task>   (Claude plans → you approve → it codes and tests)
           rebase daily: git pull --rebase origin main
before PR  claude → /pre-pr  → open the PR (under ~400 lines) → a human reviews every line
```

**When the backend needs something new:** they open an issue here. You change the contract (`/contract-change`), get the backend lead's review, merge, implement, then tag `vX.Y.Z`. Keep it backward compatible: the backend upgrades on its own schedule.

## Step 7. When things conflict

| Situation | What to do |
|---|---|
| Git conflict in your branch | `git pull --rebase origin main`, then `/resolve-conflicts`. Check each resolution and run the tests. |
| Conflict in `contracts/`, `migrations/`, `app/prompts/`, `docs/`, `CLAUDE.md`, `uv.lock` | Claude stops. Resolve with the other owner (`uv.lock`: take main's, then `uv lock`). |
| The backend and this repo disagree on the API | The released contract is the truth. Change it only through a contract PR and a new release. |
| The spec changed in the backend repo | Refresh `docs/project-instructions.md` in a `docs: sync spec <version>` PR. |
| Two people's Claude sessions chose different conventions | Decide together, write an ADR, add one line to `CLAUDE.md`. |

## Ready-for-first-feature checklist (AI owner)

- [ ] Spec copied into `docs/project-instructions.md` with its version
- [ ] CODEOWNERS filled in; ADR-0002 and ADR-0003 agreed with the backend lead
- [ ] Repo pushed, `main` protected with `ci-ok`, CI green
- [ ] Setup tasks 1–5 merged and `v0.1.0` released (YAML on the release, Java client published)
- [ ] Keycloak audience and callback client added in the backend repo's realm
- [ ] Shared dev GPU server URL known, or Ollama runs locally
- [ ] Embedding model decision scheduled (before the first chunks migration)
