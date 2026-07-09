"""news 도메인 서비스 (§3 수집, §4.3 전처리).

여기 구현할 것:
- 수집: 네이버 뉴스 API / RSS / Finnhub / DART / EDGAR
- 전처리 파이프라인: dedup → NER 종목 매핑 → 관련성 필터 → 청킹 → 임베딩
"""
