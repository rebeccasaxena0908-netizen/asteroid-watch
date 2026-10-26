"""One-off cleanup: merge asteroids stored under an old provisional neo_id into their numbered neo_id.

Same rule as transform.merge_aliases, applied to what's already in the database:
- an old id is an alias when its designation also exists under exactly one numbered id
  (e.g. 3430309 "(2008 TC4)" -> 2614134 "614134 (2008 TC4)");
- an old-id approach within an hour of a numbered-id approach is the same event -> deleted;
- any other old-id approach is moved to the numbered id;
- the then-empty old asteroid is deleted (its orbital_data row goes with it: ON DELETE CASCADE);
- the mapping is saved in neo_id_aliases so future runs store the old id under the numbered id.

Back up first:  mysqldump -u root --single-transaction asteroid_watch > backups/<name>.sql
Usage:
    python -m pipeline.cleanup_twins                      # preview only: prints exact rows, changes nothing
    python -m pipeline.cleanup_twins --apply --expect 57,1,56 [--skip OLD_ID ...]
        --expect DELETED,MOVED,ASTEROIDS refuses to apply unless the counts match what was approved.
"""
import argparse

from pipeline.db import connect
from pipeline.transform import SAME_EVENT_MS, designation, find_aliases


def plan(cur, skip: set[str]) -> dict:
    cur.execute("SELECT neo_id, name FROM asteroids")
    asteroids = cur.fetchall()
    names = {a["neo_id"]: a["name"] for a in asteroids}
    aliases = {old: new for old, new in find_aliases(asteroids).items() if old not in skip}

    cur.execute("SELECT ca.id, ca.neo_id, a.is_potentially_hazardous, ca.approach_date, ca.epoch_ms, "
                "ca.miss_distance_km FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id")
    approaches = cur.fetchall()
    numbered_rows: dict[str, list[dict]] = {}
    for r in approaches:
        numbered_rows.setdefault(r["neo_id"], []).append(r)

    delete, move = [], []
    for r in approaches:
        if r["neo_id"] not in aliases:
            continue
        target = aliases[r["neo_id"]]
        twin = next((n for n in numbered_rows.get(target, [])
                     if abs(n["epoch_ms"] - r["epoch_ms"]) <= SAME_EVENT_MS), None)
        row = {**r, "name": names[r["neo_id"]], "target": target, "target_name": names[target]}
        if twin:
            delete.append({**row, "twin_miss_km": twin["miss_distance_km"]})
        else:
            move.append(row)

    old_ids = sorted(aliases)
    orbits = set()
    if old_ids:
        cur.execute(f"SELECT neo_id FROM orbital_data WHERE neo_id IN ({', '.join(['%s'] * len(old_ids))})", old_ids)
        orbits = {r["neo_id"] for r in cur.fetchall()}
    def key(r):
        return (r["approach_date"], r["neo_id"])

    return {"aliases": aliases, "names": names, "orbits": orbits,
            "delete": sorted(delete, key=key), "move": sorted(move, key=key)}


def print_preview(p: dict) -> None:
    d, m = p["delete"], p["move"]
    print(f"close_approaches rows to DELETE (same event under the numbered id): {len(d)} "
          f"({sum(r['is_potentially_hazardous'] for r in d)} hazardous)")
    print(f"{'id':>5}  {'old id':<9} {'name':<20} {'date':<10}  {'miss_km':>14}  kept under")
    for r in d:
        print(f"{r['id']:>5}  {r['neo_id']:<9} {r['name']:<20} {r['approach_date']!s:<10}  "
              f"{r['miss_distance_km']:>14,.1f}  {r['target']} {r['target_name']} ({r['twin_miss_km']:,.1f} km)")
    print(f"\nclose_approaches rows to MOVE to the numbered id: {len(m)}")
    for r in m:
        print(f"{r['id']:>5}  {r['neo_id']:<9} {r['name']:<20} {r['approach_date']!s:<10}  "
              f"{r['miss_distance_km']:>14,.1f}  -> {r['target']} {r['target_name']}")
    print(f"\nasteroids rows to DELETE (old ids): {len(p['aliases'])}, of which {len(p['orbits'])} "
          f"also lose their orbital_data row (cascade)")
    print(f"neo_id_aliases rows to INSERT: {len(p['aliases'])}")


def apply(conn, p: dict) -> None:
    def ids_sql(values):
        return ", ".join(["%s"] * len(values))

    try:
        with conn.cursor() as cur:
            # Aliases first: they reference the numbered asteroids, which stay.
            cur.executemany("INSERT IGNORE INTO neo_id_aliases (old_neo_id, numbered_neo_id, designation) "
                            "VALUES (%s, %s, %s)",
                            [(old, new, designation(p["names"][old])) for old, new in p["aliases"].items()])
            print(f"Inserted {cur.rowcount} neo_id_aliases rows")
            if p["delete"]:
                ids = [r["id"] for r in p["delete"]]
                cur.execute(f"DELETE FROM close_approaches WHERE id IN ({ids_sql(ids)})", ids)
                print(f"Deleted {cur.rowcount} close_approaches rows")
            moved = 0
            for r in p["move"]:
                cur.execute("UPDATE close_approaches SET neo_id = %s WHERE id = %s", (r["target"], r["id"]))
                moved += cur.rowcount
            print(f"Moved {moved} close_approaches rows")
            old_ids = sorted(p["aliases"])
            if old_ids:
                cur.execute(f"DELETE FROM asteroids WHERE neo_id IN ({ids_sql(old_ids)})", old_ids)
                print(f"Deleted {cur.rowcount} asteroids rows (and their orbital_data rows)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge old provisional neo_ids into numbered neo_ids")
    parser.add_argument("--apply", action="store_true", help="make the changes (default: preview only)")
    parser.add_argument("--expect", help="DELETED,MOVED,ASTEROIDS counts that must match before applying")
    parser.add_argument("--skip", nargs="*", default=[], help="old neo_ids to leave alone")
    args = parser.parse_args()
    with connect() as conn:
        with conn.cursor() as cur:
            p = plan(cur, set(args.skip))
        print_preview(p)
        if args.skip:
            print(f"Skipped (left unchanged): {', '.join(args.skip)}")
        if not args.apply:
            print("\nPreview only. Nothing was changed. Run with --apply --expect D,M,A to apply.")
            return
        actual = f"{len(p['delete'])},{len(p['move'])},{len(p['aliases'])}"
        if args.expect != actual:
            raise SystemExit(f"Refusing to apply: counts are {actual}, expected {args.expect}")
        apply(conn, p)


if __name__ == "__main__":
    main()
