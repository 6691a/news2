from datetime import date, time
from decimal import Decimal
from enum import StrEnum

from pydantic import ConfigDict

from app.kis.schemas.common import KISBaseModel
from app.kis.schemas.parsing import parse_kis_date, parse_kis_time
from app.kis.schemas.websocket import KISWebSocketSubscription


class KISOverseasMarket(StrEnum):
    NASDAQ = "NAS"
    NYSE = "NYS"
    AMEX = "AMS"


class KISOverseasTrId(StrEnum):
    TRADE = "HDFSCNT0"  # 해외 실시간지연체결가
    ORDERBOOK = "HDFSASP0"  # 해외 실시간호가


class KISOverseasSubscription(KISBaseModel):
    model_config = ConfigDict(frozen=True, serialize_by_alias=True)

    code: str
    market: KISOverseasMarket
    tr_id: KISOverseasTrId

    def to_websocket_subscription(self) -> KISWebSocketSubscription:
        """미국주식 구독을 공용 웹소켓 구독으로 변환한다.

        tr_key 규칙: <티어><거래소코드><종목코드>  예) D + NAS + GOOGL = DNASGOOGL

        - 티어 "D": 무료 지연시세 (그래서 HDFSCNT0 = 실시간'지연'체결가).
          유료 실시간은 "R" 을 쓴다.
        - 거래소코드: NAS(나스닥)/NYS(뉴욕)/AMS(아멕스) 등 3자리.
        - 종목코드: AAPL, GOOGL 처럼 미국 티커.

        Returns:
            tr_key가 채워진 공용 웹소켓 구독.
        """

        return KISWebSocketSubscription(
            tr_id=self.tr_id,
            tr_key=f"D{self.market}{self.code}",
        )


# ---------------------------------------------------------------------------
# 수신 프레임 파싱 모델 (본문·필드 선언은 직접 구현할 부분)
# ---------------------------------------------------------------------------
# 프레임 형식: "0|HDFSCNT0|001|<body>"
#   - "|" 로 나누면 [암호화여부, tr_id, 데이터건수, body]
#   - body 는 "^" 로 나눈다. (체결=26필드 / 호가=71필드)
# 값 타입 가이드: 가격은 float 대신 Decimal, 수량/거래량은 int,
#                날짜/시간은 date·time (필요 시 datetime, Decimal 등을 import).


