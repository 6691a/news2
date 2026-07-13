"""market_data 도메인 DTO (Pydantic).

여기 구현할 것 (예시 yahoo_fetch.py 참고):
- `OHLCVQuery(BaseModel)` — 조회 파라미터 (ticker: str, period: Period, interval: Interval)

CLAUDE.md 규칙: 여러 파라미터는 개별 인자 대신 Pydantic BaseModel로 묶어 전달한다.
"""
