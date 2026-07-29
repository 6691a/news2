"""KIS 국내 투자자 수급 REST 요청 구성."""

from app.core.config import Settings
from app.kis.korea.investor.schemas import (
    InvestorFlowMarketDivisionCode,
    InvestorFlowMarketIndexCode,
    InvestorFlowPhase,
    InvestorFlowProbeOptions,
    InvestorFlowRequest,
    InvestorFlowRequestHeaders,
    InvestorFlowScope,
    InvestorFlowStockMarketCode,
    InvestorFlowTrId,
    InvestorFlowVenue,
    MarketFinalFlowParams,
    MarketIntradayFlowParams,
    StockFinalFlowParams,
    StockIntradayFlowParams,
)


def build_requests(options: InvestorFlowProbeOptions) -> tuple[InvestorFlowRequest, ...]:
    """실행 단계와 대상 범위에 맞는 공식 KIS 요청 명세를 반환한다.

    Args:
        options: 장중 또는 장 마감 수집 옵션. scope로 종목·시장을 가려낸다.

    Returns:
        호출 순서대로 정렬된 KIS REST 요청 명세.
    """

    wants_stock = options.scope is not InvestorFlowScope.MARKET
    wants_market = options.scope is not InvestorFlowScope.STOCK
    stocks = (("005930", "삼성전자"), ("000660", "SK하이닉스")) if wants_stock else ()
    if options.phase is InvestorFlowPhase.INTRADAY:
        stock_requests = tuple(
            InvestorFlowRequest(
                target=stock_code,
                target_name=stock_name,
                venue=InvestorFlowVenue.UNSPECIFIED,
                tr_id=InvestorFlowTrId.STOCK_INTRADAY,
                params=StockIntradayFlowParams(stock_code=stock_code),
            )
            for stock_code, stock_name in stocks
        )
        market_requests = (
            InvestorFlowRequest(
                target="KOSPI",
                target_name="코스피",
                venue=InvestorFlowVenue.KRX,
                tr_id=InvestorFlowTrId.KOSPI_INTRADAY,
                params=MarketIntradayFlowParams(
                    market_code="999",
                    industry_code="S001",
                ),
            ),
        )
        return stock_requests + (market_requests if wants_market else ())

    trade_date = options.trade_date
    assert trade_date is not None
    trade_date_param = trade_date.strftime("%Y%m%d")
    market_codes = (
        (InvestorFlowVenue.KRX, InvestorFlowStockMarketCode.KRX),
        (InvestorFlowVenue.NXT, InvestorFlowStockMarketCode.NXT),
    )
    stock_requests = tuple(
        InvestorFlowRequest(
            target=stock_code,
            target_name=stock_name,
            venue=venue,
            tr_id=InvestorFlowTrId.STOCK_FINAL,
            params=StockFinalFlowParams(
                market_code=market_code,
                stock_code=stock_code,
                trade_date=trade_date_param,
                original_adjusted_price="",
                other_classification_code="",
            ),
        )
        for stock_code, stock_name in stocks
        for venue, market_code in market_codes
    )
    market_requests = (
        InvestorFlowRequest(
            target="KOSPI",
            target_name="코스피",
            venue=InvestorFlowVenue.KRX,
            tr_id=InvestorFlowTrId.KOSPI_FINAL,
            params=MarketFinalFlowParams(
                market_division_code=InvestorFlowMarketDivisionCode.INDUSTRY,
                market_code="0001",
                trade_date_start=trade_date_param,
                market_index_code=InvestorFlowMarketIndexCode.KOSPI,
                trade_date_end=trade_date_param,
                industry_code="0001",
            ),
        ),
    )
    return stock_requests + (market_requests if wants_market else ())


def build_headers(
    settings: Settings,
    access_token: str,
    request: InvestorFlowRequest,
) -> InvestorFlowRequestHeaders:
    """공식 KIS REST 조회 헤더를 구성한다.

    Args:
        settings: 실전 앱키와 앱시크릿을 담은 설정.
        access_token: REST 접근 토큰.
        request: 호출할 요청 명세.

    Returns:
        KIS GET 조회에 사용할 HTTP 헤더.
    """

    return InvestorFlowRequestHeaders(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
        ),
        authorization=f"Bearer {access_token}",
        app_key=settings.kis_app_key,
        app_secret=settings.kis_app_secret,
        tr_id=request.tr_id,
    )
