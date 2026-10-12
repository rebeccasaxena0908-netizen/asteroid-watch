# Asteroid Watch

An automated data pipeline that tracks near-Earth asteroids using NASA's NeoWs API, loads them into MySQL (XAMPP), and shows them on an animated space-themed dashboard.

> Work in progress. Full documentation comes in Phase 7. See `PROGRESS.md`.

## Quick start (so far)

```bash
make install                 # Python venv + packages
cp .env.example .env         # then set DB_PASSWORD and NASA_API_KEY
make setup-db                # creates database, user, tables, views (XAMPP MySQL must be running)
make check-db
make test
make deploy                  # then open http://localhost/asteroid-watch
```

Data source: [NASA NeoWs](https://api.nasa.gov/).
