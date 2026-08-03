"""KIS 국내 투자자 수급 수집 스키마."""

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Self, cast

from pydantic import BaseModel, Field, JsonValue, RootModel, field_validator, model_validator

from app.core.logging import get_logger
from app.kis.schemas.common import KISBaseModel


logger = get_logger(__name__)


# date.weekday()의 토요일. 이 값 이상이면 주말이다.
SATURDAY = 5


class InvestorFlowPhase(StrEnum):
    """투자자 수급 수집 시점."""

    INTRADAY = "intraday"
    FINAL = "final"


class InvestorFlowScope(StrEnum):
    """한 번의 수집이 다룰 조회 대상 범위.

    두 TR의 갱신 주기가 달라서 같은 스케줄로 묶을 수 없다. 종목 가집계는 KIS가
    정한 입력시간에만 갱신되고(외국인 09:30·11:20·13:20·14:30, 기관 10:00·
    11:20·13:20·14:30), 시장 집계는 시세성이라 그보다 자주 바뀐다.
    """

    STOCK = "stock"
    MARKET = "market"
    ALL = "all"


class InvestorFlowVenue(StrEnum):
    """응답에 부여할 거래 시장 범위."""

    KRX = "KRX"
    NXT = "NXT"
    UNSPECIFIED = "UNSPECIFIED"


class InvestorType(StrEnum):
    """저장용으로 정규화한 투자자 유형.

    KIS 응답 필드 접두사를 사람이 읽는 이름으로 옮긴 것이다. 값이 DB에 그대로
    들어가므로 나중에 바꾸면 마이그레이션이 필요하다.

    INSTITUTION은 SECURITIES~PENSION_FUND의 합계다. 집계 쿼리에서 기관계와
    하위 유형을 함께 더하면 이중 계산이 된다.
    """

    FOREIGN = "foreign"  # frgn_*      외국인
    RETAIL = "retail"  # prsn_*      개인
    INSTITUTION = "institution"  # orgn_*      기관계(하위 유형의 합)
    SECURITIES = "securities"  # scrt_*      증권
    TRUST = "trust"  # ivtr_*      투자신탁
    PRIVATE_EQUITY = "private_equity"  # pe_fund_*   사모펀드
    BANK = "bank"  # bank_*      은행
    INSURANCE = "insurance"  # insu_*      보험
    MERCHANT_BANK = "merchant_bank"  # mrbn_*      종금
    PENSION_FUND = "pension_fund"  # fund_*      기금
    OTHER_ORGANIZATION = "other_organization"  # etc_orgt_*  기타 단체
    OTHER_CORPORATION = "other_corporation"  # etc_corp_*  기타 법인


INVESTOR_FLOW_FIELD_PARTS: dict[InvestorType, tuple[str, str]] = {
    InvestorType.FOREIGN: ("frgn", "qty"),
    InvestorType.RETAIL: ("prsn", "qty"),
    InvestorType.INSTITUTION: ("orgn", "qty"),
    InvestorType.SECURITIES: ("scrt", "qty"),
    InvestorType.TRUST: ("ivtr", "qty"),
    InvestorType.PRIVATE_EQUITY: ("pe_fund", "vol"),
    InvestorType.BANK: ("bank", "qty"),
    InvestorType.INSURANCE: ("insu", "qty"),
    InvestorType.MERCHANT_BANK: ("mrbn", "qty"),
    InvestorType.PENSION_FUND: ("fund", "qty"),
    InvestorType.OTHER_ORGANIZATION: ("etc_orgt", "vol"),
    InvestorType.OTHER_CORPORATION: ("etc_corp", "vol"),
}


class InvestorFlowTrId(StrEnum):
    """투자자 수급 REST API의 HTTP TR ID."""

    STOCK_INTRADAY = "HHPTJ04160200"
    KOSPI_INTRADAY = "FHPTJ04030000"
    STOCK_FINAL = "FHPTJ04160001"
    KOSPI_FINAL = "FHPTJ04040000"

    @property
    def path(self) -> str:
        """TR ID에 대응하는 REST API 경로."""

        return {
            self.STOCK_INTRADAY: "/uapi/domestic-stock/v1/quotations/investor-trend-estimate",
            self.KOSPI_INTRADAY: "/uapi/domestic-stock/v1/quotations/inquire-investor-time-by-market",
            self.STOCK_FINAL: "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
            self.KOSPI_FINAL: "/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market",
        }[self]


