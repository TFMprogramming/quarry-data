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
