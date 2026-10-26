<?php
/**
 * Database connection for the dashboard API (PDO, read-only MySQL user).
 *
 * Credentials come from an ini file OUTSIDE the web root, written by `make deploy`:
 *   /Applications/XAMPP/xamppfiles/etc/asteroid-watch/db.ini
 * Set the ASTEROID_WATCH_CONFIG environment variable to use another file (used by tests).
 * PHP never sees the NASA API key.
 */

const DEFAULT_CONFIG_PATH = '/Applications/XAMPP/xamppfiles/etc/asteroid-watch/db.ini';

class DatabaseUnavailable extends RuntimeException {}

function db_config(): array
{
    $path = getenv('ASTEROID_WATCH_CONFIG') ?: DEFAULT_CONFIG_PATH;
    $config = is_readable($path) ? parse_ini_file($path, false, INI_SCANNER_RAW) : false;
    if ($config === false) {
        throw new DatabaseUnavailable('Dashboard database config not found. Run `make deploy`.');
    }
    return $config;
}

function db(): PDO
{
    static $pdo = null;
    if ($pdo !== null) {
        return $pdo;
    }
    $c = db_config();
    // Prefer the Unix socket (same as the Python pipeline); fall back to TCP.
    $dsn = (!empty($c['socket']) && file_exists($c['socket']))
        ? "mysql:unix_socket={$c['socket']};dbname={$c['dbname']};charset=utf8mb4"
        : "mysql:host={$c['host']};port={$c['port']};dbname={$c['dbname']};charset=utf8mb4";
    try {
        $pdo = new PDO($dsn, $c['user'], $c['password'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,   // real prepared statements, native number types
            PDO::ATTR_TIMEOUT => 3,
        ]);
    } catch (PDOException $e) {
        error_log('Asteroid Watch DB connection failed: ' . $e->getMessage());
        throw new DatabaseUnavailable('Cannot connect to MySQL. Is XAMPP MySQL running?');
    }
    return $pdo;
}

/** Run a prepared statement and return all rows. Values are always bound, never concatenated. */
function query_all(string $sql, array $params = []): array
{
    $stmt = db()->prepare($sql);
    foreach ($params as $name => $value) {
        $stmt->bindValue($name, $value, is_int($value) ? PDO::PARAM_INT : PDO::PARAM_STR);
    }
    $stmt->execute();
    return $stmt->fetchAll();
}

function query_one(string $sql, array $params = []): ?array
{
    $rows = query_all($sql, $params);
    return $rows[0] ?? null;
}
