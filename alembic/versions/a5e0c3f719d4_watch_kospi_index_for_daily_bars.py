"""watch kospi index for daily bars

Revision ID: a5e0c3f719d4
Revises: e91c46f3ba27
Create Date: 2026-08-03 11:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a5e0c3f719d4"
down_revision: str | Sequence[str] | None = "e91c46f3ba27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


instruments = sa.table(
    "instruments",
    sa.column("ticker", sa.Text()),
    sa.column("market", sa.Text()),
    sa.column("is_watched", sa.Boolean()),
)

# KOSPI 행은 투자자 수급의 FK 앵커로 먼저 등록돼(8c1b0a5d7e42) is_watched=False였다.
# d7b52c1a09e4가 kind='INDEX'와 source_symbol='^KS11'을 채워 가격을 받을 수 있게 됐지만
# is_watched를 켜지 않아, list_watched()가 걸러내는 바람에 일봉이 수집되지 않고 있었다.
KOSPI = ("KOSPI", "KRX")


def _set_watched(watched: bool) -> None:
    """KOSPI 행의 추적 여부를 갱신한다.

    Args:
        watched: 설정할 is_watched 값.
    """
    op.execute(
        sa.update(instruments)
        .where(sa.tuple_(instruments.c.ticker, instruments.c.market) == sa.tuple_(*KOSPI))
        .values(is_watched=watched)
    )


def upgrade() -> None:
    """KOSPI 지수를 일봉 수집 대상으로 켠다."""
    _set_watched(True)


def downgrade() -> None:
    """KOSPI를 다시 수집 대상에서 제외한다."""
    _set_watched(False)
