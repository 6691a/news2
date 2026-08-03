# 코딩 규칙

## 에이전트 지침 파일 위치

- Claude 전용 지침은 **`.claude/CLAUDE.md`**, Codex 전용 지침은
  **`.codex/AGENTS.md`** 에 둔다.
- 프로젝트 루트에 `AGENTS.md`를 새로 만들지 않는다. 루트에서 발견한 기존 지침은
  `.codex/AGENTS.md`에 병합한 뒤 루트 파일을 제거한다.
- 두 지침 파일의 공통 규칙을 변경할 때는 함께 갱신하되, 에이전트별 이름과
  도구 사용 방식처럼 실행 환경에 종속된 차이는 유지한다.

## 프로젝트 배경 (작업 전 반드시 읽을 것)

- 이 저장소의 목적·아키텍처·데이터 스키마·수집 대상은 **`docs/README.md`** 에 정의되어 있다.
- 데이터 저장 형식, 테이블 설계, 수집 주기, 종목/지표 범위를 결정하기 전에
  `docs/README.md`(특히 §3 수집, §4 저장 스키마)를 먼저 확인한다.
- **단, `docs/README.md`는 첫 설계 초안이다. 100% 신뢰하지 말고 참고 자료로 취급한다.**
  - 문서와 실제 코드가 다르면 **코드가 소스 오브 트루스** — 문서를 근거로 코드를 되돌리지 않는다.
  - 구현 중 설계가 문서와 달라지면(스키마 변경, 테이블 추가/삭제, 수집 방식 변경 등)
    해당 작업에서 `docs/README.md`의 관련 섹션도 **함께 갱신**한다 (문서 갱신은 에이전트가 해도 됨).

## 국가별 패키지 경로

- 국가별 매크로 코드는 국가를 디렉터리 네임스페이스로 분리한다.
  예: `app/macro/us/treasury` (`app.macro.us.treasury`).
- `app/macro/us_treasury`처럼 국가와 기능을 밑줄로 합친 패키지는 만들지 않는다.
- 테스트 경로도 앱 경로를 그대로 따라 `tests/macro/us/treasury`에 둔다.
- DB 테이블·컬럼·로그 이벤트 같은 데이터 식별자는 이 규칙의 대상이 아니며 `snake_case`를 유지한다.

## 데이터 수집 (이중 그레인 원칙)

- 새 시세·지표를 수집할 때는 **두 그레인을 모두 확보할 수 있는지 먼저 확인하고,
  가능하면 둘 다 수집한다.**

  | 그레인 | 용도 | 성질 |
  |---|---|---|
  | 장중 1분봉·잠정치 | 당일 흐름 판단, 장중 대응 | 갱신 중인 값. 사후 정정될 수 있다 |
  | 장 마감 확정값 | 과거 분석·백테스트·예측 | 소스 오브 트루스. 수정주가·정산가 반영 |

- 한쪽만 만들고 끝내지 않는다. 확정값이 없으면 백테스트가 성립하지 않고,
  장중 값이 없으면 당일 대응을 할 수 없다.
- **확정값 소스가 없는 지표는 "없다"는 사실을 문서와 코드 주석에 남긴다**
  (예: ZN 선물은 무료 공식 정산가가 없음). 조사하고 없는 것과 빠뜨린 것이 구분되어야 한다.
- 두 그레인은 서로 덮어쓰지 않고 **각각 저장**한다. 장중 잠정치를 확정치로 갱신해 버리면
  "몇 시부터 흐름이 바뀌었는가"를 사후에 재구성할 수 없다.
- 확정값에는 **과거 백필 경로**를 함께 만든다(`python -m <패키지> <날짜|기간>`).
  백필이 불가능한 그레인(소스 보관 기간이 제한된 1분봉 등)은 그 한계를 주석에 적는다.
- **백필 기준 시작일은 `2025-01-01`이다** (`app/core/collection.py`의 `BACKFILL_START`).
  새 지표를 붙일 때도 이 상수를 가져다 쓰고, 진입점은 `backfill` 인자(`BACKFILL_KEYWORD`)로
  통일한다 — `python -m <패키지> backfill`.
  - 소스가 그 날짜부터 주지 못하면(상장이 늦거나 보관 기간이 짧으면) **실패로 보지 않고
    소스가 주는 가장 이른 데이터부터 담는다.** 빈 구간을 메우려고 다른 소스를 끌어오지 않는다.
  - 어디부터 실제로 담겼는지는 수집 로그의 `first_ts` 구조화 필드로 남긴다.
    "요청은 2025-01인데 데이터는 2025-06부터"인 상태가 로그만 보고 드러나야 한다.
