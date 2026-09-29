-- =============================================================
-- PHASE 7: Fraud Score Dashboard + Composite Risk Score
-- Aggregates hits from all detection rules into a per-account
-- risk score and risk tier.
-- Technique: Multiple CTEs, UNION ALL, subqueries
-- =============================================================

-- ── Rule 1: Rapid-fire hits ──────────────────────────────────────────────────
WITH rapid_fire_hits AS (
    WITH txn_with_prev AS (
        SELECT
            account_id,
            txn_timestamp,
            LAG(txn_timestamp) OVER (
                PARTITION BY account_id ORDER BY txn_timestamp
            ) AS prev_ts
        FROM transactions WHERE txn_type IN ('debit','transfer')
    )
    SELECT account_id, COUNT(*) AS rapid_count
    FROM txn_with_prev
    WHERE prev_ts IS NOT NULL
      AND (julianday(txn_timestamp) - julianday(prev_ts)) * 86400 <= 30
    GROUP BY account_id
),

-- ── Rule 2: Unusual amount hits ──────────────────────────────────────────────
user_stats AS (
    SELECT
        account_id,
        AVG(amount) AS mean_amt,
        SQRT(MAX(0, AVG(amount*amount) - AVG(amount)*AVG(amount))) AS stddev_amt
    FROM transactions
    WHERE txn_type IN ('debit','transfer')
    GROUP BY account_id
    HAVING COUNT(*) >= 5
),
unusual_amount_hits AS (
    SELECT t.account_id, COUNT(*) AS unusual_count
    FROM transactions t
    JOIN user_stats us USING (account_id)
    WHERE t.txn_type IN ('debit','transfer')
      AND us.stddev_amt > 0
      AND t.amount > us.mean_amt + 3 * us.stddev_amt
    GROUP BY t.account_id
),

-- ── Rule 3: Geo-impossible hits ──────────────────────────────────────────────
geo_txns AS (
    SELECT t.txn_id, t.account_id, t.txn_timestamp, l.latitude, l.longitude, l.city
    FROM transactions t JOIN locations l ON t.location_id = l.location_id
    WHERE t.txn_type IN ('debit','transfer')
),
geo_hits AS (
    SELECT g1.account_id, COUNT(*) AS geo_count
    FROM geo_txns g1
    JOIN geo_txns g2 ON g1.account_id = g2.account_id
                     AND g2.txn_timestamp > g1.txn_timestamp
                     AND g1.city <> g2.city
    WHERE ABS(julianday(g2.txn_timestamp) - julianday(g1.txn_timestamp)) * 1440 <= 60
      AND 6371 * ACOS(MIN(1.0, MAX(-1.0,
              SIN(RADIANS(g1.latitude)) * SIN(RADIANS(g2.latitude)) +
              COS(RADIANS(g1.latitude)) * COS(RADIANS(g2.latitude)) *
              COS(RADIANS(g2.longitude) - RADIANS(g1.longitude))
          ))) > 500
    GROUP BY g1.account_id
),

-- ── Rule 4: Smurfing hits ────────────────────────────────────────────────────
smurf_hits AS (
    SELECT recipient_account_id AS account_id, COUNT(*) AS smurf_days
    FROM (
        SELECT recipient_account_id, DATE(txn_timestamp) AS d,
               COUNT(DISTINCT account_id) AS uniq_senders
        FROM transactions
        WHERE txn_type = 'transfer' AND recipient_account_id IS NOT NULL
        GROUP BY recipient_account_id, d
        HAVING uniq_senders >= 5
    )
    GROUP BY recipient_account_id
),

-- ── Rule 5: Laundering chain involvement ─────────────────────────────────────
chain_hits AS (
    WITH RECURSIVE lc(origin, current, depth) AS (
        SELECT account_id, recipient_account_id, 1
        FROM transactions WHERE txn_type='transfer' AND recipient_account_id IS NOT NULL
        UNION ALL
        SELECT lc.origin, t.recipient_account_id, lc.depth+1
        FROM lc
        JOIN transactions t ON t.account_id = lc.current
                            AND t.txn_type='transfer'
                            AND t.recipient_account_id IS NOT NULL
                            AND t.recipient_account_id <> lc.origin
        WHERE lc.depth < 5
    )
    SELECT current AS account_id, COUNT(*) AS chain_involvement
    FROM lc WHERE depth >= 3
    GROUP BY current
),

-- ── Composite score ───────────────────────────────────────────────────────────
scores AS (
    SELECT
        a.account_id,
        a.owner_name,
        a.account_type,
        COALESCE(rf.rapid_count,    0) AS rapid_hits,
        COALESCE(ua.unusual_count,  0) AS unusual_hits,
        COALESCE(gh.geo_count,      0) AS geo_hits,
        COALESCE(sh.smurf_days,     0) AS smurf_hits,
        COALESCE(ch.chain_involvement,0) AS chain_hits,
        -- Weighted fraud score (tune weights as desired)
        (COALESCE(rf.rapid_count,     0) * 10 +
         COALESCE(ua.unusual_count,   0) * 15 +
         COALESCE(gh.geo_count,       0) * 25 +
         COALESCE(sh.smurf_days,      0) * 20 +
         COALESCE(ch.chain_involvement,0) * 30) AS fraud_score
    FROM accounts a
    LEFT JOIN rapid_fire_hits   rf ON a.account_id = rf.account_id
    LEFT JOIN unusual_amount_hits ua ON a.account_id = ua.account_id
    LEFT JOIN geo_hits           gh ON a.account_id = gh.account_id
    LEFT JOIN smurf_hits         sh ON a.account_id = sh.account_id
    LEFT JOIN chain_hits         ch ON a.account_id = ch.account_id
)

SELECT
    account_id,
    owner_name,
    account_type,
    rapid_hits,
    unusual_hits,
    geo_hits,
    smurf_hits,
    chain_hits,
    fraud_score,
    CASE
        WHEN fraud_score >= 100 THEN '🔴 CRITICAL'
        WHEN fraud_score >=  50 THEN '🟠 HIGH'
        WHEN fraud_score >=  20 THEN '🟡 MEDIUM'
        WHEN fraud_score >    0 THEN '🟢 LOW'
        ELSE                        '⚪ CLEAN'
    END AS risk_tier
FROM scores
WHERE fraud_score > 0
ORDER BY fraud_score DESC;
