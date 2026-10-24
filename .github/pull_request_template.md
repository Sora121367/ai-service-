## What and why
<!-- One or two sentences. Link the spec section / ADR / issue. -->

## Area
- [ ] ingestion  - [ ] rag  - [ ] generation  - [ ] api  - [ ] contract  - [ ] migration  - [ ] prompts

## Checklist
- [ ] Matches `contracts/ai-service.yaml` (or this PR changes only the contract)
- [ ] Every search path takes and applies a Scope; isolation tests pass
- [ ] No cloud AI calls; no logging of content, prompts or answers
- [ ] Tests added/updated (and `tests/eval` run for retrieval/prompt changes)
- [ ] I reviewed every line Claude wrote and can explain it
