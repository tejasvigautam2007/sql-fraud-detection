-- =============================================================
-- PHASE 3: Unusual Amount Detection (Statistical Anomaly)
-- Rule: Transaction amount > mean + 3 × stddev of user's own history
-- Technique: Subqueries, window aggregates, manual stddev (SQLite)
-- =============================================================

WITH user_stats AS (
    -- Compute per-account mean and population stddev
    -- SQLite has no STDDEV(), so: stddev = sqrt(E[X²] - E[X]²)
    SELECT
        account_id,
        AVG(amount)                                      AS mean_amount,
        SQRT(
            MAX(0, AVG(amount * amount) - AVG(amount) * AVG(amount))
        )                                                AS stddev_amount,
        COUNT(*)                                         AS txn_count
    FROM transactions
    WHERE txn_type IN ('debit', 'transfer')
    GROUP BY account_id
    HAVING COUNT(*) >= 5   -- need enough history to compute a meaningful baseline
),

flagged AS (
    SELECT
        t.txn_id,
        t.account_id,
        a.owner_name,
        t.amount,
        t.txn_timestamp,
        t.merchant,
        us.mean_amount,
        us.stddev_amount,
        -- Z-score: how many stddevs above the mean?
        CASE
            WHEN us.stddev_amount = 0 THEN NULL
            ELSE (t.amount - us.mean_amount) / us.stddev_amount
        END AS z_score,
        us.mean_amount + 3 * us.stddev_amount AS threshold
    FROM transactions t
    JOIN user_stats us USING (account_id)
    JOIN accounts a    USING (account_id)
    WHERE t.txn_type IN ('debit','transfer')
      AND us.stddev_amount > 0
      AND t.amount > us.mean_amount + 3 * us.stddev_amount
)

SELECT
    txn_id,
    account_id,
    owner_name,
    ROUND(amount, 2)        AS amount,
    ROUND(mean_amount, 2)   AS user_avg,
    ROUND(stddev_amount, 2) AS user_stddev,
    ROUND(z_score, 2)       AS z_score,
    ROUND(threshold, 2)     AS threshold,
    txn_timestamp,
    merchant
FROM flagged
ORDER BY z_score DESC;
