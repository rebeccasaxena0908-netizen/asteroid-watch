"""Load: upsert clean rows into MySQL.

"Upsert" = INSERT ... ON DUPLICATE KEY UPDATE. A row whose primary/unique key already
exists is updated instead of inserted, so re-running the pipeline never creates duplicates
(close_approaches has UNIQUE(neo_id, epoch_ms)).

Counting inserts vs updates: for ON DUPLICATE KEY UPDATE, MySQL reports
    affected rows = 1 per new row + 2 per existing row whose values changed (+ 0 if unchanged).
We count the table before and after, so
    inserted = after - before
    updated  = (affected - inserted) / 2
"""
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

BATCH_SIZE = 500

ASTEROID_COLUMNS = ["neo_id", "name", "nasa_jpl_url", "absolute_magnitude_h", "est_diameter_min_m",
                    "est_diameter_max_m", "is_potentially_hazardous", "is_sentry_object"]

APPROACH_COLUMNS = ["neo_id", "approach_date", "approach_datetime", "epoch_ms", "relative_velocity_kps",
                    "relative_velocity_kph", "miss_distance_km", "miss_distance_lunar", "miss_distance_au",
                    "orbiting_body"]

ORBITAL_COLUMNS = ["neo_id", "orbit_class", "orbit_class_description", "eccentricity", "inclination_deg",
                   "orbital_period_days", "first_observation_date", "last_observation_date"]


@dataclass
class LoadCounts:
    inserted: int = 0
    updated: int = 0


def upsert_sql(table: str, columns: list[str], key_columns: list[str], extra_updates: str = "") -> str:
    """Build: INSERT INTO t (a, b) VALUES (%s, %s) ON DUPLICATE KEY UPDATE b = VALUES(b)"""
    placeholders = ", ".join(["%s"] * len(columns))
    updates = [f"{c} = VALUES({c})" for c in columns if c not in key_columns]
    if extra_updates:
        updates.append(extra_updates)
    return (f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {', '.join(updates)}")


def split_counts(rows_before: int, rows_after: int, affected: int) -> LoadCounts:
    inserted = rows_after - rows_before
    return LoadCounts(inserted=inserted, updated=(affected - inserted) // 2)


def count_rows(cur, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
    return cur.fetchone()["n"]


def upsert_rows(cur, table: str, columns: list[str], key_columns: list[str], rows: list[dict],
                extra_updates: str = "") -> LoadCounts:
    if not rows:
        return LoadCounts()
    sql = upsert_sql(table, columns, key_columns, extra_updates)
    before = count_rows(cur, table)
    affected = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = [tuple(row[c] for c in columns) for row in rows[i:i + BATCH_SIZE]]
        affected += cur.executemany(sql, batch)
    return split_counts(before, count_rows(cur, table), affected)


def load_known_aliases(conn) -> dict[str, str]:
    """Old provisional neo_id -> numbered neo_id, from earlier runs (see transform.merge_aliases)."""
    with conn.cursor() as cur:
        cur.execute("SELECT old_neo_id, numbered_neo_id FROM neo_id_aliases")
        return {r["old_neo_id"]: r["numbered_neo_id"] for r in cur.fetchall()}


def save_aliases(cur, aliases: list[dict]) -> None:
    if aliases:
        cur.executemany("INSERT IGNORE INTO neo_id_aliases (old_neo_id, numbered_neo_id, designation) "
                        "VALUES (%s, %s, %s)",
                        [(a["old_neo_id"], a["numbered_neo_id"], a["designation"]) for a in aliases])
        log.info("neo_id_aliases: %d new old-id -> numbered-id mappings", len(aliases))


def load_feed_rows(conn, asteroids: list[dict], approaches: list[dict],
                   aliases: list[dict] | None = None) -> dict[str, LoadCounts]:
    """Upsert asteroids, then approaches, then new aliases, in one transaction
    (approaches and aliases reference asteroids)."""
    try:
        with conn.cursor() as cur:
            counts = {
                "asteroids": upsert_rows(cur, "asteroids", ASTEROID_COLUMNS, ["neo_id"], asteroids),
                "close_approaches": upsert_rows(cur, "close_approaches", APPROACH_COLUMNS,
                                                ["neo_id", "epoch_ms"], approaches),
            }
            save_aliases(cur, aliases or [])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    for table, c in counts.items():
        log.info("%s: %d inserted, %d updated", table, c.inserted, c.updated)
    return counts


# --- orbital data (cached NeoWs Lookup calls) ---------------------------------------

ORBITAL_STALE_DAYS = 30


def asteroids_needing_orbits(conn, limit: int) -> list[str]:
    """Asteroids with no orbital data, or data older than 30 days.

    Hazardous asteroids first, then those with the latest (upcoming) approaches,
    so the most interesting ones are fetched first when the per-run limit applies.
    """
    sql = """
        SELECT a.neo_id
        FROM asteroids a
        LEFT JOIN orbital_data o ON o.neo_id = a.neo_id
        LEFT JOIN close_approaches ca ON ca.neo_id = a.neo_id
        WHERE o.neo_id IS NULL OR o.fetched_at < NOW() - INTERVAL %s DAY
        GROUP BY a.neo_id, a.is_potentially_hazardous
        ORDER BY a.is_potentially_hazardous DESC, MAX(ca.approach_date) DESC
        LIMIT %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (ORBITAL_STALE_DAYS, limit))
        return [row["neo_id"] for row in cur.fetchall()]


def load_orbital_rows(conn, rows: list[dict]) -> LoadCounts:
    try:
        with conn.cursor() as cur:
            # Always bump fetched_at, even if the orbit is unchanged, so it isn't refetched tomorrow.
            counts = upsert_rows(cur, "orbital_data", ORBITAL_COLUMNS, ["neo_id"], rows,
                                 extra_updates="fetched_at = NOW()")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    log.info("orbital_data: %d inserted, %d refreshed", counts.inserted, counts.updated)
    return counts
