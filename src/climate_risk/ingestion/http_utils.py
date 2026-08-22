"""Bounded exponential backoff with jitter for transient transport failures.

Per 01_data_ingestion.md section 7: retry on 429/5xx and connection errors;
treat auth failures, repeated timeouts and unexpected content types as hard
failures that should not retry forever.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable

import httpx

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def get_with_retry(
    url: str,
    *,
    timeout: float = 30.0,
    max_attempts: int = 4,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=True)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            if attempt == max_attempts:
                raise
            _sleep_backoff(attempt, base_delay, sleep)
            continue

        if response.status_code in RETRYABLE_STATUS and attempt < max_attempts:
            _sleep_backoff(attempt, base_delay, sleep)
            continue
        return response

    assert last_exc is not None
    raise last_exc


def _sleep_backoff(attempt: int, base_delay: float, sleep: Callable[[float], None]) -> None:
    delay = base_delay * (2 ** (attempt - 1))
    jitter = random.uniform(0, delay * 0.25)
    sleep(delay + jitter)
