# Swagger UI (vendored)

The interactive API docs at `http://localhost:8000/docs` use these local copies, so `/docs` works offline, like the dashboard. FastAPI's default page would load an unpinned `swagger-ui-dist@5` from a CDN.

- Package: [swagger-ui-dist](https://www.npmjs.com/package/swagger-ui-dist) **5.33.2** (published 2026-10-12), Apache License 2.0 (`LICENSE`, `NOTICE`)
- Downloaded 2026-10-27. Each file's SHA-256 matched the hash jsdelivr publishes for the package (`data.jsdelivr.com/v1/packages/npm/swagger-ui-dist@5.33.2`), and `tests/test_api_app.py` re-checks them.

| File | Source | Bytes | SHA-256 |
|---|---|---|---|
| `LICENSE` | `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.2/LICENSE` | 11,358 | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `NOTICE` | `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.2/NOTICE` | 55 | `0d20d1adef18aee3f40dd258172155521ce702ac445cb5f7b7d60ed32dad2fb2` |
| `swagger-ui-bundle.js` | `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.2/swagger-ui-bundle.js` | 1,587,262 | `6b3bfcaff3fc82c0e6992ca4b370c4f22970dec35fff60d229302b3ee7688715` |
| `swagger-ui.css` | `https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.33.2/swagger-ui.css` | 186,154 | `1ac324f7dcd27e4b9386b4bd6421271ec147e922a22c05ba24b11515e9aa6321` |
