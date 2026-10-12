<?php
/**
 * GET api/runs.php?limit=10
 * Latest pipeline runs (ETL and JPL cross-check), each with its quality check results.
 */
require_once __DIR__ . '/../includes/api.php';

api_run(function () {
    $limit = param_int('limit', 10, 1, 50);

    $runs = query_all(
        'SELECT run_id, run_type, status, started_at, finished_at,
                TIMESTAMPDIFF(SECOND, started_at, finished_at) AS duration_seconds,
                date_range_start, date_range_end, api_calls, records_extracted,
                rows_inserted, rows_updated, quality_failures, error_message
         FROM pipeline_runs ORDER BY run_id DESC LIMIT :limit', [':limit' => $limit]);
    if (!$runs) {
        return ['runs' => []];
    }

    // One query for all checks of these runs; run ids are bound, not concatenated.
    $ids = array_column($runs, 'run_id');
    $placeholders = [];
    $params = [];
    foreach ($ids as $i => $run_id) {
        $placeholders[] = ":r$i";
        $params[":r$i"] = (int)$run_id;
    }
    $checks = query_all(
        'SELECT run_id, check_name, passed, details FROM quality_results
         WHERE run_id IN (' . implode(', ', $placeholders) . ') ORDER BY run_id, id', $params);

    $by_run = [];
    foreach ($checks as $c) {
        $by_run[$c['run_id']][] = with_bools(['check_name' => $c['check_name'], 'passed' => $c['passed'],
                                              'details' => $c['details']]);
    }
    foreach ($runs as &$run) {
        $run['quality'] = $by_run[$run['run_id']] ?? [];
    }
    unset($run);
    return ['runs' => $runs];
});
