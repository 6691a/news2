"""KIS 국내 투자자 수급 진단 스키마."""

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, JsonValue, RootModel, model_validator


class InvestorFlowPhase(StrEnum):
    """투자자 수급 진단 시점."""

    INTRADAY = "intraday"
    FINAL = "final"


class InvestorFlowVenue(StrEnum):
    """응답에 부여할 거래 시장 범위."""

    KRX = "KRX"
    NXT = "NXT"
    UNSPECIFIED = "UNSPECIFIED"


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
    """투자자 수급 진단 실행 옵션."""

    phase: InvestorFlowPhase
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


# --- 응답 본문 DTO (장중 2종만; 마감 TR은 샘플 확보 후 추가) -----------------


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


class InvestorFlowRawBody(RootModel[JsonValue]):
    """전용 DTO가 없거나 JSON이 아닌 KIS 응답 본문."""


type InvestorFlowBody = StockIntradayFlowBody | MarketIntradayFlowBody | InvestorFlowEnvelope | InvestorFlowRawBody


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
