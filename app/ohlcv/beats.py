"""확정 일봉 수집 beat 스케줄."""

from typing import Any

from celery.schedules import crontab


def beat_schedule() -> dict[str, dict[str, Any]]:
    """확정 일봉 수집 beat 항목을 만든다.

    Returns:
        Celery `beat_schedule`에 병합할 항목 딕셔너리.
    """

    return {
        # KRX 정규장 마감(15:30)과 종가 확정 뒤. 투자자 수급 확정(18:10)과 같은 배치 창에 둔다.
        "ohlcv-korea-daily": {
            "task": "ohlcv.collect_korea_daily",
            "schedule": crontab(minute=0, hour=18, day_of_week="mon-fri"),
        },
        # KST 07:00 = ET 17:00(서머타임)/18:00(표준시)로 미국 정규장 마감 뒤다.
        # 미국 월~금장의 마감이 한국 화~토 새벽이라 요일이 하루 밀린다.
        "ohlcv-overseas-daily": {
            "task": "ohlcv.collect_overseas_daily",
            "schedule": crontab(minute=0, hour=7, day_of_week="tue-sat"),
        },
    }
