import json

from app.kis.schemas import (
    KISAuthRequest,
    KISTrId,
    KISTrType,
    KISWebSocketSubscriptionBody,
    KISWebSocketSubscriptionHeader,
    KISWebSocketSubscriptionInput,
    KISWebSocketSubscriptionMessage,
    StockCode,
)
from app.kis.schemas.auth import KISAuthRequest as AuthRequestFromModule
from app.kis.schemas.websocket import (
    KISWebSocketSubscriptionMessage as MessageFromModule,
)


def test_schema_package_reexports_public_models() -> None:
    assert KISAuthRequest is AuthRequestFromModule
    assert KISWebSocketSubscriptionMessage is MessageFromModule


def test_auth_request_serializes_kis_aliases() -> None:
    request = KISAuthRequest(app_key="app-key", app_secret="app-secret")

    assert request.model_dump() == {
        "appkey": "app-key",
        "appsecret": "app-secret",
        "grant_type": "client_credentials",
    }


def test_websocket_subscription_serializes_kis_aliases() -> None:
    message = KISWebSocketSubscriptionMessage(
        header=KISWebSocketSubscriptionHeader(
            approval_key="approval-key",
            tr_type=KISTrType.SUBSCRIBE,
        ),
        body=KISWebSocketSubscriptionBody(
            input=KISWebSocketSubscriptionInput(
                tr_key=StockCode.SAMSUNG_ELECTRONICS,
                tr_id=KISTrId.STOCK_TRADE_KRX,
            )
        ),
    )

    assert json.loads(message.model_dump_json()) == {
        "header": {
            "approval_key": "approval-key",
            "tr_type": "1",
            "custtype": "P",
            "content-type": "utf-8",
        },
        "body": {"input": {"tr_key": "005930", "tr_id": "H0STCNT0"}},
    }
