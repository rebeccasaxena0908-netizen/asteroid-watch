<?php
/**
 * Shared helpers for the JSON API: responses, errors, input validation.
 * Every endpoint: require this file, then call api_run(function () { ... return $data; }).
 */

require_once __DIR__ . '/db.php';

// Shortest exact float output in JSON (XAMPP's php.ini sets a long serialize_precision).
ini_set('serialize_precision', '-1');

class BadRequest extends InvalidArgumentException {}
class NotFound extends RuntimeException {}

function send_json(int $status, array $body): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    // Compact by default; add ?pretty=1 to read a response in the browser.
    $flags = JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION;
    if (($_GET['pretty'] ?? '') === '1') {
        $flags |= JSON_PRETTY_PRINT;
    }
    echo json_encode($body, $flags);
}

/** Runs an endpoint and turns every failure into a friendly JSON error. */
function api_run(callable $handler): void
{
    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'GET') {
        send_json(405, ['error' => 'Only GET is supported.']);
        return;
    }
    try {
        send_json(200, ['data' => $handler()]);
    } catch (BadRequest $e) {
        send_json(400, ['error' => $e->getMessage()]);
    } catch (NotFound $e) {
        send_json(404, ['error' => $e->getMessage()]);
    } catch (DatabaseUnavailable $e) {
        send_json(503, ['error' => $e->getMessage()]);
    } catch (Throwable $e) {
        error_log('Asteroid Watch API error: ' . $e->getMessage());   // details go to the log only
        send_json(500, ['error' => 'Something went wrong on the server.']);
    }
}

// --- input validation -------------------------------------------------------------

function param_date(string $name, ?string $default = null): ?string
{
    $value = $_GET[$name] ?? null;
    if ($value === null || $value === '') {
        return $default;
    }
    $d = DateTime::createFromFormat('!Y-m-d', $value);
    if (!$d || $d->format('Y-m-d') !== $value) {
        throw new BadRequest("'$name' must be a date like 2026-10-12.");
    }
    return $value;
}

function param_int(string $name, int $default, int $min, int $max): int
{
    $value = $_GET[$name] ?? null;
    if ($value === null || $value === '') {
        return $default;
    }
    if (!preg_match('/^-?\d+$/', (string)$value) || (int)$value < $min || (int)$value > $max) {
        throw new BadRequest("'$name' must be a whole number from $min to $max.");
    }
    return (int)$value;
}

function param_enum(string $name, string $default, array $allowed): string
{
    $value = $_GET[$name] ?? null;
    if ($value === null || $value === '') {
        return $default;
    }
    if (!in_array($value, $allowed, true)) {
        throw new BadRequest("'$name' must be one of: " . implode(', ', $allowed) . '.');
    }
    return $value;
}

function param_text(string $name, int $max_length): string
{
    $value = trim((string)($_GET[$name] ?? ''));
    if (mb_strlen($value) > $max_length) {
        throw new BadRequest("'$name' must be at most $max_length characters.");
    }
    return $value;
}

// --- output shaping ----------------------------------------------------------------

/** MySQL BOOLEAN comes back as 0/1; send real true/false. */
function with_bools(array $row, array $columns = ['is_potentially_hazardous', 'is_sentry_object', 'passed']): array
{
    foreach ($columns as $c) {
        if (array_key_exists($c, $row) && $row[$c] !== null) {
            $row[$c] = (bool)$row[$c];
        }
    }
    return $row;
}

function rows_with_bools(array $rows): array
{
    return array_map('with_bools', $rows);
}
