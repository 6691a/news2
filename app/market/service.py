"""market_data 도메인 서비스 (스프링 @Service 역할).

여기 구현할 것 (예시 yahoo_fetch.py 참고):
- `fetch_ohlcv(query: OHLCVQuery) -> pd.DataFrame`
  야후(yfinance)에서 OHLCV를 받아 §4.2 ohlcv 스키마 컬럼
  (ticker/ts/timeframe/open/high/low/close/volume)으로 정규화.
- (추후) 수집 → repository 저장까지 묶는 수집 유스케이스

CLAUDE.md 규칙: 구글 스타일 docstring + 타입 힌트 + ruff/pyrefly 통과.
"""
