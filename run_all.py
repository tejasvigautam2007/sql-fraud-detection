"""
run_all.py — SQL Fraud Detection Engine
Executes all 7 phases sequentially and prints formatted results.
"""

import sqlite3, os, sys, math, random, textwrap
from datetime import datetime, timedelta

DB_PATH = "db/fraud.db"
DIVIDER = "=" * 70

# ─────────────────────────────────────────────────────────────────────────────
# PRETTY PRINTER
# ─────────────────────────────────────────────────────────────────────────────
def banner(phase: int, title: str, technique: str):
    print(f"\n{DIVIDER}")
    print(f"  PHASE {phase}: {title}")
    print(f"  SQL: {technique}")
    print(DIVIDER)

def print_table(rows, headers):
    if not rows:
        print("  ⚪  No results (no fraud detected for this rule).")
        return
    widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
              for i, h in enumerate(headers)]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  " + "  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(v) if v is not None else "NULL" for v in row]))
    print(f"\n  ➜  {len(rows)} row(s) returned.")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — SEED
# ─────────────────────────────────────────────────────────────────────────────
def phase1_seed(conn):
    banner(1, "Schema + Seed Data", "DDL, INSERT, Faker")

    cur = conn.cursor()

    # ── DDL ──────────────────────────────────────────────────────────────────
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id   INTEGER PRIMARY KEY,
        owner_name   TEXT    NOT NULL,
        account_type TEXT    NOT NULL,
        created_at   TEXT    NOT NULL,
        country      TEXT    NOT NULL DEFAULT 'US',
        is_flagged   INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS locations (
        location_id INTEGER PRIMARY KEY,
        city        TEXT    NOT NULL,
        country     TEXT    NOT NULL,
        latitude    REAL    NOT NULL,
        longitude   REAL    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS transactions (
        txn_id               INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id           INTEGER NOT NULL REFERENCES accounts(account_id),
        txn_type             TEXT    NOT NULL,
        amount               REAL    NOT NULL,
        currency             TEXT    NOT NULL DEFAULT 'USD',
        txn_timestamp        TEXT    NOT NULL,
        location_id          INTEGER REFERENCES locations(location_id),
        merchant             TEXT,
        notes                TEXT,
        recipient_account_id INTEGER REFERENCES accounts(account_id)
    );

    CREATE TABLE IF NOT EXISTS fraud_alerts (
        alert_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id  INTEGER NOT NULL,
        rule_name   TEXT    NOT NULL,
        severity    TEXT    NOT NULL,
        detected_at TEXT    NOT NULL DEFAULT (datetime('now')),
        details     TEXT
    );

    CREATE VIEW IF NOT EXISTS account_spending_stats AS
    SELECT account_id,
           COUNT(*)                              AS total_txns,
           AVG(amount)                           AS avg_amount,
           AVG(amount*amount)-AVG(amount)*AVG(amount) AS variance_amount,
           MIN(amount) AS min_amount,
           MAX(amount) AS max_amount
    FROM transactions
    WHERE txn_type IN ('debit','transfer')
    GROUP BY account_id;
    """)

    # ── Locations ─────────────────────────────────────────────────────────────
    CITIES = [
        (1,"New York","US",40.7128,-74.0060),
        (2,"Los Angeles","US",34.0522,-118.2437),
        (3,"Chicago","US",41.8781,-87.6298),
        (4,"Houston","US",29.7604,-95.3698),
        (5,"Miami","US",25.7617,-80.1918),
        (6,"London","UK",51.5074,-0.1278),
        (7,"Paris","FR",48.8566,2.3522),
        (8,"Berlin","DE",52.5200,13.4050),
        (9,"Tokyo","JP",35.6762,139.6503),
        (10,"Sydney","AU",-33.8688,151.2093),
        (11,"Dubai","AE",25.2048,55.2708),
        (12,"Singapore","SG",1.3521,103.8198),
        (13,"Toronto","CA",43.6510,-79.3470),
        (14,"Mexico City","MX",19.4326,-99.1332),
        (15,"Sao Paulo","BR",-23.5505,-46.6333),
        (16,"Moscow","RU",55.7558,37.6173),
        (17,"Cape Town","ZA",-33.9249,18.4241),
        (18,"Lagos","NG",6.5244,3.3792),
        (19,"Mumbai","IN",19.0760,72.8777),
        (20,"Beijing","CN",39.9042,116.4074),
    ]
    cur.executemany("INSERT OR IGNORE INTO locations VALUES (?,?,?,?,?)", CITIES)

    # ── Accounts ──────────────────────────────────────────────────────────────
    try:
        from faker import Faker
        fake = Faker(); Faker.seed(42)
        use_faker = True
    except ImportError:
        use_faker = False
        print("  ⚠  faker not installed — using placeholder names.")

    random.seed(42)
    base_ts = datetime(2025, 9, 1, 12, 0, 0)

    def rand_ts(base, lo=-3600*24*180, hi=0):
        return (base + timedelta(seconds=random.randint(lo, hi))).strftime("%Y-%m-%d %H:%M:%S")

    NAMES = [f"User_{i}" for i in range(1, 51)]
    acc_types = ["checking","savings","business"]
    accounts = []
    for i in range(1, 51):
        name = fake.name() if use_faker else NAMES[i-1]
        accounts.append((i, name, random.choice(acc_types),
                         rand_ts(base_ts,-3600*24*365,-3600*24*30), "US", 0))
    cur.executemany("INSERT OR IGNORE INTO accounts VALUES (?,?,?,?,?,?)", accounts)

    # ── Normal transactions ───────────────────────────────────────────────────
    merchants = ["Amazon","Walmart","Netflix","Uber","Starbucks","Shell",
                 "Airbnb","McDonald's","CVS","Target","Best Buy","Apple","Spotify"]
    us_locs = [1,2,3,4,5,13]
    txn_id = 1
    normal = []
    for acc in range(1, 51):
        for _ in range(random.randint(30, 55)):
            amount = round(random.lognormvariate(3.5, 0.8), 2)
            normal.append((txn_id, acc, "debit", amount, "USD",
                           rand_ts(base_ts), random.choice(us_locs),
                           random.choice(merchants), None, None))
            txn_id += 1
    cur.executemany("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)", normal)

    # ── FRAUD 1: Rapid-fire (account 5) ──────────────────────────────────────
    rapid_base = datetime(2025, 8, 15, 3, 0, 0)
    for i in range(6):
        ts = (rapid_base + timedelta(seconds=i*3)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (txn_id, 5, "debit", round(random.uniform(0.5,2.0),2),
                     "USD", ts, 1, "Unknown Vendor","RAPID_FIRE_TEST", None))
        txn_id += 1

    # ── FRAUD 2: Unusual amount (account 10) ─────────────────────────────────
    for _ in range(20):
        cur.execute("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (txn_id,10,"debit",round(random.uniform(25,55),2),
                     "USD",rand_ts(base_ts),3,"Grocery Store",None,None))
        txn_id += 1
    cur.execute("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (txn_id,10,"debit",8500.00,"USD",
                 "2025-08-20 14:00:00",2,"Luxury Shop","UNUSUAL_AMOUNT_TEST",None))
    txn_id += 1

    # ── FRAUD 3: Geo-impossible (account 15) ─────────────────────────────────
    cur.execute("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (txn_id,15,"debit",120.00,"USD",
                 "2025-07-10 09:00:00",1,"JFK Airport Shop","GEO_TEST",None))
    txn_id += 1
    cur.execute("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                (txn_id,15,"debit",340.00,"USD",
                 "2025-07-10 09:40:00",9,"Tokyo Mart","GEO_TEST",None))
    txn_id += 1

    # ── FRAUD 4: Smurfing (accounts 20-27 → account 30) ──────────────────────
    smurf_base = datetime(2025, 6, 5, 10, 0, 0)
    for sender in range(20, 28):
        ts = (smurf_base + timedelta(minutes=random.randint(0,360))).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (txn_id, sender,"transfer",round(random.uniform(900,9999),2),
                     "USD",ts,1,None,"SMURFING_TEST",30))
        txn_id += 1

    # ── FRAUD 5: Laundering chain 40→41→42→43→44 ─────────────────────────────
    chain_base = datetime(2025, 5, 1, 8, 0, 0)
    chain = [(40,41),(41,42),(42,43),(43,44)]
    for i,(src,dst) in enumerate(chain):
        ts = (chain_base + timedelta(hours=i*10)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (txn_id,src,"transfer",5000.00-i*200,"USD",ts,1,
                     None,"LAUNDERING_CHAIN_TEST",dst))
        txn_id += 1

    conn.commit()

    # Stats
    total_txns = cur.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    total_acc  = cur.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    print(f"  ✅ Seeded {total_acc} accounts, {total_txns} transactions")
    print(f"  📁 DB: {os.path.abspath(DB_PATH)}")
    print(f"  🔴 Injected fraud: rapid-fire(acct 5), unusual-amt(acct 10),")
    print(f"     geo-impossible(acct 15), smurfing(accts 20-27→30),")
    print(f"     laundering-chain(40→41→42→43→44)")

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — RAPID-FIRE
# ─────────────────────────────────────────────────────────────────────────────
def phase2_rapid_fire(conn):
    banner(2, "Rapid-Fire Transaction Detection", "LAG() Window Function, CTE")
    cur = conn.cursor()
    rows = cur.execute("""
    WITH txn_with_prev AS (
        SELECT account_id, amount, txn_timestamp,
               LAG(txn_timestamp) OVER (
                   PARTITION BY account_id ORDER BY txn_timestamp
               ) AS prev_ts
        FROM transactions
        WHERE txn_type IN ('debit','transfer')
    ),
    rapid_pairs AS (
        SELECT account_id,
               CAST((julianday(txn_timestamp)-julianday(prev_ts))*86400 AS INTEGER) AS secs,
               txn_timestamp, prev_ts
        FROM txn_with_prev
        WHERE prev_ts IS NOT NULL
          AND (julianday(txn_timestamp)-julianday(prev_ts))*86400 <= 30
    )
    SELECT rp.account_id,
           a.owner_name,
           COUNT(*)              AS rapid_pairs,
           MIN(rp.secs)          AS min_gap_sec,
           MIN(rp.prev_ts)       AS window_start,
           MAX(rp.txn_timestamp) AS window_end
    FROM rapid_pairs rp
    JOIN accounts a USING(account_id)
    GROUP BY rp.account_id, a.owner_name
    ORDER BY rapid_pairs DESC
    """).fetchall()

    print_table(rows, ["acct_id","owner","rapid_pairs","min_gap_sec","window_start","window_end"])

    # Write alerts
    for r in rows:
        severity = "CRITICAL" if r[2] >= 5 else "HIGH" if r[2] >= 3 else "MEDIUM"
        conn.execute("""INSERT INTO fraud_alerts(account_id,rule_name,severity,details)
                        VALUES(?,?,?,?)""",
                     (r[0],"RAPID_FIRE",severity,
                      f"{r[2]} rapid pairs, min gap {r[3]}s"))
    conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — UNUSUAL AMOUNTS
# ─────────────────────────────────────────────────────────────────────────────
def phase3_unusual_amounts(conn):
    banner(3, "Unusual Amount Detection (Z-Score)", "Subquery, Manual STDDEV, CTE")
    cur = conn.cursor()
    rows = cur.execute("""
    WITH user_stats AS (
        SELECT account_id,
               AVG(amount) AS mu,
               SQRT(MAX(0, AVG(amount*amount)-AVG(amount)*AVG(amount))) AS sigma,
               COUNT(*) AS n
        FROM transactions
        WHERE txn_type IN ('debit','transfer')
        GROUP BY account_id HAVING COUNT(*) >= 5
    ),
    flagged AS (
        SELECT t.txn_id, t.account_id, a.owner_name,
               ROUND(t.amount,2)                  AS amount,
               ROUND(us.mu,2)                     AS user_avg,
               ROUND(us.sigma,2)                  AS user_stddev,
               ROUND((t.amount-us.mu)/us.sigma,2) AS z_score,
               ROUND(us.mu+3*us.sigma,2)          AS threshold,
               t.txn_timestamp, t.merchant
        FROM transactions t
        JOIN user_stats us USING(account_id)
        JOIN accounts a    USING(account_id)
        WHERE t.txn_type IN ('debit','transfer')
          AND us.sigma > 0
          AND t.amount > us.mu + 3*us.sigma
    )
    SELECT txn_id,account_id,owner_name,amount,user_avg,user_stddev,
           z_score,threshold,txn_timestamp,merchant
    FROM flagged ORDER BY z_score DESC
    """).fetchall()

    print_table(rows, ["txn_id","acct_id","owner","amount","avg","stddev",
                        "z_score","threshold","timestamp","merchant"])

    for r in rows:
        severity = "CRITICAL" if r[6] > 10 else "HIGH" if r[6] > 5 else "MEDIUM"
        conn.execute("""INSERT INTO fraud_alerts(account_id,rule_name,severity,details)
                        VALUES(?,?,?,?)""",
                     (r[1],"UNUSUAL_AMOUNT",severity,
                      f"txn {r[0]}: ${r[3]}, z={r[6]}, threshold=${r[7]}"))
    conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 — GEO-IMPOSSIBLE
# ─────────────────────────────────────────────────────────────────────────────
def phase4_geo_impossible(conn):
    banner(4, "Geo-Impossible Travel Detection",
           "Self-Join, Inline Haversine (SIN/COS/ACOS/RADIANS), CASE")
    cur = conn.cursor()
    rows = cur.execute("""
    WITH geo AS (
        SELECT t.txn_id, t.account_id, t.txn_timestamp, t.amount,
               l.city, l.latitude, l.longitude
        FROM transactions t JOIN locations l ON t.location_id=l.location_id
        WHERE t.txn_type IN ('debit','transfer')
    ),
    pairs AS (
        SELECT g1.account_id, a.owner_name,
               g1.txn_id AS txn1, g2.txn_id AS txn2,
               g1.city AS city1, g2.city AS city2,
               g1.txn_timestamp AS ts1, g2.txn_timestamp AS ts2,
               ROUND(ABS(julianday(g2.txn_timestamp)-julianday(g1.txn_timestamp))*1440,1) AS mins,
               ROUND(6371*ACOS(MIN(1.0,MAX(-1.0,
                   SIN(RADIANS(g1.latitude))*SIN(RADIANS(g2.latitude))+
                   COS(RADIANS(g1.latitude))*COS(RADIANS(g2.latitude))*
                   COS(RADIANS(g2.longitude)-RADIANS(g1.longitude))))),0) AS dist_km
        FROM geo g1 JOIN geo g2
          ON g1.account_id=g2.account_id
         AND g2.txn_timestamp > g1.txn_timestamp
         AND g1.city <> g2.city
        JOIN accounts a ON g1.account_id=a.account_id
        WHERE ABS(julianday(g2.txn_timestamp)-julianday(g1.txn_timestamp))*1440 <= 60
    )
    SELECT account_id, owner_name, txn1, txn2, city1, city2,
           ts1, ts2, mins, dist_km,
           ROUND(dist_km/(mins/60.0),0) AS req_speed_kmh,
           CASE WHEN dist_km>5000 THEN 'CRITICAL'
                WHEN dist_km>2000 THEN 'HIGH' ELSE 'MEDIUM' END AS severity
    FROM pairs WHERE dist_km > 500
    ORDER BY dist_km DESC
    """).fetchall()

    print_table(rows, ["acct_id","owner","txn1","txn2","city1","city2",
                        "ts1","ts2","mins","dist_km","req_kmh","severity"])

    for r in rows:
        conn.execute("""INSERT INTO fraud_alerts(account_id,rule_name,severity,details)
                        VALUES(?,?,?,?)""",
                     (r[0],"GEO_IMPOSSIBLE",r[11],
                      f"{r[4]}→{r[5]} in {r[8]}min, {r[9]}km apart, req {r[10]}km/h"))
    conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5 — SMURFING
# ─────────────────────────────────────────────────────────────────────────────
def phase5_smurfing(conn):
    banner(5, "Smurfing Detection (Many Senders → One Receiver)",
           "COUNT(DISTINCT), Date Bucketing, CTE")
    cur = conn.cursor()
    rows = cur.execute("""
    WITH inbound AS (
        SELECT recipient_account_id AS recv, account_id AS sender,
               amount, DATE(txn_timestamp) AS d
        FROM transactions
        WHERE txn_type='transfer' AND recipient_account_id IS NOT NULL
    ),
    daily AS (
        SELECT recv, d,
               COUNT(DISTINCT sender)   AS uniq_senders,
               COUNT(*)                 AS transfer_count,
               ROUND(SUM(amount),2)     AS total_recv,
               ROUND(AVG(amount),2)     AS avg_transfer,
               COUNT(CASE WHEN amount BETWEEN 8000 AND 9999 THEN 1 END) AS near_threshold
        FROM inbound GROUP BY recv, d
        HAVING uniq_senders >= 5
    )
    SELECT d.recv AS account_id, a.owner_name, d.d AS txn_date,
           d.uniq_senders, d.transfer_count,
           d.total_recv, d.avg_transfer, d.near_threshold,
           CASE WHEN d.uniq_senders>=10 OR d.near_threshold>=3 THEN 'CRITICAL'
                WHEN d.uniq_senders>=7                          THEN 'HIGH'
                ELSE 'MEDIUM' END AS severity
    FROM daily d JOIN accounts a ON d.recv=a.account_id
    ORDER BY d.uniq_senders DESC, d.total_recv DESC
    """).fetchall()

    print_table(rows, ["acct_id","owner","date","uniq_senders","transfers",
                        "total_recv","avg_transfer","near_threshold","severity"])

    for r in rows:
        conn.execute("""INSERT INTO fraud_alerts(account_id,rule_name,severity,details)
                        VALUES(?,?,?,?)""",
                     (r[0],"SMURFING",r[8],
                      f"{r[3]} senders on {r[2]}, total ${r[5]}"))
    conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6 — LAUNDERING CHAINS
# ─────────────────────────────────────────────────────────────────────────────
def phase6_laundering(conn):
    banner(6, "Money Laundering Chain Detection (A→B→C→D)",
           "WITH RECURSIVE CTE, Cycle Guard, Depth Limiting")
    cur = conn.cursor()
    rows = cur.execute("""
    WITH RECURSIVE chain(origin, current, path, depth, amount, start_ts, end_ts) AS (
        SELECT account_id, recipient_account_id,
               CAST(account_id AS TEXT)||'->'||CAST(recipient_account_id AS TEXT),
               1, amount, txn_timestamp, txn_timestamp
        FROM transactions
        WHERE txn_type='transfer' AND recipient_account_id IS NOT NULL

        UNION ALL

        SELECT c.origin, t.recipient_account_id,
               c.path||'->'||CAST(t.recipient_account_id AS TEXT),
               c.depth+1,
               MIN(c.amount, t.amount),
               c.start_ts, t.txn_timestamp
        FROM chain c
        JOIN transactions t
          ON t.account_id = c.current
         AND t.txn_type='transfer'
         AND t.recipient_account_id IS NOT NULL
         AND t.txn_timestamp > c.end_ts
         AND t.recipient_account_id <> c.origin
         AND INSTR(c.path, CAST(t.recipient_account_id AS TEXT)) = 0
        WHERE c.depth < 5
    )
    SELECT c.origin, ao.owner_name AS origin_name,
           c.current AS final_acct, af.owner_name AS final_name,
           c.path, c.depth AS hops,
           ROUND(c.amount,2) AS min_amount,
           c.start_ts, c.end_ts,
           ROUND((julianday(c.end_ts)-julianday(c.start_ts))*24,1) AS duration_hrs,
           CASE WHEN c.depth>=4 THEN 'CRITICAL'
                WHEN c.depth=3  THEN 'HIGH' ELSE 'MEDIUM' END AS severity
    FROM chain c
    JOIN accounts ao ON c.origin  = ao.account_id
    JOIN accounts af ON c.current = af.account_id
    WHERE c.depth >= 3
    ORDER BY c.depth DESC, c.amount DESC
    LIMIT 20
    """).fetchall()

    print_table(rows, ["origin","origin_name","final","final_name","path",
                        "hops","min_$","start_ts","end_ts","hrs","severity"])

    for r in rows:
        conn.execute("""INSERT INTO fraud_alerts(account_id,rule_name,severity,details)
                        VALUES(?,?,?,?)""",
                     (r[0],"LAUNDERING_CHAIN",r[10],
                      f"chain: {r[4]}, {r[5]} hops, ${r[6]}, {r[9]}hrs"))
    conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 7 — INDEXES + DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
def phase7_dashboard(conn):
    banner(7, "Performance Indexes + Fraud Score Dashboard",
           "Multiple CTEs, COALESCE, Weighted Scoring, UNION ALL")

    # Apply indexes
    conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_txn_account_ts   ON transactions(account_id,txn_timestamp);
    CREATE INDEX IF NOT EXISTS idx_txn_type         ON transactions(txn_type);
    CREATE INDEX IF NOT EXISTS idx_txn_recipient    ON transactions(recipient_account_id);
    CREATE INDEX IF NOT EXISTS idx_txn_location     ON transactions(location_id);
    CREATE INDEX IF NOT EXISTS idx_accounts_name    ON accounts(owner_name);
    CREATE INDEX IF NOT EXISTS idx_locations_city   ON locations(city);
    ANALYZE;
    """)
    print("  ✅ 6 performance indexes created + ANALYZE run")

    cur = conn.cursor()

    # Fraud alert summary
    print("\n  📋 Fraud Alerts Summary (all phases):")
    alerts = cur.execute("""
        SELECT rule_name, severity, COUNT(*) AS hits
        FROM fraud_alerts
        GROUP BY rule_name, severity
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                               WHEN 'MEDIUM' THEN 3 ELSE 4 END
    """).fetchall()
    print_table(alerts, ["rule","severity","hits"])

    # Dashboard
    print("\n  🔴 Fraud Score Dashboard (accounts with score > 0):")
    rows = cur.execute("""
    WITH rf AS (
        SELECT account_id, COUNT(*) AS rapid_hits
        FROM fraud_alerts WHERE rule_name='RAPID_FIRE' GROUP BY account_id
    ),
    ua AS (
        SELECT account_id, COUNT(*) AS unusual_hits
        FROM fraud_alerts WHERE rule_name='UNUSUAL_AMOUNT' GROUP BY account_id
    ),
    gi AS (
        SELECT account_id, COUNT(*) AS geo_hits
        FROM fraud_alerts WHERE rule_name='GEO_IMPOSSIBLE' GROUP BY account_id
    ),
    sm AS (
        SELECT account_id, COUNT(*) AS smurf_hits
        FROM fraud_alerts WHERE rule_name='SMURFING' GROUP BY account_id
    ),
    lc AS (
        SELECT account_id, COUNT(*) AS chain_hits
        FROM fraud_alerts WHERE rule_name='LAUNDERING_CHAIN' GROUP BY account_id
    )
    SELECT a.account_id, a.owner_name, a.account_type,
           COALESCE(rf.rapid_hits,  0) AS rapid,
           COALESCE(ua.unusual_hits,0) AS unusual,
           COALESCE(gi.geo_hits,    0) AS geo,
           COALESCE(sm.smurf_hits,  0) AS smurf,
           COALESCE(lc.chain_hits,  0) AS chain,
           (COALESCE(rf.rapid_hits, 0)*10 +
            COALESCE(ua.unusual_hits,0)*15 +
            COALESCE(gi.geo_hits,   0)*25 +
            COALESCE(sm.smurf_hits, 0)*20 +
            COALESCE(lc.chain_hits, 0)*30) AS fraud_score,
           CASE
             WHEN (COALESCE(rf.rapid_hits,0)*10+COALESCE(ua.unusual_hits,0)*15+
                   COALESCE(gi.geo_hits,0)*25+COALESCE(sm.smurf_hits,0)*20+
                   COALESCE(lc.chain_hits,0)*30) >= 100 THEN 'CRITICAL'
             WHEN (COALESCE(rf.rapid_hits,0)*10+COALESCE(ua.unusual_hits,0)*15+
                   COALESCE(gi.geo_hits,0)*25+COALESCE(sm.smurf_hits,0)*20+
                   COALESCE(lc.chain_hits,0)*30) >= 50  THEN 'HIGH'
             WHEN (COALESCE(rf.rapid_hits,0)*10+COALESCE(ua.unusual_hits,0)*15+
                   COALESCE(gi.geo_hits,0)*25+COALESCE(sm.smurf_hits,0)*20+
                   COALESCE(lc.chain_hits,0)*30) >= 20  THEN 'MEDIUM'
             ELSE 'LOW'
           END AS risk_tier
    FROM accounts a
    LEFT JOIN rf USING(account_id)
    LEFT JOIN ua USING(account_id)
    LEFT JOIN gi USING(account_id)
    LEFT JOIN sm USING(account_id)
    LEFT JOIN lc USING(account_id)
    WHERE (COALESCE(rf.rapid_hits,0)+COALESCE(ua.unusual_hits,0)+
           COALESCE(gi.geo_hits,0)+COALESCE(sm.smurf_hits,0)+
           COALESCE(lc.chain_hits,0)) > 0
    ORDER BY fraud_score DESC
    """).fetchall()
    print_table(rows, ["acct_id","owner","type","rapid","unusual","geo",
                        "smurf","chain","score","risk"])

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs("db", exist_ok=True)

    # Fresh run — delete old DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    start = datetime.now()
    print(f"\n{'#'*70}")
    print(f"  🕵️  SQL FRAUD DETECTION ENGINE — Full Run")
    print(f"  Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}")

    phase1_seed(conn)
    phase2_rapid_fire(conn)
    phase3_unusual_amounts(conn)
    phase4_geo_impossible(conn)
    phase5_smurfing(conn)
    phase6_laundering(conn)
    phase7_dashboard(conn)

    conn.close()
    elapsed = (datetime.now() - start).total_seconds()

    print(f"\n{'#'*70}")
    print(f"  ✅ ALL 7 PHASES COMPLETE  ({elapsed:.2f}s)")
    print(f"  📁 DB saved: {os.path.abspath(DB_PATH)}")
    print(f"{'#'*70}\n")
