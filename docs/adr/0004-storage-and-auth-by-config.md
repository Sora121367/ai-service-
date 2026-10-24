# ADR-0004: Object storage and auth reached by configuration

- Status: Accepted
- Date: 2026-10-24

## Decision
- Files live in RustFS (S3-compatible), shared with the backend. Access only through boto3 with path-style addressing, endpoint and bucket from config.
- Incoming requests must carry a Keycloak JWT from the backend's service client (`insighthub-ai-caller`) with audience `insighthub-ai-service`. Issuer, JWKS URL and audience come from config.
- Local dev: point to the backend's local Keycloak and RustFS by URL, or run `--profile standalone` (own RustFS) for work that doesn't need them.
