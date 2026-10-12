-- Asteroid Watch: dashboard views (the "gold" layer).
-- Safe to re-run: CREATE OR REPLACE VIEW.

-- Close approaches from today onwards, with asteroid details.
CREATE OR REPLACE VIEW v_upcoming_approaches AS
SELECT
    ca.id AS approach_id,
    ca.neo_id,
    a.name,
    a.is_potentially_hazardous,
    a.est_diameter_min_m,
    a.est_diameter_max_m,
    ca.approach_date,
    ca.approach_datetime,
    ca.relative_velocity_kps,
    ca.miss_distance_km,
    ca.miss_distance_lunar,
    ca.miss_distance_au,
    ca.orbiting_body
FROM close_approaches ca
JOIN asteroids a ON a.neo_id = ca.neo_id
WHERE ca.approach_date >= CURDATE();

-- Number of approaches per day (all and hazardous only).
CREATE OR REPLACE VIEW v_daily_counts AS
SELECT
    ca.approach_date,
    COUNT(*) AS approach_count,
    SUM(a.is_potentially_hazardous) AS hazardous_count
FROM close_approaches ca
JOIN asteroids a ON a.neo_id = ca.neo_id
GROUP BY ca.approach_date;

-- Hazardous vs non-hazardous totals.
CREATE OR REPLACE VIEW v_hazardous_summary AS
SELECT
    a.is_potentially_hazardous,
    COUNT(DISTINCT a.neo_id) AS asteroid_count,
    COUNT(ca.id) AS approach_count,
    MIN(ca.miss_distance_km) AS closest_miss_km
FROM asteroids a
LEFT JOIN close_approaches ca ON ca.neo_id = a.neo_id
GROUP BY a.is_potentially_hazardous;

-- The 10 closest approaches on record.
CREATE OR REPLACE VIEW v_top_closest AS
SELECT
    ca.id AS approach_id,
    ca.neo_id,
    a.name,
    a.is_potentially_hazardous,
    ca.approach_date,
    ca.miss_distance_km,
    ca.miss_distance_lunar,
    ca.relative_velocity_kps
FROM close_approaches ca
JOIN asteroids a ON a.neo_id = ca.neo_id
ORDER BY ca.miss_distance_km ASC
LIMIT 10;

-- The 10 largest asteroids (by maximum estimated diameter).
CREATE OR REPLACE VIEW v_top_largest AS
SELECT
    a.neo_id,
    a.name,
    a.is_potentially_hazardous,
    a.est_diameter_min_m,
    a.est_diameter_max_m,
    COUNT(ca.id) AS approach_count,
    MIN(ca.miss_distance_km) AS closest_miss_km
FROM asteroids a
LEFT JOIN close_approaches ca ON ca.neo_id = a.neo_id
GROUP BY a.neo_id, a.name, a.is_potentially_hazardous, a.est_diameter_min_m, a.est_diameter_max_m
ORDER BY a.est_diameter_max_m DESC
LIMIT 10;
