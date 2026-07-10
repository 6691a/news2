# Codex Instructions

## 학습 모드 (최우선)

- 이 프로젝트는 사용자가 직접 코드를 작성하며 학습하는 것이 목적이다.
- Codex는 구현 코드를 대신 작성하지 않는다. 함수 본문, 클래스 로직, 알고리즘 등 실제 동작하는 코드를 파일에 채워 넣지 않는다.
- Codex가 할 수 있는 일:
  - 폴더와 빈 파일 스캐폴딩 생성
  - 각 파일, 함수, 클래스에 무엇을 구현해야 하는지 설명하는 주석, docstring, TODO 작성
  - 채팅으로 설계, 개념, 예시 스니펫 설명
- 사용자가 명시적으로 구현을 요청하지 않는 한, 구현 코드를 생성하지 말고 사용자가 직접 구현하도록 안내한다.

## 타입 / 모델

- 값이 정해진 집합, 예를 들어 조회 기간이나 봉 간격은 `Literal`이 아니라 `Enum` 클래스로 정의한다.
- 여러 파라미터를 함께 넘길 때는 개별 인자 나열 대신 Pydantic `BaseModel`로 묶어 전달한다.
- 모든 함수와 변수에는 타입 힌트를 붙인다.
- 변경 후에는 가능한 범위에서 `ruff`, `pyrefly`, `pytest` 검사를 통과하도록 한다.

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

- 함수를 작성할 때는 구글 스타일 docstring을 작성한다.
- 첫 줄은 한 문장 요약으로 쓴다.
- 인자, 반환값, 예외가 있으면 `Args:`, `Returns:`, `Raises:` 섹션으로 기술한다.
- 인자가 없거나 자명한 한 줄짜리 함수는 요약 한 줄만 있어도 된다.

예시:

```python
def fetch_ohlcv(query: OHLCVQuery) -> pd.DataFrame:
    """야후에서 OHLCV를 받아 스키마 컬럼으로 정규화한다.

    Args:
        query: 조회할 티커, 기간, 봉 간격을 담은 파라미터.

    Returns:
        ticker/ts/timeframe/open/high/low/close/volume 컬럼의 DataFrame.
        데이터가 없으면 빈 DataFrame.
    """
```

## Git / Commit

- Codex는 절대 직접 커밋하지 않는다.
- 커밋 명령 실행, 커밋 생성, amend, rebase, push는 모두 금지한다.
- 커밋은 사용자가 직접 실행한다.
- Codex는 필요할 때 커밋 메시지 초안만 제안한다.
- 커밋 메시지는 Conventional Commits 형식을 따른다.
  - 형식: `<type>(<scope>): <summary>`
  - 예: `chore(pre-commit): uv 기반 로컬 검증 훅 추가`
- 첫 줄은 간결하게 작성하고, 문장형 종결보다 짧은 요약형을 선호한다.
- 본문은 필요할 때만 추가하고, 변경한 내용과 제외/주의 사항을 짧게 적는다.
- 본문은 빈 줄로 구분한다.

예시:

```text
chore(pre-commit): uv 기반 로컬 검증 훅 추가

Ruff, Pyrefly, pytest를 pre-commit의 local hook으로 구성

docs, migrations, devcontainer, static vendor 경로는 자동 검증 대상에서 제외
```
