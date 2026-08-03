class KISWebSocketNotConnectedError(Exception):
    def __init__(self) -> None:
        """열린 웹소켓 연결이 없다는 사실을 알린다."""

        super().__init__("WebSocket connection is not established.")


class KISWebSocketSubscriptionLimitError(Exception):
    def __init__(self, max_subscriptions: int) -> None:
        """한도를 넘긴 구독 요청 정보를 보존한다.

        기본값을 두지 않는다. 이 모듈이 base를 import하면 순환이 생겨 한도 상수를
        공유할 수 없으므로, 대신 호출자가 `KIS_MAX_SUBSCRIPTIONS`를 넘기게 한다.

        Args:
            max_subscriptions: KIS가 허용하는 동시 구독 수.
        """

        super().__init__(f"KIS WebSocket subscription limit exceeded: {max_subscriptions}")


class KISWebSocketSubscriptionRejectedError(RuntimeError):
    def __init__(
        self,
        tr_id: str,
        tr_key: str,
        msg_cd: str,
        msg1: str,
    ) -> None:
        """KIS가 거절한 구독 응답 정보를 보존한다.

        Args:
            tr_id: 거절된 실시간 TR ID.
            tr_key: 거절된 종목 또는 구독 키.
            msg_cd: KIS 응답 메시지 코드.
            msg1: KIS 응답 메시지.
        """

        self.tr_id = tr_id
        self.tr_key = tr_key
        self.msg_cd = msg_cd
        self.msg1 = msg1
        super().__init__(
            f"KIS WebSocket subscription rejected: tr_id={tr_id!r}, tr_key={tr_key!r}, msg_cd={msg_cd!r}, msg1={msg1!r}"
        )


class KISWebSocketSubscriptionTimeoutError(TimeoutError):
    def __init__(
        self,
        pending_subscriptions: frozenset[tuple[str, str]],
    ) -> None:
        """확인 시간을 넘긴 구독 키를 보존한다.

        Args:
            pending_subscriptions: 아직 확인되지 않은 `(tr_id, tr_key)` 집합.
        """

        self.pending_subscriptions = pending_subscriptions
        super().__init__(f"KIS WebSocket subscription acknowledgement timed out: {sorted(pending_subscriptions)!r}")
