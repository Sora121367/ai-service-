# Isolation tests (required in CI, spec Section 5)

A user must not retrieve:
- another user's personal-workspace chunks
- chunks of a course they don't belong to
- personal sources from inside a course workspace, or course documents from inside a personal workspace
- a selected document_id outside their scope (including a stale chat selection after leaving a classroom)

Also (backend side): a shared set's frozen content cites only documents of its course.
