"""create ohlcv table

Revision ID: c4a1e7b93f52
Revises: b7f2c9a41d38
Create Date: 2026-07-31 15:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c4a1e7b93f52"
down_revision: str | Sequence[str] | None = "b7f2c9a41d38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """확정 일봉과 장중 분봉을 담을 ohlcv 테이블을 만든다."""
    op.create_table(
        "ohlcv",
        sa.Column(
            "instrument_id",
            sa.BigInteger(),
            nullable=False,
            comment="봉이 속한 추적 종목",
        ),
        sa.Column(
            "timeframe",
            sa.Enum(
                "1m",
                "1d",
                name="ohlcv_timeframe",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            comment="봉 간격. 1d=확정 일봉, 1m=장중 분봉",
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="봉이 시작한 UTC 시각. 일봉은 거래소 현지 00:00에 대응한다",
        ),
        sa.Column(
            "open",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="시가",
        ),
        sa.Column(
            "high",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="고가",
        ),
        sa.Column(
            "low",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="저가",
        ),
        sa.Column(
            "close",
            sa.Numeric(precision=28, scale=8),
            nullable=False,
            comment="종가. 국내는 KIS 수정주가, 해외는 Yahoo 배당·분할 조정가",
        ),
        sa.Column(
            "volume",
            sa.BigInteger(),
            nullable=False,
            comment="봉 구간 거래량(주)",
        ),
        sa.Column(
            "snapshot_ts",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="응답을 수신한 UTC 시각. 수정주가 소급 반영 시 갱신된다",
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
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "instrument_id",
            "timeframe",
            "ts",
            name="uq_ohlcv_instrument_timeframe_ts",
        ),
        comment="추적 종목의 확정 일봉과 장중 분봉",
    )


def downgrade() -> None:
    """ohlcv 테이블을 제거한다."""
    op.drop_table("ohlcv")
