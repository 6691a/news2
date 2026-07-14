import json

from app.kis.exceptions import (
    KISWebSocketSubscriptionRejectedError,
    KISWebSocketSubscriptionTimeoutError,
)
from app.kis.schemas import (
    KISAuthRequest,
    KISTrType,
    KISWebSocketSubscriptionResponse,
    KISWebSocketSubscriptionBody,
    KISWebSocketSubscriptionHeader,
    KISWebSocketSubscriptionInput,
    KISWebSocketSubscriptionMessage,
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
                tr_key="005930",
                tr_id="H0STCNT0",
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


def test_websocket_subscription_response_parses_success() -> None:
    response = KISWebSocketSubscriptionResponse.model_validate(
        {
            "header": {
                "tr_id": "H0STCNT0",
                "tr_key": "000660",
                "encrypt": "N",
            },
            "body": {
                "rt_cd": "0",
                "msg_cd": "OPSP0000",
                "msg1": "SUBSCRIBE SUCCESS",
                "output": {"iv": "unused", "key": "unused"},
            },
        }
    )

    assert response.header.tr_id == "H0STCNT0"
    assert response.header.tr_key == "000660"
    assert response.header.encrypt == "N"
    assert response.is_success


def test_websocket_subscription_errors_preserve_response_context() -> None:
    rejected = KISWebSocketSubscriptionRejectedError(
        tr_id="H0STCNT0",
        tr_key="000660",
        msg_cd="OPSP9999",
        msg1="INVALID SUBSCRIPTION",
    )
    timeout = KISWebSocketSubscriptionTimeoutError(frozenset({("H0STCNT0", "000660")}))

    assert rejected.tr_id == "H0STCNT0"
    assert rejected.tr_key == "000660"
    assert rejected.msg_cd == "OPSP9999"
    assert rejected.msg1 == "INVALID SUBSCRIPTION"
    assert timeout.pending_subscriptions == frozenset({("H0STCNT0", "000660")})
