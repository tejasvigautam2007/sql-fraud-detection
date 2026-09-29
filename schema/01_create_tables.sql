-- =============================================================
-- PHASE 1: Schema Design
-- SQL Fraud Detection Engine
-- =============================================================

-- Accounts table: represents bank customers
CREATE TABLE IF NOT EXISTS accounts (
    account_id   INTEGER PRIMARY KEY,
    owner_name   TEXT    NOT NULL,
    account_type TEXT    NOT NULL CHECK(account_type IN ('checking','savings','business')),
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    country      TEXT    NOT NULL DEFAULT 'US',
    is_flagged   INTEGER NOT NULL DEFAULT 0  -- 1 = already known bad actor
);

-- Locations: cities with lat/lon for geo-impossible detection
CREATE TABLE IF NOT EXISTS locations (
    location_id INTEGER PRIMARY KEY,
    city        TEXT    NOT NULL,
    country     TEXT    NOT NULL,
    latitude    REAL    NOT NULL,
    longitude   REAL    NOT NULL
);

-- Transactions: every debit/credit movement
CREATE TABLE IF NOT EXISTS transactions (
    txn_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id     INTEGER NOT NULL REFERENCES accounts(account_id),
    txn_type       TEXT    NOT NULL CHECK(txn_type IN ('debit','credit','transfer')),
    amount         REAL    NOT NULL CHECK(amount > 0),
    currency       TEXT    NOT NULL DEFAULT 'USD',
    txn_timestamp  TEXT    NOT NULL,          -- ISO-8601 datetime string
    location_id    INTEGER REFERENCES locations(location_id),
    merchant       TEXT,                      -- merchant name for debit txns
    notes          TEXT,
    -- For transfers: who received the money
    recipient_account_id INTEGER REFERENCES accounts(account_id)
);

-- Fraud alerts: output table written to by detection queries
CREATE TABLE IF NOT EXISTS fraud_alerts (
    alert_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL REFERENCES accounts(account_id),
    rule_name     TEXT    NOT NULL,  -- e.g. 'RAPID_FIRE', 'GEO_IMPOSSIBLE'
    severity      TEXT    NOT NULL CHECK(severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
    detected_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    details       TEXT               -- JSON-ish description of the anomaly
);

-- =============================================================
-- Useful views
-- =============================================================

-- Per-account spending stats (used by Phase 3)
CREATE VIEW IF NOT EXISTS account_spending_stats AS
SELECT
    account_id,
    COUNT(*)        AS total_txns,
    AVG(amount)     AS avg_amount,
    -- SQLite doesn't have STDDEV; we compute variance manually
    AVG(amount * amount) - AVG(amount) * AVG(amount) AS variance_amount,
    MIN(amount)     AS min_amount,
    MAX(amount)     AS max_amount
FROM transactions
WHERE txn_type IN ('debit','transfer')
GROUP BY account_id;
