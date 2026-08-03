"""seed macro instruments

Revision ID: e91c46f3ba27
Revises: d7b52c1a09e4
Create Date: 2026-07-31 17:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e91c46f3ba27"
down_revision: str | Sequence[str] | None = "d7b52c1a09e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


instruments = sa.table(
    "instruments",
    sa.column("ticker", sa.Text()),
    sa.column("market", sa.Text()),
    sa.column("name", sa.Text()),
    sa.column("kind", sa.Text()),
    sa.column("source_symbol", sa.Text()),
    sa.column("is_watched", sa.Boolean()),
)

MARKETS = ["KRX", "NASDAQ", "NYSE", "NYSE_ARCA", "US_INDEX", "JPX", "HKEX", "SSE", "TWSE", "GLOBEX", "FX"]
KINDS = ["EQUITY", "ETF", "INDEX", "FX", "FUTURES", "COMMODITY"]

# §1.5 매크로 지표. ticker는 Yahoo 심볼을 그대로 쓴다 — 이름을 따로 만들면 매핑 표가
# 하나 더 생기고 오타가 들어갈 자리가 늘어난다. 이미 다른 이름이 박힌 KOSPI만 예외로
# source_symbol을 갖는다(투자자 수급이 'KOSPI'로 참조 중).
#
# 미국채 금리(DGS2/10/30)와 ZN 선물은 us_treasury 패키지가 전용 테이블에 담으므로 제외한다.
MACRO_INSTRUMENTS: list[dict[str, object]] = [
    # 지수 — 미국
    {"ticker": "^GSPC", "market": "US_INDEX", "name": "S&P 500", "kind": "INDEX"},
    {"ticker": "^IXIC", "market": "US_INDEX", "name": "나스닥 종합", "kind": "INDEX"},
    {"ticker": "^SOX", "market": "US_INDEX", "name": "필라델피아 반도체", "kind": "INDEX"},
    {"ticker": "^VIX", "market": "US_INDEX", "name": "VIX 변동성", "kind": "INDEX"},
    {"ticker": "^RUT", "market": "US_INDEX", "name": "러셀 2000", "kind": "INDEX"},
    # 지수 — 아시아
    {"ticker": "^N225", "market": "JPX", "name": "니케이 225", "kind": "INDEX"},
    {"ticker": "^HSI", "market": "HKEX", "name": "항셍", "kind": "INDEX"},
    {"ticker": "000001.SS", "market": "SSE", "name": "상하이 종합", "kind": "INDEX"},
    {"ticker": "^TWII", "market": "TWSE", "name": "대만 가권", "kind": "INDEX"},
    # 개별 참조 — 시그널 대상이 아니라 반도체 공급망 참조 가격
    {"ticker": "TSM", "market": "NYSE", "name": "TSMC ADR", "kind": "EQUITY"},
    # 환율
    {"ticker": "KRW=X", "market": "FX", "name": "USD/KRW", "kind": "FX"},
    {"ticker": "JPY=X", "market": "FX", "name": "USD/JPY", "kind": "FX"},
    {"ticker": "JPYKRW=X", "market": "FX", "name": "JPY/KRW", "kind": "FX"},
    {"ticker": "CNY=X", "market": "FX", "name": "USD/CNY", "kind": "FX"},
    # 역외 위안(CNH)은 제외한다. Yahoo가 `CNH=X`·`USDCNH=X` 모두 당일 1행만 주고 일봉
    # 히스토리를 주지 않아 백필도 백테스트도 불가능하다(2026-07-31 확인). 역내(CNY=X)로
    # 대체하고, 역외 프리미엄이 필요해지면 별도 소스를 찾는다.
    {"ticker": "DX-Y.NYB", "market": "FX", "name": "달러 인덱스", "kind": "FX"},
    # 지수 선물 — 프리마켓 방향성. 연속선물 심볼로 방향만 보므로 Yahoo로 충분하다.
    {"ticker": "ES=F", "market": "GLOBEX", "name": "S&P 500 선물", "kind": "FUTURES"},
    {"ticker": "NQ=F", "market": "GLOBEX", "name": "나스닥 100 선물", "kind": "FUTURES"},
    # 원자재 선물(금·은·구리·WTI)은 여기 없다. §1.5·§3.1에 따라 KIS 해외선물의
    # **거래량 기준 최근월물**을 REST·WebSocket으로 받고 월물별로 원가격을 보존한다.
    # Yahoo 연속선물 심볼(`GC=F` 등)은 롤 시점 가격이 이어 붙어 있어 쓰지 않는다.
]


def upgrade() -> None:
    """거래 세션·자산 유형 값을 넓히고 매크로 지표를 등록한다."""
    # 값 목록이 늘어나 CHECK 제약을 다시 만든다. kind는 'COMMODITY'가 들어가도록 넓힌다.
    op.drop_constraint("instrument_market", "instruments", type_="check")
    op.drop_constraint("instrument_kind", "instruments", type_="check")
    op.alter_column("instruments", "kind", type_=sa.String(length=9), existing_nullable=False)
    op.create_check_constraint("instrument_market", "instruments", sa.column("market").in_(MARKETS))
    op.create_check_constraint("instrument_kind", "instruments", sa.column("kind").in_(KINDS))

    op.bulk_insert(
        instruments,
        [{**row, "source_symbol": None, "is_watched": True} for row in MACRO_INSTRUMENTS],
    )


def downgrade() -> None:
    """매크로 지표를 제거하고 값 목록을 되돌린다."""
    op.execute(
        sa.delete(instruments).where(
            sa.tuple_(instruments.c.ticker, instruments.c.market).in_(
                [(row["ticker"], row["market"]) for row in MACRO_INSTRUMENTS]
            )
        )
    )

    op.drop_constraint("instrument_market", "instruments", type_="check")
    op.drop_constraint("instrument_kind", "instruments", type_="check")
    op.alter_column("instruments", "kind", type_=sa.String(length=6), existing_nullable=False)
    op.create_check_constraint(
        "instrument_market",
        "instruments",
        sa.column("market").in_(["KRX", "NASDAQ", "NYSE_ARCA"]),
    )
    op.create_check_constraint(
        "instrument_kind",
        "instruments",
        sa.column("kind").in_(["EQUITY", "ETF", "INDEX"]),
    )
