"""KIS 국내 투자자 수급 수집 스키마."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, JsonValue, RootModel, model_validator


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


class InvestorFlowProbeOptions(BaseModel):
    """투자자 수급 수집 실행 옵션."""

    phase: InvestorFlowPhase
    scope: InvestorFlowScope = InvestorFlowScope.ALL
    trade_date: date | None = None

    @model_validator(mode="after")
    def validate_trade_date(self) -> Self:
        """마감 조회일의 존재 여부를 검증한다."""

        if self.phase is InvestorFlowPhase.FINAL and self.trade_date is None:
            raise ValueError("final phase requires trade_date")
        return self


class InvestorFlowRequest(BaseModel):
    """단일 KIS 투자자 수급 REST 요청 명세."""

    target: str
    target_name: str
    venue: InvestorFlowVenue
    tr_id: InvestorFlowTrId
    params: dict[str, str]


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


class StockIntradayFlowBody(InvestorFlowEnvelope):
    """TR HHPTJ04160200 응답 본문."""

    output2: list[StockIntradayFlowRow]


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


class InvestorFlowRawBody(RootModel[JsonValue]):
    """전용 DTO가 없거나 JSON이 아닌 KIS 응답 본문."""


type InvestorFlowBody = (
    StockIntradayFlowBody
    | MarketIntradayFlowBody
    | StockFinalFlowBody
    | MarketFinalFlowBody
    | InvestorFlowEnvelope
    | InvestorFlowRawBody
)


def parse_investor_flow_body(
    tr_id: InvestorFlowTrId,
    body: JsonValue,
) -> InvestorFlowBody:
    """TR ID와 결과 코드에 맞는 투자자 수급 응답 DTO를 반환한다."""

    if isinstance(body, dict):
        if body.get("rt_cd") == "0":
            if tr_id is InvestorFlowTrId.STOCK_INTRADAY:
                return StockIntradayFlowBody.model_validate(body)
            if tr_id is InvestorFlowTrId.KOSPI_INTRADAY:
                return MarketIntradayFlowBody.model_validate(body)
            if tr_id is InvestorFlowTrId.STOCK_FINAL:
                return StockFinalFlowBody.model_validate(body)
            if tr_id is InvestorFlowTrId.KOSPI_FINAL:
                return MarketFinalFlowBody.model_validate(body)
        elif {"rt_cd", "msg_cd", "msg1"} <= body.keys():
            return InvestorFlowEnvelope.model_validate(body)
    return InvestorFlowRawBody(root=body)


class InvestorFlowResult(BaseModel):
    """민감한 요청 헤더를 제외한 단일 KIS 응답 결과."""

    target: str  # 조회 대상 종목코드 또는 시장 식별자
    target_name: str  # 조회 대상 표시명
    venue: InvestorFlowVenue  # 응답의 거래 시장 범위
    tr_id: InvestorFlowTrId  # 호출한 KIS 거래 ID
    http_status: int  # HTTP 응답 상태 코드
    tr_cont: str  # 연속 조회 여부
    body: InvestorFlowBody  # TR ID와 결과에 맞게 파싱된 응답 본문