class InvestorFlowStockMarketCode(StrEnum):
    """종목별 마감 수급 조회 시장 코드."""

    KRX = "J"
    NXT = "NX"
    UNIFIED = "UN"


class InvestorFlowMarketDivisionCode(StrEnum):
    """시장별 마감 수급 조회 시장 구분 코드."""

    INDUSTRY = "U"


class InvestorFlowMarketIndexCode(StrEnum):
    """시장별 마감 수급 조회 지수 코드."""

    KOSPI = "KSP"
    KOSDAQ = "KSQ"


class StockIntradayFlowParams(KISBaseModel):
    """종목별 장중 수급 조회 파라미터."""

    stock_code: str = Field(serialization_alias="MKSC_SHRN_ISCD")


class MarketIntradayFlowParams(KISBaseModel):
    """시장별 장중 수급 조회 파라미터."""

    market_code: str = Field(serialization_alias="FID_INPUT_ISCD")
    industry_code: str = Field(serialization_alias="FID_INPUT_ISCD_2")


class StockFinalFlowParams(KISBaseModel):
    """종목별 마감 수급 조회 파라미터."""

    market_code: InvestorFlowStockMarketCode = Field(serialization_alias="FID_COND_MRKT_DIV_CODE")
    stock_code: str = Field(serialization_alias="FID_INPUT_ISCD")
    trade_date: str = Field(serialization_alias="FID_INPUT_DATE_1", pattern=r"^\d{8}$")
    original_adjusted_price: str = Field(serialization_alias="FID_ORG_ADJ_PRC")
    other_classification_code: str = Field(serialization_alias="FID_ETC_CLS_CODE")


class MarketFinalFlowParams(KISBaseModel):
    """시장별 마감 수급 조회 파라미터."""

    market_division_code: InvestorFlowMarketDivisionCode = Field(serialization_alias="FID_COND_MRKT_DIV_CODE")
    market_code: str = Field(serialization_alias="FID_INPUT_ISCD")
    trade_date_start: str = Field(serialization_alias="FID_INPUT_DATE_1", pattern=r"^\d{8}$")
    market_index_code: InvestorFlowMarketIndexCode = Field(serialization_alias="FID_INPUT_ISCD_1")
    trade_date_end: str = Field(serialization_alias="FID_INPUT_DATE_2", pattern=r"^\d{8}$")
    industry_code: str = Field(serialization_alias="FID_INPUT_ISCD_2")


type InvestorFlowParams = (
    StockIntradayFlowParams | MarketIntradayFlowParams | StockFinalFlowParams | MarketFinalFlowParams
)


class InvestorFlowProbeOptions(BaseModel):
    """투자자 수급 수집 실행 옵션."""

    phase: InvestorFlowPhase
    scope: InvestorFlowScope = InvestorFlowScope.ALL
    trade_date: date | None = None  # 마감 조회일. 백필에서는 구간 종료일
    start_date: date | None = None  # 백필 구간 시작일. None이면 trade_date 하루만

    @model_validator(mode="after")
    def validate_trade_date(self) -> Self:
        """마감 조회일과 백필 구간을 검증한다.

        Returns:
            검증을 통과한 옵션.

        Raises:
            ValueError: 마감 수집에 조회일이 없거나, 장중 수집에 백필 구간을 주었거나,
                구간 순서가 뒤집힌 경우.
        """

        if self.phase is InvestorFlowPhase.FINAL:
            if self.trade_date is None:
                raise ValueError("final phase requires trade_date")
            if self.start_date is not None and self.start_date > self.trade_date:
                raise ValueError("start_date must not be after trade_date")
        elif self.start_date is not None:
            raise ValueError("intraday phase does not accept start_date")
        return self

    def trade_dates(self) -> tuple[date, ...]:
        """수집할 한국 거래일 목록을 만든다.

        종목 확정 TR은 날짜를 하나씩만 받아 백필이 곧 날짜 루프다. 주말은 어차피 빈
        응답이라 미리 걸러 호출 수를 3할 줄인다. 공휴일은 달력 없이 거를 수 없어
        그대로 호출하고 0행으로 끝난다.

        Returns:
            오름차순 거래일 목록. 백필이 아니면 원소 하나(또는 장중이면 빈 튜플).
        """

        if self.trade_date is None:
            return ()
        if self.start_date is None:
            return (self.trade_date,)

        span = (self.trade_date - self.start_date).days
        days = (self.start_date + timedelta(days=offset) for offset in range(span + 1))
        return tuple(day for day in days if day.weekday() < SATURDAY)


