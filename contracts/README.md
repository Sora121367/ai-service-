# Contract: `ai-service.yaml`

Owned by this repo. The only consumer is the InsightHub Spring Boot backend (separate repo), which uses released versions.

## Changing it
1. Branch `contract/<short-name>`. Change only `contracts/ai-service.yaml` (use `/contract-change`).
2. Bump `info.version`: additive = minor; removal/rename = major, only after a release that marked it `deprecated`.
3. Review: AI owner + backend lead (add the backend lead as reviewer by hand; they're not in this repo's CODEOWNERS teams by default).
4. Merge, then implement in a separate PR. CI fails if FastAPI's exported OpenAPI differs from this file.
5. Release: tag `v<info.version>` on `main` (e.g. `git tag v0.2.0 && git push origin v0.2.0`). The release workflow attaches the YAML to the GitHub release and publishes the Java client.
6. Tell the backend team; they run `/use-ai-contract <version>` in their repo.

## Rules
- Every operation has a unique camelCase `operationId` and documented error responses (Problem Details).
- Every search, chat or generation request has a required `scope` (see `components/schemas/Scope`).
