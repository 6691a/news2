"""relation 도메인 DB 엔티티 (§6.2 경량 관계 레이어).

여기 구현할 것:
- `Entity`             — entities 테이블 (name, ticker, type, aliases)
- `Relation`           — relations 테이블 (source_id, target_id, rel_type, weight, valid_from)
- `NewsEntityMention`  — news_entity_mentions 테이블 (news_id, entity_id, sentiment, confidence)
"""
