---
name: implement
description: Use when implementing an existing docs/plans/NNN-slug.md whose status is designed, or when the user invokes $implement with a plan slug.
---

# Implement

Act only as the implementer. Treat `docs/plans/<slug>.md` as the complete specification.

## Preconditions

1. Read `.codex/AGENTS.md` and the entire plan. Do not read `<slug>.verify.md`.
2. Stop if the plan is missing.
3. Continue only when front matter has `status: designed` and §9 has no unresolved questions.
4. Report the current status and stop for `implemented`, `blocked`, or `verified`.

## Procedure

1. Trace the relevant code and every caller of shared code before editing.
2. Implement §4 and complete §6 in order, reusing existing code and dependencies.
3. Update each finished §6 checkbox. Do not edit §§1–5 or §§7–9.
4. If the implementation changes a schema or collection behavior described in `docs/README.md`, update that document as part of the implementation.
5. Run the smallest checks needed to show the changed code executes. Record facts, not a PASS verdict.
6. When every §6 step is implemented, set front matter to `status: implemented`.

If the plan omits a required decision, contradicts the code, or would require violating §3 or §5, stop, set `status: blocked`, and append a concise `## 구현 중 발견` section. Record optional better approaches there rather than implementing unplanned work.

## Boundaries

- Do not add features, files, dependencies, or refactors absent from the plan.
- Do not change the plan's design body except §6 checkboxes and an appended `## 구현 중 발견`.
- Do not check §7 completion criteria or issue a PASS/FAIL verdict.
- Do not create, read, or modify `<slug>.verify.md`.
- Do not commit, push, amend, or rebase.
- Do not continue to verification in this session.

## Return

Report only:

- changed file paths
- `status`
- whether §5 was violated
- entries from `## 구현 중 발견`, if any

When implemented, direct the user to start a new session with `$verify <slug>`.
