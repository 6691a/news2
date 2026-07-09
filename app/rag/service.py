"""rag 도메인 서비스 (§5 하이브리드 검색).

여기 구현할 것:
- 벡터 검색(pgvector cosine) + 키워드 검색(tsvector) → RRF 결합
- 시간 가중치(recency decay)
- "필터 먼저(종목·기간·소스), 유사도는 그 다음" 원칙
"""
