"""미국 국채 수집 테스트에 쓰는 실측 데이터 샘플."""

import pandas as pd

from app.core.config import Settings


def settings(*, fred_api_key: str = "fred-key") -> Settings:
    """미국 국채 수집 테스트용 설정을 반환한다.

    Args:
        fred_api_key: 확정치 조회에 쓸 FRED API 키.

    Returns:
        테스트용 Settings 인스턴스.
    """

    return Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/news2",
        redis_url="redis://localhost:6379/0",
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_rest_domain="https://rest.example",
        kis_websocket_domain="wss://websocket.example",
        kis_virtual_rest_domain="https://virtual-rest.example",
        kis_virtual_websocket_domain="wss://virtual-websocket.example",
        fred_api_key=fred_api_key,
    )


# 실측 Yahoo 응답과 같은 값·거래소 시간대를 가진 yfinance history DataFrame.
TNX_HISTORY_FRAME = pd.DataFrame(
    {
        "Open": [4.647000312805176, 4.647000312805176, 4.647000312805176],
        "High": [4.647000312805176, 4.64900016784668, 4.64900016784668],
        "Low": [4.647000312805176, 4.647000312805176, 4.638999938964844],
        "Close": [4.647000312805176, 4.647000312805176, 4.640999794006348],
        "Volume": [0, 0, 0],
    },
    index=pd.date_range("2026-07-27 07:20", periods=3, freq="min", tz="America/Chicago"),
)

ZN_HISTORY_FRAME = pd.DataFrame(
    {
        "Open": [108.65625, 108.65625, 108.65625, None],
        "High": [108.65625, 108.65625, 108.671875, None],
        "Low": [108.65625, 108.65625, 108.65625, None],
        "Close": [108.65625, 108.65625, 108.671875, None],
        "Volume": [0, 2, 769, None],
    },
    index=pd.date_range("2026-07-28 00:00", periods=4, freq="min", tz="America/New_York"),
)

FRED_DGS10_RESPONSE: dict[str, object] = {
    "realtime_start": "2026-07-28",
    "realtime_end": "2026-07-28",
    "observation_start": "2026-07-24",
    "observation_end": "2026-07-24",
    "units": "lin",
    "output_type": 1,
    "file_type": "json",
    "order_by": "observation_date",
    "sort_order": "asc",
    "count": 1,
    "offset": 0,
    "limit": 100000,
    "observations": [
        {
            "realtime_start": "2026-07-28",
            "realtime_end": "2026-07-28",
            "date": "2026-07-24",
            "value": "4.64",
        }
    ],
}

# 휴장일·미공표 관측값은 value가 "."로 온다.
FRED_DGS10_MISSING_RESPONSE: dict[str, object] = {
    **FRED_DGS10_RESPONSE,
    "observations": [
        {
            "realtime_start": "2026-07-28",
            "realtime_end": "2026-07-28",
            "date": "2026-07-24",
            "value": ".",
        }
    ],
}

# 아직 관측값 자체가 없는 응답.
FRED_DGS10_EMPTY_RESPONSE: dict[str, object] = {
    **FRED_DGS10_RESPONSE,
    "count": 0,
    "observations": [],
}
