"""create instruments table

Revision ID: fb3d9d22e93b
Revises: 395d397a95aa
Create Date: 2026-07-17 13:52:18.475933

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "fb3d9d22e93b"
down_revision: str | Sequence[str] | None = "395d397a95aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """종목 마스터 테이블을 생성한다."""
    op.create_table(
        "instruments",
        sa.Column(
            "ticker",
            sa.Text(),
            nullable=False,
            comment="거래 시장에서 사용하는 종목 코드",
        ),
        sa.Column(
            "market",
            sa.Enum(
                "KRX",
                "NASDAQ",
                "NYSE_ARCA",
                name="instrument_market",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
            comment="종목이 상장된 거래 시장",
        ),
        sa.Column(
            "name",
            sa.Text(),
            nullable=False,
            comment="종목 표시 이름",
        ),
        sa.Column(
            "is_watched",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
            comment="신규 데이터 수집과 분석을 수행할 추적 대상 여부",
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
            "ticker",
            "market",
            name="uq_instruments_ticker_market",
        ),
        comment="시세·뉴스·시그널이 참조하는 추적 종목 마스터",
    )


def downgrade() -> None:
    """종목 마스터 테이블을 제거한다."""
    op.drop_table("instruments")
