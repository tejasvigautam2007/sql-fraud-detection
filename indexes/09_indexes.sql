-- =============================================================
-- PHASE 7: Performance Indexes
-- Covers the most frequent WHERE/JOIN/ORDER patterns used
-- across all detection queries.
-- =============================================================

-- Index on transactions.account_id + timestamp (used by rapid-fire, geo, dashboard)
CREATE INDEX IF NOT EXISTS idx_txn_account_ts
    ON transactions(account_id, txn_timestamp);

-- Index on transaction type (filters debit/transfer frequently)
CREATE INDEX IF NOT EXISTS idx_txn_type
    ON transactions(txn_type);

-- Index on recipient_account_id (smurfing + laundering chain joins)
CREATE INDEX IF NOT EXISTS idx_txn_recipient
    ON transactions(recipient_account_id);

-- Index on location_id (geo-impossible joins to locations)
CREATE INDEX IF NOT EXISTS idx_txn_location
    ON transactions(location_id);

-- Composite index for transfer queries (type + recipient + timestamp)
CREATE INDEX IF NOT EXISTS idx_txn_transfer_lookup
    ON transactions(txn_type, recipient_account_id, txn_timestamp)
    WHERE txn_type = 'transfer';

-- Accounts lookup by owner name
CREATE INDEX IF NOT EXISTS idx_accounts_name
    ON accounts(owner_name);

-- Locations lookup by city
CREATE INDEX IF NOT EXISTS idx_locations_city
    ON locations(city);

-- Analyze to update SQLite query planner statistics
ANALYZE;
