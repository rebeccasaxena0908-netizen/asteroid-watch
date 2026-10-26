# Legacy PHP API (v1)

The v1 JSON API (PHP 8.2 + PDO on XAMPP Apache). It was **retired in v2 Phase 2**, when the FastAPI API in `api/` replaced it. It's kept here, unchanged, as a reference and for the parity tests.

- `api/*.php`: the five endpoints (`summary`, `approaches`, `asteroid`, `trends`, `runs`)
- `includes/`: the PDO connection (read-only user) and the validation helpers; blocked from the web by `.htaccess`
- `index.php`: the v1 dashboard shell. In v2 the dashboard is `dashboard/index.html`, served by FastAPI.

## Why it was replaced, and how we know nothing changed

FastAPI keeps the whole backend in Python, adds `/docs`, response models and exports, and needs no Apache. Before the switch, `tests/parity/test_parity.py` called both APIs with the same requests: every endpoint, all 1,684 asteroid IDs and aliases, every page of the approaches table, bad input, and wrong HTTP methods. Every one of the 104 tests got the same status, the same headers and a **byte-for-byte identical** body.

## Running it again (for the parity tests)

```
make legacy-deploy     # writes the read-only DB config for PHP, copies api/ and includes/ to XAMPP htdocs
make parity-test       # PHP vs FastAPI
make legacy-undeploy   # removes it from htdocs
```

The API is then at `http://localhost/asteroid-watch/api/*.php`. `index.php` isn't deployed: it was written for the v1 JavaScript, which now calls `/api/<name>` on FastAPI. That version is on the `main` branch (v1).
