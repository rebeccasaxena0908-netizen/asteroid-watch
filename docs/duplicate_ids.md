# Data quality issue: the same asteroid under two IDs

**Found:** 2026-10-12, while preparing the JPL cross-check (Phase 4).
**Status:** fixed in the pipeline and fully cleaned in the database. The quality check passes, with 0 duplicates.

## 1. The problem

NASA's NeoWs feed sometimes lists **one physical asteroid twice, under two different `neo_id`s**:

| neo_id | Name in NeoWs | Kind of ID |
|---|---|---|
| `3430309` | `(2008 TC4)` | old provisional ID (from before the asteroid was numbered) |
| `2614134` | `614134 (2008 TC4)` | current ID (2,000,000 + its official number 614134) |

Both rows describe the same close approach on 2026-10-17 at the same moment. Their miss distances are 45,552,721.06 km and 45,552,721.16 km.

### How it was found

The JPL Close-Approach Data API is queried by SPK-ID, the same number NeoWs uses as `neo_id`. Asking JPL for `3430309` returned the object **614134**. JPL had already redirected the old ID to the numbered asteroid. A database search for designations stored under more than one `neo_id` then found the rest.

### Why our existing checks missed it

`close_approaches` has `UNIQUE(neo_id, epoch_ms)`, which stops the *same* ID being loaded twice. Here the two rows have *different* `neo_id`s, so the database accepted both.

### Size of the problem (backfill 2025-10-12 to 2026-11-11)

- **57 approaches stored twice**, 25 of them potentially hazardous.
- **56 old IDs** involved, mostly of the form `3xxxxxx` and some `54xxxxxx`. A rule based on the first digit would have been unreliable, so the fix uses the **name** instead: numbered asteroids' names start with their number.
- **Distances:** across the 57 pairs, 18 were identical to 0.1 km, the median difference was 1.3 km, and the largest was 86.9 km, for (2018 LC3). The approach times were identical. Small distance differences like these suggest the two IDs were computed from slightly different orbit solutions.
- **(2017 AE5)**: the old ID also had an approach on **2026-07-04** that NeoWs did **not** list under the numbered ID.
- **(2022 OP)**: the same approach under two IDs, but the two times are **1 minute apart** (06:29 vs 06:30), so an exact-time match misses it.

**Effect on results:** the dashboard would have overcounted. Hazardous approaches would have read 213 instead of 188, about 12% too high.

## 2. The fix

### Rule

> If a designation (the text in brackets, e.g. `2008 TC4`) appears under several `neo_id`s and **exactly one** of them is numbered, the other IDs are **aliases** of the numbered one.
> Approaches of an alias are stored under the numbered ID. If the numbered ID already has an approach **within 60 minutes**, it is the same event listed twice, and the alias's copy is dropped.

- **Why keep the numbered ID?** It's the asteroid's current official identity. JPL itself maps the old ID to it.
- **Why 60 minutes?** Two listings of one event differ by at most a minute in our data. A genuine second approach of the same object is days or months apart.
- **What if a group doesn't have exactly one numbered ID?** The rule does nothing and leaves it to the quality check to report. It doesn't guess.

### Where it is implemented

| Part | File | What it does |
|---|---|---|
| Transform | `pipeline/transform.py`: `find_aliases`, `merge_aliases` | Applies the rule to every batch before loading |
| Alias table | `sql/01_schema.sql`: `neo_id_aliases` | Remembers old ID → numbered ID, so an old ID that later appears **on its own** (like the 2017 AE5 July approach) is still stored under the numbered ID |
| Load | `pipeline/load.py`: `load_known_aliases`, `save_aliases` | Reads known aliases before the transform, and saves new ones in the same transaction as the data |
| Quality check | `pipeline/quality.py`: `no_same_object_under_two_ids` | Table-wide check: one designation with approaches under two IDs within an hour |
| One-off cleanup | `pipeline/cleanup_twins.py` | Applies the same rule to rows already in the database |
| Tests | `tests/test_transform.py`, `tests/fixtures/feed_twins.json` | Uses the real 2026-10-17 feed containing both (2008 TC4) IDs. Covers twins, the 1-minute case, the moved approach, known aliases, and the "don't guess" case |

