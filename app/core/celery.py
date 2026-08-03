"""Celery 애플리케이션과 각 패키지 beat 스케줄 등록."""

from celery import Celery

from app.core.config import settings
from app.core.sentry import configure_sentry
from app.kis.korea.investor.beats import beat_schedule as investor_beat_schedule
from app.macro.us.treasury.beats import beat_schedule as us_treasury_beat_schedule
from app.notifications.beats import beat_schedule as notification_beat_schedule
from app.ohlcv.beats import beat_schedule as ohlcv_beat_schedule


configure_sentry(settings)
app = Celery("news2", broker=settings.redis_url)

# 결과를 조회할 일이 없으므로 result backend를 두지 않는다. 켜두면 Redis에
# 아무도 읽지 않는 결과 키만 쌓인다.
app.conf.timezone = "Asia/Seoul"
app.conf.enable_utc = False
app.conf.task_acks_late = True
# asyncio.run을 반복 호출하므로 주기적으로 프로세스를 재활용해 누수를 끊는다.
app.conf.worker_max_tasks_per_child = 100
app.conf.imports = (
    "app.kis.korea.investor.tasks",
    "app.macro.us.treasury.tasks",
    "app.ohlcv.tasks",
    "app.notifications.tasks",
)

# beat crontab만 KST로 읽는다. CLAUDE.md의 UTC 규칙은 저장되는 datetime에 대한
# 것이고, DB에 들어가는 값은 여전히 전부 UTC다. 장 시간(09:00~15:30)과 같은
# 눈금으로 읽히는 편이 UTC로 환산해 적는 것보다 덜 틀린다.
#
# 공휴일은 crontab으로 거를 수 없다. 휴장일에는 빈 응답이 와서 0행 저장으로
# 끝나므로 그대로 둔다.
#
# 스케줄 본문은 각 패키지의 beats.py에 있다. 여기서는 모아 등록만 한다.
# beats.py는 task를 import하지 않고 task 이름 문자열만 참조하므로 순환 import가 없다.
app.conf.beat_schedule = {
    **investor_beat_schedule(),
    **us_treasury_beat_schedule(),
    **ohlcv_beat_schedule(),
    **notification_beat_schedule(),
}