class InvestorFlowRequest(BaseModel):
    """단일 KIS 투자자 수급 REST 요청 명세."""

    target: str
    target_name: str
    venue: InvestorFlowVenue
    tr_id: InvestorFlowTrId
    params: InvestorFlowParams

    @model_validator(mode="after")
    def validate_params_for_tr_id(self) -> Self:
        """TR ID에 대응하는 파라미터 DTO인지 검증한다."""

        expected_type = {
            InvestorFlowTrId.STOCK_INTRADAY: StockIntradayFlowParams,
            InvestorFlowTrId.KOSPI_INTRADAY: MarketIntradayFlowParams,
            InvestorFlowTrId.STOCK_FINAL: StockFinalFlowParams,
            InvestorFlowTrId.KOSPI_FINAL: MarketFinalFlowParams,
        }[self.tr_id]
        if not isinstance(self.params, expected_type):
            raise ValueError(f"{self.tr_id.value} requires {expected_type.__name__}")
        return self


class InvestorFlowRequestHeaders(KISBaseModel):
    """KIS 투자자 수급 REST 요청 공통 헤더."""

    content_type: str = Field(serialization_alias="Content-Type", default="application/json")
    accept: str = Field(serialization_alias="Accept", default="text/plain")
    charset: str = "UTF-8"
    user_agent: str = Field(serialization_alias="User-Agent")
    authorization: str
    app_key: str = Field(serialization_alias="appkey")
    app_secret: str = Field(serialization_alias="appsecret")
    tr_id: InvestorFlowTrId
    customer_type: str = Field(serialization_alias="custtype", default="P")
    tr_cont: str = ""


# --- 응답 본문 DTO ---------------------------------------------------------


class InvestorFlowEnvelope(BaseModel):
    """KIS 응답 공통 봉투. 모든 투자자 수급 본문이 공유한다."""

    rt_cd: str  # 결과 코드("0": 성공)
    msg_cd: str  # 응답 메시지 코드
    msg1: str  # 응답 메시지


class StockIntradayFlowRow(BaseModel):
    """종목별 장중 가집계 순매수 한 시간대 행 (TR HHPTJ04160200, output2 원소)."""

    bsop_hour_gb: str  # 입력 구분(장중 집계 시점 1~4)
    frgn_fake_ntby_qty: int  # 외국인 가집계 순매수 수량(주)
    orgn_fake_ntby_qty: int  # 기관 가집계 순매수 수량(주)
    sum_fake_ntby_qty: int  # 외국인·기관 합산 가집계 순매수 수량(주)


class StockIntradayFlowDetails(BaseModel):
    """종목별 장중 수급 저장 상세."""

    sum_fake_ntby_qty: int


class StockIntradayFlowBody(InvestorFlowEnvelope):
    """TR HHPTJ04160200 응답 본문."""

    output2: list[StockIntradayFlowRow]


class MarketInvestorFlowDetails(BaseModel):
    """시장 수급의 매도·매수 원본 값."""

    seln_vol: int
    shnu_vol: int
    seln_tr_pbmn: int
    shnu_tr_pbmn: int