- 실시간 tick은 1분봉을 대신하지 않는다. 프로세스가 죽은 구간이 영구 결손이 되고,
  수정주가가 반영되지 않으며, 과거 백필 경로가 없다.

## 테스트

- 테스트는 `httpx.MockTransport` 같은 수단으로 네트워크를 타지 않게 만든다.
  실제 도메인으로 나가는 테스트를 작성하지 않는다.

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

## 데이터베이스 / 의존성 주입

- 데이터베이스 연결, 트랜잭션, ORM 모델과 쿼리는 **SQLAlchemy**를 사용한다.
  DB 드라이버를 애플리케이션 코드에서 직접 호출하지 않는다.
- 의존성 주입은 **Python Dependency Injector**를 사용한다.
  - 공식 문서: <https://python-dependency-injector.ets-labs.org/>
  - FastAPI + SQLAlchemy 예제:
    <https://python-dependency-injector.ets-labs.org/examples/fastapi-sqlalchemy.html>
- `containers.DeclarativeContainer`에 설정, DB 엔진/세션 팩토리, repository,
  service provider를 선언한다. 애플리케이션 진입점은 컨테이너를 생성하고 필요한
  모듈을 wiring한다.
- `Settings` 인스턴스를 provider로 등록하고, DB URL 등 개별 설정값은
  `settings.provided.<field>`로 의존 객체에 주입한다. 컨테이너 초기화 코드에서
  `from_value()`로 필드를 다시 복사하거나 연결 문자열을 하드코딩하지 않는다.
- 엔진과 세션 팩토리는 애플리케이션 생명주기 동안 재사용할 수 있지만,
  `Session`/`AsyncSession` 인스턴스는 싱글턴으로 공유하지 않는다. 세션은 작업 단위마다
  생성하고 성공 시 commit, 실패 시 rollback한 뒤 항상 close한다.
- 데이터베이스 스키마 생성과 변경은 **Alembic revision**으로만 관리한다.
  애플리케이션 코드나 시작 과정에서 `Base.metadata.create_all()`을 호출하지 않는다.
- 영속 ORM 모델은 `app.core.models.EntityModel`을 상속한다. 공통 `id`, `created_at`,
  `updated_at`을 개별 모델에서 중복 선언하지 않는다.
- 모든 `datetime` 컬럼은 `UTCDateTime`을 사용하고 timezone-aware UTC 값만 저장한다.
  - naive datetime은 저장 단계에서 거부한다.
  - KST 또는 거래소 현지시각은 timezone을 적용해 UTC로 변환한 뒤 저장한다.
  - 현지 날짜·시간 원본이 필요하면 `details` JSONB에 문자열로 보존하고, 별도의
    non-UTC timestamp 컬럼을 만들지 않는다.
  - PostgreSQL 연결과 Alembic 연결의 세션 timezone도 `UTC`로 설정한다.
- repository와 service는 생성자 주입을 기본으로 하며, 내부에서 전역 컨테이너를
  조회하는 Service Locator 패턴을 사용하지 않는다.
- 테스트에서는 실제 전역 의존성을 교체하지 말고 Dependency Injector의 provider
  override를 사용해 DB 또는 repository를 격리한다.

## Celery / 스케줄

- Celery task 함수는 그 기능을 담당하는 패키지의 **`tasks.py`** 에만 둔다.
  다른 모듈이나 `app/core/celery.py`에 task를 직접 정의하지 않는다.
- beat 스케줄 정의는 같은 패키지의 **`beats.py`** 에 둔다. `app/core/celery.py`는
  Celery 앱 인스턴스와 공통 설정만 갖고, 각 패키지의 `beats.py`를 모아 등록한다.
- 함수 이름에 역할을 접두사로 붙인다.
  - task 함수: **`task_`** 로 시작한다 (예: `task_collect_intraday`).
  - beat 정의 함수: **`beat_`** 로 시작한다. 패키지마다 `beat_schedule()` 하나를 두고
    그 패키지의 항목 딕셔너리를 반환한다.
- `beats.py`는 task 모듈을 import하지 않고 task 이름 문자열만 참조한다.
  (`app/core/celery.py` → `beats.py` → `tasks.py` 순환 import를 막는다.)
- task 이름 문자열(`@app.task(name=...)`)은 접두사 규칙과 무관하게 기존처럼
  `<도메인>.<동작>` 형식을 유지한다.

## 로깅

- 애플리케이션 코드에서는 `app.core.logging.get_logger()`로 받은 structlog 로거만 사용한다.
  `logging.getLogger()`와 `logging.basicConfig()`를 개별 모듈에서 직접 호출하지 않는다.
