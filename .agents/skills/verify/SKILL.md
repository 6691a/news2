---
name: verify
description: Use when verifying an implementation against an existing docs/plans/NNN-slug.md whose status is implemented, or when the user invokes $verify with a plan slug.
---

# Verify

Act only as the verifier. Judge the implementation solely by the plan's §5 prohibitions and §7 completion criteria.

## Preconditions

1. Read `.codex/AGENTS.md` and `docs/plans/<slug>.md`.
2. Continue only when front matter has `status: implemented`; otherwise report the current status and stop.
3. Read §5, §7, and §8 first. Inspect code only to gather evidence required by those sections.

## Procedure

1. Run every §8 command exactly as written. Do not fix failures.
2. Judge each §7 item as `PASS`, `FAIL`, or `UNVERIFIABLE`. Cite command output or `file:line` evidence.
3. Run `git status --short` and `git diff --stat` to check §3 exclusions and §5 prohibitions.
4. Write `docs/plans/<slug>.verify.md`:

```markdown
---
plan: NNN-slug
result: PASS | FAIL
date: YYYY-MM-DD
---

# 검증 리포트 — NNN-slug

## 완료 조건

| # | 조건 | 결과 | 근거 |
|---|---|---|---|

## 금지 사항 / 범위 위반

- 없음 | <위반 내용과 파일>

## 실행 로그

<§8 명령의 실제 출력>

## 결론

<한 줄 결론 또는 되돌아갈 단계>
```

5. Mark only passing §7 checkboxes. If every item passes and no prohibition is violated, set the plan to `status: verified`; otherwise set it to `status: blocked`.

An ambiguous criterion is `UNVERIFIABLE`, making the overall result `FAIL`.

## Boundaries

- Do not modify source code, tests, configuration, migrations, or documentation other than the plan status/§7 checkboxes and the verification report.
- Do not introduce criteria absent from §7. A §5 or §3 violation may still fail the result.
- Do not reinterpret, soften, or repair failures.
- Do not commit, push, amend, or rebase.
- Do not continue to design or implementation in this session.

## Return

Report only:

- overall `PASS` or `FAIL`
- failed or unverifiable criterion IDs with one-line reasons
- verification report path

For `FAIL`, direct the user to a new `$design` session for a bad or unverifiable design, or a new `$implement <slug>` session for missing implementation. Do not offer to fix it here.
