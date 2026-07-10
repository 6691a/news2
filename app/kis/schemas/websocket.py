from enum import StrEnum

from pydantic import Field, ConfigDict

from app.kis.schemas.common import KISBaseModel
from app.kis.schemas.stock import StockCode


class KISTrType(StrEnum):
    SUBSCRIBE = "1"
    UNSUBSCRIBE = "2"


class KISWebSocketSubscriptionHeader(KISBaseModel):
    approval_key: str
    tr_type: KISTrType
    cust_type: str = Field(serialization_alias="custtype", default="P")
    content_type: str = Field(serialization_alias="content-type", default="utf-8")


class KISTrId(StrEnum):
    STOCK_TRADE_KRX = "H0STCNT0"  # KRX(한국거래소) 실시간 체결가
    STOCK_TRADE_NXT = "H0NXCNT0"  # NXT(넥스트레이드) 실시간 체결가
    STOCK_TRADE_UNIFIED = "H0UNCNT0"  # KRX와 NXT 통합 실시간 체결가

    STOCK_ORDERBOOK_KRX = "H0STASP0"  # KRX(한국거래소) 실시간 매수·매도 호가
    STOCK_ORDERBOOK_NXT = "H0NXASP0"  # NXT(넥스트레이드) 실시간 매수·매도 호가
    STOCK_ORDERBOOK_UNIFIED = "H0UNASP0"  # KRX와 NXT 통합 실시간 매수·매도 호가


class KISWebSocketSubscriptionInput(KISBaseModel):
    tr_key: StockCode
    tr_id: KISTrId


class KISWebSocketSubscriptionBody(KISBaseModel):
    input: KISWebSocketSubscriptionInput


class KISWebSocketSubscriptionMessage(KISBaseModel):
    header: KISWebSocketSubscriptionHeader
    body: KISWebSocketSubscriptionBody


class KISSubscription(KISBaseModel):
    model_config = ConfigDict(frozen=True, serialize_by_alias=True)

    code: StockCode
    tr_id: KISTrId
