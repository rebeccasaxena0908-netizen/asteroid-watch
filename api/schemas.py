"""Pydantic response models: the exact JSON shape of every endpoint.

They document the API (http://localhost:8000/docs) and validate every response before it
is sent. Field order is the JSON key order. Types match the PHP API: dates are strings
("2026-10-12", "2026-10-12 06:30:00") and absolute_magnitude_h is a string ("21.650"),
because that's how PHP's PDO returned DATE, DATETIME and DECIMAL columns.
"""

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    # strict: no silent type conversion (an int stays an int, a string stays a string)
    model_config = ConfigDict(strict=True, extra="forbid")


class ErrorResponse(Model):
    error: str


# --- summary --------------------------------------------------------------------------

class Totals(Model):
    asteroids: int
    hazardous_asteroids: int
    approaches: int
    hazardous_approaches: int
    asteroids_with_orbits: int
    first_date: str | None
    last_date: str | None
    today: str


class ThisWeek(Model):
    approaches: int
    asteroids: int
    hazardous: int


class ClosestApproach(Model):
    neo_id: str
    name: str
    is_potentially_hazardous: bool
    approach_date: str
    approach_datetime: str | None
    miss_distance_km: float | None
    miss_distance_lunar: float | None
    relative_velocity_kps: float | None


class ClosestOnRecord(Model):
    approach_id: int
    neo_id: str
    name: str
    is_potentially_hazardous: bool
    approach_date: str
    miss_distance_km: float | None
    miss_distance_lunar: float | None
    relative_velocity_kps: float | None


class Largest(Model):
    neo_id: str
    name: str
    is_potentially_hazardous: bool
    est_diameter_min_m: float | None
    est_diameter_max_m: float | None
    approach_count: int
    closest_miss_km: float | None


class LastRun(Model):
    run_id: int
    run_type: str
    status: str
    started_at: str
    finished_at: str | None
    duration_seconds: int | None
    api_calls: int
    records_extracted: int
    records_after_dedupe: int | None
    rows_inserted: int
    rows_updated: int
    quality_failures: int
    quality_checks: int


class Summary(Model):
    totals: Totals
    this_week: ThisWeek
    closest_this_week: ClosestApproach | None
    closest_upcoming: ClosestApproach | None
    closest_on_record: ClosestOnRecord | None
    largest: Largest | None
    last_run: LastRun | None


class SummaryResponse(Model):
    data: Summary


# --- approaches -----------------------------------------------------------------------

class ApproachItem(Model):
    approach_id: int
    neo_id: str
    name: str
    is_potentially_hazardous: bool
    est_diameter_min_m: float | None
    est_diameter_max_m: float | None
    approach_date: str
    approach_datetime: str | None
    relative_velocity_kps: float | None
    relative_velocity_kph: float | None
    miss_distance_km: float | None
    miss_distance_lunar: float | None
    miss_distance_au: float | None
    orbiting_body: str


class ApproachFilters(Model):
    start: str | None
    end: str | None
    hazardous: str
    q: str
    sort: str
    order: str


class Approaches(Model):
    items: list[ApproachItem]
    page: int
    per_page: int
    total: int
    total_pages: int
    filters: ApproachFilters


class ApproachesResponse(Model):
    data: Approaches


# --- asteroid -------------------------------------------------------------------------

class AsteroidRow(Model):
    neo_id: str
    name: str
    nasa_jpl_url: str | None
    absolute_magnitude_h: str | None
    est_diameter_min_m: float | None
    est_diameter_max_m: float | None
    is_potentially_hazardous: bool
    is_sentry_object: bool
    first_seen_at: str
    updated_at: str


class Orbit(Model):
    orbit_class: str | None
    orbit_class_description: str | None
    eccentricity: float | None
    inclination_deg: float | None
    orbital_period_days: float | None
    first_observation_date: str | None
    last_observation_date: str | None
    fetched_at: str


class AsteroidApproach(Model):
    approach_id: int
    approach_date: str
    approach_datetime: str | None
    relative_velocity_kps: float | None
    relative_velocity_kph: float | None
    miss_distance_km: float | None
    miss_distance_lunar: float | None
    miss_distance_au: float | None
    orbiting_body: str


class AsteroidDetail(Model):
    asteroid: AsteroidRow
    orbit: Orbit | None
    approaches: list[AsteroidApproach]
    old_ids: list[str]
    resolved_from: str | None


class AsteroidResponse(Model):
    data: AsteroidDetail


# --- trends ---------------------------------------------------------------------------

class DateRange(Model):
    start: str | None
    end: str | None


class DailyCount(Model):
    approach_date: str
    approach_count: int
    hazardous_count: int


class SizeBin(Model):
    min_m: int
    max_m: int | None
    label: str
    count: int
    hazardous: int


class TrendCounts(Model):
    approaches: int
    asteroids: int
    asteroids_without_size: int


class ScatterPoint(Model):
    neo_id: str
    name: str
    is_potentially_hazardous: bool
    approach_date: str
    relative_velocity_kps: float | None
    miss_distance_lunar: float | None


class HazardSplit(Model):
    is_potentially_hazardous: bool
    asteroid_count: int
    approach_count: int


class Trends(Model):
    range: DateRange
    daily: list[DailyCount]
    size_histogram: list[SizeBin]
    counts: TrendCounts
    velocity_vs_distance: list[ScatterPoint]
    hazardous_split: list[HazardSplit]


class TrendsResponse(Model):
    data: Trends


# --- runs -----------------------------------------------------------------------------

class QualityCheck(Model):
    check_name: str
    passed: bool
    details: str | None


class Run(Model):
    run_id: int
    run_type: str
    status: str
    started_at: str
    finished_at: str | None
    duration_seconds: int | None
    date_range_start: str | None
    date_range_end: str | None
    api_calls: int
    records_extracted: int
    records_after_dedupe: int | None
    rows_inserted: int
    rows_updated: int
    quality_failures: int
    error_message: str | None
    quality: list[QualityCheck]


class Runs(Model):
    runs: list[Run]


class RunsResponse(Model):
    data: Runs
