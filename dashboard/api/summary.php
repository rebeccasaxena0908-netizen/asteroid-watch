<?php
/**
 * GET api/summary.php
 * Headline numbers for the dashboard cards. Everything is read from MySQL.
 */
require_once __DIR__ . '/../includes/api.php';

api_run(function () {
    $totals = query_one(
        "SELECT
            (SELECT COUNT(*) FROM asteroids) AS asteroids,
            (SELECT COUNT(*) FROM asteroids WHERE is_potentially_hazardous) AS hazardous_asteroids,
            (SELECT COUNT(*) FROM close_approaches) AS approaches,
            (SELECT COUNT(*) FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id
              WHERE a.is_potentially_hazardous) AS hazardous_approaches,
            (SELECT COUNT(*) FROM orbital_data) AS asteroids_with_orbits,
            (SELECT MIN(approach_date) FROM close_approaches) AS first_date,
            (SELECT MAX(approach_date) FROM close_approaches) AS last_date,
            CURDATE() AS today"
    );

    // "This week" = today and the next 6 days.
    $week = query_one(
        "SELECT COUNT(*) AS approaches, COUNT(DISTINCT ca.neo_id) AS asteroids,
                CAST(COALESCE(SUM(a.is_potentially_hazardous), 0) AS UNSIGNED) AS hazardous
         FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id
         WHERE ca.approach_date BETWEEN CURDATE() AND CURDATE() + INTERVAL 6 DAY"
    );

    $closest_this_week = query_one(
        "SELECT neo_id, name, is_potentially_hazardous, approach_date, approach_datetime,
                miss_distance_km, miss_distance_lunar, relative_velocity_kps
         FROM v_upcoming_approaches
         WHERE approach_date <= CURDATE() + INTERVAL 6 DAY
         ORDER BY miss_distance_km ASC LIMIT 1"
    );
    $closest_upcoming = query_one(
        "SELECT neo_id, name, is_potentially_hazardous, approach_date, approach_datetime,
                miss_distance_km, miss_distance_lunar, relative_velocity_kps
         FROM v_upcoming_approaches ORDER BY miss_distance_km ASC LIMIT 1"
    );
    $closest_on_record = query_one("SELECT * FROM v_top_closest LIMIT 1");
    $largest = query_one("SELECT * FROM v_top_largest LIMIT 1");

    // Latest ETL run (cross-check runs are listed separately in runs.php).
    $last_run = query_one(
        "SELECT r.run_id, r.run_type, r.status, r.started_at, r.finished_at,
                TIMESTAMPDIFF(SECOND, r.started_at, r.finished_at) AS duration_seconds,
                r.api_calls, r.records_extracted, r.rows_inserted, r.rows_updated, r.quality_failures,
                (SELECT COUNT(*) FROM quality_results q WHERE q.run_id = r.run_id) AS quality_checks
         FROM pipeline_runs r WHERE r.run_type <> 'crosscheck'
         ORDER BY r.run_id DESC LIMIT 1"
    );

    return [
        'totals' => $totals,
        'this_week' => $week,
        'closest_this_week' => $closest_this_week ? with_bools($closest_this_week) : null,
        'closest_upcoming' => $closest_upcoming ? with_bools($closest_upcoming) : null,
        'closest_on_record' => $closest_on_record ? with_bools($closest_on_record) : null,
        'largest' => $largest ? with_bools($largest) : null,
        'last_run' => $last_run,
    ];
});
