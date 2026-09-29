-- =============================================================
-- PHASE 4: Geo-Impossible Transaction Detection
-- Rule: Same account, 2 transactions in cities >500 km apart,
--       within 60 minutes — physically impossible to travel.
-- Technique: Self-join, Haversine approximation in SQL
-- =============================================================

-- Haversine in SQLite: computed inline using trig approximation.
-- We use the spherical law of cosines for simplicity (accurate to <0.5%):
--   d = acos(sin(lat1)*sin(lat2) + cos(lat1)*cos(lat2)*cos(lon2-lon1)) * R

WITH geo_txns AS (
    SELECT
        t.txn_id,
        t.account_id,
        t.txn_timestamp,
        t.amount,
        l.city,
        l.country,
        l.latitude,
        l.longitude
    FROM transactions t
    JOIN locations l ON t.location_id = l.location_id
    WHERE t.txn_type IN ('debit','transfer')
),

suspicious_pairs AS (
    SELECT
        g1.account_id,
        a.owner_name,
        g1.txn_id        AS txn1_id,
        g2.txn_id        AS txn2_id,
        g1.city          AS city1,
        g2.city          AS city2,
        g1.txn_timestamp AS ts1,
        g2.txn_timestamp AS ts2,
        g1.amount        AS amount1,
        g2.amount        AS amount2,

        -- Minutes between the two transactions
        ROUND(
            ABS(julianday(g2.txn_timestamp) - julianday(g1.txn_timestamp)) * 1440
        , 1) AS minutes_apart,

        -- Approximate great-circle distance (km) using spherical law of cosines
        ROUND(
            6371 * ACOS(
                MIN(1.0, MAX(-1.0,
                    SIN(RADIANS(g1.latitude))  * SIN(RADIANS(g2.latitude)) +
                    COS(RADIANS(g1.latitude))  * COS(RADIANS(g2.latitude)) *
                    COS(RADIANS(g2.longitude) - RADIANS(g1.longitude))
                ))
            )
        , 0) AS distance_km

    FROM geo_txns  g1
    JOIN geo_txns  g2 ON  g1.account_id = g2.account_id
                      AND g2.txn_timestamp > g1.txn_timestamp
                      AND g1.city <> g2.city
    JOIN accounts a   ON  g1.account_id = a.account_id

    -- Only pairs within 60 minutes
    WHERE ABS(julianday(g2.txn_timestamp) - julianday(g1.txn_timestamp)) * 1440 <= 60
)

SELECT
    account_id,
    owner_name,
    txn1_id,
    txn2_id,
    city1,
    city2,
    ts1,
    ts2,
    minutes_apart,
    distance_km,
    -- Required speed to travel this distance in this time (km/h)
    ROUND(distance_km / (minutes_apart / 60.0), 0) AS required_speed_kmh,
    CASE
        WHEN distance_km > 5000 THEN 'CRITICAL'
        WHEN distance_km > 2000 THEN 'HIGH'
        ELSE 'MEDIUM'
    END AS severity
FROM suspicious_pairs
WHERE distance_km > 500     -- must be >500 km apart
ORDER BY distance_km DESC;
