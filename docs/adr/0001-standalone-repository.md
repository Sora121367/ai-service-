# ADR-0001: The AI service is a standalone repository

- Status: Accepted
- Date: 2026-10-24

## Context
InsightHub has five repos: backend (Spring Boot), ai-service, frontend, iOS, Android. The team wants each to stand alone: no shared folder or sibling checkout.

## Decision
- This repo owns `contracts/ai-service.yaml`. A tag `vX.Y.Z` releases it: the YAML as a GitHub release asset, plus a generated Java client `com.insighthub:ai-service-client:X.Y.Z` on GitHub Packages for the backend.
- The backend keeps a read-only copy of the YAML and pins the client version. It upgrades on its own schedule.
- The spec is a copy of the master in the backend repo, refreshed by a `docs:` PR.
- Integration is configuration only: backend callback URL, Keycloak issuer/JWKS/audience, S3 endpoint and bucket.

## Consequences
- Contract changes must stay backward compatible for one release.
- New backend needs arrive as issues in this repo; the AI owner decides the contract shape.