class KISOverseasTrade(KISBaseModel):
    """해외주식 실시간 체결(HDFSCNT0) 한 건.

    body(^구분) 26필드를 순서대로 매핑한다. 아래 스펙대로 필드를 직접 선언하고,
    from_body 에서 fields 리스트를 파싱해 인스턴스를 만든다.

    필드 스펙 (index: 이름 - 뜻):
        0  rsym   실시간종목코드 (예: DNASGOOGL)
        1  symb   종목코드 (예: GOOGL)
        2  zdiv   소수점 자리수
        3  tymd   현지 영업일자
        4  xymd   현지 일자
        5  xhms   현지 시간
        6  kymd   한국 일자
        7  khms   한국 시간
        8  open   시가
        9  high   고가
        10 low    저가
        11 last   현재가(체결가)
        12 sign   대비구분
        13 diff   전일대비
        14 rate   등락율
        15 pbid   매수호가
        16 pask   매도호가
        17 vbid   매수잔량
        18 vask   매도잔량
        19 evol   체결량 (직전 프레임 이후 증가분)
        20 tvol   누적거래량
        21 tamt   누적거래대금
        22 bivl   매도체결량
        23 asvl   매수체결량
        24 strn   체결강도
        25 mtyp   시장구분
    """

    # 현재 공식 예제의 25필드 앞에 실제 캡처의 RSYM 필드를 포함한 26필드 구조다.
    realtime_symbol: str  # RSYM: 실시간 종목코드(시세 구분·거래소·티커 조합)
    symbol: str  # SYMB: 종목코드(미국 티커)
    decimal_places: int  # ZDIV: 가격 소수점 자리수
    local_business_date: date  # TYMD: 현지 영업일자
    local_date: date  # XYMD: 현지 일자
    local_time: time  # XHMS: 현지 시각
    korea_date: date  # KYMD: 한국 일자
    korea_time: time  # KHMS: 한국 시각
    open_price: Decimal  # OPEN: 당일 시가
    high_price: Decimal  # HIGH: 당일 최고가
    low_price: Decimal  # LOW: 당일 최저가
    last_price: Decimal  # LAST: 현재가(체결가)
    change_sign: str  # SIGN: 전일 대비 부호
    change_amount: Decimal  # DIFF: 전일 대비 가격
    change_rate: Decimal  # RATE: 전일 대비율
    bid_price: Decimal  # PBID: 최우선 매수호가
    ask_price: Decimal  # PASK: 최우선 매도호가
    bid_quantity: int  # VBID: 최우선 매수호가 잔량
    ask_quantity: int  # VASK: 최우선 매도호가 잔량
    trade_volume: int  # EVOL: 직전 체결 수량
    total_volume: int  # TVOL: 당일 누적 거래량
    total_amount: Decimal  # TAMT: 당일 누적 거래대금
    sell_trade_volume: int  # BIVL: 누적 매도 체결량
    buy_trade_volume: int  # ASVL: 누적 매수 체결량
    trade_strength: Decimal  # STRN: 체결강도
    market_type: str  # MTYP: 시장 구분 코드

    @classmethod
    def from_body(cls, fields: list[str]) -> "KISOverseasTrade":
        """^로 분리된 체결 body 필드 리스트(26개)를 모델로 변환한다.

        Args:
            fields: "^" 로 split 한 body 필드 리스트.

        Returns:
            파싱된 체결 모델.
        """

        if len(fields) != 26:
            raise ValueError(f"Overseas trade body must contain 26 fields: {len(fields)}")

        return cls(
            realtime_symbol=fields[0],
            symbol=fields[1],
            decimal_places=int(fields[2]),
            local_business_date=parse_kis_date(fields[3]),
            local_date=parse_kis_date(fields[4]),
            local_time=parse_kis_time(fields[5]),
            korea_date=parse_kis_date(fields[6]),
            korea_time=parse_kis_time(fields[7]),
            open_price=Decimal(fields[8]),
            high_price=Decimal(fields[9]),
            low_price=Decimal(fields[10]),
            last_price=Decimal(fields[11]),
            change_sign=fields[12],
            change_amount=Decimal(fields[13]),
            change_rate=Decimal(fields[14]),
            bid_price=Decimal(fields[15]),
            ask_price=Decimal(fields[16]),
            bid_quantity=int(fields[17]),
            ask_quantity=int(fields[18]),
            trade_volume=int(fields[19]),
            total_volume=int(fields[20]),
            total_amount=Decimal(fields[21]),
            sell_trade_volume=int(fields[22]),
            buy_trade_volume=int(fields[23]),
            trade_strength=Decimal(fields[24]),
            market_type=fields[25],
        )


class KISOverseasOrderbookLevel(KISBaseModel):
    """해외주식 호가 한 단계.

    6필드 묶음: 매수호가 / 매도호가 / 매수잔량 / 매도잔량 /
              매수잔량대비 / 매도잔량대비.
    """

    bid_price: Decimal  # PBID1~10: 단계별 매수호가
    ask_price: Decimal  # PASK1~10: 단계별 매도호가
    bid_quantity: int  # VBID1~10: 단계별 매수호가 잔량
    ask_quantity: int  # VASK1~10: 단계별 매도호가 잔량
    bid_quantity_change: int  # DBID1~10: 단계별 매수호가 잔량 증감
    ask_quantity_change: int  # DASK1~10: 단계별 매도호가 잔량 증감


