"""JSON responses shaped like the PHP API's send_json(): {"data": ...} or {"error": "..."}.

Compact JSON by default and indented with ?pretty=1, unicode escaped and slashes not
(json_encode with JSON_UNESCAPED_SLASHES), plus the same headers.
"""

import json

from fastapi import Request
from fastapi.responses import Response

from api.schemas import Model

HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def render(body: dict, pretty: bool = False) -> bytes:
    if pretty:
        return json.dumps(body, indent=4).encode()
    return json.dumps(body, separators=(",", ":")).encode()


def json_response(request: Request, status: int, body: dict) -> Response:
    pretty = request.query_params.get("pretty") == "1"
    return Response(render(body, pretty), status_code=status, headers=HEADERS,
                    media_type="application/json; charset=utf-8")


def data_response(request: Request, model: type[Model], data: dict) -> Response:
    """Validate {"data": data} against the endpoint's response model, then send it."""
    body = model.model_validate({"data": data}).model_dump(mode="json")
    return json_response(request, 200, body)


def error_response(request: Request, status: int, message: str) -> Response:
    return json_response(request, status, {"error": message})
