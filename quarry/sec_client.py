"""Polite HTTP access to SEC EDGAR: User-Agent, throttling, retries."""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request


class SecClient:
    def __init__(self, user_agent: str, max_per_second: float = 8.0, retries: int = 3, opener=None):
        self.user_agent = user_agent
        self.min_interval = 1.0 / max_per_second
        self.retries = retries
        self.opener = opener or urllib.request.urlopen
        self._last_request = 0.0

    def get_text(self, url: str, absent_codes: tuple[int, ...] = (404,)) -> str | None:
        """Body as text, or None if the resource does not exist.

        EDGAR answers 403 instead of 404 for daily indexes that aren't
        published yet, so callers can widen `absent_codes`."""
        body = self.get_bytes(url, absent_codes)
        return body.decode("utf-8", errors="replace") if body is not None else None

    def get_bytes(self, url: str, absent_codes: tuple[int, ...] = (404,)) -> bytes | None:
        for attempt in range(self.retries):
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
                if error.code in (403, 429, 500, 502, 503) and attempt < self.retries - 1:
                    time.sleep(2 ** attempt * 5)
                    continue
                raise
            except urllib.error.URLError:
                if attempt < self.retries - 1:
                    time.sleep(2 ** attempt * 5)
                    continue
                raise
        return None

    def get_json(self, url: str) -> dict | None:
        text = self.get_text(url)
        return json.loads(text) if text else None

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()
