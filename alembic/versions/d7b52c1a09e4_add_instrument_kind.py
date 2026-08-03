"""add instrument kind and source symbol

Revision ID: d7b52c1a09e4
Revises: c4a1e7b93f52
Create Date: 2026-07-31 16:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d7b52c1a09e4"
down_revision: str | Sequence[str] | None = "c4a1e7b93f52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


instruments = sa.table(
    "instruments",
    sa.column("ticker", sa.Text()),
    sa.column("kind", sa.Text()),
    sa.column("source_symbol", sa.Text()),
)

# 거래되는 ETF. 개별주와 같은 소스를 쓰지만 분석에서 벤치마크로 구분해야 한다.
ETF_TICKERS = ("QQQ", "SPY")

# 계산 지수. 종목 시세 TR로 받을 수 없어 소스 심볼을 따로 갖는다.
# KOSPI 행은 투자자 수급의 FK 앵커로 먼저 등록됐고, 이제 가격도 함께 받는다.
INDEX_SOURCE_SYMBOLS = {"KOSPI": "^KS11"}


def upgrade() -> None:
    """가격 수집 소스를 가르는 kind와 소스 심볼 컬럼을 추가한다."""
    op.add_column(
        "instruments",
        sa.Column(
            "kind",
            sa.Enum(
                "EQUITY",
                "ETF",
                "INDEX",
                name="instrument_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=True,
            comment="가격 수집 소스를 가르는 유형",
        ),
    )
    op.add_column(
        "instruments",
        sa.Column(
            "source_symbol",
            sa.Text(),
            nullable=True,
            comment="수집 소스에서 쓰는 심볼. 티커와 다를 때만 채운다(예: KOSPI → ^KS11)",
        ),
    )

    # 기존 행을 채운 뒤 NOT NULL로 조인다. 기본값을 서버에 남기면 새 종목을 등록할 때
    # 유형을 빠뜨려도 EQUITY로 조용히 들어간다.
    op.execute(sa.update(instruments).values(kind="EQUITY"))
    op.execute(sa.update(instruments).where(instruments.c.ticker.in_(ETF_TICKERS)).values(kind="ETF"))
    for ticker, symbol in INDEX_SOURCE_SYMBOLS.items():
        op.execute(
            sa.update(instruments).where(instruments.c.ticker == ticker).values(kind="INDEX", source_symbol=symbol)
        )

    op.alter_column("instruments", "kind", nullable=False)


def downgrade() -> None:
    """kind와 소스 심볼 컬럼을 제거한다."""
    op.drop_column("instruments", "source_symbol")
    op.drop_column("instruments", "kind")
