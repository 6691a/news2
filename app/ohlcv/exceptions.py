"""OHLCV 수집 과정에서 발생하는 예외."""


class OhlcvSourceError(Exception):
    """소스가 업무 오류를 돌려줬다. 다시 물어봐도 같은 답이라 재시도하지 않는다."""


class YahooRetryableError(Exception):
    """Celery가 재시도해야 하는 Yahoo 실패."""
