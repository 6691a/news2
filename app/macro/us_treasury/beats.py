"""미국 국채 수익률·국채선물 수집 beat 스케줄."""

from typing import Any

from celery.schedules import crontab


def beat_schedule() -> dict[str, dict[str, Any]]:
    """미국 국채 수집 beat 항목을 만든다.

    Returns:
        Celery `beat_schedule`에 병합할 항목 딕셔너리.
    """

    return {
        # ^TNX 산출 세션은 미 중부 08:30~15:10.
        # KST로 22:30~05:10(서머타임)/23:30~06:10(표준시)라 22:00~07:45 창으로 둘 다 덮는다.
        # 폐장·휴장 폴링은 (series, event_ts) 중복으로 전부 skip되어 무해하다.
        "us-treasury-intraday-evening": {
            "task": "macro.us_treasury.collect_intraday",
            "schedule": crontab(minute="*/15", hour="22-23", day_of_week="mon-fri"),
            "args": ("US10Y",),
        },
        "us-treasury-intraday-morning": {
            "task": "macro.us_treasury.collect_intraday",
            "schedule": crontab(minute="*/15", hour="0-7", day_of_week="tue-sat"),
            "args": ("US10Y",),
        },
        # ZN 선물은 Globex에서 거의 23시간(ET 18:00~다음날 17:00) 거래된다. 한국 낮 시간
        # 커버가 도입 목적이므로 시간대를 제한하지 않고 24시간 폴링한다 — ^TNX 창과 통합하지
        # 않는 이유: 세션이 전혀 다르고, ^TNX를 24시간 폴링하면 무의미한 호출만 는다.
        # Globex 폐장 구간(KST 토 06:00 ~ 월 07:00 부근)과 유지보수 휴지의 폴링은
        # (series, event_ts) 중복으로 전부 skip되어 무해하다. 일요일만 제외한다.
        "us-treasury-futures-intraday": {
            "task": "macro.us_treasury.collect_intraday",
            "schedule": crontab(minute="*/15", day_of_week="mon-sat"),
            "args": ("ZN",),
        },
        # KST 10:00 = ET 20:00/21:00(전일). dispatch 시점 ET 날짜 = 방금 끝난 미국 영업일이고
        # 그 날짜의 H.15(16:15 ET 공표)는 이미 나와 있다.
        "us-treasury-final": {
            "task": "macro.us_treasury.dispatch_final",
            "schedule": crontab(minute=0, hour=10, day_of_week="tue-sat"),
        },
    }
