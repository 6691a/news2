"""추적 대상 티커 정의.

여기 구현할 것 (예시 yahoo_fetch.py 참고):
- `WATCHED: list[str]`            — §1.4 미국 7종목 (AAPL, GOOGL, MSFT, META, NVDA, QQQ, SPY)
- `MACRO: dict[str, list[str]]`  — §1.5 매크로 지표를 카테고리별(index/reference/fx/rates/commodity)로
- `macro_tickers: list[str]`     — MACRO를 평탄화한 리스트 (수집 루프용)

한국 2종(삼성전자·SK하이닉스)은 yfinance가 아니라 KIS API로 수집.
"""
