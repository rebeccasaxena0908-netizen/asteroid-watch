<?php
/**
 * GET api/trends.php?start=2025-10-12&end=2026-11-11
 * Data for the charts: approaches per day, size histogram, velocity vs miss distance,
 * hazardous vs non-hazardous. start/end (optional) filter by approach date.
 */
require_once __DIR__ . '/../includes/api.php';

// Size bins by maximum estimated diameter, in meters: [min, max)
const SIZE_BINS = [[0, 10], [10, 25], [25, 50], [50, 100], [100, 250], [250, 500], [500, 1000], [1000, null]];

api_run(function () {
    $start = param_date('start');
    $end = param_date('end');
    if ($start && $end && $start > $end) {
        throw new BadRequest("'start' must be on or before 'end'.");
    }
    $where = [];
    $params = [];
    if ($start) {
        $where[] = 'ca.approach_date >= :start';
        $params[':start'] = $start;
    }
    if ($end) {
        $where[] = 'ca.approach_date <= :end';
        $params[':end'] = $end;
    }
    $where_sql = $where ? 'WHERE ' . implode(' AND ', $where) : '';
    $from = 'FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id';

    $daily = query_all(
        "SELECT ca.approach_date, COUNT(*) AS approach_count,
                CAST(SUM(a.is_potentially_hazardous) AS UNSIGNED) AS hazardous_count
         $from $where_sql GROUP BY ca.approach_date ORDER BY ca.approach_date", $params);

    // Size histogram over the distinct asteroids that approach in the range.
    $sizes = query_all(
        "SELECT DISTINCT a.neo_id, a.est_diameter_max_m, a.is_potentially_hazardous $from $where_sql", $params);
    $histogram = [];
    foreach (SIZE_BINS as [$min, $max]) {
        $histogram[] = ['min_m' => $min, 'max_m' => $max,
                        // Braces matter: PHP would read "$min–" (UTF-8 dash) as one variable name.
                        'label' => $max === null ? "≥ {$min} m" : "{$min}–{$max} m",
                        'count' => 0, 'hazardous' => 0];
    }
    foreach ($sizes as $s) {
        if ($s['est_diameter_max_m'] === null) {
            continue;
        }
        foreach (SIZE_BINS as $i => [$min, $max]) {
            if ($s['est_diameter_max_m'] >= $min && ($max === null || $s['est_diameter_max_m'] < $max)) {
                $histogram[$i]['count']++;
                $histogram[$i]['hazardous'] += (int)$s['is_potentially_hazardous'];
                break;
            }
        }
    }

    $scatter = query_all(
        "SELECT ca.neo_id, a.name, a.is_potentially_hazardous, ca.approach_date,
                ca.relative_velocity_kps, ca.miss_distance_lunar
         $from $where_sql ORDER BY ca.epoch_ms", $params);

    $hazardous = query_all(
        "SELECT a.is_potentially_hazardous, COUNT(DISTINCT a.neo_id) AS asteroid_count, COUNT(*) AS approach_count
         $from $where_sql GROUP BY a.is_potentially_hazardous ORDER BY a.is_potentially_hazardous", $params);

    return [
        'range' => ['start' => $start, 'end' => $end],
        'daily' => $daily,
        'size_histogram' => $histogram,
        'velocity_vs_distance' => rows_with_bools($scatter),
        'hazardous_split' => rows_with_bools($hazardous),
    ];
});
