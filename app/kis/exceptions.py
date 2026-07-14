class KISWebSocketNotConnectedError(Exception):
    def __init__(self) -> None:
        super().__init__("WebSocket connection is not established.")


class KISWebSocketSubscriptionLimitError(Exception):
    def __init__(self, max_subscriptions: int = 40) -> None:
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
