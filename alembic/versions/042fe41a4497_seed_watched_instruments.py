"""seed watched instruments

Revision ID: 042fe41a4497
Revises: fb3d9d22e93b
Create Date: 2026-07-17 13:56:35.441334

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "042fe41a4497"
down_revision: str | Sequence[str] | None = "fb3d9d22e93b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


instruments = sa.table(
    "instruments",
    sa.column("ticker", sa.Text()),
    sa.column("market", sa.Text()),
    sa.column("name", sa.Text()),
    sa.column("is_watched", sa.Boolean()),
)


def upgrade() -> None:
    """확정된 추적 종목 9개를 등록한다."""
    op.bulk_insert(
        instruments,
        [
            {"ticker": "005930", "market": "KRX", "name": "삼성전자", "is_watched": True},
            {"ticker": "000660", "market": "KRX", "name": "SK하이닉스", "is_watched": True},
            {"ticker": "AAPL", "market": "NASDAQ", "name": "Apple", "is_watched": True},
            {"ticker": "GOOGL", "market": "NASDAQ", "name": "Alphabet", "is_watched": True},
            {"ticker": "MSFT", "market": "NASDAQ", "name": "Microsoft", "is_watched": True},
            {"ticker": "META", "market": "NASDAQ", "name": "Meta", "is_watched": True},
            {"ticker": "NVDA", "market": "NASDAQ", "name": "NVIDIA", "is_watched": True},
            {"ticker": "QQQ", "market": "NASDAQ", "name": "Invesco QQQ", "is_watched": True},
            {
                "ticker": "SPY",
                "market": "NYSE_ARCA",
                "name": "SPDR S&P 500 ETF",
                "is_watched": True,
            },
        ],
    )


def downgrade() -> None:
    """초기 등록한 추적 종목 9개를 제거한다."""
    op.execute(
        sa.delete(instruments).where(
            sa.tuple_(instruments.c.ticker, instruments.c.market).in_(
                [
                    ("005930", "KRX"),
                    ("000660", "KRX"),
                    ("AAPL", "NASDAQ"),
                    ("GOOGL", "NASDAQ"),
                    ("MSFT", "NASDAQ"),
                    ("META", "NASDAQ"),
                    ("NVDA", "NASDAQ"),
                    ("QQQ", "NASDAQ"),
                    ("SPY", "NYSE_ARCA"),
                ]
            )
        )
    )
