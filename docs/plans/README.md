# docs/plans — 설계·구현·검증 워크플로

한 작업(task)은 **설계 → 구현 → 검증** 세 단계를 거친다.
세 단계는 **서로 다른 세션**에서 실행하며, 단계 사이의 유일한 전달 매개체는
이 폴더의 파일이다. 대화 맥락은 넘기지 않는다.

## 파일

| 파일 | 만드는 단계 | 고치는 단계 |
|---|---|---|
| `NNN-slug.md` | 설계 (`/design` 또는 `$design`) | 설계 본문은 설계만. 구현은 `status`/§6, 검증은 `status`/§7만 갱신 |
| `NNN-slug.verify.md` | 검증 (`/verify` 또는 `$verify`) | 검증만 |
| `TEMPLATE.md` | — | 워크플로 자체를 바꿀 때 |

`NNN`은 3자리 일련번호(`001`, `002`, …), `slug`는 영문 소문자-하이픈.

## 상태 전이

```
(없음) --/design--> designed --/implement--> implemented --/verify--> verified
                                    |                          |
                                    +--> blocked <-------------+  (FAIL)
```

- `designed`: 설계 문서 완성. §9 미해결 질문이 비어 있어야 한다.
- `implemented`: 구현 완료. 구현자는 스스로 PASS 판정을 내리지 않는다.
- `verified`: 검증 통과.
- `blocked`: 설계 결함이나 검증 FAIL. 다음 행동은 `/design`으로 돌아가는 것.

## 실행 방법

```
새 세션 →  /design  <무엇을 만들지>       → NNN-slug.md 생성
새 세션 →  /implement NNN-slug            → 코드 작성, status: implemented
새 세션 →  /verify NNN-slug               → NNN-slug.verify.md 생성, PASS/FAIL
```

Codex에서는 같은 순서로 `$design`, `$implement NNN-slug`,
`$verify NNN-slug` 프로젝트 스킬을 사용한다.

**각 단계를 시작하기 전에 반드시 새 대화를 열거나 `/clear`를 실행한다.**
이전 단계의 대화가 남아 있으면 격리가 깨진다 — 특히 검증 단계에서
"구현할 때 이렇게 하기로 했으니 통과" 같은 오염된 판정이 나온다.
