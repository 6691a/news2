"""거래 시장 시간대 상수와 시간 변환 도구.

시장의 시간대는 환경에 따라 달라지지 않는 도메인 사실이라 `Settings`가 아니라
상수로 둔다. 저장되는 datetime은 여전히 전부 UTC다.
"""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")
# 미 국채·주식 시장 시간대. FRED H.15는 16:15 ET에 공표된다.
ET = ZoneInfo("America/New_York")
# 아시아 지수의 거래소 시간대. 일봉의 거래일 판정이 시간대에 걸려 있어 시장마다 필요하다.
JST = ZoneInfo("Asia/Tokyo")
HKT = ZoneInfo("Asia/Hong_Kong")
SHANGHAI = ZoneInfo("Asia/Shanghai")
TAIPEI = ZoneInfo("Asia/Taipei")


def kst_datetime(day: date, clock: time) -> datetime:
    """한국 날짜와 시각을 결합해 UTC 시각으로 변환한다."""

    return datetime.combine(day, clock, tzinfo=KST).astimezone(UTC)
