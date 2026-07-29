"""국내 투자자 수급 수집 beat 스케줄."""

from typing import Any

from celery.schedules import crontab


# 종목 가집계는 증권사 직원이 장중에 입력한 자료라 KIS가 정한 시각에만 갱신된다.
# 외국인 09:30·11:20·13:20·14:30, 기관종합 10:00·11:20·13:20·14:30.
# 그 합집합에 입력 지연을 감안해 1분을 더한 시각으로 수집한다.
STOCK_COLLECT_TIMES = ((9, 31), (10, 1), (11, 21), (13, 21), (14, 31))


def beat_schedule() -> dict[str, dict[str, Any]]:
    """국내 투자자 수급 수집 beat 항목을 만든다.

    Returns:
        Celery `beat_schedule`에 병합할 항목 딕셔너리.
    """

    return {
        **{
            f"investor-flow-stock-{hour:02d}{minute:02d}": {
                "task": "kis.korea.investor.collect_stock_intraday",
                "schedule": crontab(minute=minute, hour=hour, day_of_week="mon-fri"),
            }
            for hour, minute in STOCK_COLLECT_TIMES
        },
        "investor-flow-market-intraday": {
            "task": "kis.korea.investor.collect_market_intraday",
            # 시장 집계는 시세성이라 갱신 시각이 따로 없다. 정규장 09:00~15:30 30분 간격.
            "schedule": crontab(minute="0,30", hour="9-15", day_of_week="mon-fri"),
        },
        "investor-flow-final": {
            "task": "kis.korea.investor.collect_final",
            # 확정치는 장 마감 후에 나온다.
            "schedule": crontab(minute=10, hour=18, day_of_week="mon-fri"),
        },
    }
