"""Transform: turn nested NeoWs JSON into flat, typed rows (the "silver" layer).

Feed JSON shape:
    near_earth_objects -> { "2026-10-13": [ asteroid, ... ], ... }
    asteroid -> estimated_diameter, close_approach_data: [ approach, ... ]

Output:
    asteroids  : one dict per asteroid (deduplicated by neo_id)
    approaches : one dict per close approach (deduplicated by (neo_id, epoch_ms))

NASA sends most numbers as strings ("23.6179645803"), so every number is converted.
Records that cannot be loaded at all (no id, no date, no epoch) are rejected and counted.
When one asteroid appears under two neo_ids (old provisional + numbered), everything is stored
under the numbered id (see merge_aliases).
"""
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class TransformResult:
    asteroids: list[dict] = field(default_factory=list)
    approaches: list[dict] = field(default_factory=list)
    records_seen: int = 0                                  # approach records in the raw JSON
    duplicates_removed: int = 0
    same_object_removed: int = 0                           # old-id copies of an approach dropped
    same_object_remapped: int = 0                          # old-id approaches moved to the numbered id
    new_aliases: list[dict] = field(default_factory=list)  # old id -> numbered id found in this batch
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


def diameter_m(estimated_diameter: dict | None, bound: str) -> float | None:
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


def transform_feeds(payloads: list[dict], known_aliases: dict[str, str] | None = None) -> TransformResult:
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
    merge_aliases(result, known_aliases or {})
    return result


def designation(name: str) -> str:
    """Text in the last brackets: '614134 (2008 TC4)' -> '2008 TC4'; '(2008 TC4)' -> '2008 TC4'."""
    if "(" not in name:
        return name.strip()
    return name.rsplit("(", 1)[1].split(")", 1)[0].strip()


def is_numbered(name: str) -> bool:
    """Numbered asteroids have their number first ('614134 (2008 TC4)', '433 Eros (A898 PA)');
    provisional-only names start with the bracket ('(2008 TC4)')."""
    return name[:1].isdigit()


SAME_EVENT_MS = 60 * 60 * 1000   # two listings of one approach are at most minutes apart


def find_aliases(asteroids: list[dict]) -> dict[str, str]:
    """Old provisional neo_id -> numbered neo_id, for designations listed under 2+ neo_ids.

    Only when exactly one of them is numbered; otherwise we don't guess.
    """
    by_designation: dict[str, list[dict]] = {}
    for a in asteroids:
        by_designation.setdefault(designation(a["name"]), []).append(a)
    aliases = {}
    for group in by_designation.values():
        numbered = [a for a in group if is_numbered(a["name"])]
        if len(group) < 2 or len(numbered) != 1:
            continue
        for a in group:
            if a["neo_id"] != numbered[0]["neo_id"]:
                aliases[a["neo_id"]] = numbered[0]["neo_id"]
    return aliases


def merge_aliases(result: TransformResult, known_aliases: dict[str, str]) -> None:
    """NeoWs sometimes lists one asteroid under two neo_ids: its old provisional id and its newer
    numbered id (e.g. 3430309 '(2008 TC4)' and 2614134 '614134 (2008 TC4)').

    Approaches of an old id are stored under the numbered id. If the numbered id already has an
    approach within an hour (the same event listed twice), the old id's copy is dropped.
    Aliases come from this batch (both ids present) and from earlier runs (known_aliases, from
    the neo_id_aliases table), so an old id appearing on its own is handled too.
    """
    names = {a["neo_id"]: a["name"] for a in result.asteroids}
    batch_aliases = find_aliases(result.asteroids)
    aliases = {**known_aliases, **batch_aliases}
    result.new_aliases = [{"old_neo_id": old, "numbered_neo_id": new, "designation": designation(names[old])}
                          for old, new in batch_aliases.items() if known_aliases.get(old) != new]
    if not aliases:
        return

    kept = [r for r in result.approaches if r["neo_id"] not in aliases]
    epochs: dict[str, list[int]] = {}
    for r in kept:
        epochs.setdefault(r["neo_id"], []).append(r["epoch_ms"])
    for r in result.approaches:
        if r["neo_id"] not in aliases:
            continue
        target = aliases[r["neo_id"]]
        if any(abs(e - r["epoch_ms"]) <= SAME_EVENT_MS for e in epochs.get(target, [])):
            result.same_object_removed += 1
            continue
        kept.append({**r, "neo_id": target})
        epochs.setdefault(target, []).append(r["epoch_ms"])
        result.same_object_remapped += 1

    result.approaches = kept
    result.asteroids = [a for a in result.asteroids if a["neo_id"] not in aliases]


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
