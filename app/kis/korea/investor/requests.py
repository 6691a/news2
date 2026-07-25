"""KIS 국내 투자자 수급 REST 요청 구성."""

from app.core.config import Settings
from app.kis.korea.investor.schemas import (
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowRequest,
    InvestorFlowTrId,
    InvestorFlowVenue,
)


def build_requests(options: InvestorFlowProbeOptions) -> tuple[InvestorFlowRequest, ...]:
    """실행 단계에 맞는 공식 KIS 요청 명세를 반환한다.

    Args:
        options: 장중 또는 장 마감 진단 옵션.

    Returns:
        호출 순서대로 정렬된 KIS REST 요청 명세.
    """

    stocks = (("005930", "삼성전자"), ("000660", "SK하이닉스"))
    if options.phase is InvestorFlowPhase.INTRADAY:
        stock_requests = tuple(
            InvestorFlowRequest(
                target=stock_code,
                target_name=stock_name,
                venue=InvestorFlowVenue.UNSPECIFIED,
                tr_id=InvestorFlowTrId.STOCK_INTRADAY,
                params={"MKSC_SHRN_ISCD": stock_code},
            )
            for stock_code, stock_name in stocks
        )
        return stock_requests + (
            InvestorFlowRequest(
                target="KOSPI",
                target_name="코스피",
                venue=InvestorFlowVenue.KRX,
                tr_id=InvestorFlowTrId.KOSPI_INTRADAY,
                params={
                    "FID_INPUT_ISCD": "999",
                    "FID_INPUT_ISCD_2": "S001",
                },
            ),
        )

    trade_date = options.trade_date
    assert trade_date is not None
    trade_date_param = trade_date.strftime("%Y%m%d")
    market_codes = (
        (InvestorFlowVenue.KRX, "J"),
        (InvestorFlowVenue.NXT, "NX"),
    )
    stock_requests = tuple(
        InvestorFlowRequest(
            target=stock_code,
            target_name=stock_name,
            venue=venue,
            tr_id=InvestorFlowTrId.STOCK_FINAL,
            params={
                "FID_COND_MRKT_DIV_CODE": market_code,
                "FID_INPUT_ISCD": stock_code,
                "FID_INPUT_DATE_1": trade_date_param,
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
            },
        )
        for stock_code, stock_name in stocks
        for venue, market_code in market_codes
    )
    return stock_requests + (
        InvestorFlowRequest(
            target="KOSPI",
            target_name="코스피",
            venue=InvestorFlowVenue.KRX,
            tr_id=InvestorFlowTrId.KOSPI_FINAL,
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001",
                "FID_INPUT_DATE_1": trade_date_param,
                "FID_INPUT_ISCD_1": "KSP",
                "FID_INPUT_DATE_2": trade_date_param,
                "FID_INPUT_ISCD_2": "0001",
            },
        ),
    )


def build_headers(
    settings: Settings,
    access_token: str,
    request: InvestorFlowRequest,
) -> dict[str, str]:
    """공식 KIS REST 조회 헤더를 구성한다.

    Args:
        settings: 실전 앱키와 앱시크릿을 담은 설정.
        access_token: REST 접근 토큰.
        request: 호출할 요청 명세.

    Returns:
        KIS GET 조회에 사용할 HTTP 헤더.
    """

    return {
        "Content-Type": "application/json",
        "Accept": "text/plain",
        "charset": "UTF-8",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        "authorization": f"Bearer {access_token}",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
        "tr_id": request.tr_id.value,
        "custtype": "P",
        "tr_cont": "",
    }