class MarketInvestorFlowValues(BaseModel):
    """투자자 유형 하나의 정규화된 시장 수급 값."""

    net_buy_volume: int
    net_buy_value: int
    details: MarketInvestorFlowDetails

    @property
    def reports_investor(self) -> bool:
        """시장 TR이 해당 투자자 유형을 실제로 집계했는지 반환한다."""

        return any(
            (
                self.net_buy_volume,
                self.net_buy_value,
                self.details.seln_vol,
                self.details.shnu_vol,
                self.details.seln_tr_pbmn,
                self.details.shnu_tr_pbmn,
            )
        )


class MarketIntradayFlowRow(BaseModel):
    """시장별 장중 투자자매매동향 행 (TR FHPTJ04030000, output 원소)."""

    frgn_seln_vol: int  # 외국인 매도 거래량(주)
    frgn_shnu_vol: int  # 외국인 매수 거래량(주)
    frgn_ntby_qty: int  # 외국인 순매수 수량(주)
    frgn_seln_tr_pbmn: int  # 외국인 매도 거래대금(백만원)
    frgn_shnu_tr_pbmn: int  # 외국인 매수 거래대금(백만원)
    frgn_ntby_tr_pbmn: int  # 외국인 순매수 거래대금(백만원)
    prsn_seln_vol: int  # 개인 매도 거래량(주)
    prsn_shnu_vol: int  # 개인 매수 거래량(주)
    prsn_ntby_qty: int  # 개인 순매수 수량(주)
    prsn_seln_tr_pbmn: int  # 개인 매도 거래대금(백만원)
    prsn_shnu_tr_pbmn: int  # 개인 매수 거래대금(백만원)
    prsn_ntby_tr_pbmn: int  # 개인 순매수 거래대금(백만원)
    orgn_seln_vol: int  # 기관계 매도 거래량(주)
    orgn_shnu_vol: int  # 기관계 매수 거래량(주)
    orgn_ntby_qty: int  # 기관계 순매수 수량(주)
    orgn_seln_tr_pbmn: int  # 기관계 매도 거래대금(백만원)
    orgn_shnu_tr_pbmn: int  # 기관계 매수 거래대금(백만원)
    orgn_ntby_tr_pbmn: int  # 기관계 순매수 거래대금(백만원)
    scrt_seln_vol: int  # 증권 매도 거래량(주)
    scrt_shnu_vol: int  # 증권 매수 거래량(주)
    scrt_ntby_qty: int  # 증권 순매수 수량(주)
    scrt_seln_tr_pbmn: int  # 증권 매도 거래대금(백만원)
    scrt_shnu_tr_pbmn: int  # 증권 매수 거래대금(백만원)
    scrt_ntby_tr_pbmn: int  # 증권 순매수 거래대금(백만원)
    ivtr_seln_vol: int  # 투자신탁 매도 거래량(주)
    ivtr_shnu_vol: int  # 투자신탁 매수 거래량(주)
    ivtr_ntby_qty: int  # 투자신탁 순매수 수량(주)
    ivtr_seln_tr_pbmn: int  # 투자신탁 매도 거래대금(백만원)
    ivtr_shnu_tr_pbmn: int  # 투자신탁 매수 거래대금(백만원)
    ivtr_ntby_tr_pbmn: int  # 투자신탁 순매수 거래대금(백만원)
    pe_fund_seln_tr_pbmn: int  # 사모펀드 매도 거래대금(백만원)
    pe_fund_seln_vol: int  # 사모펀드 매도 거래량(주)
    pe_fund_ntby_vol: int  # 사모펀드 순매수 거래량(주)
    pe_fund_shnu_tr_pbmn: int  # 사모펀드 매수 거래대금(백만원)
    pe_fund_shnu_vol: int  # 사모펀드 매수 거래량(주)
    pe_fund_ntby_tr_pbmn: int  # 사모펀드 순매수 거래대금(백만원)
    bank_seln_vol: int  # 은행 매도 거래량(주)
    bank_shnu_vol: int  # 은행 매수 거래량(주)
    bank_ntby_qty: int  # 은행 순매수 수량(주)
    bank_seln_tr_pbmn: int  # 은행 매도 거래대금(백만원)
    bank_shnu_tr_pbmn: int  # 은행 매수 거래대금(백만원)
    bank_ntby_tr_pbmn: int  # 은행 순매수 거래대금(백만원)
    insu_seln_vol: int  # 보험 매도 거래량(주)
    insu_shnu_vol: int  # 보험 매수 거래량(주)
    insu_ntby_qty: int  # 보험 순매수 수량(주)
    insu_seln_tr_pbmn: int  # 보험 매도 거래대금(백만원)
    insu_shnu_tr_pbmn: int  # 보험 매수 거래대금(백만원)
    insu_ntby_tr_pbmn: int  # 보험 순매수 거래대금(백만원)
    mrbn_seln_vol: int  # 종금 매도 거래량(주)
    mrbn_shnu_vol: int  # 종금 매수 거래량(주)
    mrbn_ntby_qty: int  # 종금 순매수 수량(주)
    mrbn_seln_tr_pbmn: int  # 종금 매도 거래대금(백만원)
    mrbn_shnu_tr_pbmn: int  # 종금 매수 거래대금(백만원)
    mrbn_ntby_tr_pbmn: int  # 종금 순매수 거래대금(백만원)
    fund_seln_vol: int  # 기금 매도 거래량(주)
    fund_shnu_vol: int  # 기금 매수 거래량(주)
    fund_ntby_qty: int  # 기금 순매수 수량(주)
    fund_seln_tr_pbmn: int  # 기금 매도 거래대금(백만원)
    fund_shnu_tr_pbmn: int  # 기금 매수 거래대금(백만원)
    fund_ntby_tr_pbmn: int  # 기금 순매수 거래대금(백만원)
    etc_orgt_seln_vol: int  # 기타 단체 매도 거래량(주)
    etc_orgt_shnu_vol: int  # 기타 단체 매수 거래량(주)
    etc_orgt_ntby_vol: int  # 기타 단체 순매수 거래량(주)
    etc_orgt_seln_tr_pbmn: int  # 기타 단체 매도 거래대금(백만원)
    etc_orgt_shnu_tr_pbmn: int  # 기타 단체 매수 거래대금(백만원)
    etc_orgt_ntby_tr_pbmn: int  # 기타 단체 순매수 거래대금(백만원)
    etc_corp_seln_vol: int  # 기타 법인 매도 거래량(주)
    etc_corp_shnu_vol: int  # 기타 법인 매수 거래량(주)
    etc_corp_ntby_vol: int  # 기타 법인 순매수 거래량(주)
    etc_corp_seln_tr_pbmn: int  # 기타 법인 매도 거래대금(백만원)
    etc_corp_shnu_tr_pbmn: int  # 기타 법인 매수 거래대금(백만원)
    etc_corp_ntby_tr_pbmn: int  # 기타 법인 순매수 거래대금(백만원)

    def values_for(self, investor_type: InvestorType) -> MarketInvestorFlowValues:
        """한 투자자 유형의 매도·매수·순매수 값을 정규화한다."""

        prefix, volume_suffix = INVESTOR_FLOW_FIELD_PARTS[investor_type]
        return MarketInvestorFlowValues(
            net_buy_volume=cast(int, getattr(self, f"{prefix}_ntby_{volume_suffix}")),
            net_buy_value=cast(int, getattr(self, f"{prefix}_ntby_tr_pbmn")),
            details=MarketInvestorFlowDetails(
                seln_vol=cast(int, getattr(self, f"{prefix}_seln_vol")),
                shnu_vol=cast(int, getattr(self, f"{prefix}_shnu_vol")),
                seln_tr_pbmn=cast(int, getattr(self, f"{prefix}_seln_tr_pbmn")),
                shnu_tr_pbmn=cast(int, getattr(self, f"{prefix}_shnu_tr_pbmn")),
            ),
        )


