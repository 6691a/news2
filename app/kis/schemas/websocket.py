from enum import StrEnum

from pydantic import ConfigDict, Field

from app.kis.schemas.common import KISBaseModel


class KISTrType(StrEnum):
    SUBSCRIBE = "1"
    UNSUBSCRIBE = "2"


class KISWebSocketSubscriptionHeader(KISBaseModel):
    approval_key: str
    tr_type: KISTrType
    cust_type: str = Field(serialization_alias="custtype", default="P")
    content_type: str = Field(serialization_alias="content-type", default="utf-8")


class KISWebSocketSubscriptionInput(KISBaseModel):
    tr_key: str
    tr_id: str


class KISWebSocketSubscriptionBody(KISBaseModel):
    input: KISWebSocketSubscriptionInput


class KISWebSocketSubscriptionMessage(KISBaseModel):
    header: KISWebSocketSubscriptionHeader
    body: KISWebSocketSubscriptionBody


class KISWebSocketSubscription(KISBaseModel):
    model_config = ConfigDict(frozen=True, serialize_by_alias=True)

    tr_id: str
    tr_key: str
