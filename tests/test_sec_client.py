import io
import urllib.error

from quarry.sec_client import SecClient


class FakeResponse(io.BytesIO):
    headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_sends_user_agent_and_returns_text():
    seen = {}

    def opener(request, timeout):
        seen["ua"] = request.get_header("User-agent")
        return FakeResponse(b"hello")

    client = SecClient("Quarry test@example.com", opener=opener, max_per_second=1000)
    assert client.get_text("https://example.com") == "hello"
    assert seen["ua"] == "Quarry test@example.com"


def test_404_returns_none():
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    client = SecClient("ua", opener=opener, max_per_second=1000)
    assert client.get_text("https://example.com/missing") is None


def test_custom_absent_codes_return_none_without_retrying():
    calls = []

    def opener(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)

    client = SecClient("ua", opener=opener, max_per_second=1000)
    assert client.get_text("https://example.com/not-yet", absent_codes=(403, 404)) is None
    assert len(calls) == 1


def _flaky_opener(failures, error):
    calls = []

    def opener(request, timeout):
        calls.append(1)
        if len(calls) <= failures:
            raise error(request)
        return FakeResponse(b"ok")
    return opener, calls


def _http(code, headers=None):
    return lambda request: urllib.error.HTTPError(request.full_url, code, "error", headers or {}, None)


def test_rate_limit_waits_patiently_and_slows_down():
    waits = []
    opener, calls = _flaky_opener(3, _http(429))
    client = SecClient("ua", opener=opener, max_per_second=8, sleep=waits.append, log=lambda _: None)
    assert client.get_text("https://example.com") == "ok"
    assert len(calls) == 4
    # Long pauses: the SEC blocks for several minutes once the limit is hit.
    assert [w for w in waits if w >= 1] == [10, 30, 60]
    assert client.min_interval == 1 / 4


def test_retry_after_header_is_honoured():
    waits = []
    opener, _ = _flaky_opener(1, _http(429, {"Retry-After": "90"}))
    client = SecClient("ua", opener=opener, max_per_second=1000, sleep=waits.append, log=lambda _: None)
    assert client.get_text("https://example.com") == "ok"
    assert 90 in waits


def test_timeouts_and_dropped_connections_are_retried():
    for error in (lambda r: TimeoutError("read timed out"), lambda r: ConnectionResetError("reset")):
        opener, calls = _flaky_opener(2, error)
        client = SecClient("ua", opener=opener, max_per_second=1000, sleep=lambda _: None, log=lambda _: None)
        assert client.get_text("https://example.com") == "ok"
        assert len(calls) == 3


def test_gives_up_after_all_retries():
    opener, calls = _flaky_opener(99, _http(503))
    client = SecClient("ua", opener=opener, max_per_second=1000, sleep=lambda _: None, log=lambda _: None)
    try:
        client.get_text("https://example.com")
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError:
        pass
    assert len(calls) == len(SecClient.BACKOFF) + 1
