from datetime import date, time
from decimal import Decimal
from enum import StrEnum

from pydantic import ConfigDict

from app.kis.schemas.common import KISBaseModel
from app.kis.schemas.parsing import none_if_empty, parse_kis_date, parse_kis_time
from app.kis.schemas.websocket import KISWebSocketSubscription


class KISKoreaStockCode(StrEnum):
    SAMSUNG_ELECTRONICS = "005930"
    SK_HYNIX = "000660"


class KISKoreaTrId(StrEnum):
    STOCK_TRADE_KRX = "H0STCNT0"  # KRX(한국거래소) 실시간 체결가
    STOCK_TRADE_NXT = "H0NXCNT0"  # NXT(넥스트레이드) 실시간 체결가
    STOCK_TRADE_UNIFIED = "H0UNCNT0"  # KRX와 NXT 통합 실시간 체결가

    STOCK_ORDERBOOK_KRX = "H0STASP0"  # KRX 실시간 매수·매도 호가
    STOCK_ORDERBOOK_NXT = "H0NXASP0"  # NXT 실시간 매수·매도 호가
    STOCK_ORDERBOOK_UNIFIED = "H0UNASP0"  # KRX와 NXT 통합 실시간 호가


class KISKoreaSubscription(KISBaseModel):
    model_config = ConfigDict(frozen=True, serialize_by_alias=True)

    code: KISKoreaStockCode
    tr_id: KISKoreaTrId

    def to_websocket_subscription(self) -> KISWebSocketSubscription:
        """한국주식 구독을 공용 웹소켓 구독으로 변환한다."""

        return KISWebSocketSubscription(tr_id=self.tr_id, tr_key=self.code)


