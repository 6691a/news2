"""create investor flows table

Revision ID: 8c1b0a5d7e42
Revises: 042fe41a4497
Create Date: 2026-07-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "8c1b0a5d7e42"
down_revision: str | Sequence[str] | None = "042fe41a4497"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


instruments = sa.table(
    "instruments",
    sa.column("ticker", sa.Text()),
    sa.column("market", sa.Text()),
    sa.column("name", sa.Text()),
    sa.column("is_watched", sa.Boolean()),
)

KOSPI_INSTRUMENT = {
    "ticker": "KOSPI",
    "market": "KRX",
    "name": "코스피",
    # 실시간 시세 구독 대상이 아니라 시장 단위 수급을 매달기 위한 macro instrument다.
    "is_watched": False,
}


def upgrade() -> None:
    """투자자 수급 테이블을 만들고 KOSPI macro instrument를 등록한다."""
    op.create_table(
        "investor_flows",
        sa.Column(
            "instrument_id",
            sa.BigInteger(),
            nullable=False,
            comment="수급 대상 종목 또는 시장 instrument",
        ),
        sa.Column(
            "trade_date",
            sa.Date(),
            nullable=False,
            comment="수급 기준 영업일(한국 날짜)",
        ),
        sa.Column(
            "venue",
            sa.Enum(
                "KRX",
                "NXT",
                "UNSPECIFIED",
                name="investor_flow_venue",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            comment="응답의 거래 시장 범위",
        ),
        sa.Column(
            "investor_type",
            sa.Enum(
                "foreign",
                "retail",
                "institution",
                "securities",
                "trust",
                "private_equity",
                "bank",
                "insurance",
                "merchant_bank",
                "pension_fund",
                "other_organization",
                "other_corporation",
                name="investor_flow_investor_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            comment="투자자 유형",
        ),
        sa.Column(
            "net_buy_volume",
            sa.BigInteger(),
            nullable=True,
            comment="순매수 수량(주)",
        ),
        sa.Column(
            "net_buy_value",
            sa.BigInteger(),
            nullable=True,
            comment="순매수 거래대금(백만원, KIS 원본 단위). 금액을 주지 않는 TR은 NULL",
        ),
        sa.Column(
            "time_bucket",
            sa.Text(),
            server_default="",
            nullable=False,
            comment="장중 집계 시간대 구분. 구분이 없으면 빈 문자열",
        ),
        sa.Column(
            "is_provisional",
            sa.Boolean(),
            nullable=False,
            comment="장중 가집계(잠정치) 여부",
        ),
        sa.Column(
            "snapshot_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="응답을 수신한 UTC 시각",
        ),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="매도·매수 원본 등 순매수 외 필드",
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
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "trade_date",
            "investor_type",
            "venue",
            "time_bucket",
            "is_provisional",
            "snapshot_ts",
            name="uq_investor_flows_snapshot",
        ),
        comment="KIS 국내 투자자별 순매수 동향",
    )
    op.create_index(
        "ix_investor_flows_instrument_id_trade_date",
        "investor_flows",
        ["instrument_id", "trade_date"],
    )
    op.bulk_insert(instruments, [KOSPI_INSTRUMENT])


def downgrade() -> None:
    """투자자 수급 테이블과 KOSPI macro instrument를 제거한다.

    자식 테이블을 먼저 지운다. instrument를 먼저 지우면 수급 행이 남아 있는 DB에서
    FK 위반으로 롤백 자체가 실패한다.
    """
    op.drop_index("ix_investor_flows_instrument_id_trade_date", table_name="investor_flows")
    op.drop_table("investor_flows")
    op.execute(
        sa.delete(instruments).where(
            sa.tuple_(instruments.c.ticker, instruments.c.market).in_(
                [(KOSPI_INSTRUMENT["ticker"], KOSPI_INSTRUMENT["market"])]
            )
        )
    )
