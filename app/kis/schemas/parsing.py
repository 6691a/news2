from datetime import date, time


def parse_kis_date(value: str) -> date:
    """KIS YYYYMMDD 문자열을 날짜로 변환한다."""

    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def parse_kis_time(value: str) -> time:
    """KIS HHMMSS 문자열을 시각으로 변환한다."""

    return time(int(value[:2]), int(value[2:4]), int(value[4:6]))


def none_if_empty(value: str) -> str | None:
    """빈 KIS 문자열을 None으로 정규화한다."""

    return value or None
