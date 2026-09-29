# 🕵️ SQL Fraud Detection Engine

> Build a database of banking transactions and make **SQL itself detect suspicious behavior**.

## Project Overview

This project demonstrates advanced SQL techniques (CTEs, window functions, self-joins, recursive CTEs, subqueries, indexing) applied to real-world fraud detection scenarios on a simulated banking dataset.

---

## 📦 Phases

| Phase | Focus | Status |
|-------|-------|--------|
| **Phase 1** | Schema Design + Seed Data | ✅ Done |
| **Phase 2** | Rapid-Fire Transactions (30-second rule) | ✅ Done |
| **Phase 3** | Unusual Amount Detection (Z-score / stddev) | ✅ Done |
| **Phase 4** | Geo-Impossible Transactions | ✅ Done |
| **Phase 5** | Smurfing — Many Accounts → One Receiver | ✅ Done |
| **Phase 6** | Money Laundering Chains (Recursive CTE) | ✅ Done |
| **Phase 7** | Fraud Score Dashboard + Indexes | ✅ Done |

---

## 🗃️ Tech Stack

- **Database:** SQLite (portable, zero-install) — scripts also compatible with PostgreSQL
- **Language:** SQL (pure)
- **Tools:** Python (for seeding fake data via `faker`)

---

## 📁 Folder Structure

```
sql-fraud-detection/
├── README.md
├── schema/
│   └── 01_create_tables.sql        # Phase 1 — DDL
├── seed/
│   └── 02_seed_data.py             # Phase 1 — Faker data generator
│   └── 02_seed_data.sql            # Phase 1 — Static seed (subset)
├── queries/
│   ├── 03_rapid_transactions.sql   # Phase 2
│   ├── 04_unusual_amounts.sql      # Phase 3
│   ├── 05_geo_impossible.sql       # Phase 4
│   ├── 06_smurfing.sql             # Phase 5
│   ├── 07_laundering_chains.sql    # Phase 6
│   └── 08_fraud_dashboard.sql      # Phase 7
├── indexes/
│   └── 09_indexes.sql              # Phase 7
└── db/
    └── fraud.db                    # SQLite database (generated)
```

---

## 🚀 Quick Start

```bash
# 1. Install Python deps
pip install faker

# 2. Generate the database
python seed/02_seed_data.py

# 3. Run any query
sqlite3 db/fraud.db < queries/03_rapid_transactions.sql
```

---

## 🔍 Detection Rules

### Phase 2 — Rapid-Fire Transactions
> Same account, 2+ transactions within 30 seconds → card testing attack

### Phase 3 — Unusual Amounts
> Amount > mean + 3×stddev of user's own history → statistical anomaly

### Phase 4 — Geo-Impossible Travel
> Two transactions from cities >500 km apart within 1 hour → physically impossible

### Phase 5 — Smurfing Detection
> One account receives money from 5+ unrelated accounts in 24 hours

### Phase 6 — Money Laundering Chains
> Recursive CTE walks A→B→C→D transfer chains up to depth 5

### Phase 7 — Fraud Score Dashboard
> Composite score aggregating all rule hits per account
