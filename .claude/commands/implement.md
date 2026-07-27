---
description: implementer 에이전트에 구현을 위임한다
argument-hint: <NNN-slug>
allowed-tools: Task, Read
---

# /implement

대상: `docs/plans/$ARGUMENTS.md`

너는 **디스패처**다. 직접 구현하지 마라.

## 절차

1. 설계 문서의 front matter만 확인한다.
   - 파일이 없으면 → `/design` 부터 하라고 안내하고 중단.
   - `status`가 `designed`가 아니면 중단하고 현재 상태를 알린다.
   - **문서 본문은 읽지 마라.** 설계 내용이 이 세션에 남으면 이어지는
     `/verify`의 판정이 오염된다.
2. `implementer` 에이전트를 호출한다. 전달할 것은 슬러그(`$ARGUMENTS`) 하나뿐이다.
   설계 내용을 요약해서 넘기지 마라 — 에이전트가 문서를 직접 읽는다.
3. 반환된 결과를 그대로 전달한다.

## 금지

- 직접 코드를 작성·수정하지 않는다.
- 에이전트의 구현 결과를 재검토하거나 "이 부분이 좋다/아쉽다"고 평가하지 않는다.
  평가는 `/verify`가 격리된 상태에서 한다.
- 검증 리포트를 만들거나 합격 판정을 내리지 않는다.
- 커밋·push 금지.

## 마무리

바뀐 파일 목록과 `status`를 알리고:

> `/verify $ARGUMENTS`
