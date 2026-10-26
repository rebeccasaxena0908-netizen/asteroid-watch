<?php
/**
 * GET api/asteroid.php?id=2614134
 * One asteroid with its orbital data and every stored close approach.
 * An old provisional id (see docs/duplicate_ids.md) resolves to its numbered id.
 */
require_once __DIR__ . '/../includes/api.php';

api_run(function () {
    $id = (string)($_GET['id'] ?? '');
    if (!preg_match('/^\d{1,20}$/', $id)) {
        throw new BadRequest("'id' is required and must be a numeric neo_id.");
    }

    $resolved_from = null;
    $alias = query_one('SELECT numbered_neo_id FROM neo_id_aliases WHERE old_neo_id = :id', [':id' => $id]);
    if ($alias) {
        $resolved_from = $id;
        $id = $alias['numbered_neo_id'];
    }

    $asteroid = query_one('SELECT * FROM asteroids WHERE neo_id = :id', [':id' => $id]);
    if (!$asteroid) {
        throw new NotFound("No asteroid with id $id.");
    }

    $orbit = query_one(
        'SELECT orbit_class, orbit_class_description, eccentricity, inclination_deg, orbital_period_days,
                first_observation_date, last_observation_date, fetched_at
         FROM orbital_data WHERE neo_id = :id', [':id' => $id]);

    $approaches = query_all(
        'SELECT id AS approach_id, approach_date, approach_datetime, relative_velocity_kps, relative_velocity_kph,
                miss_distance_km, miss_distance_lunar, miss_distance_au, orbiting_body
         FROM close_approaches WHERE neo_id = :id ORDER BY epoch_ms', [':id' => $id]);

    $old_ids = array_column(
        query_all('SELECT old_neo_id FROM neo_id_aliases WHERE numbered_neo_id = :id ORDER BY old_neo_id',
                  [':id' => $id]),
        'old_neo_id');

    return [
        'asteroid' => with_bools($asteroid),
        'orbit' => $orbit,
        'approaches' => $approaches,
        'old_ids' => $old_ids,
        'resolved_from' => $resolved_from,
    ];
});