class KISKoreaTrade(KISBaseModel):
    """국내주식 KRX 실시간 체결 한 건을 표현한다."""

    stock_code: str  # MKSC_SHRN_ISCD: 유가증권 단축 종목코드
    trade_time: time  # STCK_CNTG_HOUR: 주식 체결 시각
    current_price: Decimal  # STCK_PRPR: 주식 현재가(체결가)
    previous_day_sign: str  # PRDY_VRSS_SIGN: 전일 대비 부호
    previous_day_difference: Decimal  # PRDY_VRSS: 전일 대비 가격
    previous_day_rate: Decimal  # PRDY_CTRT: 전일 대비율
    weighted_average_price: Decimal  # WGHN_AVRG_STCK_PRC: 가중 평균 주식 가격
    open_price: Decimal  # STCK_OPRC: 당일 시가
    high_price: Decimal  # STCK_HGPR: 당일 최고가
    low_price: Decimal  # STCK_LWPR: 당일 최저가
    best_ask_price: Decimal  # ASKP1: 최우선 매도호가
    best_bid_price: Decimal  # BIDP1: 최우선 매수호가
    trade_volume: int  # CNTG_VOL: 직전 체결 수량
    cumulative_volume: int  # ACML_VOL: 당일 누적 거래량
    cumulative_trade_amount: Decimal  # ACML_TR_PBMN: 당일 누적 거래대금
    sell_trade_count: int  # SELN_CNTG_CSNU: 누적 매도 체결 건수
    buy_trade_count: int  # SHNU_CNTG_CSNU: 누적 매수 체결 건수
    net_buy_trade_count: int  # NTBY_CNTG_CSNU: 순매수 체결 건수
    trade_strength: Decimal  # CTTR: 체결강도
    cumulative_sell_quantity: int  # SELN_CNTG_SMTN: 누적 매도 체결 수량
    cumulative_buy_quantity: int  # SHNU_CNTG_SMTN: 누적 매수 체결 수량
    trade_classification_code: str  # CCLD_DVSN: 체결 구분 코드
    buy_rate: Decimal  # SHNU_RATE: 매수 비율
    previous_volume_cumulative_rate: Decimal  # PRDY_VOL_VRSS_ACML_VOL_RATE: 전일 거래량 대비 누적 거래량 비율
    open_time: time  # OPRC_HOUR: 시가 형성 시각
    open_price_sign: str  # OPRC_VRSS_PRPR_SIGN: 시가 대비 현재가 부호
    open_price_difference: Decimal  # OPRC_VRSS_PRPR: 시가 대비 현재가 차이
    high_time: time  # HGPR_HOUR: 최고가 형성 시각
    high_price_sign: str  # HGPR_VRSS_PRPR_SIGN: 최고가 대비 현재가 부호
    high_price_difference: Decimal  # HGPR_VRSS_PRPR: 최고가 대비 현재가 차이
    low_time: time  # LWPR_HOUR: 최저가 형성 시각
    low_price_sign: str  # LWPR_VRSS_PRPR_SIGN: 최저가 대비 현재가 부호
    low_price_difference: Decimal  # LWPR_VRSS_PRPR: 최저가 대비 현재가 차이
    business_date: date  # BSOP_DATE: 영업일자
    new_market_operation_code: str  # NEW_MKOP_CLS_CODE: 신시장 운영 구분 코드
    trading_halt_yn: str  # TRHT_YN: 거래정지 여부
    best_ask_quantity: int  # ASKP_RSQN1: 최우선 매도호가 잔량
    best_bid_quantity: int  # BIDP_RSQN1: 최우선 매수호가 잔량
    total_ask_quantity: int  # TOTAL_ASKP_RSQN: 총 매도호가 잔량
    total_bid_quantity: int  # TOTAL_BIDP_RSQN: 총 매수호가 잔량
    volume_turnover_rate: Decimal  # VOL_TNRT: 거래량 회전율
    previous_same_time_cumulative_volume: int  # PRDY_SMNS_HOUR_ACML_VOL: 전일 동시간 누적 거래량
    previous_same_time_cumulative_volume_rate: Decimal  # PRDY_SMNS_HOUR_ACML_VOL_RATE: 전일 동시간 누적 거래량 비율
    hour_classification_code: str  # HOUR_CLS_CODE: 시간 구분 코드
    market_operation_code: str | None  # MRKT_TRTM_CLS_CODE: 시장 운영 구분 코드
    vi_standard_price: Decimal  # VI_STND_PRC: 변동성 완화장치(VI) 발동 기준 가격

    @classmethod
    def from_body(cls, fields: list[str]) -> "KISKoreaTrade":
        """46개 체결 본문 필드를 타입이 지정된 DTO로 변환한다.

        Args:
            fields: 캐럿 구분자로 분리된 체결 본문 필드.

        Returns:
            변환된 국내주식 체결 DTO.

        Raises:
            ValueError: 필드 수가 46개가 아닌 경우.
        """

        if len(fields) != 46:
            raise ValueError(f"Korea trade body must contain 46 fields: {len(fields)}")

        return cls(
            stock_code=fields[0],
            trade_time=parse_kis_time(fields[1]),
            current_price=Decimal(fields[2]),
            previous_day_sign=fields[3],
            previous_day_difference=Decimal(fields[4]),
            previous_day_rate=Decimal(fields[5]),
            weighted_average_price=Decimal(fields[6]),
            open_price=Decimal(fields[7]),
            high_price=Decimal(fields[8]),
            low_price=Decimal(fields[9]),
            best_ask_price=Decimal(fields[10]),
            best_bid_price=Decimal(fields[11]),
            trade_volume=int(fields[12]),
            cumulative_volume=int(fields[13]),
            cumulative_trade_amount=Decimal(fields[14]),
            sell_trade_count=int(fields[15]),
            buy_trade_count=int(fields[16]),
            net_buy_trade_count=int(fields[17]),
            trade_strength=Decimal(fields[18]),
            cumulative_sell_quantity=int(fields[19]),
            cumulative_buy_quantity=int(fields[20]),
            trade_classification_code=fields[21],
            buy_rate=Decimal(fields[22]),
            previous_volume_cumulative_rate=Decimal(fields[23]),
            open_time=parse_kis_time(fields[24]),
            open_price_sign=fields[25],
            open_price_difference=Decimal(fields[26]),
            high_time=parse_kis_time(fields[27]),
            high_price_sign=fields[28],
            high_price_difference=Decimal(fields[29]),
            low_time=parse_kis_time(fields[30]),
            low_price_sign=fields[31],
            low_price_difference=Decimal(fields[32]),
            business_date=parse_kis_date(fields[33]),
            new_market_operation_code=fields[34],
            trading_halt_yn=fields[35],
            best_ask_quantity=int(fields[36]),
            best_bid_quantity=int(fields[37]),
            total_ask_quantity=int(fields[38]),
            total_bid_quantity=int(fields[39]),
            volume_turnover_rate=Decimal(fields[40]),
            previous_same_time_cumulative_volume=int(fields[41]),
            previous_same_time_cumulative_volume_rate=Decimal(fields[42]),
            hour_classification_code=fields[43],
            market_operation_code=none_if_empty(fields[44]),
            vi_standard_price=Decimal(fields[45]),
        )


