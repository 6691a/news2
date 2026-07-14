"""국내주식 실시간 tick 저장 테이블 (docs/README §4.2 tick 스키마).

여기 구현할 것 — `app.core.database.Base`를 상속하는 ORM 클래스 2개
(SQLAlchemy 2.0 `Mapped[...]` / `mapped_column` 스타일):

1. `KoreaTrade` → 테이블 `korea_trades`
   - id: BIGSERIAL PK (자연키 없음 — 같은 초에 다건 체결 가능)
   - stock_code: TEXT NOT NULL ('005930')
   - ts: TIMESTAMPTZ NOT NULL — DTO의 business_date + trade_time을 KST aware로 결합
   - price: NUMERIC NOT NULL (current_price)
   - volume: BIGINT NOT NULL (trade_volume, 직전 체결 수량)
   - cumulative_volume: BIGINT NOT NULL
   - trade_classification_code: TEXT NOT NULL (매수/매도 구분)
   - trade_strength: NUMERIC NULL (체결강도)
   - received_at: TIMESTAMPTZ NOT NULL DEFAULT now()
   - 인덱스: (stock_code, ts)
   ※ 46필드 전량 컬럼화는 과잉 — 대부분 파생/누적 통계라 OHLCV 집계에 위 subset이면 충분.

2. `KoreaOrderbook` → 테이블 `korea_orderbooks`
   - id, stock_code, ts, received_at: 위와 동일
     ※ ts 함정: 호가 DTO엔 business_time(시각)만 있고 날짜가 없다.
       received_at의 KST 날짜와 결합해 만든다 (변환은 repository의 순수 함수에서).
   - levels: JSONB NOT NULL — KISKoreaOrderbookLevel 10개를 그대로 직렬화한 리스트
     [{ask_price, bid_price, ask_quantity, bid_quantity} x10]
     타입은 `JSON().with_variant(JSONB(), "postgresql")` 권장 → 테스트에서 sqlite 대체 가능.
     ※ 정규화(레벨 자식 테이블) 대신 JSONB인 이유: 소비 패턴이 항상 스냅샷 전체 복원이라
       join 이득이 없고, 스냅샷당 insert가 11행 → 1행으로 준다.
   - total_ask_quantity, total_bid_quantity: BIGINT NOT NULL
   - 인덱스: (stock_code, ts)

공통 설계 노트:
- instruments FK는 v1에서 생략, stock_code 직저장 (instruments 테이블 미구현 + 종목 2개).
  instruments 정착 후 FK 전환.
- Decimal 컬럼은 Numeric, JSONB의 Decimal 값은 직렬화 시 str/float 변환 필요에 유의.
"""

# TODO(사용자): 위 명세대로 KoreaTrade, KoreaOrderbook ORM 클래스를 구현한다.
