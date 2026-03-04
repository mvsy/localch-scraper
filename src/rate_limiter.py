import time


class RateLimiter:
    """Einfacher Rate-Limiter der zwischen Requests wartet."""

    def __init__(self, requests_per_second: float = 1.0):
        self.min_interval = 1.0 / requests_per_second
        self._last_request_time = 0.0

    def wait(self):
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_time = time.monotonic()
