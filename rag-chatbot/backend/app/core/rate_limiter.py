"""
Simple in-memory sliding-window rate limiter.
For multi-process / distributed deployments, replace with Redis (e.g. slowapi + redis).
"""

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Tuple


class RateLimiter:
    def __init__(self, requests_per_minute: int = 20, requests_per_hour: int = 200):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        # Per-IP timestamps stored as deques for O(1) eviction
        self._minute_window: dict[str, deque] = defaultdict(deque)
        self._hour_window: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def is_allowed(self, client_ip: str) -> Tuple[bool, str]:
        now = time.time()
        with self._lock:
            # Evict stale timestamps
            minute_q = self._minute_window[client_ip]
            hour_q = self._hour_window[client_ip]

            while minute_q and now - minute_q[0] > 60:
                minute_q.popleft()
            while hour_q and now - hour_q[0] > 3600:
                hour_q.popleft()

            if len(minute_q) >= self.rpm:
                return False, f"Max {self.rpm} requests per minute."
            if len(hour_q) >= self.rph:
                return False, f"Max {self.rph} requests per hour."

            minute_q.append(now)
            hour_q.append(now)
            return True, ""
