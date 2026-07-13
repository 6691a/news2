from enum import StrEnum

from pydantic import ConfigDict

from app.kis.schemas.common import KISBaseModel
from app.kis.schemas.websocket import KISWebSocketSubscription


class KISOverseasStockCode(StrEnum):
    APPLE = "AAPL"
    ALPHABET = "GOOGL"
    MICROSOFT = "MSFT"
    META = "META"
    NVIDIA = "NVDA"
    QQQ = "QQQ"
    SP500 = "SPY"


class KISOverseasMarket(StrEnum):
    NASDAQ = "NAS"
    NYSE = "NYS"
    AMEX = "AMS"


class KISOverseasTrId(StrEnum):
    TRADE = "HDFSCNT0"  # 해외 실시간지연체결가
    ORDERBOOK = "HDFSASP0"  # 해외 실시간호가


class KISOverseasSubscription(KISBaseModel):
    model_config = ConfigDict(frozen=True, serialize_by_alias=True)

    code: KISOverseasStockCode
    market: KISOverseasMarket
    tr_id: KISOverseasTrId

    def to_websocket_subscription(self) -> KISWebSocketSubscription:
        """미국주식 구독을 공용 웹소켓 구독으로 변환한다.
        tr_key 규칙: <티어><거래소코드><종목코드>  예) D + NAS + GOOGL = DNASGOOGL
        - 티어 "D": 무료 지연시세 (그래서 HDFSCNT0 = 실시간'지연'체결가).
        유료 실시간은 "R" 을 쓴다.
        - 거래소코드: NAS(나스닥)/NYS(뉴욕)/AMS(아멕스) 등 3자리.
        - 종목코드: AAPL, GOOGL 처럼 미국 티커.
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

    # TODO: 위 스펙대로 필드 선언 (예: last: Decimal, evol: int, ...)

    @classmethod
    def from_body(cls, fields: list[str]) -> "KISOverseasTrade":
        """^로 분리된 체결 body 필드 리스트(26개)를 모델로 변환한다.

        Args:
            fields: "^" 로 split 한 body 필드 리스트.

        Returns:
            파싱된 체결 모델.
        """

        # TODO: fields 인덱스를 위 스펙에 맞춰 매핑
        raise NotImplementedError


class KISOverseasOrderbookLevel(KISBaseModel):
    """해외주식 호가 한 단계.

    6필드 묶음: 매수호가 / 매도호가 / 매수잔량 / 매도잔량 /
              매수잔량대비 / 매도잔량대비.
    """

    # TODO: 6개 필드 선언


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

    # TODO: 헤더/총잔량 필드 + levels: list[KISOverseasOrderbookLevel]

    @classmethod
    def from_body(cls, fields: list[str]) -> "KISOverseasOrderbook":
        """^로 분리된 호가 body 필드 리스트(71개)를 모델로 변환한다.

        Args:
            fields: "^" 로 split 한 body 필드 리스트.

        Returns:
            10단계 호가를 담은 호가 스냅샷 모델.
        """

        # TODO: 헤더 11필드 파싱 후, 11번 인덱스부터 6개씩 잘라 levels 구성
        raise NotImplementedError


def parse_frame(raw: str) -> KISOverseasTrade | KISOverseasOrderbook | None:
    """수신 프레임 문자열을 tr_id에 따라 알맞은 모델로 파싱한다.

    Args:
        raw: 웹소켓에서 받은 원본 프레임 문자열.

    Returns:
        체결/호가 모델. 구독 성공 JSON 등 데이터 프레임이 아니면 None.
    """

    # TODO: "|" 로 헤더 분리 → tr_id 로 분기 → body 를 "^" 로 split →
    #       KISOverseasTrade / KISOverseasOrderbook 의 from_body 호출.
    #       데이터 프레임이 아니면(JSON 등) None 반환.
    raise NotImplementedError
