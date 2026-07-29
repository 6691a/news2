"""create us treasury tables

Revision ID: b7f2c9a41d38
Revises: 8c1b0a5d7e42
Create Date: 2026-07-28 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b7f2c9a41d38"
down_revision: str | Sequence[str] | None = "8c1b0a5d7e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """미국 국채 장중 1분봉과 일별 확정 수익률 테이블을 만든다."""
    op.create_table(
        "us_treasury_bars",
        sa.Column(
            "series",
            sa.Enum(
                "US10Y",
                "ZN",
                name="us_treasury_series",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            comment="국채 계열. US10Y=10년물 수익률, ZN=10년물 국채선물",
        ),
        sa.Column(
            "event_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="봉이 시작한 UTC 시각",
        ),
        sa.Column(
            "open",
            sa.Numeric(precision=16, scale=8),
            nullable=True,
            comment="시가. US10Y=수익률 %, ZN=가격 포인트",
        ),
        sa.Column(
            "high",
            sa.Numeric(precision=16, scale=8),
            nullable=True,
            comment="고가. US10Y=수익률 %, ZN=가격 포인트",
        ),
        sa.Column(
            "low",
            sa.Numeric(precision=16, scale=8),
            nullable=True,
            comment="저가. US10Y=수익률 %, ZN=가격 포인트",
        ),
        sa.Column(
            "close",
            sa.Numeric(precision=16, scale=8),
            nullable=False,
            comment="종가. US10Y=수익률 %, ZN=가격 포인트(1/64 분수)",
        ),
        sa.Column(
            "snapshot_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="응답을 수신한 UTC 시각",
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
        sa.UniqueConstraint(
            "series",
            "event_ts",
            name="uq_us_treasury_bars_series_event_ts",
        ),
        comment="미국 국채 수익률(^TNX)·국채선물 가격(ZN=F) 장중 1분봉 (Yahoo)",
    )
    op.create_table(
        "us_treasury_yield_daily",
        sa.Column(
            "series",
            sa.Enum(
                "US10Y",
                "ZN",
                name="us_treasury_series",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            comment="국채 계열. 확정치는 US10Y만 존재한다",
        ),
        sa.Column(
            "observation_date",
            sa.Date(),
            nullable=False,
            comment="확정치 기준 미 동부(ET) 영업일",
        ),
        sa.Column(
            "yield_pct",
            sa.Numeric(precision=8, scale=4),
            nullable=False,
            comment="H.15 CMT 수익률(%)",
        ),
        sa.Column(
            "snapshot_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="응답을 수신한 UTC 시각",
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
        sa.UniqueConstraint(
            "series",
            "observation_date",
            name="uq_us_treasury_yield_daily_series_observation_date",
        ),
        comment="미국 국채 수익률 일별 확정치 (FRED H.15)",
    )


def downgrade() -> None:
    """미국 국채 테이블을 제거한다."""
    op.drop_table("us_treasury_yield_daily")
    op.drop_table("us_treasury_bars")
