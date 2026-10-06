"""Polite HTTP access to SEC EDGAR: User-Agent, throttling, patient retries."""
from __future__ import annotations

import gzip
import http.client
import json
import time
import urllib.error
import urllib.request

# Answers worth waiting for: rate limits, overloaded servers.
RETRY_CODES = (403, 429, 500, 502, 503, 504)


class SecClient:
    # Pauses between attempts in seconds. Once the SEC rate limit is hit it
    # blocks for several minutes, so short pauses alone would just fail again.
    BACKOFF = (10, 30, 60, 120, 300, 600)

    def __init__(self, user_agent: str, max_per_second: float = 8.0, opener=None, sleep=time.sleep, log=print):
        self.user_agent = user_agent
        self.base_interval = self.min_interval = 1.0 / max_per_second
        self.opener = opener or urllib.request.urlopen
        self.sleep = sleep
        self.log = log
        self._last_request = 0.0

    def get_text(self, url: str, absent_codes: tuple[int, ...] = (404,)) -> str | None:
        """Body as text, or None if the resource does not exist.

        EDGAR answers 403 instead of 404 for daily indexes that aren't
        published yet, so callers can widen `absent_codes`."""
        body = self.get_bytes(url, absent_codes)
        return body.decode("utf-8", errors="replace") if body is not None else None

    def get_bytes(self, url: str, absent_codes: tuple[int, ...] = (404,)) -> bytes | None:
        for attempt in range(len(self.BACKOFF) + 1):
            self._throttle()
            request = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip"})
            try:
                with self.opener(request, timeout=60) as response:
                    body = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    return body
            except urllib.error.HTTPError as error:
                if error.code in absent_codes:
                    return None
                if error.code not in RETRY_CODES or attempt == len(self.BACKOFF):
                    raise
                if error.code == 429:
                    self._slow_down()
                self._wait(attempt, f"HTTP {error.code}", _retry_after(error))
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as error:
                if attempt == len(self.BACKOFF):
                    raise
                self._wait(attempt, type(error).__name__, None)
        return None

    def get_json(self, url: str) -> dict | None:
        text = self.get_text(url)
        return json.loads(text) if text else None

    def _wait(self, attempt: int, reason: str, retry_after: float | None) -> None:
        pause = max(self.BACKOFF[attempt], retry_after or 0)
        self.log(f"SEC: {reason}, neuer Versuch in {pause:.0f} s")
        self.sleep(pause)

    def _slow_down(self) -> None:
        """Halves the request rate for the rest of the run."""
        self.min_interval = self.base_interval * 2

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()


def _retry_after(error: urllib.error.HTTPError) -> float | None:
    value = (error.headers or {}).get("Retry-After")
    return float(value) if value and value.isdigit() else None
