# 코딩 규칙

## 프로젝트 배경 (작업 전 반드시 읽을 것)

- 이 저장소의 목적·아키텍처·데이터 스키마·수집 대상은 **`docs/README.md`** 에 정의되어 있다.
- 데이터 저장 형식, 테이블 설계, 수집 주기, 종목/지표 범위를 결정하기 전에
  `docs/README.md`(특히 §3 수집, §4 저장 스키마)를 먼저 확인한다.
- **단, `docs/README.md`는 첫 설계 초안이다. 100% 신뢰하지 말고 참고 자료로 취급한다.**
  - 문서와 실제 코드가 다르면 **코드가 소스 오브 트루스** — 문서를 근거로 코드를 되돌리지 않는다.
  - 구현 중 설계가 문서와 달라지면(스키마 변경, 테이블 추가/삭제, 수집 방식 변경 등)
    해당 작업에서 `docs/README.md`의 관련 섹션도 **함께 갱신**한다 (문서 갱신은 에이전트가 해도 됨).

## 학습 모드 (최우선 — 반드시 지킬 것)

- 이 프로젝트는 **사용자가 직접 코드를 작성하며 학습**하는 것이 목적이다.
- **Codex는 구현 코드를 대신 작성하지 않는다.** 함수 본문·클래스 로직·알고리즘 등
  실제 동작하는 코드를 파일에 채워 넣지 말 것.
- Codex가 할 수 있는 것:
  - 폴더/빈 파일(스캐폴딩) 생성
  - 각 파일/함수에 **무엇을 구현해야 하는지 설명하는 주석·docstring·TODO**
  - 채팅으로 설계·개념·예시 스니펫 설명 (사용자가 참고해 직접 작성)
- 사용자가 "직접 작성한다"는 전제이므로, 다음 답변이나 유사 상황에서도
  요청이 없는 한 구현 코드를 생성하지 않는다. 필요하면 "직접 구현해 보라"고 안내한다.

## 타입 / 모델

- 값이 정해진 집합(예: 조회 기간, 봉 간격)은 `Literal`이 아니라 **Enum 클래스**로 정의한다.
- 여러 파라미터를 함께 넘길 때는 개별 인자 나열 대신 **Pydantic `BaseModel`** 로 묶어 전달한다
  (검증 + 자동완성 + 문서화 이점).
- 모든 함수/변수에 타입 힌트를 붙이고, `ruff`와 `pyrefly` 검사를 통과해야 한다.

예시:

```python
from enum import Enum
from pydantic import BaseModel


class Interval(str, Enum):
    DAY_1 = "1d"
    MIN_1 = "1m"


class OHLCVQuery(BaseModel):
    ticker: str
    interval: Interval = Interval.DAY_1
```

## Docstring

- 함수를 작성할 때는 **구글 스타일 docstring**을 작성한다.
- 첫 줄은 한 문장 요약. 인자/반환/예외가 있으면 `Args:` / `Returns:` / `Raises:` 섹션으로 기술한다.
- 인자가 없거나 자명한 한 줄짜리 함수는 요약 한 줄만 있어도 된다.

예시:

```python
def fetch_ohlcv(query: OHLCVQuery) -> pd.DataFrame:
    """야후에서 OHLCV를 받아 §4.2 ohlcv 스키마 컬럼으로 정규화한다.

    Args:
        query: 조회할 티커·기간·봉 간격을 담은 파라미터.

    Returns:
        ticker/ts/timeframe/open/high/low/close/volume 컬럼의 DataFrame.
        데이터가 없으면 빈 DataFrame.
    """
```

## Git / Commit

- **Codex는 절대 직접 커밋하지 않는다.** 커밋 명령 실행, 커밋 생성, amend, rebase, push 모두 금지한다.
- 커밋은 사용자가 직접 실행한다. Codex는 필요할 때 커밋 메시지 초안만 제안한다.
- 커밋 메시지는 Conventional Commits 형식을 따른다.
  - 형식: `<type>(<scope>): <summary>`
  - 예: `chore(pre-commit): uv 기반 로컬 검증 훅을 추가`
- 첫 줄은 간결하게 작성하고, `한다`처럼 문장형 종결보다 짧은 요약형을 선호한다.
- 본문은 필요할 때만 추가하고, 변경한 내용과 제외/주의 사항을 짧게 적는다.
- 본문은 빈 줄로 구분한다.

예시:

```text
chore(pre-commit): uv 기반 로컬 검증 훅을 추가

Ruff, Pyrefly, pytest를 pre-commit의 local hook으로 구성

docs, migrations, devcontainer, static vendor 경로는 자동 검증 대상에서 제외
```
