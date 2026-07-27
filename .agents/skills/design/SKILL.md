---
name: design
description: Use when starting a non-trivial coding task that needs an isolated design phase before implementation, or when the user invokes $design.
---

# Design

Act only as the designer. Create exactly one `docs/plans/NNN-slug.md`; do not implement or verify.

## Procedure

1. Read `.codex/AGENTS.md`, `docs/README.md`, `docs/plans/README.md`, and `docs/plans/TEMPLATE.md`.
2. Trace the relevant existing code end to end. Treat code as the source of truth when it differs from documentation.
3. Inspect `docs/plans/` and select the next three-digit sequence number.
4. Write one plan that follows `docs/plans/TEMPLATE.md` exactly.
5. Set `status: designed` only when §9 has no unresolved questions. Otherwise set `status: blocked`.

## Plan contract

- Make §4 concrete enough that the implementer need not make new design decisions.
- Preserve signatures, schemas, and type definitions where useful, but do not write function bodies or algorithm implementations.
- In §5, name the files and boundaries that implementation must not touch; preserve the template's shared prohibitions.
- Make every §7 item runnable or objectively inspectable. Include a file path, symbol, command, or expected output; phrases such as "works correctly" are not acceptance criteria.
- Put unresolved decisions in §9 with concrete choices. Do not guess.

## Boundaries

- Do not create or modify anything outside `docs/plans/`.
- Do not scaffold source files, start implementation, run verification, commit, or push.
- Do not continue to another phase in this session.

## Return

Report only:

- plan path
- `status`
- number of §7 completion criteria
- unresolved questions when blocked

When designed, direct the user to start a new session with `$implement NNN-slug`.
