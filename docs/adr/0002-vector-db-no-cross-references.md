# ADR-0002: Vector DB owned here; no references into the backend database

- Status: Proposed — confirm with the backend lead (mirrors backend ADR-0003)
- Date: 2026-10-24

## Decision (proposed)
- Chunks store `document_id`, `workspace_id`, `course_id`, etc. as plain indexed UUIDs. No foreign keys, no connection to the backend DB.
- The backend deletes AI data through idempotent endpoints: delete by document, delete by workspace, delete by owner.
- A list-document-ids endpoint lets the backend run a nightly reconciliation.

## Consequences
The contract must define these endpoints before Feature 4.
