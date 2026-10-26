"""Extract: download close-approach data from the NASA NeoWs feed API.

- The feed allows at most 7 days per request, so any date range is split into 7-day chunks.
- HTTP 429 (rate limited) and 5xx errors are retried with exponential backoff.
- The remaining hourly rate limit is logged from the response headers.
- Each response is saved unchanged (except the API key is removed) as raw JSON
  under data/raw/<run date>/ : this is the "bronze" layer.

Usage: python -m pipeline.extract --backfill-days 7 --forward-days 7
"""
import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import requests

from pipeline.config import PROJECT_ROOT, load_settings

log = logging.getLogger(__name__)

NEOWS_BASE_URL = "https://api.nasa.gov/neo/rest/v1"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
MAX_DAYS_PER_REQUEST = 7
RETRY_STATUSES = {429, 500, 502, 503, 504}


class ExtractError(Exception):
    pass


def date_chunks(start: date, end: date, max_days: int = MAX_DAYS_PER_REQUEST) -> list[tuple[date, date]]:
    """Split [start, end] (both inclusive) into chunks of at most max_days days."""
    if end < start:
        raise ValueError(f"end date {end} is before start date {start}")
    chunks = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=max_days - 1), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks


class NeoWsClient:
    """Small HTTP client for NeoWs with retries. Never logs or raises the API key."""

    def __init__(self, api_key: str, session=None, base_url: str = NEOWS_BASE_URL,
                 max_retries: int = 4, backoff_seconds: float = 2.0, timeout: float = 30.0,
                 sleep=time.sleep):
        self.api_key = api_key
        self.session = session or requests.Session()
        self.base_url = base_url
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.timeout = timeout
        self.sleep = sleep            # injectable so tests don't really wait
        self.api_calls = 0            # every HTTP attempt, including retries
        self.rate_limit_remaining: int | None = None

    def redact(self, text: str) -> str:
        return text.replace(self.api_key, "REDACTED") if self.api_key else text

    def get_json(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        if self.api_key:  # JPL APIs need no key
            params["api_key"] = self.api_key
        for attempt in range(self.max_retries + 1):
            self.api_calls += 1
            wait = self.backoff_seconds * (2 ** attempt)
            try:
                response = self.session.get(self.base_url + path, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                # The exception text can contain the full URL (with the key), so log only its type.
                problem = f"network error ({type(exc).__name__})"
            else:
                self._record_rate_limit(response)
                if response.status_code == 200:
                    return response.json()
                if response.status_code not in RETRY_STATUSES:
                    body = self.redact(response.text[:300])
                    raise ExtractError(f"HTTP {response.status_code} for {path}: {body}")
                problem = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    wait = float(retry_after)

            if attempt == self.max_retries:
                raise ExtractError(f"Gave up on {path} after {attempt + 1} attempts: {problem}")
            log.warning("%s for %s, retrying in %.0fs (attempt %d/%d)",
                        problem, path, wait, attempt + 1, self.max_retries)
            self.sleep(wait)
        raise AssertionError("unreachable: the last attempt returns or raises")

    def _record_rate_limit(self, response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is None:
            return
        self.rate_limit_remaining = int(remaining)
        limit = response.headers.get("X-RateLimit-Limit", "?")
        log.info("Rate limit remaining: %s/%s", remaining, limit)
        if self.rate_limit_remaining < 50:
            log.warning("NASA rate limit is nearly used up (%s left this hour)", remaining)

    def feed(self, start: date, end: date) -> dict:
        return self.get_json("/feed", {"start_date": start.isoformat(), "end_date": end.isoformat()})

    def lookup(self, neo_id: str) -> dict:
        return self.get_json(f"/neo/{neo_id}")


@dataclass
class ExtractResult:
    start: date
    end: date
    payloads: list[dict] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    api_calls: int = 0
    element_count: int = 0          # sum of the API's own element_count per response
    dates_fetched: set[str] = field(default_factory=set)

    @property
    def days_requested(self) -> int:
        return (self.end - self.start).days + 1


def save_raw(payload: dict, filename: str, client: NeoWsClient, raw_dir: Path, run_date: date) -> Path:
    """Write one API response to data/raw/<run date>/<filename>, with the key removed."""
    folder = raw_dir / run_date.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    # NeoWs puts the api_key inside its "links" URLs, so redact the whole text before saving.
    path.write_text(client.redact(json.dumps(payload, indent=1)))
    return path


def extract_feed(client: NeoWsClient, start: date, end: date,
                 raw_dir: Path = RAW_DIR, run_date: date | None = None) -> ExtractResult:
    run_date = run_date or date.today()
    result = ExtractResult(start=start, end=end)
    calls_before = client.api_calls
    for chunk_start, chunk_end in date_chunks(start, end):
        log.info("Fetching feed %s to %s", chunk_start, chunk_end)
        payload = client.feed(chunk_start, chunk_end)
        result.payloads.append(payload)
        filename = f"feed_{chunk_start.isoformat()}_{chunk_end.isoformat()}.json"
        result.files.append(save_raw(payload, filename, client, raw_dir, run_date))
        result.element_count += int(payload.get("element_count", 0))
        result.dates_fetched.update(payload.get("near_earth_objects", {}).keys())
    result.api_calls = client.api_calls - calls_before
    return result


MAX_LOOKUP_FAILURES = 5


def extract_lookups(client: NeoWsClient, neo_ids: list[str],
                    raw_dir: Path = RAW_DIR, run_date: date | None = None) -> list[dict]:
    """Fetch NeoWs Lookup data (orbits) for each asteroid id; saves raw JSON as neo_<id>.json.

    One failed asteroid is skipped; after several failures we stop (the API is probably down
    or the rate limit is used up) and keep what we have.
    """
    run_date = run_date or date.today()
    payloads, failures = [], 0
    for neo_id in neo_ids:
        try:
            payload = client.lookup(neo_id)
        except ExtractError as exc:
            failures += 1
            log.warning("Lookup failed for %s: %s", neo_id, exc)
            if failures >= MAX_LOOKUP_FAILURES:
                log.warning("Stopping orbital lookups after %d failures", failures)
                break
            continue
        save_raw(payload, f"neo_{neo_id}.json", client, raw_dir, run_date)
        payloads.append(payload)
    return payloads


def main() -> None:
    parser = argparse.ArgumentParser(description="Download NeoWs feed data as raw JSON.")
    parser.add_argument("--backfill-days", type=int, default=7, help="days before today to fetch")
    parser.add_argument("--forward-days", type=int, default=7, help="days after today to fetch")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    settings = load_settings()
    if not settings.has_real_api_key:
        raise SystemExit("NASA_API_KEY is not set in .env")
    today = date.today()
    start, end = today - timedelta(days=args.backfill_days), today + timedelta(days=args.forward_days)

    client = NeoWsClient(settings.nasa_api_key)
    result = extract_feed(client, start, end)
    print(f"Range {start} to {end}: {result.days_requested} days requested, "
          f"{len(result.dates_fetched)} days returned")
    print(f"API calls: {result.api_calls}, close approaches (element_count): {result.element_count}")
    print(f"Rate limit remaining: {client.rate_limit_remaining}")
    print(f"Raw files: {len(result.files)} in {result.files[0].parent.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
