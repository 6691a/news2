import logging
from datetime import UTC, date, datetime
from decimal import Decimal

import numpy as np
import pytest

from app.instruments.models import Market
from app.ohlcv.korea import split_period
from app.core.collection import BACKFILL_START
from app.ohlcv.schemas import (
    MARKET_SESSION,
    KoreaDailyChartBody,
    OhlcvCollectOptions,
    OhlcvScope,
    parse_korea_daily_chart,
    parse_yahoo_daily_frame,
    session_settled,
    session_start,
)
from tests.ohlcv.fixtures import KOREA_DAILY_CHART_RESPONSE, yahoo_daily_frame


# 2026-07-31 06:30 UTC = KST 15:30, ET 02:30. 국내는 마감 직전, 미국은 전일 마감 뒤다.
AS_OF = datetime(2026, 7, 31, 6, 30, tzinfo=UTC)


def test_session_start_maps_local_midnight_to_utc() -> None:
    assert session_start(Market.KRX, date(2026, 7, 30)) == datetime(2026, 7, 29, 15, 0, tzinfo=UTC)
    assert session_start(Market.NASDAQ, date(2026, 7, 30)) == datetime(2026, 7, 30, 4, 0, tzinfo=UTC)


def test_session_settled_excludes_session_before_close() -> None:
    assert session_settled(Market.KRX, session_start(Market.KRX, date(2026, 7, 30)), AS_OF) is True
    # KST 15:30은 마감 여유(15:40) 전이라 당일 봉은 아직 확정이 아니다.
    assert session_settled(Market.KRX, session_start(Market.KRX, date(2026, 7, 31)), AS_OF) is False


def test_session_settled_waits_a_full_day_for_round_the_clock_markets() -> None:
    # 환율은 마감이 없어 하루가 통째로 지나야 확정이다. AS_OF는 07-31 06:30 UTC(ET 02:30)라
    # 07-30 봉은 방금(07-31 04:00 UTC) 끝났고 07-31 봉은 아직 진행 중이다.
    assert session_settled(Market.FX, session_start(Market.FX, date(2026, 7, 30)), AS_OF) is True
    assert session_settled(Market.FX, session_start(Market.FX, date(2026, 7, 31)), AS_OF) is False


def test_every_market_has_a_session_definition() -> None:
    # 시장을 늘리고 세션 표를 빠뜨리면 그 계열 수집이 KeyError로 죽는다.
    assert set(MARKET_SESSION) == set(Market)


def test_parse_korea_daily_chart_drops_blank_rows_and_sorts_ascending() -> None:
    body = KoreaDailyChartBody.model_validate(KOREA_DAILY_CHART_RESPONSE)

    result = parse_korea_daily_chart("005930", body, as_of=AS_OF)

    assert result.ticker == "005930"
    assert result.market is Market.KRX
    assert [bar.event_ts for bar in result.bars] == [
        datetime(2026, 7, 28, 15, 0, tzinfo=UTC),
        datetime(2026, 7, 29, 15, 0, tzinfo=UTC),
    ]
    assert result.bars[1].open == Decimal("76100")
    assert result.bars[1].high == Decimal("77000")
    assert result.bars[1].low == Decimal("75900")
    assert result.bars[1].close == Decimal("76800")
    assert result.bars[1].volume == 12345678


def test_parse_korea_daily_chart_excludes_unsettled_session() -> None:
    body = KoreaDailyChartBody.model_validate(KOREA_DAILY_CHART_RESPONSE)

    # 2026-07-30 KST 09:30 — 07-30 장이 아직 끝나지 않은 시각.
    result = parse_korea_daily_chart("005930", body, as_of=datetime(2026, 7, 30, 0, 30, tzinfo=UTC))

    assert [bar.event_ts for bar in result.bars] == [datetime(2026, 7, 28, 15, 0, tzinfo=UTC)]


def test_parse_yahoo_daily_frame_converts_local_midnight_index() -> None:
    result = parse_yahoo_daily_frame("AAPL", Market.NASDAQ, yahoo_daily_frame(), as_of=AS_OF)

    assert [bar.event_ts for bar in result.bars] == [
        datetime(2026, 7, 29, 4, 0, tzinfo=UTC),
        datetime(2026, 7, 30, 4, 0, tzinfo=UTC),
    ]
    assert result.bars[0].close == Decimal("213.4")
    assert result.bars[0].volume == 45123400


