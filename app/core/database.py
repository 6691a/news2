"""DB 연결 (§4.1 PostgreSQL 단일 저장소).

여기 구현할 것:
- SQLAlchemy 2.0 엔진 생성 (config.get_settings().database_url 사용)
- 세션 팩토리 (sessionmaker) + 세션 획득 의존성
- 공용 declarative Base (모든 도메인 models.py가 상속)
"""