class KISKoreaOrderbookLevel(KISBaseModel):
    """국내주식 호가 한 단계를 표현한다."""

    ask_price: Decimal  # ASKP1~10: 단계별 매도호가
    bid_price: Decimal  # BIDP1~10: 단계별 매수호가
    ask_quantity: int  # ASKP_RSQN1~10: 단계별 매도호가 잔량
    bid_quantity: int  # BIDP_RSQN1~10: 단계별 매수호가 잔량


class KISKoreaOrderbook(KISBaseModel):
    """국내주식 KRX 실시간 10단계 호가를 표현한다."""

    stock_code: str  # MKSC_SHRN_ISCD: 유가증권 단축 종목코드
    business_time: time  # BSOP_HOUR: 호가가 생성된 영업 시각
    hour_classification_code: str  # HOUR_CLS_CODE: 시간 구분 코드
    levels: list[KISKoreaOrderbookLevel]  # 1~10단계 매도·매수 호가와 잔량
    total_ask_quantity: int  # TOTAL_ASKP_RSQN: 총 매도호가 잔량
    total_bid_quantity: int  # TOTAL_BIDP_RSQN: 총 매수호가 잔량
    overtime_total_ask_quantity: int  # OVTM_TOTAL_ASKP_RSQN: 시간외 총 매도호가 잔량
    overtime_total_bid_quantity: int  # OVTM_TOTAL_BIDP_RSQN: 시간외 총 매수호가 잔량
    anticipated_trade_price: Decimal  # ANTC_CNPR: 예상 체결가
    anticipated_trade_quantity: int  # ANTC_CNQN: 예상 체결 수량
    anticipated_volume: int  # ANTC_VOL: 예상 거래량
    anticipated_price_difference: Decimal  # ANTC_CNTG_VRSS: 예상 체결 대비 가격 차이
    anticipated_price_sign: str  # ANTC_CNTG_VRSS_SIGN: 예상 체결 대비 부호
    anticipated_price_rate: Decimal  # ANTC_CNTG_PRDY_CTRT: 예상 체결 전일 대비율
    cumulative_volume: int  # ACML_VOL: 당일 누적 거래량
    total_ask_quantity_change: int  # TOTAL_ASKP_RSQN_ICDC: 총 매도호가 잔량 증감
    total_bid_quantity_change: int  # TOTAL_BIDP_RSQN_ICDC: 총 매수호가 잔량 증감
    overtime_total_ask_quantity_change: int  # OVTM_TOTAL_ASKP_ICDC: 시간외 총 매도호가 잔량 증감
    overtime_total_bid_quantity_change: int  # OVTM_TOTAL_BIDP_ICDC: 시간외 총 매수호가 잔량 증감
    stock_deal_classification_code: str  # STCK_DEAL_CLS_CODE: 주식 거래 구분 코드
    krx_mid_price: Decimal  # KMID_PRC: KRX 중간가
    krx_mid_total_quantity: int  # KMID_TOTAL_RSQN: KRX 중간가 총 잔량
    krx_mid_classification_code: str  # KMID_CLS_CODE: KRX 중간가 구분 코드

    @classmethod
    def from_body(cls, fields: list[str]) -> "KISKoreaOrderbook":
        """62개 호가 본문 필드를 타입이 지정된 DTO로 변환한다.

        Args:
            fields: 캐럿 구분자로 분리된 호가 본문 필드.

        Returns:
            10단계 가격과 잔량을 포함한 국내주식 호가 DTO.

        Raises:
            ValueError: 필드 수가 62개가 아닌 경우.
        """

        if len(fields) != 62:
            raise ValueError(f"Korea orderbook body must contain 62 fields: {len(fields)}")

        levels = [
            KISKoreaOrderbookLevel(
                ask_price=Decimal(fields[3 + index]),
                bid_price=Decimal(fields[13 + index]),
                ask_quantity=int(fields[23 + index]),
                bid_quantity=int(fields[33 + index]),
            )
            for index in range(10)
        ]

        return cls(
            stock_code=fields[0],
            business_time=parse_kis_time(fields[1]),
            hour_classification_code=fields[2],
            levels=levels,
            total_ask_quantity=int(fields[43]),
            total_bid_quantity=int(fields[44]),
            overtime_total_ask_quantity=int(fields[45]),
            overtime_total_bid_quantity=int(fields[46]),
            anticipated_trade_price=Decimal(fields[47]),
            anticipated_trade_quantity=int(fields[48]),
            anticipated_volume=int(fields[49]),
            anticipated_price_difference=Decimal(fields[50]),
            anticipated_price_sign=fields[51],
            anticipated_price_rate=Decimal(fields[52]),
            cumulative_volume=int(fields[53]),
            total_ask_quantity_change=int(fields[54]),
            total_bid_quantity_change=int(fields[55]),
            overtime_total_ask_quantity_change=int(fields[56]),
            overtime_total_bid_quantity_change=int(fields[57]),
            stock_deal_classification_code=fields[58],
            krx_mid_price=Decimal(fields[59]),
            krx_mid_total_quantity=int(fields[60]),
            krx_mid_classification_code=fields[61],
        )


