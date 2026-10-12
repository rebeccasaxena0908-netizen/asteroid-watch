<?php
/**
 * GET api/approaches.php
 * Close approaches with filters, sorting and pagination.
 *
 * Parameters (all optional):
 *   start, end   YYYY-MM-DD, inclusive approach-date range
 *   hazardous    all | true | false              (default all)
 *   q            name search, max 50 characters
 *   sort         date | distance | velocity | size | name   (default date)
 *   order        asc | desc                      (default asc)
 *   page         1..10000                        (default 1)
 *   per_page     1..100                          (default 25)
 */
require_once __DIR__ . '/../includes/api.php';

// Sort keys map to fixed SQL. User input never becomes SQL text.
const SORT_COLUMNS = [
    'date' => 'ca.epoch_ms',
    'distance' => 'ca.miss_distance_km',
    'velocity' => 'ca.relative_velocity_kps',
    'size' => 'a.est_diameter_max_m',
    'name' => 'a.name',
];

api_run(function () {
    $start = param_date('start');
    $end = param_date('end');
    if ($start && $end && $start > $end) {
        throw new BadRequest("'start' must be on or before 'end'.");
    }
    $hazardous = param_enum('hazardous', 'all', ['all', 'true', 'false']);
    $q = param_text('q', 50);
    $sort = param_enum('sort', 'date', array_keys(SORT_COLUMNS));
    $order = param_enum('order', 'asc', ['asc', 'desc']);
    $page = param_int('page', 1, 1, 10000);
    $per_page = param_int('per_page', 25, 1, 100);

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
    if ($hazardous !== 'all') {
        $where[] = 'a.is_potentially_hazardous = :hazardous';
        $params[':hazardous'] = $hazardous === 'true' ? 1 : 0;
    }
    if ($q !== '') {
        // Escape LIKE wildcards so "%" or "_" in the search are matched literally.
        $where[] = "a.name LIKE :q ESCAPE '\\\\'";
        $params[':q'] = '%' . addcslashes($q, '%_\\') . '%';
    }
    $where_sql = $where ? 'WHERE ' . implode(' AND ', $where) : '';
    $from = 'FROM close_approaches ca JOIN asteroids a ON a.neo_id = ca.neo_id';

    $total = (int)query_one("SELECT COUNT(*) AS n $from $where_sql", $params)['n'];

    $order_sql = SORT_COLUMNS[$sort] . ($order === 'desc' ? ' DESC' : ' ASC') . ', ca.id ASC';
    $rows = query_all(
        "SELECT ca.id AS approach_id, ca.neo_id, a.name, a.is_potentially_hazardous,
                a.est_diameter_min_m, a.est_diameter_max_m, ca.approach_date, ca.approach_datetime,
                ca.relative_velocity_kps, ca.relative_velocity_kph,
                ca.miss_distance_km, ca.miss_distance_lunar, ca.miss_distance_au, ca.orbiting_body
         $from $where_sql
         ORDER BY $order_sql
         LIMIT :limit OFFSET :offset",
        $params + [':limit' => $per_page, ':offset' => ($page - 1) * $per_page]
    );

    return [
        'items' => rows_with_bools($rows),
        'page' => $page,
        'per_page' => $per_page,
        'total' => $total,
        'total_pages' => (int)ceil($total / $per_page),
        'filters' => compact('start', 'end', 'hazardous', 'q', 'sort', 'order'),
    ];
});