class MarketIntradayFlowBody(InvestorFlowEnvelope):
    """TR FHPTJ04030000 응답 본문."""

    output: list[MarketIntradayFlowRow]


class StockFinalFlowSummary(BaseModel):
    """종목별 일별 투자자매매동향 현재가 요약 (TR FHPTJ04160001, output1)."""

    stck_prpr: int
    prdy_vrss: int
    prdy_vrss_sign: str
    prdy_ctrt: Decimal
    acml_vol: int
    prdy_vol: int
    rprs_mrkt_kor_name: str


class StockFinalFlowRow(MarketIntradayFlowRow):
    """종목별 일별 투자자매매동향 행 (TR FHPTJ04160001, output2 원소)."""

    stck_bsop_date: str
    stck_clpr: int
    prdy_vrss: int
    prdy_vrss_sign: str
    prdy_ctrt: Decimal
    acml_vol: int
    acml_tr_pbmn: int
    stck_oprc: int
    stck_hgpr: int
    stck_lwpr: int
    frgn_reg_ntby_qty: int
    frgn_nreg_ntby_qty: int
    etc_ntby_qty: int
    frgn_reg_ntby_pbmn: int
    frgn_nreg_ntby_pbmn: int
    etc_ntby_tr_pbmn: int
    frgn_reg_askp_qty: int
    frgn_reg_bidp_qty: int
    frgn_reg_askp_pbmn: int
    frgn_reg_bidp_pbmn: int
    frgn_nreg_askp_qty: int
    frgn_nreg_bidp_qty: int
    frgn_nreg_askp_pbmn: int
    frgn_nreg_bidp_pbmn: int
    etc_seln_vol: int
    etc_shnu_vol: int
    etc_seln_tr_pbmn: int
    etc_shnu_tr_pbmn: int
    bold_yn: str


