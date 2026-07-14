"""국내주식 실시간 tick DB 적재 (§4.2 korea_trades / korea_orderbooks).

여기 구현할 것:

1. 모듈 레벨 순수 변환 함수 2개 (DB 없이 단위 테스트 가능하도록 분리):
   - `to_trade_row(dto: KISKoreaTrade) -> KoreaTrade`
     · ts = business_date + trade_time을 KST(Asia/Seoul) aware datetime으로 결합
       (stdlib zoneinfo.ZoneInfo 사용)
     · price=current_price, volume=trade_volume 등 필드 매핑
   - `to_orderbook_row(dto: KISKoreaOrderbook, received_at: datetime) -> KoreaOrderbook`
     · ts = received_at의 KST 날짜 + dto.business_time 결합
       (호가 DTO엔 날짜가 없다 — models.py 주석 참조)
     · levels = [level.model_dump() for ...] — Decimal이 JSONB에 그대로 못 들어가면
       mode="json" 직렬화 고려

2. `KISKoreaTickRepository` 클래스:
   - `__init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None`
   - `async def save_trades(self, trades: list[KISKoreaTrade]) -> None`
     · 변환 함수로 row 목록 생성 → session.add_all → commit
   - `async def save_orderbooks(self, orderbooks: list[KISKoreaOrderbook]) -> None`
     · 동일 패턴
   ※ tick은 append-only라 upsert 불필요. 배치 flush 최적화는 소비 루프 쪽 선택 과제.
"""

# TODO(사용자): 위 명세대로 변환 함수와 KISKoreaTickRepository를 구현한다.