def parse_frame(
    raw: str,
) -> list[KISKoreaTrade | KISKoreaOrderbook] | None:
    """KIS 국내주식 웹소켓 프레임을 체결 또는 호가 DTO로 변환한다.

    Args:
        raw: 웹소켓에서 수신한 원본 문자열.

    Returns:
        프레임에 포함된 체결 또는 호가 DTO 목록. JSON 제어 메시지는 None.

    Raises:
        ValueError: 프레임 헤더, TR ID, 레코드 수 또는 본문이 잘못된 경우.
    """

    if raw.lstrip().startswith("{"):
        return None

    parts = raw.split("|", 3)
    if len(parts) != 4:
        raise ValueError("KIS data frame must contain four pipe-delimited parts")

    data_type, tr_id, record_count_value, body = parts
    if data_type != "0":
        raise ValueError(f"Unsupported KIS data type: {data_type!r}")

    try:
        record_count = int(record_count_value)
    except ValueError as error:
        raise ValueError(f"KIS record count must be an integer: {record_count_value!r}") from error

    if record_count <= 0:
        raise ValueError("KIS record count must be positive")

    fields = body.split("^")
    if tr_id == KISKoreaTrId.STOCK_TRADE_KRX:
        field_count = 46
        if len(fields) != record_count * field_count:
            raise ValueError(f"Korea trade frame must contain {record_count * field_count} body fields: {len(fields)}")
        return [
            KISKoreaTrade.from_body(fields[offset : offset + field_count])
            for offset in range(0, len(fields), field_count)
        ]

    if tr_id == KISKoreaTrId.STOCK_ORDERBOOK_KRX:
        field_count = 62
        if len(fields) != record_count * field_count:
            raise ValueError(
                f"Korea orderbook frame must contain {record_count * field_count} body fields: {len(fields)}"
            )
        return [
            KISKoreaOrderbook.from_body(fields[offset : offset + field_count])
            for offset in range(0, len(fields), field_count)
        ]

    raise ValueError(f"Unsupported KIS Korea TR ID: {tr_id!r}")