class StockFinalFlowBody(InvestorFlowEnvelope):
    """TR FHPTJ04160001 응답 본문."""

    output1: StockFinalFlowSummary
    output2: list[StockFinalFlowRow]

    @field_validator("output2", mode="before")
    @classmethod
    def drop_blank_rows(cls, value: object) -> object:
        """값이 비어 있는 자리 채움 행을 파싱 전에 걸러낸다.

        KIS는 데이터가 없는 구간에도 30행을 채워 보내는데, 그 행들은 **영업일자만 있고
        나머지가 전부 빈 문자열**이다. NXT(넥스트레이드) 거래소가 생기기 전 날짜를
        조회하면 전 구간이 이 모양으로 온다. 두면 숫자 필드 파싱이 통째로 깨져 그 날짜
        수집이 죽으므로, 종가가 비어 있는 행을 값 없는 행으로 보고 버린다.

        버린 건수는 로그로 남긴다 — 응답 형식이 바뀌어 멀쩡한 행을 버리기 시작해도
        건수만 보면 드러나야 한다.

        Args:
            value: 검증 전 output2 값.

        Returns:
            종가가 채워진 행만 남긴 목록. 목록이 아니면 원본 그대로 돌려준다.
        """

        if not isinstance(value, list):
            return value

        rows = [row for row in value if not isinstance(row, dict) or row.get("stck_clpr")]
        if len(rows) != len(value):
            logger.warning(
                "investor_flow_blank_rows_dropped",
                tr_id=InvestorFlowTrId.STOCK_FINAL.value,
                received=len(value),
                dropped=len(value) - len(rows),
            )
        return rows


