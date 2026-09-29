-- =============================================================
-- PHASE 5: Smurfing Detection (Many → One)
-- Rule: One account receives money from 5+ UNRELATED senders
--       within a 24-hour window → structuring / smurfing attack
-- Technique: Window aggregates, CTEs, subqueries
-- =============================================================

WITH inbound_transfers AS (
    -- Every credit transfer arriving at a recipient account
    SELECT
        recipient_account_id  AS receiver_id,
        account_id            AS sender_id,
        amount,
        txn_timestamp,
        txn_id,
        -- Date bucket: group into 24-hour windows by calendar date
        DATE(txn_timestamp)   AS txn_date
    FROM transactions
    WHERE txn_type = 'transfer'
      AND recipient_account_id IS NOT NULL
),

daily_inbound AS (
    -- Count distinct senders and total amount per receiver per day
    SELECT
        receiver_id,
        txn_date,
        COUNT(DISTINCT sender_id)  AS unique_senders,
        COUNT(*)                   AS transfer_count,
        ROUND(SUM(amount), 2)      AS total_received,
        ROUND(AVG(amount), 2)      AS avg_transfer,
        ROUND(MAX(amount), 2)      AS max_transfer,
        GROUP_CONCAT(DISTINCT sender_id) AS sender_ids
    FROM inbound_transfers
    GROUP BY receiver_id, txn_date
),

-- Detect structuring: many senders each sending just below $10,000
-- (common to avoid bank reporting thresholds)
structuring_check AS (
    SELECT
        it.receiver_id,
        it.txn_date,
        COUNT(CASE WHEN it.amount BETWEEN 8000 AND 9999 THEN 1 END) AS near_threshold_count
    FROM inbound_transfers it
    GROUP BY it.receiver_id, it.txn_date
)

SELECT
    di.receiver_id                        AS account_id,
    a.owner_name,
    di.txn_date,
    di.unique_senders,
    di.transfer_count,
    di.total_received,
    di.avg_transfer,
    di.max_transfer,
    COALESCE(sc.near_threshold_count, 0)  AS near_threshold_txns,
    di.sender_ids,
    CASE
        WHEN di.unique_senders >= 10 OR sc.near_threshold_count >= 3 THEN 'CRITICAL'
        WHEN di.unique_senders >= 7                                   THEN 'HIGH'
        WHEN di.unique_senders >= 5                                   THEN 'MEDIUM'
        ELSE 'LOW'
    END AS severity
FROM daily_inbound di
JOIN accounts a               ON di.receiver_id = a.account_id
LEFT JOIN structuring_check sc ON di.receiver_id = sc.receiver_id
                               AND di.txn_date   = sc.txn_date
WHERE di.unique_senders >= 5
ORDER BY di.unique_senders DESC, di.total_received DESC;
