"""market_data 도메인 열거형.

여기 구현할 것 (예시 yahoo_fetch.py 참고):
- `Period(str, Enum)`   — yfinance history()가 허용하는 조회 기간 (1d, 5d, 1mo, ..., max)
- `Interval(str, Enum)` — yfinance history()가 허용하는 봉 간격 (1m, ..., 1d, 1wk, 1mo)

CLAUDE.md 규칙: 값이 정해진 집합은 Literal 대신 Enum 클래스로 정의한다.
"""
