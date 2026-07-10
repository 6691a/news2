class KISWebSocketNotConnectedError(Exception):
    def __init__(self) -> None:
        super().__init__("WebSocket connection is not established.")


class KISWebSocketSubscriptionLimitError(Exception):
    def __init__(self, max_subscriptions: int = 40) -> None:
        super().__init__(
            f"KIS WebSocket subscription limit exceeded: {max_subscriptions}"
        )
