from __future__ import annotations

import httpx
import respx

from climate_risk.ingestion.http_utils import get_with_retry


@respx.mock
def test_retries_on_503_then_succeeds() -> None:
    route = respx.get("https://example.invalid/data").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, content=b"ok"),
        ]
    )
    response = get_with_retry(
        "https://example.invalid/data", max_attempts=3, base_delay=0.0, sleep=lambda _: None
    )
    assert response.status_code == 200
    assert route.call_count == 2


@respx.mock
def test_does_not_retry_on_404() -> None:
    route = respx.get("https://example.invalid/missing").mock(return_value=httpx.Response(404))
    response = get_with_retry(
        "https://example.invalid/missing", max_attempts=3, base_delay=0.0, sleep=lambda _: None
    )
    assert response.status_code == 404
    assert route.call_count == 1
