---
id: NNN-slug
title: <한 문장 제목>
status: designed        # designed → implemented → verified | blocked
created: YYYY-MM-DD
---

# NNN-slug

## 1. 목표

<이 작업이 끝나면 무엇이 가능해지는지 1~3문장. "왜"는 여기, "어떻게"는 §4.>

## 2. 배경 / 참고

- 관련 문서: `docs/README.md` §<n>
- 관련 코드: `app/...`
- 선행 작업: <없음 | NNN-slug>

## 3. 범위

### 포함 (In scope)

- <이번 작업에서 만들거나 바꿀 것>

### 제외 (Out of scope)

- <다음 작업으로 미루는 것. 구현자가 "겸사겸사" 손대지 못하게 명시.>

## 4. 설계

<모듈 구조, 클래스/함수 시그니처, 데이터 흐름, DB 스키마 변경, Enum/BaseModel 정의.
구현자가 판단할 여지가 없을 만큼 구체적으로. 필요하면 시그니처만 코드 블록으로.>

## 5. 금지 사항 (Prohibitions)

> 구현 단계에서 이 목록을 위반하면 즉시 중단하고 `status: blocked` 로 기록한다.

- 이 문서(`docs/plans/NNN-slug.md`)를 수정하지 않는다.
- §3 "제외" 항목에 손대지 않는다.
- 현재 실행 환경의 프로젝트 규칙(`.claude/CLAUDE.md` 또는 `.codex/AGENTS.md`)에 있는
  Enum/Pydantic, SQLAlchemy, DI, structlog, UTCDateTime, Alembic,
  구글 스타일 docstring 규칙을 우회하지 않는다.
- `Base.metadata.create_all()` 호출 금지. 스키마 변경은 Alembic revision으로만.
- 커밋·push·rebase 금지.
- <이 작업 고유의 금지 사항: 건드리면 안 되는 파일, 쓰면 안 되는 라이브러리 등>

## 6. 구현 단계

- [ ] 1. <파일/함수 단위로 쪼갠 순서>
- [ ] 2.
- [ ] 3.

## 7. 완료 조건 (Definition of Done)

> 검증 단계는 오직 이 목록만 보고 PASS/FAIL을 판정한다.
> 각 항목은 "실행해서 확인 가능한" 형태로 쓴다. "잘 동작한다" 같은 문장 금지.

- [ ] D1. <예: `app/collectors/ohlcv.py`에 `fetch_ohlcv(query: OHLCVQuery) -> pd.DataFrame` 존재>
- [ ] D2. <예: `uv run ruff check .` 통과>
- [ ] D3. <예: `uv run pyrefly check` 통과>
- [ ] D4. <예: `uv run pytest tests/test_ohlcv.py` 전부 통과>
- [ ] D5. <예: 빈 응답일 때 빈 DataFrame 반환 — 해당 테스트 케이스 존재>

## 8. 검증 방법

```bash
# 검증자가 그대로 실행할 명령
uv run ruff check .
uv run pyrefly check
uv run pytest tests/... -q
```

기대 결과: <각 명령의 통과 기준>

## 9. 미해결 질문

- <설계 단계에서 결정 못 한 것. 남아 있으면 구현 시작 금지.>