def test_parse_yahoo_daily_frame_skips_rows_without_price() -> None:
    frame = yahoo_daily_frame()
    frame.loc[frame.index[0], "Close"] = np.nan

    result = parse_yahoo_daily_frame("AAPL", Market.NASDAQ, frame, as_of=AS_OF)

    assert [bar.event_ts for bar in result.bars] == [datetime(2026, 7, 30, 4, 0, tzinfo=UTC)]


def test_parse_yahoo_daily_frame_rejects_naive_index() -> None:
    frame = yahoo_daily_frame().tz_localize(None)

    with pytest.raises(ValueError, match="timezone-aware"):
        parse_yahoo_daily_frame("AAPL", Market.NASDAQ, frame, as_of=AS_OF)


def test_collect_options_period_defaults_to_recent_local_window() -> None:
    options = OhlcvCollectOptions(scope=OhlcvScope.KOREA)

    start, end = options.period(Market.KRX, AS_OF)

    assert (start, end) == (date(2026, 7, 24), date(2026, 7, 31))


def test_collect_options_period_uses_given_range() -> None:
    options = OhlcvCollectOptions(start=date(2024, 1, 1), end=date(2024, 3, 1))

    assert options.period(Market.NASDAQ, AS_OF) == (date(2024, 1, 1), date(2024, 3, 1))


def test_collect_options_period_without_end_runs_to_local_today() -> None:
    options = OhlcvCollectOptions(start=BACKFILL_START)

    # 같은 순간이라도 KST는 07-31, ET는 07-31 02:30이라 종료일이 시장마다 정해진다.
    assert options.period(Market.KRX, AS_OF) == (BACKFILL_START, date(2026, 7, 31))
    assert options.period(Market.NASDAQ, AS_OF) == (BACKFILL_START, date(2026, 7, 31))


def test_collect_options_rejects_end_without_start() -> None:
    with pytest.raises(ValueError, match="end requires start"):
        OhlcvCollectOptions(end=date(2024, 1, 1))


def test_collect_options_rejects_reversed_period() -> None:
    with pytest.raises(ValueError, match="after end"):
        OhlcvCollectOptions(start=date(2024, 3, 1), end=date(2024, 1, 1))


def test_scope_markets() -> None:
    assert OhlcvScope.KOREA.markets == frozenset({Market.KRX})
    # 해외는 "국내가 아닌 전부" — 매크로 시장을 늘려도 자동으로 포함된다.
    assert Market.KRX not in OhlcvScope.OVERSEAS.markets
    assert {Market.NASDAQ, Market.US_INDEX, Market.FX, Market.GLOBEX} <= OhlcvScope.OVERSEAS.markets
    assert OhlcvScope.ALL.markets == frozenset(Market)


def test_split_period_chunks_within_response_limit() -> None:
    periods = split_period(date(2024, 1, 1), date(2024, 12, 31))

    assert periods[0] == (date(2024, 1, 1), date(2024, 4, 9))
    assert periods[-1][1] == date(2024, 12, 31)
    assert all((end - start).days < 100 for start, end in periods)
    # 구간이 겹치지도 비지도 않는다.
    assert all((later[0] - earlier[1]).days == 1 for earlier, later in zip(periods, periods[1:], strict=False))


def test_split_period_single_day() -> None:
    assert split_period(date(2024, 1, 1), date(2024, 1, 1)) == [(date(2024, 1, 1), date(2024, 1, 1))]


def test_parse_yahoo_daily_frame_keeps_index_bars_without_volume() -> None:
    # 지수는 체결이 없어 거래량이 NaN으로 온다. 가격이 멀쩡하면 버리면 안 된다.
    frame = yahoo_daily_frame()
    frame["Volume"] = np.nan

    result = parse_yahoo_daily_frame("KOSPI", Market.KRX, frame, as_of=AS_OF)

    assert len(result.bars) == 2
    assert all(bar.volume == 0 for bar in result.bars)


def test_parse_yahoo_daily_frame_warns_when_rows_lack_price(caplog: pytest.LogCaptureFixture) -> None:
    frame = yahoo_daily_frame()
    frame.loc[frame.index[0], "Close"] = np.nan

    with caplog.at_level(logging.WARNING):
        parse_yahoo_daily_frame("AAPL", Market.NASDAQ, frame, as_of=AS_OF)

    assert "yahoo_daily_chart_rows_without_price" in caplog.text


def test_korea_daily_chart_body_warns_when_blank_rows_dropped(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        KoreaDailyChartBody.model_validate(KOREA_DAILY_CHART_RESPONSE)

    # 픽스처에 빈 자리 채움 행이 하나 있다.
    assert "kis_daily_chart_blank_rows_dropped" in caplog.text
