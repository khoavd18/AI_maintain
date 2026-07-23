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
