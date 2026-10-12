import json
from datetime import date
from pathlib import Path

import pytest
import requests

from pipeline.extract import ExtractError, NeoWsClient, date_chunks, extract_feed

FIXTURE = Path(__file__).parent / "fixtures" / "feed_sample.json"
KEY = "TEST_KEY_123"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    """Returns queued responses (or raises queued exceptions) and records each request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, params=None, timeout=None):
        self.requests.append((url, params))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def fixture_with_key():
    """The fixture as the API would send it: with the real key inside the links."""
    return json.loads(FIXTURE.read_text().replace("REDACTED", KEY))


def make_client(responses, sleeps=None):
    sleeps = [] if sleeps is None else sleeps
    return NeoWsClient(KEY, session=FakeSession(responses), sleep=sleeps.append)


# --- date_chunks -------------------------------------------------------------

def test_chunks_split_into_seven_day_pieces():
    chunks = date_chunks(date(2026, 10, 5), date(2026, 10, 19))
    assert chunks == [
        (date(2026, 10, 5), date(2026, 10, 11)),
        (date(2026, 10, 12), date(2026, 10, 18)),
        (date(2026, 10, 19), date(2026, 10, 19)),
    ]


def test_backfill_range_needs_57_calls():
    # 365 days back + 30 days forward + today = 396 days
    assert len(date_chunks(date(2025, 10, 12), date(2026, 11, 11))) == 57


def test_chunks_cover_every_day_exactly_once():
    chunks = date_chunks(date(2026, 1, 1), date(2026, 3, 31))
    days = sum((end - start).days + 1 for start, end in chunks)
    assert days == 90
    assert all((end - start).days < 7 for start, end in chunks)


def test_chunks_reject_reversed_range():
    with pytest.raises(ValueError):
        date_chunks(date(2026, 1, 2), date(2026, 1, 1))


# --- retries and errors --------------------------------------------------------

def test_retries_on_429_then_succeeds():
    sleeps = []
    client = make_client([FakeResponse(429), FakeResponse(503), FakeResponse(200, {"ok": 1})], sleeps)

    assert client.get_json("/feed") == {"ok": 1}
    assert client.api_calls == 3
    assert sleeps == [2.0, 4.0]  # exponential backoff


def test_uses_retry_after_header_when_given():
    sleeps = []
    client = make_client([FakeResponse(429, headers={"Retry-After": "30"}), FakeResponse(200, {})], sleeps)

    client.get_json("/feed")
    assert sleeps == [30.0]


def test_retries_network_errors():
    client = make_client([requests.ConnectionError("boom"), FakeResponse(200, {"ok": 1})])
    assert client.get_json("/feed") == {"ok": 1}


def test_gives_up_after_max_retries():
    client = make_client([FakeResponse(500)] * 5)
    with pytest.raises(ExtractError, match="after 5 attempts"):
        client.get_json("/feed")
    assert client.api_calls == 5


def test_does_not_retry_client_errors():
    client = make_client([FakeResponse(403, text="API_KEY_INVALID")])
    with pytest.raises(ExtractError, match="HTTP 403"):
        client.get_json("/feed")
    assert client.api_calls == 1


def test_errors_never_contain_the_api_key():
    url_with_key = f"https://api.nasa.gov/neo/rest/v1/feed?api_key={KEY}"
    client = make_client([FakeResponse(400, text=f"bad request for {url_with_key}")])
    with pytest.raises(ExtractError) as err:
        client.get_json("/feed")
    assert KEY not in str(err.value)

    client = make_client([requests.ConnectionError(f"failed: {url_with_key}")] * 5)
    with pytest.raises(ExtractError) as err:
        client.get_json("/feed")
    assert KEY not in str(err.value)


def test_records_rate_limit_from_headers():
    headers = {"X-RateLimit-Remaining": "1997", "X-RateLimit-Limit": "2000"}
    client = make_client([FakeResponse(200, {}, headers=headers)])
    client.get_json("/feed")
    assert client.rate_limit_remaining == 1997


def test_feed_sends_dates_and_key():
    client = make_client([FakeResponse(200, {})])
    client.feed(date(2026, 10, 13), date(2026, 10, 14))
    url, params = client.session.requests[0]
    assert url.endswith("/neo/rest/v1/feed")
    assert params == {"start_date": "2026-10-13", "end_date": "2026-10-14", "api_key": KEY}


# --- extract_feed --------------------------------------------------------------

def test_extract_feed_saves_raw_json_without_key(tmp_path):
    client = make_client([FakeResponse(200, fixture_with_key())])

    result = extract_feed(client, date(2026, 10, 13), date(2026, 10, 14),
                          raw_dir=tmp_path, run_date=date(2026, 10, 12))

    assert result.api_calls == 1
    assert result.element_count == 4
    assert result.dates_fetched == {"2026-10-13", "2026-10-14"}
    assert result.days_requested == 2
    saved = tmp_path / "2026-10-12" / "feed_2026-10-13_2026-10-14.json"
    assert result.files == [saved]
    assert KEY not in saved.read_text()
    assert json.loads(saved.read_text())["element_count"] == 4


def test_extract_feed_makes_one_call_per_chunk(tmp_path):
    client = make_client([FakeResponse(200, fixture_with_key()) for _ in range(3)])

    result = extract_feed(client, date(2026, 10, 5), date(2026, 10, 19),
                          raw_dir=tmp_path, run_date=date(2026, 10, 12))

    assert result.api_calls == 3
    assert len(result.files) == 3
    assert [p["start_date"] for _, p in client.session.requests] == ["2026-10-05", "2026-10-12", "2026-10-19"]
