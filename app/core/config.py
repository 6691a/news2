"""전역 설정.

여기 구현할 것:
- pydantic-settings `BaseSettings`를 상속한 `Settings` 클래스
  (예: `database_url` 등 .env/환경변수에서 읽는 공용 설정)
- 설정 싱글턴 반환 함수 (예: `@lru_cache` 적용한 `get_settings()`)

참고: 도메인 공통 설정만 여기 두고, 도메인 전용 설정은 각 도메인 패키지에 둔다.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
