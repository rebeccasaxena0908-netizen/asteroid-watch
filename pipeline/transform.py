"""Transform: turn nested NeoWs JSON into flat, typed rows (the "silver" layer).

Feed JSON shape:
    near_earth_objects -> { "2026-10-13": [ asteroid, ... ], ... }
    asteroid -> estimated_diameter, close_approach_data: [ approach, ... ]

Output:
    asteroids  : one dict per asteroid (deduplicated by neo_id)
    approaches : one dict per close approach (deduplicated by (neo_id, epoch_ms))

NASA sends most numbers as strings ("23.6179645803"), so every number is converted.
Records that cannot be loaded at all (no id, no date, no epoch) are rejected and counted.
"""
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class TransformResult:
    asteroids: list[dict] = field(default_factory=list)
    approaches: list[dict] = field(default_factory=list)
    records_seen: int = 0                                  # approach records in the raw JSON
    duplicates_removed: int = 0
    rejected: list[str] = field(default_factory=list)      # human-readable reasons


def to_float(value) -> float | None:
    """'23.61' -> 23.61, '.3163' -> 0.3163, None/''/'abc' -> None."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_date(value) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def parse_approach_datetime(value) -> datetime | None:
    """NeoWs format: '2026-Oct-19 00:44'."""
    try:
        return datetime.strptime(value, "%Y-%b-%d %H:%M")
    except (TypeError, ValueError):
        return None


def diameter_m(estimated_diameter: dict, bound: str) -> float | None:
    """Estimated diameter in meters. bound is 'min' or 'max'.

    Uses the 'meters' figures; falls back to kilometers x 1000 if meters are missing.
    """
    key = f"estimated_diameter_{bound}"
    meters = to_float((estimated_diameter or {}).get("meters", {}).get(key))
    if meters is not None:
        return meters
    km = to_float((estimated_diameter or {}).get("kilometers", {}).get(key))
    return km * 1000 if km is not None else None


def transform_asteroid(neo: dict) -> dict:
    diameters = neo.get("estimated_diameter")
    return {
        "neo_id": str(neo["id"]),
        "name": neo.get("name") or str(neo["id"]),
        "nasa_jpl_url": neo.get("nasa_jpl_url"),
        "absolute_magnitude_h": to_float(neo.get("absolute_magnitude_h")),
        "est_diameter_min_m": diameter_m(diameters, "min"),
        "est_diameter_max_m": diameter_m(diameters, "max"),
        "is_potentially_hazardous": bool(neo.get("is_potentially_hazardous_asteroid")),
        "is_sentry_object": bool(neo.get("is_sentry_object")),
    }


def transform_approach(neo_id: str, approach: dict) -> dict:
    velocity = approach.get("relative_velocity") or {}
    distance = approach.get("miss_distance") or {}
    epoch = approach.get("epoch_date_close_approach")
    return {
        "neo_id": neo_id,
        "approach_date": to_date(approach.get("close_approach_date")),
        "approach_datetime": parse_approach_datetime(approach.get("close_approach_date_full")),
        "epoch_ms": int(epoch) if epoch is not None else None,
        "relative_velocity_kps": to_float(velocity.get("kilometers_per_second")),
        "relative_velocity_kph": to_float(velocity.get("kilometers_per_hour")),
        "miss_distance_km": to_float(distance.get("kilometers")),
        "miss_distance_lunar": to_float(distance.get("lunar")),
        "miss_distance_au": to_float(distance.get("astronomical")),
        "orbiting_body": approach.get("orbiting_body") or "Earth",
    }


def transform_feeds(payloads: list[dict]) -> TransformResult:
    result = TransformResult()
    asteroids: dict[str, dict] = {}
    approaches: dict[tuple, dict] = {}

    for payload in payloads:
        for feed_date, neos in payload.get("near_earth_objects", {}).items():
            for neo in neos:
                if not neo.get("id"):
                    result.rejected.append(f"asteroid without id on {feed_date}")
                    result.records_seen += len(neo.get("close_approach_data", []))
                    continue
                asteroid = transform_asteroid(neo)
                asteroids[asteroid["neo_id"]] = asteroid   # same id later = same asteroid

                for raw in neo.get("close_approach_data", []):
                    result.records_seen += 1
                    row = transform_approach(asteroid["neo_id"], raw)
                    if row["approach_date"] is None or row["epoch_ms"] is None:
                        result.rejected.append(f"approach without date/epoch for {row['neo_id']}")
                        continue
                    key = (row["neo_id"], row["epoch_ms"])
                    if key in approaches:
                        result.duplicates_removed += 1
                    approaches[key] = row

    result.asteroids = list(asteroids.values())
    result.approaches = list(approaches.values())
    return result


def transform_orbital(neo: dict) -> dict | None:
    """Lookup API response -> one orbital_data row (None if it has no orbital data)."""
    orbit = neo.get("orbital_data")
    if not orbit or not neo.get("id"):
        return None
    orbit_class = orbit.get("orbit_class") or {}
    return {
        "neo_id": str(neo["id"]),
        "orbit_class": orbit_class.get("orbit_class_type"),
        "orbit_class_description": orbit_class.get("orbit_class_description"),
        "eccentricity": to_float(orbit.get("eccentricity")),
        "inclination_deg": to_float(orbit.get("inclination")),
        "orbital_period_days": to_float(orbit.get("orbital_period")),
        "first_observation_date": to_date(orbit.get("first_observation_date")),
        "last_observation_date": to_date(orbit.get("last_observation_date")),
    }
