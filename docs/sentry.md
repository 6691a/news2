# Sentry 오류 및 성능 모니터링

News2는 FastAPI, Celery worker/beat, 단독 실행 Python 모듈의 오류와 성능 정보를
하나의 Sentry 프로젝트로 전송한다. 각 이벤트는 `service=news2`와 `runtime`
태그로 구분된다.

## 필수 환경변수

| 환경변수 | 기본값 | 규칙 |
| --- | --- | --- |
| `SENTRY_DSN` | 없음 | 필수 HTTPS DSN |
| `SENTRY_ENVIRONMENT` | 없음 | 필수, 공백 불가 |
| `SENTRY_RELEASE` | 없음 | 필수, 공백 불가 |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` | `0.0~1.0` |
| `SENTRY_ERROR_SAMPLE_RATE` | `1.0` | `0.0~1.0` |

필수값 누락, 빈 문자열, 잘못된 DSN, 범위를 벗어난 샘플링 값이 있으면 Pydantic
`ValidationError`가 발생하고 프로세스는 시작되지 않는다. Sentry 없이 조용히
계속 실행하는 fallback은 제공하지 않는다.

`SENTRY_ENVIRONMENT`는 `development`, `staging`, `production`처럼
일관된 이름을 사용한다. `SENTRY_RELEASE`에는 배포 버전 또는 Git SHA를 사용한다.
실제 DSN은 `.env`나 배포 플랫폼의 secret 저장소에서 주입하고 커밋하지 않는다.

## 실행 환경별 수집 범위

| runtime | 수집 대상 |
| --- | --- |
| `fastapi` | 처리되지 않은 요청 예외, 5xx, 요청 트랜잭션 |
| `celery` | Celery 공통 모듈 초기화 오류 |
| `celery-worker` | 실패한 task 예외와 task 트랜잭션 |
| `celery-beat` | 스케줄러 예외와 ERROR 이상 로그 |
| `script` | 단독 실행 모듈의 예외, asyncio 오류, ERROR 이상 로그 |

에러 이벤트는 기본 100%, 성능 트랜잭션은 기본 10%를 수집한다. 운영량과 Sentry
할당량에 맞춰 두 환경변수로 비율을 조정한다.

## 개인정보와 인증정보

`send_default_pii=False`가 기본이다. Authorization, cookie, DSN, password,
token, KIS 앱 키·시크릿, FRED 키는 중첩 데이터에서도 `[Filtered]`로 마스킹한다.
민감한 원문을 로그 메시지 문자열 자체에 포함하지 않는다.

## 새로운 실행 모듈 연결

```python
from app.core.config import settings
from app.core.sentry import SentryRuntime, configure_sentry, flush_sentry

configure_sentry(settings, SentryRuntime.SCRIPT)

try:
    run_job()
finally:
    flush_sentry()
```

비동기 모듈은 `run_job()` 대신 `asyncio.run(main())`을 사용한다. 처리되지 않은
예외를 소비하지 않아야 원래의 0이 아닌 종료 코드와 Sentry 보고가 함께 유지된다.

## 처리한 예외 보고

예외를 잡은 뒤 무시하면 Sentry는 알 수 없다. 운영상 확인해야 하는 처리된 예외는
명시적으로 보고하거나 ERROR 로그와 stack trace를 남긴다.

```python
import sentry_sdk

try:
    run_optional_step()
except RecoverableError:
    sentry_sdk.capture_exception()
    logger.error('optional_step_failed', exc_info=True)
```

## 운영 확인과 한계

배포 후 의도적인 테스트 예외 한 건을 발생시키고 Sentry Issues에서 environment,
release, service, runtime 태그를 확인한다. 테스트가 끝나면 테스트 코드는 제거한다.

정상 종료 시 단독 실행 모듈은 대기 이벤트를 flush한다. `SIGKILL`, 시스템 중단,
강제 컨테이너 제거처럼 프로세스가 즉시 종료되는 경우에는 대기 이벤트 전송을
보장할 수 없다.
