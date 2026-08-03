import pandas as pd

from app.core._time import ET
from app.core.config import Settings
from app.kis.schemas import KISAuthTokenResponse


def settings(*, kis_virtual: bool = False) -> Settings:
    """일봉 수집 테스트용 설정을 반환한다."""

    return Settings(
        sentry_dsn='https://public@example.ingest.sentry.io/1',
        sentry_environment='test',
        sentry_release='news2@test',
        sentry_traces_sample_rate=0.0,
        sentry_error_sample_rate=0.0,
        database_url="postgresql+asyncpg://user:pass@localhost/news2",
        kis_virtual=kis_virtual,
        kis_app_key="app-key",
        kis_app_secret="app-secret",
        kis_rest_domain="https://rest.example",
        kis_websocket_domain="wss://websocket.example",
        kis_virtual_rest_domain="https://virtual-rest.example",
        kis_virtual_websocket_domain="wss://virtual-websocket.example",
    )


class FakeAuth:
    """접근 토큰 발급 횟수를 기록하는 테스트 인증 객체."""

    def __init__(self) -> None:
        self.call_count = 0

    async def get_auth_token(self) -> KISAuthTokenResponse:
        """고정된 테스트 접근 토큰을 반환한다."""

        self.call_count += 1
        return KISAuthTokenResponse(
            access_token="access-token",
            token_type="Bearer",
            expires_in=86400,
            access_token_token_expired="2026-07-22 00:00:00",
        )


# TR FHKST03010100 응답. KIS는 최신 거래일부터 내려주며, 요청 기간의 거래일이 정원보다
# 적으면 마지막에 빈 자리 채움 행이 붙어 올 수 있다.
KOREA_DAILY_CHART_RESPONSE: dict[str, object] = {
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다.",
    "output1": {"hts_kor_isnm": "삼성전자", "stck_shrn_iscd": "005930"},
    "output2": [
        {
            "stck_bsop_date": "20260730",
            "stck_clpr": "76800",
            "stck_oprc": "76100",
            "stck_hgpr": "77000",
            "stck_lwpr": "75900",
            "acml_vol": "12345678",
            "acml_tr_pbmn": "948000000000",
            "flng_cls_code": "00",
            "prtt_rate": "0.00",
            "mod_yn": "N",
        },
        {
            "stck_bsop_date": "20260729",
            "stck_clpr": "75600",
            "stck_oprc": "75000",
            "stck_hgpr": "75900",
            "stck_lwpr": "74800",
            "acml_vol": "9876543",
            "acml_tr_pbmn": "742000000000",
            "flng_cls_code": "00",
            "prtt_rate": "0.00",
            "mod_yn": "N",
        },
        {
            "stck_bsop_date": "",
            "stck_clpr": "",
            "stck_oprc": "",
            "stck_hgpr": "",
            "stck_lwpr": "",
            "acml_vol": "",
        },
        # 날짜만 채우고 값이 전부 빈 행. 투자자 수급 TR에서 실제로 이 모양이 온다.
        {
            "stck_bsop_date": "20241118",
            "stck_clpr": "",
            "stck_oprc": "",
            "stck_hgpr": "",
            "stck_lwpr": "",
            "acml_vol": "",
        },
    ],
}

KOREA_DAILY_CHART_ERROR_RESPONSE: dict[str, object] = {
    "rt_cd": "1",
    "msg_cd": "EGW00201",
    "msg1": "초당 거래건수를 초과하였습니다.",
    "output2": [],
}


def yahoo_daily_frame() -> pd.DataFrame:
    """거래소 현지 자정 인덱스를 가진 yfinance 일봉 DataFrame을 만든다."""

    index = pd.DatetimeIndex(
        [
            pd.Timestamp("2026-07-29 00:00:00", tz=ET),
            pd.Timestamp("2026-07-30 00:00:00", tz=ET),
        ]
    )
    return pd.DataFrame(
        {
            "Open": [210.5, 213.0],
            "High": [214.25, 215.5],
            "Low": [209.75, 212.0],
            "Close": [213.4, 214.8],
            "Volume": [45123400, 38210500],
        },
        index=index,
    )