class KISOverseasOrderbook(KISBaseModel):
    """해외주식 실시간 호가(HDFSASP0) 스냅샷.

    body(^구분) 71필드 = 헤더 7 + 총잔량 4 + (6필드 × 10단계).

    헤더/총잔량 스펙 (index: 이름 - 뜻):
        0 rsym   실시간종목코드
        1 symb   종목코드
        2 zdiv   소수점 자리수
        3 xymd   현지 일자
        4 xhms   현지 시간
        5 kymd   한국 일자
        6 khms   한국 시간
        7 bvol   매수 총잔량
        8 avol   매도 총잔량
        9 bdvl   매수 총잔량대비
        10 advl  매도 총잔량대비
    이후 index 11부터 6필드씩 10단계 → levels: list[KISOverseasOrderbookLevel]
    """

    # 현재 공식 미국 무료 예제의 1단계 호가를 실제 캡처 구조에 맞춰 10단계로 확장해 보존한다.
    realtime_symbol: str  # RSYM: 실시간 종목코드(시세 구분·거래소·티커 조합)
    symbol: str  # SYMB: 종목코드(미국 티커)
    decimal_places: int  # ZDIV: 가격 소수점 자리수
    local_date: date  # XYMD: 현지 일자
    local_time: time  # XHMS: 현지 시각
    korea_date: date  # KYMD: 한국 일자
    korea_time: time  # KHMS: 한국 시각
    total_bid_quantity: int  # BVOL: 총 매수호가 잔량
    total_ask_quantity: int  # AVOL: 총 매도호가 잔량
    total_bid_quantity_change: int  # BDVL: 총 매수호가 잔량 증감
    total_ask_quantity_change: int  # ADVL: 총 매도호가 잔량 증감
    levels: list[KISOverseasOrderbookLevel]  # 1~10단계 가격별 매수·매도 호가와 잔량

    @classmethod
    def from_body(cls, fields: list[str]) -> "KISOverseasOrderbook":
        """^로 분리된 호가 body 필드 리스트(71개)를 모델로 변환한다.

        Args:
            fields: "^" 로 split 한 body 필드 리스트.

        Returns:
            10단계 호가를 담은 호가 스냅샷 모델.
        """

        if len(fields) != 71:
            raise ValueError(f"Overseas orderbook body must contain 71 fields: {len(fields)}")

        levels = []
        for index in range(10):
            offset = 11 + index * 6
            levels.append(
                KISOverseasOrderbookLevel(
                    bid_price=Decimal(fields[offset]),
                    ask_price=Decimal(fields[offset + 1]),
                    bid_quantity=int(fields[offset + 2]),
                    ask_quantity=int(fields[offset + 3]),
                    bid_quantity_change=int(fields[offset + 4]),
                    ask_quantity_change=int(fields[offset + 5]),
                )
            )

        return cls(
            realtime_symbol=fields[0],
            symbol=fields[1],
            decimal_places=int(fields[2]),
            local_date=parse_kis_date(fields[3]),
            local_time=parse_kis_time(fields[4]),
            korea_date=parse_kis_date(fields[5]),
            korea_time=parse_kis_time(fields[6]),
            total_bid_quantity=int(fields[7]),
            total_ask_quantity=int(fields[8]),
            total_bid_quantity_change=int(fields[9]),
            total_ask_quantity_change=int(fields[10]),
            levels=levels,
        )


def parse_frame(raw: str) -> list[KISOverseasTrade | KISOverseasOrderbook] | None:
    """수신 프레임 문자열을 tr_id에 따라 알맞은 모델로 파싱한다.

    Args:
        raw: 웹소켓에서 받은 원본 프레임 문자열.

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
    if tr_id == KISOverseasTrId.TRADE:
        field_count = 26
        if len(fields) != record_count * field_count:
            raise ValueError(
                f"Overseas trade frame must contain {record_count * field_count} body fields: {len(fields)}"
            )
        return [
            KISOverseasTrade.from_body(fields[offset : offset + field_count])
            for offset in range(0, len(fields), field_count)
        ]

    if tr_id == KISOverseasTrId.ORDERBOOK:
        field_count = 71
        if len(fields) != record_count * field_count:
            raise ValueError(
                f"Overseas orderbook frame must contain {record_count * field_count} body fields: {len(fields)}"
            )
        return [
            KISOverseasOrderbook.from_body(fields[offset : offset + field_count])
            for offset in range(0, len(fields), field_count)
        ]

    raise ValueError(f"Unsupported KIS overseas TR ID: {tr_id!r}")
