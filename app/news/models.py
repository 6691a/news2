"""news 도메인 DB 엔티티 (§4.2).

여기 구현할 것:
- `News`        — news 테이블 (source, url, title, body, published_at, lang, dedup_hash)
- `NewsChunk`   — news_chunks 테이블 (news_id, chunk_index, content, embedding, tsv) — pgvector
"""
