"""Celery 애플리케이션과 주기 작업 스케줄."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings


app = Celery("news2", broker=settings.redis_url)

# 결과를 조회할 일이 없으므로 result backend를 두지 않는다. 켜두면 Redis에
# 아무도 읽지 않는 결과 키만 쌓인다.
app.conf.timezone = "Asia/Seoul"
app.conf.enable_utc = False
app.conf.task_acks_late = True
# asyncio.run을 반복 호출하므로 주기적으로 프로세스를 재활용해 누수를 끊는다.
app.conf.worker_max_tasks_per_child = 100
app.conf.imports = ("app.kis.korea.investor.tasks",)

# beat crontab만 KST로 읽는다. CLAUDE.md의 UTC 규칙은 저장되는 datetime에 대한
# 것이고, DB에 들어가는 값은 여전히 전부 UTC다. 장 시간(09:00~15:30)과 같은
# 눈금으로 읽히는 편이 UTC로 환산해 적는 것보다 덜 틀린다.
#
# 공휴일은 crontab으로 거를 수 없다. 휴장일에는 빈 응답이 와서 0행 저장으로
# 끝나므로 그대로 둔다.

# 종목 가집계는 증권사 직원이 장중에 입력한 자료라 KIS가 정한 시각에만 갱신된다.
# 외국인 09:30·11:20·13:20·14:30, 기관종합 10:00·11:20·13:20·14:30.
# 그 합집합에 입력 지연을 감안해 1분을 더한 시각으로 수집한다.
STOCK_COLLECT_TIMES = ((9, 31), (10, 1), (11, 21), (13, 21), (14, 31))

app.conf.beat_schedule = {
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
