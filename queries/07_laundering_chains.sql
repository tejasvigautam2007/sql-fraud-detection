-- =============================================================
-- PHASE 6: Money Laundering Chain Detection (A→B→C→D)
-- Rule: Follow transfer chains up to depth 5 using Recursive CTE.
--       Chains of 3+ hops where money moves in one direction
--       indicate layering (a laundering phase).
-- Technique: Recursive CTE
-- =============================================================

-- ⚠️  SQLite requires PRAGMA recursive_triggers=ON is not needed here;
--     WITH RECURSIVE is supported natively in SQLite 3.8.3+.

WITH RECURSIVE laundering_chain(
    origin_account,     -- root of the chain (first sender)
    current_account,    -- current node we're visiting
    chain_path,         -- string representation: "40->41->42"
    chain_depth,        -- how many hops so far
    total_amount,       -- cumulative amount transferred along the chain
    chain_start_ts,     -- when did the chain start?
    chain_end_ts        -- most recent hop timestamp
) AS (
    -- BASE CASE: every outgoing transfer is a potential chain root
    SELECT
        t.account_id                 AS origin_account,
        t.recipient_account_id       AS current_account,
        CAST(t.account_id AS TEXT) || '->' ||
        CAST(t.recipient_account_id AS TEXT) AS chain_path,
        1                            AS chain_depth,
        t.amount                     AS total_amount,
        t.txn_timestamp              AS chain_start_ts,
        t.txn_timestamp              AS chain_end_ts
    FROM transactions t
    WHERE t.txn_type = 'transfer'
      AND t.recipient_account_id IS NOT NULL

    UNION ALL

    -- RECURSIVE CASE: follow transfers FROM the current node
    SELECT
        lc.origin_account,
        t.recipient_account_id,
        lc.chain_path || '->' || CAST(t.recipient_account_id AS TEXT),
        lc.chain_depth + 1,
        MIN(lc.total_amount, t.amount),   -- chain carries the min amount (bottleneck)
        lc.chain_start_ts,
        t.txn_timestamp
    FROM laundering_chain lc
    JOIN transactions t
        ON  t.account_id            = lc.current_account
        AND t.txn_type              = 'transfer'
        AND t.recipient_account_id  IS NOT NULL
        -- Avoid cycles: current hop must come AFTER the last hop
        AND t.txn_timestamp         > lc.chain_end_ts
        -- Don't revisit the origin account (simple cycle guard)
        AND t.recipient_account_id  <> lc.origin_account
        -- Avoid loops: recipient not already in path
        AND INSTR(lc.chain_path, CAST(t.recipient_account_id AS TEXT)) = 0
    WHERE lc.chain_depth < 5    -- max chain depth
)

-- Only report chains of 3+ hops (classic layering: place → layer → integrate)
SELECT
    lc.origin_account,
    a_origin.owner_name     AS origin_name,
    lc.current_account      AS final_account,
    a_final.owner_name      AS final_name,
    lc.chain_path,
    lc.chain_depth          AS hops,
    ROUND(lc.total_amount, 2) AS bottleneck_amount,
    lc.chain_start_ts,
    lc.chain_end_ts,
    ROUND(
        (julianday(lc.chain_end_ts) - julianday(lc.chain_start_ts)) * 24
    , 1)                    AS duration_hours,
    CASE
        WHEN lc.chain_depth >= 4 THEN 'CRITICAL'
        WHEN lc.chain_depth = 3  THEN 'HIGH'
        ELSE 'MEDIUM'
    END AS severity
FROM laundering_chain lc
JOIN accounts a_origin ON lc.origin_account  = a_origin.account_id
JOIN accounts a_final  ON lc.current_account = a_final.account_id
WHERE lc.chain_depth >= 3
ORDER BY lc.chain_depth DESC, lc.total_amount DESC;