class MarketFinalFlowRow(BaseModel):
    """시장별 일별 투자자매매동향 행 (TR FHPTJ04040000, output 원소)."""

    stck_bsop_date: str  # 영업일자(YYYYMMDD)
    bstp_nmix_prpr: Decimal  # 업종 지수 현재가
    bstp_nmix_prdy_vrss: Decimal  # 업종 지수 전일 대비
    prdy_vrss_sign: str  # 전일 대비 부호 코드
    bstp_nmix_prdy_ctrt: Decimal  # 업종 지수 전일 대비율(%)
    bstp_nmix_oprc: Decimal  # 업종 지수 시가
    bstp_nmix_hgpr: Decimal  # 업종 지수 고가
    bstp_nmix_lwpr: Decimal  # 업종 지수 저가
    stck_prdy_clpr: Decimal  # 전일 종가
    frgn_ntby_qty: int  # 외국인 순매수 수량
    frgn_reg_ntby_qty: int  # 등록 외국인 순매수 수량
    frgn_nreg_ntby_qty: int  # 비등록 외국인 순매수 수량
    prsn_ntby_qty: int  # 개인 순매수 수량
    orgn_ntby_qty: int  # 기관계 순매수 수량
    scrt_ntby_qty: int  # 증권 순매수 수량
    ivtr_ntby_qty: int  # 투자신탁 순매수 수량
    pe_fund_ntby_vol: int  # 사모펀드 순매수 수량
    bank_ntby_qty: int  # 은행 순매수 수량
    insu_ntby_qty: int  # 보험 순매수 수량
    mrbn_ntby_qty: int  # 종금 순매수 수량
    fund_ntby_qty: int  # 기금 순매수 수량
    etc_ntby_qty: int  # 기타 순매수 수량
    etc_orgt_ntby_vol: int  # 기타 단체 순매수 수량
    etc_corp_ntby_vol: int  # 기타 법인 순매수 수량
    frgn_ntby_tr_pbmn: int  # 외국인 순매수 거래대금
    frgn_reg_ntby_pbmn: int  # 등록 외국인 순매수 거래대금
    frgn_nreg_ntby_pbmn: int  # 비등록 외국인 순매수 거래대금
    prsn_ntby_tr_pbmn: int  # 개인 순매수 거래대금
    orgn_ntby_tr_pbmn: int  # 기관계 순매수 거래대금
    scrt_ntby_tr_pbmn: int  # 증권 순매수 거래대금
    ivtr_ntby_tr_pbmn: int  # 투자신탁 순매수 거래대금
    pe_fund_ntby_tr_pbmn: int  # 사모펀드 순매수 거래대금
    bank_ntby_tr_pbmn: int  # 은행 순매수 거래대금
    insu_ntby_tr_pbmn: int  # 보험 순매수 거래대금
    mrbn_ntby_tr_pbmn: int  # 종금 순매수 거래대금
    fund_ntby_tr_pbmn: int  # 기금 순매수 거래대금
    etc_ntby_tr_pbmn: int  # 기타 순매수 거래대금
    etc_orgt_ntby_tr_pbmn: int  # 기타 단체 순매수 거래대금
    etc_corp_ntby_tr_pbmn: int  # 기타 법인 순매수 거래대금


class MarketFinalFlowBody(InvestorFlowEnvelope):
    """TR FHPTJ04040000 응답 본문."""

    output: list[MarketFinalFlowRow]


class InvestorFlowTextBody(RootModel[str]):
    """JSON이 아닌 HTTP 200 응답 원문."""


type InvestorFlowBody = (
    StockIntradayFlowBody
    | MarketIntradayFlowBody
    | StockFinalFlowBody
    | MarketFinalFlowBody
    | InvestorFlowEnvelope
    | InvestorFlowTextBody
)


def parse_investor_flow_body(
    tr_id: InvestorFlowTrId,
    body: JsonValue,
) -> InvestorFlowBody:
    """TR ID와 결과 코드에 맞는 투자자 수급 응답 DTO를 반환한다."""

    if isinstance(body, str):
        return InvestorFlowTextBody(root=body)

    envelope = InvestorFlowEnvelope.model_validate(body)
    if envelope.rt_cd != "0":
        return envelope
    if tr_id is InvestorFlowTrId.STOCK_INTRADAY:
        return StockIntradayFlowBody.model_validate(body)
    if tr_id is InvestorFlowTrId.KOSPI_INTRADAY:
        return MarketIntradayFlowBody.model_validate(body)
    if tr_id is InvestorFlowTrId.STOCK_FINAL:
        return StockFinalFlowBody.model_validate(body)
    return MarketFinalFlowBody.model_validate(body)


class InvestorFlowResult(BaseModel):
    """민감한 요청 헤더를 제외한 단일 KIS 응답 결과."""

    target: str  # 조회 대상 종목코드 또는 시장 식별자
    target_name: str  # 조회 대상 표시명
    venue: InvestorFlowVenue  # 응답의 거래 시장 범위
    tr_id: InvestorFlowTrId  # 호출한 KIS 거래 ID
    http_status: int  # HTTP 응답 상태 코드
    tr_cont: str  # 연속 조회 여부
    body: InvestorFlowBody  # TR ID와 결과에 맞게 파싱된 응답 본문
