"""GET /api/asteroid?id=...: one asteroid with its orbit and every stored approach (was asteroid.php).

An old provisional id (see docs/duplicate_ids.md) resolves to its numbered id.
"""

import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from api.db import query_all, query_one, with_bools
from api.params import BadRequest, NotFound
from api.responses import data_response
from api.schemas import AsteroidResponse

router = APIRouter()

NEO_ID = re.compile(r"^\d{1,20}$")


@router.get("/asteroid", response_model=AsteroidResponse, summary="One asteroid")
def asteroid(request: Request, id: str | None = Query(None, description="Numeric neo_id (required)")) -> Response:
    neo_id = id or ""
    if not NEO_ID.match(neo_id):
        raise BadRequest("'id' is required and must be a numeric neo_id.")

    resolved_from = None
    alias = query_one("SELECT numbered_neo_id FROM neo_id_aliases WHERE old_neo_id = :id", {"id": neo_id})
    if alias:
        resolved_from = neo_id
        neo_id = alias["numbered_neo_id"]

    row = query_one("SELECT * FROM asteroids WHERE neo_id = :id", {"id": neo_id})
    if not row:
        raise NotFound(f"No asteroid with id {neo_id}.")

    orbit = query_one(
        """SELECT orbit_class, orbit_class_description, eccentricity, inclination_deg, orbital_period_days,
                first_observation_date, last_observation_date, fetched_at
         FROM orbital_data WHERE neo_id = :id""", {"id": neo_id})

    approaches = query_all(
        """SELECT id AS approach_id, approach_date, approach_datetime, relative_velocity_kps, relative_velocity_kph,
                miss_distance_km, miss_distance_lunar, miss_distance_au, orbiting_body
         FROM close_approaches WHERE neo_id = :id ORDER BY epoch_ms""", {"id": neo_id})

    old_ids = [r["old_neo_id"] for r in query_all(
        "SELECT old_neo_id FROM neo_id_aliases WHERE numbered_neo_id = :id ORDER BY old_neo_id", {"id": neo_id})]

    return data_response(request, AsteroidResponse, {
        "asteroid": with_bools(row),
        "orbit": orbit,
        "approaches": approaches,
        "old_ids": old_ids,
        "resolved_from": resolved_from,
    })
