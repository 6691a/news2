# AGENTS

작업 시작 전 다음 두 문서를 반드시 읽는다.

- **`docs/README.md`** — 프로젝트 목적·아키텍처·데이터 스키마(§4)·수집 대상. 데이터
  저장 형식/테이블/수집 범위를 결정하기 전에 먼저 확인한다.
- **`.claude/CLAUDE.md`** — 코딩 규칙(학습 모드, 타입/모델, docstring, 커밋 규칙).

두 문서의 지침이 기본 동작보다 우선한다.

## 데이터베이스 / 의존성 주입

- 데이터베이스 연결과 ORM은 **SQLAlchemy**를 사용한다.
- 의존성 주입은 **Python Dependency Injector**를 사용한다.
  - 공식 문서: <https://python-dependency-injector.ets-labs.org/>
- DB 엔진·세션 팩토리·repository·service는 컨테이너에서 조립하고, 구체적인
  provider 구성과 세션 생명주기는 `.claude/CLAUDE.md`의 규칙을 따른다.
