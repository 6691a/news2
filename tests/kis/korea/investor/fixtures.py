from app.core.config import Settings
from app.kis.schemas import KISAuthTokenResponse


def settings(*, kis_virtual: bool = False) -> Settings:
    """투자자 수급 진단 테스트용 설정을 반환한다."""

    return Settings(
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


STOCK_INTRADAY_FLOW_RESPONSES: tuple[dict[str, object], ...] = (
    {
        "output2": [
            {
                "bsop_hour_gb": "4",
                "frgn_fake_ntby_qty": "000000000000476000",
                "orgn_fake_ntby_qty": "000000000001164000",
                "sum_fake_ntby_qty": "000000000001640000",
            },
            {
                "bsop_hour_gb": "3",
                "frgn_fake_ntby_qty": "000000000000367000",
                "orgn_fake_ntby_qty": "000000000000623000",
                "sum_fake_ntby_qty": "000000000000990000",
            },
            {
                "bsop_hour_gb": "2",
                "frgn_fake_ntby_qty": "000000000000008000",
                "orgn_fake_ntby_qty": "-00000000000061000",
                "sum_fake_ntby_qty": "-00000000000053000",
            },
            {
                "bsop_hour_gb": "1",
                "frgn_fake_ntby_qty": "000000000000090000",
                "orgn_fake_ntby_qty": "000000000000000000",
                "sum_fake_ntby_qty": "000000000000090000",
            },
        ],
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리 되었습니다.",
    },
    {
        "output2": [
            {
                "bsop_hour_gb": "4",
                "frgn_fake_ntby_qty": "-00000000000147000",
                "orgn_fake_ntby_qty": "000000000000146000",
                "sum_fake_ntby_qty": "-00000000000001000",
            },
            {
                "bsop_hour_gb": "3",
                "frgn_fake_ntby_qty": "-00000000000089000",
                "orgn_fake_ntby_qty": "000000000000075000",
                "sum_fake_ntby_qty": "-00000000000014000",
            },
            {
                "bsop_hour_gb": "2",
                "frgn_fake_ntby_qty": "-00000000000061000",
                "orgn_fake_ntby_qty": "-00000000000017000",
                "sum_fake_ntby_qty": "-00000000000078000",
            },
            {
                "bsop_hour_gb": "1",
                "frgn_fake_ntby_qty": "000000000000001000",
                "orgn_fake_ntby_qty": "000000000000000000",
                "sum_fake_ntby_qty": "000000000000001000",
            },
        ],
        "rt_cd": "0",
        "msg_cd": "MCA00000",
        "msg1": "정상처리 되었습니다.",
    },
)

MARKET_INTRADAY_FLOW_RESPONSE: dict[str, object] = {
    "output": [
        {
            "frgn_seln_vol": "4114713",
            "frgn_shnu_vol": "4081868",
            "frgn_ntby_qty": "-32845",
            "frgn_seln_tr_pbmn": "12713602",
            "frgn_shnu_tr_pbmn": "13691086",
            "frgn_ntby_tr_pbmn": "977484",
            "prsn_seln_vol": "287236",
            "prsn_shnu_vol": "367744",
            "prsn_ntby_qty": "80508",
            "prsn_seln_tr_pbmn": "1016620",
            "prsn_shnu_tr_pbmn": "1271780",
            "prsn_ntby_tr_pbmn": "255160",
            "orgn_seln_vol": "1827737",
            "orgn_shnu_vol": "1725619",
            "orgn_ntby_qty": "-102118",
            "orgn_seln_tr_pbmn": "6387644",
            "orgn_shnu_tr_pbmn": "4988248",
            "orgn_ntby_tr_pbmn": "-1399396",
            "scrt_seln_vol": "1031084",
            "scrt_shnu_vol": "925178",
            "scrt_ntby_qty": "-105906",
            "scrt_seln_tr_pbmn": "3409855",
            "scrt_shnu_tr_pbmn": "2087912",
            "scrt_ntby_tr_pbmn": "-1321943",
            "ivtr_seln_vol": "16521",
            "ivtr_shnu_vol": "32932",
            "ivtr_ntby_qty": "16411",
            "ivtr_seln_tr_pbmn": "58680",
            "ivtr_shnu_tr_pbmn": "117914",
            "ivtr_ntby_tr_pbmn": "59234",
            "pe_fund_seln_tr_pbmn": "0",
            "pe_fund_seln_vol": "0",
            "pe_fund_ntby_vol": "0",
            "pe_fund_shnu_tr_pbmn": "0",
            "pe_fund_shnu_vol": "0",
            "pe_fund_ntby_tr_pbmn": "0",
            "bank_seln_vol": "0",
            "bank_shnu_vol": "0",
            "bank_ntby_qty": "0",
            "bank_seln_tr_pbmn": "0",
            "bank_shnu_tr_pbmn": "0",
            "bank_ntby_tr_pbmn": "0",
            "insu_seln_vol": "74",
            "insu_shnu_vol": "157",
            "insu_ntby_qty": "83",
            "insu_seln_tr_pbmn": "446",
            "insu_shnu_tr_pbmn": "806",
            "insu_ntby_tr_pbmn": "360",
            "mrbn_seln_vol": "0",
            "mrbn_shnu_vol": "0",
            "mrbn_ntby_qty": "0",
            "mrbn_seln_tr_pbmn": "0",
            "mrbn_shnu_tr_pbmn": "0",
            "mrbn_ntby_tr_pbmn": "0",
            "fund_seln_vol": "780058",
            "fund_shnu_vol": "767352",
            "fund_ntby_qty": "-12706",
            "fund_seln_tr_pbmn": "2918663",
            "fund_shnu_tr_pbmn": "2781616",
            "fund_ntby_tr_pbmn": "-137047",
            "etc_orgt_seln_vol": "0",
            "etc_orgt_shnu_vol": "0",
            "etc_orgt_ntby_vol": "0",
            "etc_orgt_seln_tr_pbmn": "0",
            "etc_orgt_shnu_tr_pbmn": "0",
            "etc_orgt_ntby_tr_pbmn": "0",
            "etc_corp_seln_vol": "15884",
            "etc_corp_shnu_vol": "70339",
            "etc_corp_ntby_vol": "54455",
            "etc_corp_seln_tr_pbmn": "90504",
            "etc_corp_shnu_tr_pbmn": "257257",
            "etc_corp_ntby_tr_pbmn": "166752",
        }
    ],
    "rt_cd": "0",
    "msg_cd": "MCA00000",
    "msg1": "정상처리 되었습니다.",
}

INTRADAY_FLOW_RESPONSES = (*STOCK_INTRADAY_FLOW_RESPONSES, MARKET_INTRADAY_FLOW_RESPONSE)
