"""미국 국채 수집 과정에서 발생하는 예외."""


class TreasuryDataUnavailableError(Exception):
    """외부 소스에 아직 데이터가 없다. 재시도 대상."""


class YahooRetryableError(Exception):
    """Celery가 재시도해야 하는 Yahoo 실패."""
