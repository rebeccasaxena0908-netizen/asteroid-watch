"""The FastAPI app: JSON API under /api, the dashboard at /, interactive docs at /docs.

Run it with `asteroid-watch serve` (uvicorn, 1 worker, http://localhost:8000).
Errors are JSON in the same form and with the same status codes as the PHP API:
400 bad input, 404 not found, 405 wrong method, 503 MySQL off, 500 anything else
(details only in the server log).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from api.db import DatabaseUnavailable
from api.params import BadRequest, NotFound
from api.responses import error_response
from api.routes import approaches, asteroid, exports, runs, summary, trends
from pipeline.config import PROJECT_ROOT

log = logging.getLogger("api")
DASHBOARD = PROJECT_ROOT / "dashboard"
SWAGGER = PROJECT_ROOT / "api" / "static" / "swagger-ui"
FAVICON = "/assets/favicon.svg"

app = FastAPI(
    title="Asteroid Watch API",
    version="2.0",
    summary="Near-Earth asteroid close approaches from NASA, read from MySQL with a read-only user.",
    description="Every number comes from the database. \"Potentially hazardous\" is NASA's classification "
                "(size and orbit), not an impact prediction.",
    docs_url=None,  # served below from local files instead of a CDN
    redoc_url=None,
)

for module in (summary, approaches, asteroid, trends, runs, exports):
    app.include_router(module.router, prefix="/api")


@app.exception_handler(BadRequest)
def bad_request(request: Request, exc: BadRequest) -> Response:
    return error_response(request, 400, str(exc))


@app.exception_handler(NotFound)
def not_found(request: Request, exc: NotFound) -> Response:
    return error_response(request, 404, str(exc))


@app.exception_handler(DatabaseUnavailable)
def database_unavailable(request: Request, exc: DatabaseUnavailable) -> Response:
    return error_response(request, 503, str(exc))


@app.exception_handler(HTTPException)
def http_error(request: Request, exc: HTTPException) -> Response:
    if exc.status_code == 405:
        return error_response(request, 405, "Only GET is supported.")
    if exc.status_code == 404:
        return error_response(request, 404, "Not found.")
    return error_response(request, exc.status_code, str(exc.detail))


@app.exception_handler(Exception)
def server_error(request: Request, exc: Exception) -> Response:
    # Details (with traceback) go to the server log only, never to the client.
    log.error("Asteroid Watch API error on %s", request.url.path, exc_info=exc)
    return error_response(request, 500, "Something went wrong on the server.")


class RevalidatedStaticFiles(StaticFiles):
    """Static files the browser must re-check on every load (cheap: unchanged files get a 304)."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


@app.get("/", include_in_schema=False)
def dashboard() -> Response:
    return FileResponse(DASHBOARD / "index.html",
                        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"})


@app.get("/docs", include_in_schema=False)
def docs() -> HTMLResponse:
    """Interactive API docs, with Swagger UI from api/static/swagger-ui (works offline)."""
    return get_swagger_ui_html(openapi_url=app.openapi_url or "/openapi.json", title="Asteroid Watch API",
                               swagger_js_url="/static/swagger-ui/swagger-ui-bundle.js",
                               swagger_css_url="/static/swagger-ui/swagger-ui.css",
                               swagger_favicon_url=FAVICON)


# Only these two folders are served: nothing else in the project is reachable over HTTP.
app.mount("/assets", RevalidatedStaticFiles(directory=DASHBOARD / "assets"), name="assets")
app.mount("/static/swagger-ui", RevalidatedStaticFiles(directory=SWAGGER), name="swagger-ui")
