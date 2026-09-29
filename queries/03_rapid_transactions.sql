-- =============================================================
-- PHASE 2: Rapid-Fire Transaction Detection (Card Testing)
-- Rule: Same account, 2+ transactions within 30 seconds
-- Technique: Window functions (LAG), CTEs
-- =============================================================

WITH txn_with_prev AS (
    SELECT
        txn_id,
        account_id,
        amount,
        txn_timestamp,
        -- Previous transaction timestamp for the same account
        LAG(txn_timestamp) OVER (
            PARTITION BY account_id
            ORDER BY txn_timestamp
        ) AS prev_timestamp,
        LAG(txn_id) OVER (
            PARTITION BY account_id
            ORDER BY txn_timestamp
        ) AS prev_txn_id
    FROM transactions
    WHERE txn_type IN ('debit', 'transfer')
),

rapid_pairs AS (
    SELECT
        account_id,
        txn_id          AS current_txn_id,
        prev_txn_id,
        txn_timestamp   AS current_ts,
        prev_timestamp  AS prev_ts,
        -- Seconds between consecutive transactions
        CAST(
            (julianday(txn_timestamp) - julianday(prev_timestamp)) * 86400
        AS INTEGER) AS seconds_apart,
        amount
    FROM txn_with_prev
    WHERE prev_timestamp IS NOT NULL
      AND (julianday(txn_timestamp) - julianday(prev_timestamp)) * 86400 <= 30
)

SELECT
    rp.account_id,
    a.owner_name,
    COUNT(*)                  AS rapid_pair_count,
    MIN(rp.seconds_apart)     AS min_gap_seconds,
    MIN(rp.prev_ts)           AS window_start,
    MAX(rp.current_ts)        AS window_end,
    GROUP_CONCAT(rp.current_txn_id) AS flagged_txn_ids
FROM rapid_pairs rp
JOIN accounts a USING (account_id)
GROUP BY rp.account_id, a.owner_name
ORDER BY rapid_pair_count DESC;