## 3. Cleaning the existing data

1. **Backup:** `mysqldump -u root --single-transaction --triggers asteroid_watch > backups/asteroid_watch_2026-10-12_before_twin_cleanup.sql`. I checked it by restoring it into a temporary database, where all 5 table counts matched. (`--routines` was left off: XAMPP's system tables are out of date, which makes that option fail, and the project has no stored routines.)
2. **Preview:** `python -m pipeline.cleanup_twins` printed every row to be changed. Nothing was modified.
3. **Approval:** the row list was reviewed and approved before anything was deleted.
4. **Apply with a guard:** `python -m pipeline.cleanup_twins --apply --expect 57,1,56 --skip 54290860`. The script refuses to run if the counts differ from the approved ones. Everything runs in one transaction.

### Result

| | Before | After | Change |
|---|---|---|---|
| asteroids | 1,684 | 1,628 | −56 |
| potentially hazardous asteroids | 201 | 176 | −25 |
| close_approaches | 1,934 | 1,877 | −57 |
| hazardous approaches | 213 | 188 | −25 |
| orbital_data | 605 | 578 | −27 (deleted along with their asteroids) |
| neo_id_aliases | 0 | 56 | +56 |

- 57 duplicate approaches deleted. Each one still exists under its numbered ID, so no approach was lost.
- 1 approach moved: (2017 AE5), 2026-07-04, from `3766360` to `2755140`. The numbered asteroid now has both of its approaches (2026-03-08 and 2026-07-04).
- 56 old-ID asteroid rows deleted.

### Quality checks after the fix (pipeline run 7, full backfill range)

The pipeline re-read all 1,934 records from NASA. The transform removed 58 alias copies and moved 1 approach, and the load inserted 0 rows and updated 0, so the fix works on live data without re-creating duplicates.

| Check | Before | After |
|---|---|---|
| `no_same_object_under_two_ids` | FAIL: 57 (58 with the 60-minute tolerance) | FAIL: **1**, the skipped (2022 OP); see section 4 |
| all other checks | unchanged | unchanged (`expected_days_fetched` still fails on the 4 days missing from the feed; see `docs/jpl_crosscheck.md`) |

## 4. Second cleanup: (2022 OP)

(2022 OP) was found only after the 60-minute tolerance was added. Its two listings are 1 minute apart. It wasn't in the first approved list, so the first cleanup skipped it, and it was approved separately afterwards.

1. **Fresh backup:** `backups/asteroid_watch_2026-10-12_before_2022OP_cleanup.sql`, checked by a test restore. All 6 table counts matched.
2. **Preview:** exactly 1 row. Approach 355 (old ID `54290860`, 2025-12-08 06:29, 23,622,650.0 km) is the same event as approach 356 under `2847304` "847304 (2022 OP)" (06:30, 23,622,502.7 km).
3. **Apply:** `python -m pipeline.cleanup_twins --apply --expect 1,0,1`.

| | Before | After |
|---|---|---|
| asteroids | 1,628 | 1,627 |
| close_approaches | 1,877 | 1,876 |
| orbital_data | 578 | 578 (the old ID had no orbit row) |
| neo_id_aliases | 57 | 57 (the mapping was already recorded by run 7) |

**Quality checks after the second cleanup (pipeline run 8, full backfill range):** `no_same_object_under_two_ids` **PASS, 0 approaches under two IDs**. Run 8 again inserted and updated 0 rows: the transform dropped the 58 alias copies and moved 1 approach, as in run 7. The only failing check is `expected_days_fetched` (4 dates NeoWs leaves out; see `jpl_crosscheck.md`).

## Overall result

| | Original | Final |
|---|---|---|
| asteroids | 1,684 | **1,627** |
| close_approaches | 1,934 | **1,876** |
| hazardous approaches | 213 | **188** |
| approaches stored under two IDs | 58 | **0** |

## Limitations

- If an old ID is loaded on a day when its numbered twin isn't in the feed, and the alias isn't known yet, the old row goes in under the old ID. The quality check reports it, and `cleanup_twins` (preview first) fixes it.
