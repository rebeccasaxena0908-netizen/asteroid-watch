# 5-minute demo script

For presenting Asteroid Watch to your teacher. Times are a guide; the "Say" lines are suggestions, so put them in your own words.

## Before the demo (10 minutes earlier)

- [ ] Open the XAMPP control panel and start **Apache** and **MySQL**.
- [ ] In a terminal, `cd ~/code/asteroid-watch`, then run:
  - [ ] `make test` (should say **96 passed**)
  - [ ] `make deploy`
  - [ ] `make check-db` (should list the tables with row counts)
- [ ] Browser tab 1: <http://localhost/asteroid-watch>. Wait until Earth turns from the plain shader planet into the photo texture.
- [ ] Browser tab 2: <http://localhost/phpmyadmin>, with database `asteroid_watch` → table `close_approaches` → **Structure** open.
- [ ] Terminal: font size up, window next to the browser.
- [ ] Close other apps (smoother 3D). No internet is needed: everything is local.
- [ ] Plan B if MySQL won't start: the screenshots in `docs/screenshots/` and the README on GitHub.

---

## 0:00 – 0:30 · Introduction

**Show:** the dashboard hero (Earth with orbiting asteroids).

**Say:** "This is Asteroid Watch, an automated data pipeline. Every day it pulls near-Earth asteroid data from NASA's API, cleans it, checks its quality, loads it into MySQL in XAMPP, and this dashboard shows it. Every number here comes from the database. These rocks are this week's 38 real close approaches; orange means NASA classifies them as potentially hazardous."

**Do:** hover a rock to show its name and distance, then drag to rotate the scene.

## 0:30 – 1:15 · Architecture

**Show:** the README architecture diagram on GitHub (or `docs/architecture.md`).

**Say:** "There are three layers. **Extract**: Python calls the NASA NeoWs feed. It only allows 7 days per request, so a year is split into 57 calls, and errors are retried with exponential backoff. Raw JSON is saved as the bronze layer. **Transform**: the JSON is nested four levels deep, and numbers come as text, so it's flattened, converted and deduplicated. **Load**: rows are upserted into MySQL. Then PHP serves JSON to this dashboard. A launchd job runs it every morning at 9."

## 1:15 – 2:15 · Live run and idempotency

**Do:** in the terminal, run `make quick-run` (a few seconds).

**Say while it runs:** "This is the daily run: yesterday to 7 days ahead. You can see the API calls, the rate limit remaining, the 8 quality checks, and the result: 0 inserted, because this data is already loaded. That's the key property: **the pipeline is idempotent**."

(If NASA has added an approach since the last run, you'll see "1 inserted" instead. Say so: "NASA published a new approach overnight, and only that one was added.")

**Show:** phpMyAdmin tab → `close_approaches` → **Structure** → Indexes → `uq_approach (neo_id, epoch_ms)`.

**Say:** "This unique key means an asteroid can't have two approaches at the same moment, and every load is an `INSERT … ON DUPLICATE KEY UPDATE`. When I re-ran the whole year, it read 1,934 records and inserted zero."

**Do:** refresh the dashboard and scroll to **Pipeline health**. The new run is at the top.

## 2:15 – 3:30 · Dashboard tour

**Do and say, in order:**
1. **Tiles:** "38 asteroids pass this week; the closest is about 20 lunar distances away. 1 LD is the distance to the Moon." Click **Largest tracked object** to open 433 Eros, then close it.
2. **Charts:** click **Full year**. "Approaches per week over the year, the hazardous share, sizes, and speed against distance on a log scale." Click a dot in the scatter to open that asteroid. "The orbit sketch is calculated from the orbital period with Kepler's third law." Close it.
3. **Table:** type `2008 TC4` in the search. "Search, filter and sort all run on the server through prepared statements."

## 3:30 – 4:30 · Data quality (the strongest part)

**Show:** **Pipeline health**. Open the latest run.

**Say:** "Every run records 8 quality checks. One fails honestly: **NASA's feed left out 4 days of the year**. I didn't hide it; I investigated it."

**Say (the duplicate story):** "While cross-checking with NASA's JPL database, I found NASA listing **the same asteroid under two IDs**, an old provisional one and its new numbered one. That was 58 duplicate listings, so hazardous approaches were overcounted by about 12%. My unique key couldn't catch it because the IDs differ. So I added a quality check, a mapping table, and a fix in the transform. I backed up the database before deleting anything. That's the `2008 TC4` I just searched for: now it's one asteroid."

**Do:** open the **JPL cross-check** run. "Against JPL, the values match almost exactly, but NeoWs only has about a quarter of the approaches JPL knows about. That's a limitation of the source, and I documented it."

## 4:30 – 5:00 · Wrap-up

**Say:** "To summarise: it's automated, idempotent, quality-checked, validated against a second NASA source, and secure. The API key is never in Git, PHP uses a read-only database user, and every query is a prepared statement. It has 96 offline tests plus API tests. Next steps would be using JPL as a second source and adding alerts. Thank you."

---

## Likely viva questions (short answers)

**Why did you split requests into 7-day chunks?**
The NeoWs feed API allows at most 7 days per request. 396 days ÷ 7, rounded up, is 57 calls.

**What is an upsert and why use it?**
`INSERT … ON DUPLICATE KEY UPDATE`: if the unique key already exists, the row is updated instead of duplicated. It makes re-runs safe (idempotent).

**How do you know how many rows were inserted vs updated?**
MySQL reports 1 affected row per insert and 2 per changed row. I count the table before and after: inserted = after − before, and updated = (affected − inserted) / 2.

**What happens if NASA is down or you hit the rate limit?**
HTTP 429 and 5xx errors are retried after 2, 4, 8 and 16 seconds, or the server's `Retry-After`. If it still fails, the run is marked `failed` in `pipeline_runs` with the error, and the next daily run tries again.

**How do you protect the API key?**
It's only in `.env`, which is gitignored and readable only by me. It's hidden from logs and removed from the saved raw files, because NASA puts it in its response links. PHP never sees it.

**How do you prevent SQL injection?**
PDO prepared statements with bound values. Things that can't be bound, like the sort column, come from a fixed whitelist. The API tests send an injection attempt, and it's treated as plain text.

**Why a separate read-only database user for PHP?**
Least privilege: even if the web layer had a bug, it couldn't change or delete data.

**Why does `make deploy` copy files instead of using a symlink?**
Apache runs as the `daemon` user, which can't read my home folder, so a symlink gave HTTP 403. I tested both.

**What are bronze, silver and gold?**
Bronze is the raw JSON as received. Silver is cleaned, typed, deduplicated rows. Gold is the MySQL tables and views the dashboard reads.

**Why log scales in the charts and the 3D scene?**
Miss distances range from 0.36 to about 195 lunar distances. On a linear scale, almost everything would be squeezed into one corner.

**What does "potentially hazardous" mean?**
NASA's classification: larger than about 140 m, and an orbit that comes within 0.05 AU of Earth's. It's not a prediction of impact.

**How did you decide which of the two IDs to keep?**
The numbered ID is the asteroid's current official identity, and JPL itself redirects the old ID to it. My rule only acts when exactly one of the IDs is numbered; otherwise it reports the case instead of guessing.

**How is the data checked for quality?**
8 checks per run: no missing keys, distance and speed > 0, minimum size ≤ maximum, every requested day returned, record count = NASA's `element_count`, no duplicate keys, and no asteroid under two IDs. There's also a separate cross-check against NASA JPL.

**What would you do with more time?**
Use JPL as a second source to fill NeoWs's gaps, add alerts for close hazardous approaches and failed runs, and move to Docker with Airflow scheduling.
