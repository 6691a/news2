"""KIS 국내·해외 시세에서 공유하는 한국 시간 변환 도구."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def kst_datetime(day: date, clock: time) -> datetime:
    """한국 날짜와 시각을 결합해 UTC 시각으로 변환한다."""

    return datetime.combine(day, clock, tzinfo=KST).astimezone(UTC)
