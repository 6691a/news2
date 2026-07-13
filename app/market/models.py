"""market_data 도메인 DB 엔티티 (§4.2 스키마).

여기 구현할 것:
- `Instrument` — instruments 테이블 (ticker, market, name, is_watched)
- `Ohlcv`      — ohlcv 테이블 (instrument_id, ts, timeframe, open/high/low/close, volume)

core/database.py 의 declarative Base를 상속.
"""
