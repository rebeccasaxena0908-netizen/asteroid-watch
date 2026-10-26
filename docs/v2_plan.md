# Asteroid Watch v2: plan

v2 grows the v1 pipeline (NeoWs → MySQL → PHP → dashboard) into a Python-only NASA near-Earth data platform. Work happens on the `v2` branch, one phase at a time. `main` stays the submitted v1 until v2 is finished.

## Baseline (Phase 0, 2026-10-27)

| | Value |
|---|---|
| Tests | 96 offline unit tests and 10 API tests, all passing |
| Tables | 1,627 asteroids, 1,876 close approaches, 1,078 orbits, 57 ID aliases, 21 pipeline runs, 121 quality results |
| Last run | Run 21 (`make quick-run`), 2026-10-27 00:54: 2 API calls, 3.0 s, 0 inserted and 3 updated, 8/8 checks passed |
| Machine | MacBook Air M2, 8 GB RAM, 30 GB disk free (85% used) |

## Phase order

0 → 1 → 2 → 3 → 4 → 5 → 7 → 8 → 9 → 6 → 10 → 11 → 12 → 13

- **Phase 6 ("Space today": DONKI, EONET, APOD) comes after Phase 9.** It doesn't depend on anything else and is the least central to the asteroid story.
- **Phases 7–9 build on Phase 5.** The real orbits need full orbital elements from SBDB, and the discovery statistics need discovery dates.

## Decisions

- **Phase 4:** one cached download of JPL's full near-Earth asteroid list, so JPL-only approaches get a size estimate and NASA's hazard flag. Per-asteroid SBDB details stay in Phase 5.
- **Phase 8:** models are trained and tested on the full JPL near-Earth catalogue, with scores also reported separately for the asteroids in our own database. The hazard classifier comes in two versions, with and without the features NASA's definition uses (H and MOID).
- **Phase 10:** a third database user, `asteroid_app`, can write only to the users, watchlist, api_keys and api_usage tables. All data reads stay on the read-only `asteroid_reader`.
- **Phase 11:** the local model is chosen just before the phase. The suggestion is `qwen2.5-coder:3b`, with `1.5b` as the fallback.

## Memory and disk per phase (estimates)

These are estimates, made before building each part. Each phase's progress notes will record the measured values.

| Phase | RAM while running | Disk added |
|---|---|---|
| 0 Tooling (pyproject, ruff, mypy, pre-commit, CI) | < 300 MB | ~100 MB |
| 1 SQLAlchemy, Alembic, Typer CLI | ~150 MB | ~30 MB |
| 2 FastAPI (1 uvicorn worker, always on) | ~120 MB | ~50 MB |
| 3 Prefect 3 server + worker (always on) | ~500–700 MB | ~400 MB, plus a SQLite file that grows ~100–200 MB a year |
| 4 JPL CAD, merge, century table | < 300 MB (loaded one year at a time) | Year table < 10 MB; century table about 50–500 MB, depending on the distance limit (measured first) |
| 5 Sentry, Fireball, Scout, NHATS, SBDB | < 300 MB | ~100 MB, plus Scout's 30-minute raw files (~1 GB a year without a retention rule) |
| 7 Science (numpy, skyfield + 17 MB ephemeris) | < 300 MB | ~50 MB |
| 8 Data science and ML (Jupyter kernel) | ~400–700 MB | ~700 MB |
| 9 Streamlit + Plotly | ~250 MB while open | ~200 MB |
| 6 DONKI, EONET, APOD (image URLs, not files) | < 200 MB | < 50 MB |
| 10 Accounts, API keys, Discord, Tkinter, Hindi | < 200 MB | ~30 MB |
| 11 Local LLM via Ollama (loaded only while in use) | ~1.5–3 GB | ~1–2 GB |
| 12 Teaching mode, PDFs (made on request), widgets | < 200 MB | ~20 MB |

With everything running together (MariaDB, API, Prefect, Streamlit), RAM use is about 1.5 GB. It rises to about 4 GB while the language model is in use. No single part goes over the 3 GB budget.

## Final folder structure

```
asteroid-watch-py/
├── pyproject.toml          dependencies and tool settings (requirements.txt is generated from it)
├── Makefile                short commands; from Phase 1 they call the CLI
├── .github/workflows/      CI: lint, type check, offline tests on every push
├── pipeline/               ETL (v1 NeoWs code, kept)
│   ├── cli.py              Typer CLI `asteroid-watch` (Phase 1)
│   ├── models.py           SQLAlchemy models (Phase 1)
│   ├── merge.py            NeoWs + JPL entity resolution (Phase 4)
│   └── sources/            one module per new source: jpl_cad, nea_catalog, sentry, fireball,
│                           scout, nhats, sbdb, donki, eonet, apod (each: extract, transform, load, checks)
├── migrations/             Alembic: every schema change from Phase 1 on
├── flows/                  Prefect flows and deployments (Phase 3)
├── api/                    FastAPI: endpoints, Pydantic schemas, exports, auth, widgets (Phases 2, 10, 12)
├── science/                impact energy, size from brightness, visibility, orbits (Phase 7)
├── ml/                     features, training, evaluation; saved models go in ml/models/ (gitignored)
├── notebooks/              01_eda.ipynb (Phase 8)
├── streamlit_app/          pure-Python dashboard (Phase 9)
├── dashboard/              the web dashboard, served by FastAPI from Phase 2; i18n/ en + hi (Phase 10)
├── desktop/                Tkinter app (Phase 10)
├── bots/                   Discord bot (Phase 10, only if a token is provided)
├── legacy/php/             the retired PHP API (moved in Phase 2, not deleted)
├── sql/                    v1 schema files (Alembic owns changes after Phase 1)
├── scheduler/              launchd templates: pipeline (until Prefect takes over), API, Prefect worker
├── scripts/                development tools: requirements generator, secret scan
├── tests/                  unit tests, fixtures/, integration/, parity/ (PHP vs FastAPI)
└── docs/                   one "how it works" page per module, data_sources.md
```

Keeping `pipeline/` as it is means the v1 code explained in the report stays where it was. New sources go in `pipeline/sources/` and follow the same extract → transform → load → checks pattern.