- structlog와 외부 라이브러리 로그의 handler, processor, renderer 설정은
  `app.core.logging.configure_logging()`에서만 관리한다.
- 이벤트 이름은 `snake_case`로 작성하고, 동적 값은 문자열 보간 대신 구조화 필드로 전달한다.
- 모든 로그 timestamp는 UTC ISO 8601 형식으로 출력한다. 로컬은 `console`, 운영 환경은
  `json` 형식을 사용하며 `LOG_FORMAT`과 `LOG_LEVEL`은 `Settings`를 통해 주입한다.

### 실패는 조용히 묻지 않는다

- **외부 API 응답이 4xx·5xx면 반드시 `ERROR` 로그를 남기고 예외를 올린다.**
  `app.core.http.raise_for_status()`를 쓴다. `response.raise_for_status()`를 직접
  부르지 않는다 — 예외는 올라가지만 상태 코드가 구조화 필드로 남지 않아 운영에서
  `429`·`500`을 집계하거나 알림 규칙을 걸 수 없다.
- 실패를 삼키고 빈 결과·`None`·기본값으로 대체하지 않는다. 저장 0건과 호출 실패는
  로그에서 구분되어야 한다. "값이 안 들어왔는데 아무 로그도 없는" 상태를 만들지 않는다.
- 예외를 잡아 흐름을 계속할 때는(예: 개별 틱 저장 실패) 반드시 `logger.exception()`
  또는 `logger.warning()`으로 남기고, 무엇을 건너뛰었는지 구조화 필드에 적는다.
  `except ... : pass`는 이유를 주석으로 설명할 수 있을 때만 쓴다.

**예외만이 아니라 "조용히 줄어드는 것" 전부가 대상이다.** 데이터가 사라지는 자리는
예외보다 필터·건너뛰기 쪽이 훨씬 많고, 그쪽이 더 늦게 발견된다.

- **행을 버리는 모든 필터는 버린 건수를 남긴다.** 파서의 결측 행 제거, 자리 채움 행 제거,
  미확정 봉 제외, 미등록 대상 건너뛰기가 전부 해당한다. 응답 형식이 바뀌어 멀쩡한 행을
  버리기 시작해도 `received`/`parsed`/`dropped` 건수만 보면 드러나야 한다.
- **0건 결과는 정상일 수 있어도 `WARNING`으로 남긴다.** 휴장으로 0건인 것과 심볼·설정을
  잘못 넣어 0건인 것은 응답 모양이 같다. 조용히 넘어가면 그 대상만 영영 비어 있는다.
- **빈 응답과 호출 실패를 로그에서 구분한다.** 외부 라이브러리가 없는 심볼에 예외 대신
  빈 결과를 주는 경우가 있다(yfinance). "성공했지만 0건"도 사건으로 남긴다.
- 정상 경로에도 `received`·`parsed`·`saved` 같은 건수를 남겨, 어제와 오늘을 비교할 수
  있게 한다. 저장 0건과 수집 0건이 로그에서 갈라져야 한다.
- 판단이 서지 않으면 **로그를 남기는 쪽**을 고른다. 시끄러운 로그는 나중에 줄일 수 있지만,
  남기지 않은 사건은 복구할 수 없다.
- 로그에 **비밀값을 남기지 않는다.** URL 쿼리에 API 키가 실릴 수 있으므로
  (FRED `api_key`) 전체 URL 대신 host와 path만 남긴다. 응답 본문은 앞부분만 남긴다.

### HTTP 상태 코드 표기

- 상태 코드를 코드에 적을 때는 `200`·`429` 같은 숫자 리터럴 대신
  **`fastapi.status` 상수**를 쓴다 (`status.HTTP_200_OK`, `status.HTTP_429_TOO_MANY_REQUESTS`).
- **테스트만이 아니라 `app/` 아래 애플리케이션 코드를 포함한 모든 코드에 적용된다.**
  응답 생성, 상태 비교, 상수 정의, 재시도 대상 목록 어디에서든 숫자를 직접 적지 않는다.
- 응답에서 읽어 온 값(`response.status_code`)을 그대로 담거나 로깅하는 것은 해당 없다.
  비교·생성처럼 **코드에 숫자를 직접 적는 자리**가 대상이다.
  주석·docstring에서 `4xx`·`5xx`처럼 범위를 설명하는 것도 해당 없다.

```python
from fastapi import status

return httpx.Response(status.HTTP_502_BAD_GATEWAY, request=request)
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
