"""create kis realtime tables

Revision ID: 395d397a95aa
Revises:
Create Date: 2026-07-14 17:52:33.598767

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "395d397a95aa"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """KIS 국내·해외 실시간 체결 및 호가 테이블을 생성한다."""
    op.create_table(
        "korea_trades",
        sa.Column(
            "stock_code",
            sa.Text(),
            nullable=False,
            comment="KIS 유가증권 단축 종목코드",
        ),
        sa.Column(
            "event_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="영업일자와 체결시각을 결합한 UTC 체결 시각",
        ),
        sa.Column(
            "price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="주식 현재가 기준 체결 가격",
        ),
        sa.Column(
            "volume",
            sa.BigInteger(),
            nullable=False,
            comment="직전 체결 수량",
        ),
        sa.Column(
            "cumulative_volume",
            sa.BigInteger(),
            nullable=False,
            comment="영업일 누적 거래량",
        ),
        sa.Column(
            "cumulative_amount",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="영업일 누적 거래대금",
        ),
        sa.Column(
            "trade_strength",
            sa.Numeric(precision=20, scale=8),
            nullable=True,
            comment="매수와 매도 체결량을 이용한 체결강도",
        ),
        sa.Column(
            "best_bid_price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="체결 수신 시점의 최우선 매수호가",
        ),
        sa.Column(
            "best_ask_price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="체결 수신 시점의 최우선 매도호가",
        ),
        sa.Column(
            "trade_classification_code",
            sa.Text(),
            nullable=False,
            comment="KIS 체결 구분 코드",
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="등락률과 장중 통계 등 비핵심 체결 DTO 필드",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="애플리케이션이 체결 tick을 수신한 UTC 시각",
        ),
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="엔티티 내부 식별자",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="레코드가 생성된 UTC 시각",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="레코드가 마지막으로 수정된 UTC 시각",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="KIS 국내주식 실시간 체결 tick",
    )
    op.create_index(
        "ix_korea_trades_stock_code_event_ts",
        "korea_trades",
        ["stock_code", "event_ts"],
        unique=False,
    )

    op.create_table(
        "korea_orderbooks",
        sa.Column(
            "stock_code",
            sa.Text(),
            nullable=False,
            comment="KIS 유가증권 단축 종목코드",
        ),
        sa.Column(
            "event_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="수신일자와 영업시각을 결합한 UTC 호가 시각",
        ),
        sa.Column(
            "best_bid_price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="1단계 최우선 매수호가",
        ),
        sa.Column(
            "best_ask_price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="1단계 최우선 매도호가",
        ),
        sa.Column(
            "total_bid_quantity",
            sa.BigInteger(),
            nullable=False,
            comment="전체 매수호가 잔량",
        ),
        sa.Column(
            "total_ask_quantity",
            sa.BigInteger(),
            nullable=False,
            comment="전체 매도호가 잔량",
        ),
        sa.Column(
            "levels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="가격과 잔량을 포함한 1단계부터 10단계까지의 호가 목록",
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="예상체결과 시간외 잔량 등 비핵심 호가 DTO 필드",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="애플리케이션이 호가 스냅샷을 수신한 UTC 시각",
        ),
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="엔티티 내부 식별자",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="레코드가 생성된 UTC 시각",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="레코드가 마지막으로 수정된 UTC 시각",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="KIS 국내주식 실시간 10단계 호가 스냅샷",
    )
    op.create_index(
        "ix_korea_orderbooks_stock_code_event_ts",
        "korea_orderbooks",
        ["stock_code", "event_ts"],
        unique=False,
    )

    op.create_table(
        "overseas_trades",
        sa.Column(
            "realtime_symbol",
            sa.Text(),
            nullable=False,
            comment="시세 구분과 거래소 및 티커가 결합된 KIS 실시간 종목코드",
        ),
        sa.Column(
            "symbol",
            sa.Text(),
            nullable=False,
            comment="해외주식 종목 티커",
        ),
        sa.Column(
            "market",
            sa.Text(),
            nullable=False,
            comment="구독 정보에서 확인한 KIS 해외 거래소 코드",
        ),
        sa.Column(
            "event_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="한국 일자와 시간을 결합해 변환한 UTC 체결 시각",
        ),
        sa.Column(
            "local_business_date",
            sa.Date(),
            nullable=False,
            comment="거래소 현지 영업일자",
        ),
        sa.Column(
            "decimal_places",
            sa.SmallInteger(),
            nullable=False,
            comment="가격 표시에 사용하는 소수점 자리수",
        ),
        sa.Column(
            "price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="해외주식 현재가 기준 체결 가격",
        ),
        sa.Column(
            "volume",
            sa.BigInteger(),
            nullable=False,
            comment="직전 체결 수량",
        ),
        sa.Column(
            "cumulative_volume",
            sa.BigInteger(),
            nullable=False,
            comment="현지 영업일 누적 거래량",
        ),
        sa.Column(
            "cumulative_amount",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="현지 영업일 누적 거래대금",
        ),
        sa.Column(
            "best_bid_price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="체결 수신 시점의 최우선 매수호가",
        ),
        sa.Column(
            "best_ask_price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="체결 수신 시점의 최우선 매도호가",
        ),
        sa.Column(
            "best_bid_quantity",
            sa.BigInteger(),
            nullable=False,
            comment="체결 수신 시점의 최우선 매수호가 잔량",
        ),
        sa.Column(
            "best_ask_quantity",
            sa.BigInteger(),
            nullable=False,
            comment="체결 수신 시점의 최우선 매도호가 잔량",
        ),
        sa.Column(
            "trade_strength",
            sa.Numeric(precision=20, scale=8),
            nullable=True,
            comment="매수와 매도 체결량을 이용한 체결강도",
        ),
        sa.Column(
            "market_type",
            sa.Text(),
            nullable=False,
            comment="KIS 체결 응답의 시장 구분 코드",
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="시가와 등락률 등 비핵심 체결 DTO 필드",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="애플리케이션이 체결 tick을 수신한 UTC 시각",
        ),
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="엔티티 내부 식별자",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="레코드가 생성된 UTC 시각",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="레코드가 마지막으로 수정된 UTC 시각",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="KIS 해외주식 실시간 체결 tick",
    )
    op.create_index(
        "ix_overseas_trades_symbol_event_ts",
        "overseas_trades",
        ["symbol", "event_ts"],
        unique=False,
    )

    op.create_table(
        "overseas_orderbooks",
        sa.Column(
            "realtime_symbol",
            sa.Text(),
            nullable=False,
            comment="시세 구분과 거래소 및 티커가 결합된 KIS 실시간 종목코드",
        ),
        sa.Column(
            "symbol",
            sa.Text(),
            nullable=False,
            comment="해외주식 종목 티커",
        ),
        sa.Column(
            "market",
            sa.Text(),
            nullable=False,
            comment="구독 정보에서 확인한 KIS 해외 거래소 코드",
        ),
        sa.Column(
            "event_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="한국 일자와 시간을 결합해 변환한 UTC 호가 시각",
        ),
        sa.Column(
            "decimal_places",
            sa.SmallInteger(),
            nullable=False,
            comment="가격 표시에 사용하는 소수점 자리수",
        ),
        sa.Column(
            "best_bid_price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="1단계 최우선 매수호가",
        ),
        sa.Column(
            "best_ask_price",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="1단계 최우선 매도호가",
        ),
        sa.Column(
            "best_bid_quantity",
            sa.BigInteger(),
            nullable=False,
            comment="1단계 최우선 매수호가 잔량",
        ),
        sa.Column(
            "best_ask_quantity",
            sa.BigInteger(),
            nullable=False,
            comment="1단계 최우선 매도호가 잔량",
        ),
        sa.Column(
            "total_bid_quantity",
            sa.BigInteger(),
            nullable=False,
            comment="전체 매수호가 잔량",
        ),
        sa.Column(
            "total_ask_quantity",
            sa.BigInteger(),
            nullable=False,
            comment="전체 매도호가 잔량",
        ),
        sa.Column(
            "levels",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="가격과 잔량 및 증감을 포함한 1단계부터 10단계까지의 호가 목록",
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="총잔량 증감 등 비핵심 호가 DTO 필드",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="애플리케이션이 호가 스냅샷을 수신한 UTC 시각",
        ),
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="엔티티 내부 식별자",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="레코드가 생성된 UTC 시각",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="레코드가 마지막으로 수정된 UTC 시각",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="KIS 해외주식 실시간 10단계 호가 스냅샷",
    )
    op.create_index(
        "ix_overseas_orderbooks_symbol_event_ts",
        "overseas_orderbooks",
        ["symbol", "event_ts"],
        unique=False,
    )


def downgrade() -> None:
    """KIS 국내·해외 실시간 체결 및 호가 테이블을 제거한다."""
    op.drop_index(
        "ix_overseas_orderbooks_symbol_event_ts",
        table_name="overseas_orderbooks",
    )
    op.drop_table("overseas_orderbooks")
    op.drop_index(
        "ix_overseas_trades_symbol_event_ts",
        table_name="overseas_trades",
    )
    op.drop_table("overseas_trades")
    op.drop_index(
        "ix_korea_orderbooks_stock_code_event_ts",
        table_name="korea_orderbooks",
    )
    op.drop_table("korea_orderbooks")
    op.drop_index(
        "ix_korea_trades_stock_code_event_ts",
        table_name="korea_trades",
    )
    op.drop_table("korea_trades")
