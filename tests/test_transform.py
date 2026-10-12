import copy
import json
from datetime import date, datetime
from pathlib import Path

from pipeline.transform import (diameter_m, parse_approach_datetime, to_float, transform_feeds,
                                transform_orbital)

FIXTURES = Path(__file__).parent / "fixtures"


def feed():
    return json.loads((FIXTURES / "feed_sample.json").read_text())


def first_neo(payload):
    return payload["near_earth_objects"]["2026-10-13"][0]


# --- small converters ------------------------------------------------------------

def test_to_float_handles_nasa_strings():
    assert to_float("23.6179645803") == 23.6179645803
    assert to_float(".3163015049894188") == 0.3163015049894188
    assert to_float(12) == 12.0
    assert to_float(None) is None
    assert to_float("") is None
    assert to_float("n/a") is None


def test_parse_approach_datetime():
    assert parse_approach_datetime("2026-Oct-19 00:44") == datetime(2026, 10, 19, 0, 44)
    assert parse_approach_datetime(None) is None
    assert parse_approach_datetime("garbage") is None


def test_diameter_uses_meters_and_falls_back_to_kilometers():
    assert diameter_m({"meters": {"estimated_diameter_min": 12.5}}, "min") == 12.5
    assert diameter_m({"kilometers": {"estimated_diameter_max": 0.25}}, "max") == 250.0
    assert diameter_m({}, "min") is None
    assert diameter_m(None, "max") is None


# --- feed transform ----------------------------------------------------------------

def test_flattens_fixture_into_rows():
    result = transform_feeds([feed()])

    assert result.records_seen == 4
    assert len(result.asteroids) == 4
    assert len(result.approaches) == 4
    assert result.rejected == []
    assert result.duplicates_removed == 0


def test_asteroid_row_matches_raw_values():
    payload = feed()
    raw = first_neo(payload)
    row = next(a for a in transform_feeds([payload]).asteroids if a["neo_id"] == raw["id"])

    assert row["name"] == raw["name"]
    assert row["is_potentially_hazardous"] is raw["is_potentially_hazardous_asteroid"]
    assert row["est_diameter_min_m"] == raw["estimated_diameter"]["meters"]["estimated_diameter_min"]
    assert row["est_diameter_max_m"] == raw["estimated_diameter"]["meters"]["estimated_diameter_max"]
    assert row["absolute_magnitude_h"] == raw["absolute_magnitude_h"]


def test_approach_row_has_numeric_types():
    payload = feed()
    raw = first_neo(payload)
    raw_approach = raw["close_approach_data"][0]
    row = next(a for a in transform_feeds([payload]).approaches if a["neo_id"] == raw["id"])

    assert row["approach_date"] == date(2026, 10, 13)
    assert isinstance(row["approach_datetime"], datetime)
    assert row["epoch_ms"] == raw_approach["epoch_date_close_approach"]
    assert row["miss_distance_km"] == float(raw_approach["miss_distance"]["kilometers"])
    assert row["miss_distance_lunar"] == float(raw_approach["miss_distance"]["lunar"])
    assert row["miss_distance_au"] == float(raw_approach["miss_distance"]["astronomical"])
    assert row["relative_velocity_kps"] == float(raw_approach["relative_velocity"]["kilometers_per_second"])
    assert row["orbiting_body"] == "Earth"


def test_same_payload_twice_is_deduplicated():
    result = transform_feeds([feed(), feed()])

    assert result.records_seen == 8
    assert len(result.approaches) == 4
    assert len(result.asteroids) == 4
    assert result.duplicates_removed == 4


def test_same_asteroid_on_two_dates_gives_one_asteroid_two_approaches():
    payload = feed()
    neo = copy.deepcopy(first_neo(payload))
    neo["close_approach_data"][0]["epoch_date_close_approach"] += 86_400_000
    neo["close_approach_data"][0]["close_approach_date"] = "2026-10-14"
    payload["near_earth_objects"]["2026-10-14"].append(neo)

    result = transform_feeds([payload])

    assert len(result.asteroids) == 4
    assert len([a for a in result.approaches if a["neo_id"] == neo["id"]]) == 2


def test_rejects_records_that_cannot_be_loaded():
    payload = feed()
    neos = payload["near_earth_objects"]["2026-10-13"]
    neos[0]["close_approach_data"][0]["epoch_date_close_approach"] = None
    del neos[1]["id"]

    result = transform_feeds([payload])

    assert result.records_seen == 4
    assert len(result.approaches) == 2
    assert len(result.rejected) == 2


def test_empty_feed():
    result = transform_feeds([{"element_count": 0, "near_earth_objects": {}}])
    assert result.asteroids == [] and result.approaches == [] and result.records_seen == 0


# --- orbital transform ----------------------------------------------------------------

def test_transform_orbital_from_lookup_shape():
    neo = {"id": "3542519", "orbital_data": {
        "eccentricity": ".3163", "inclination": "42.05", "orbital_period": "270.51",
        "first_observation_date": "2009-10-15", "last_observation_date": "2009-11-09",
        "orbit_class": {"orbit_class_type": "ATE", "orbit_class_description": "Aten-like"}}}

    row = transform_orbital(neo)

    assert row == {"neo_id": "3542519", "orbit_class": "ATE", "orbit_class_description": "Aten-like",
                   "eccentricity": 0.3163, "inclination_deg": 42.05, "orbital_period_days": 270.51,
                   "first_observation_date": date(2009, 10, 15),
                   "last_observation_date": date(2009, 11, 9)}


def test_transform_orbital_without_orbit_returns_none():
    assert transform_orbital({"id": "1"}) is None


def test_transform_orbital_on_real_lookup_fixture():
    neo = json.loads((FIXTURES / "lookup_sample.json").read_text())

    row = transform_orbital(neo)

    assert row["neo_id"] == neo["id"]
    assert row["orbit_class"] == neo["orbital_data"]["orbit_class"]["orbit_class_type"]
    assert row["eccentricity"] == float(neo["orbital_data"]["eccentricity"])
    assert row["orbital_period_days"] == float(neo["orbital_data"]["orbital_period"])
    assert isinstance(row["first_observation_date"], date)
