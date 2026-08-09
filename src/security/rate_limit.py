"""Small in-process login attempt limiter for the single-instance pilot."""

from collections import defaultdict, deque
from threading import Lock
import time


class LoginRateLimitExceededError(RuntimeError):
    """Raised when one normalized identifier exceeds the configured failure budget."""


class LoginRateLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        with self._lock:
            failures = self._current_failures(key)
            if len(failures) >= self.max_attempts:
                raise LoginRateLimitExceededError

    def record_failure(self, key: str) -> None:
        with self._lock:
            failures = self._current_failures(key)
            failures.append(time.monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()

    def _current_failures(self, key: str) -> deque[float]:
        failures = self._failures[key]
        cutoff = time.monotonic() - self.window_seconds
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures


class RequestRateLimitExceededError(RuntimeError):
    """Raised when a caller exceeds a bounded request budget."""


class RequestRateLimiter:
    """Small per-caller limiter for the documented single-API-instance pilot."""

    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def consume(self, key: str) -> None:
        with self._lock:
            requests = self._current_requests(key)
            if len(requests) >= self.max_requests:
                raise RequestRateLimitExceededError
            requests.append(time.monotonic())

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()

    def _current_requests(self, key: str) -> deque[float]:
        requests = self._requests[key]
        cutoff = time.monotonic() - self.window_seconds
        while requests and requests[0] <= cutoff:
            requests.popleft()
        return requests
