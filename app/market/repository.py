"""market_data 도메인 DB 접근 (스프링 @Repository 역할).

여기 구현할 것:
- OHLCV DataFrame → ohlcv 테이블 upsert (중복 시 갱신)
- 종목/기간별 OHLCV 조회 함수
- ticker ↔ instrument_id 매핑 조회
"""
