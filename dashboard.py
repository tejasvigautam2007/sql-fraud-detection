"""
dashboard.py — SQL Fraud Detection Engine
Interactive Flask web dashboard with live query execution.
Run: python dashboard.py  →  open http://localhost:5000
"""

import sqlite3, os, json, random, math
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
DB_PATH = "db/fraud.db"

# ─────────────────────────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def db_exists():
    return os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0

# ─────────────────────────────────────────────────────────────────
# SEED  (copy of run_all.py phase1 — kept in sync)
# ─────────────────────────────────────────────────────────────────
def seed_database():
    from faker import Faker
    fake = Faker(); Faker.seed(42); random.seed(42)

    os.makedirs("db", exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS accounts (
        account_id INTEGER PRIMARY KEY, owner_name TEXT NOT NULL,
        account_type TEXT NOT NULL, created_at TEXT NOT NULL,
        country TEXT NOT NULL DEFAULT 'US', is_flagged INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS locations (
        location_id INTEGER PRIMARY KEY, city TEXT NOT NULL,
        country TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS transactions (
        txn_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL,
        txn_type TEXT NOT NULL, amount REAL NOT NULL,
        currency TEXT NOT NULL DEFAULT 'USD', txn_timestamp TEXT NOT NULL,
        location_id INTEGER, merchant TEXT, notes TEXT,
        recipient_account_id INTEGER);
    CREATE TABLE IF NOT EXISTS fraud_alerts (
        alert_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER NOT NULL,
        rule_name TEXT NOT NULL, severity TEXT NOT NULL,
        detected_at TEXT NOT NULL DEFAULT (datetime('now')), details TEXT);
    """)

    CITIES = [
        (1,"New York","US",40.7128,-74.0060),(2,"Los Angeles","US",34.0522,-118.2437),
        (3,"Chicago","US",41.8781,-87.6298),(4,"Houston","US",29.7604,-95.3698),
        (5,"Miami","US",25.7617,-80.1918),(6,"London","UK",51.5074,-0.1278),
        (7,"Paris","FR",48.8566,2.3522),(8,"Berlin","DE",52.5200,13.4050),
        (9,"Tokyo","JP",35.6762,139.6503),(10,"Sydney","AU",-33.8688,151.2093),
        (11,"Dubai","AE",25.2048,55.2708),(12,"Singapore","SG",1.3521,103.8198),
        (13,"Toronto","CA",43.6510,-79.3470),(14,"Mexico City","MX",19.4326,-99.1332),
        (15,"Sao Paulo","BR",-23.5505,-46.6333),(16,"Moscow","RU",55.7558,37.6173),
        (17,"Cape Town","ZA",-33.9249,18.4241),(18,"Lagos","NG",6.5244,3.3792),
        (19,"Mumbai","IN",19.0760,72.8777),(20,"Beijing","CN",39.9042,116.4074),
    ]
    conn.executemany("INSERT OR IGNORE INTO locations VALUES(?,?,?,?,?)", CITIES)

    base_ts = datetime(2025, 9, 1, 12, 0, 0)
    def rand_ts(base, lo=-3600*24*180, hi=0):
        return (base+timedelta(seconds=random.randint(lo,hi))).strftime("%Y-%m-%d %H:%M:%S")

    acc_types = ["checking","savings","business"]
    accounts = [(i, fake.name(), random.choice(acc_types),
                 rand_ts(base_ts,-3600*24*365,-3600*24*30),"US",0) for i in range(1,51)]
    conn.executemany("INSERT OR IGNORE INTO accounts VALUES(?,?,?,?,?,?)", accounts)

    merchants = ["Amazon","Walmart","Netflix","Uber","Starbucks","Shell",
                 "Airbnb","McDonald's","CVS","Target","Best Buy","Apple","Spotify"]
    us_locs = [1,2,3,4,5,13]
    txn_id = 1
    normal = []
    for acc in range(1,51):
        for _ in range(random.randint(30,55)):
            normal.append((txn_id,acc,"debit",round(random.lognormvariate(3.5,0.8),2),
                           "USD",rand_ts(base_ts),random.choice(us_locs),
                           random.choice(merchants),None,None))
            txn_id+=1
    conn.executemany("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?)", normal)

    # Fraud 1: rapid-fire
    rb = datetime(2025,8,15,3,0,0)
    for i in range(6):
        ts=(rb+timedelta(seconds=i*3)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (txn_id,5,"debit",round(random.uniform(0.5,2.0),2),"USD",ts,1,"Unknown Vendor","RAPID_FIRE_TEST",None)); txn_id+=1
    # Fraud 2: unusual amount
    for _ in range(20):
        conn.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (txn_id,10,"debit",round(random.uniform(25,55),2),"USD",rand_ts(base_ts),3,"Grocery Store",None,None)); txn_id+=1
    conn.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (txn_id,10,"debit",8500.00,"USD","2025-08-20 14:00:00",2,"Luxury Shop","UNUSUAL_AMOUNT_TEST",None)); txn_id+=1
    # Fraud 3: geo
    conn.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (txn_id,15,"debit",120.00,"USD","2025-07-10 09:00:00",1,"JFK Airport Shop","GEO_TEST",None)); txn_id+=1
    conn.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?)",
                 (txn_id,15,"debit",340.00,"USD","2025-07-10 09:40:00",9,"Tokyo Mart","GEO_TEST",None)); txn_id+=1
    # Fraud 4: smurfing
    sb=datetime(2025,6,5,10,0,0)
    for sender in range(20,28):
        ts=(sb+timedelta(minutes=random.randint(0,360))).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (txn_id,sender,"transfer",round(random.uniform(900,9999),2),"USD",ts,1,None,"SMURFING_TEST",30)); txn_id+=1
    # Fraud 5: chain
    cb=datetime(2025,5,1,8,0,0)
    for i,(src,dst) in enumerate([(40,41),(41,42),(42,43),(43,44)]):
        ts=(cb+timedelta(hours=i*10)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT OR IGNORE INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (txn_id,src,"transfer",5000.0-i*200,"USD",ts,1,None,"LAUNDERING_CHAIN_TEST",dst)); txn_id+=1

    conn.commit(); conn.close()

def run_all_detections():
    conn = get_conn()
    cur = conn.cursor()

    # Clear old alerts
    conn.execute("DELETE FROM fraud_alerts")

    # Phase 2: Rapid fire
    rows = cur.execute("""
    WITH p AS (SELECT account_id,txn_timestamp,
        LAG(txn_timestamp) OVER(PARTITION BY account_id ORDER BY txn_timestamp) prev
        FROM transactions WHERE txn_type IN('debit','transfer')),
    r AS (SELECT account_id,
        CAST((julianday(txn_timestamp)-julianday(prev))*86400 AS INTEGER) secs,
        txn_timestamp,prev FROM p
        WHERE prev IS NOT NULL AND (julianday(txn_timestamp)-julianday(prev))*86400<=30)
    SELECT r.account_id,a.owner_name,COUNT(*) pairs,MIN(r.secs) min_sec,
           MIN(r.prev) wstart,MAX(r.txn_timestamp) wend
    FROM r JOIN accounts a USING(account_id)
    GROUP BY r.account_id,a.owner_name ORDER BY pairs DESC""").fetchall()
    for row in rows:
        sev="CRITICAL" if row[2]>=5 else "HIGH" if row[2]>=3 else "MEDIUM"
        conn.execute("INSERT INTO fraud_alerts(account_id,rule_name,severity,details) VALUES(?,?,?,?)",
                     (row[0],"RAPID_FIRE",sev,f"{row[2]} pairs, min_gap={row[3]}s"))

    # Phase 3: Unusual amount
    rows = cur.execute("""
    WITH s AS(SELECT account_id,AVG(amount) mu,
        SQRT(MAX(0,AVG(amount*amount)-AVG(amount)*AVG(amount))) sigma
        FROM transactions WHERE txn_type IN('debit','transfer')
        GROUP BY account_id HAVING COUNT(*)>=5)
    SELECT t.txn_id,t.account_id,a.owner_name,ROUND(t.amount,2),
           ROUND(s.mu,2),ROUND(s.sigma,2),
           ROUND((t.amount-s.mu)/s.sigma,2) z,
           ROUND(s.mu+3*s.sigma,2) thresh,t.txn_timestamp,t.merchant
    FROM transactions t JOIN s USING(account_id) JOIN accounts a USING(account_id)
    WHERE t.txn_type IN('debit','transfer') AND s.sigma>0
      AND t.amount>s.mu+3*s.sigma ORDER BY z DESC""").fetchall()
    for row in rows:
        sev="CRITICAL" if row[6]>10 else "HIGH" if row[6]>5 else "MEDIUM"
        conn.execute("INSERT INTO fraud_alerts(account_id,rule_name,severity,details) VALUES(?,?,?,?)",
                     (row[1],"UNUSUAL_AMOUNT",sev,f"txn#{row[0]} ${row[3]} z={row[6]}"))

    # Phase 4: Geo impossible
    rows = cur.execute("""
    WITH g AS(SELECT t.txn_id,t.account_id,t.txn_timestamp,l.city,l.latitude,l.longitude
        FROM transactions t JOIN locations l ON t.location_id=l.location_id
        WHERE t.txn_type IN('debit','transfer')),
    p AS(SELECT g1.account_id,a.owner_name,g1.txn_id t1,g2.txn_id t2,
        g1.city c1,g2.city c2,g1.txn_timestamp ts1,g2.txn_timestamp ts2,
        ROUND(ABS(julianday(g2.txn_timestamp)-julianday(g1.txn_timestamp))*1440,1) mins,
        ROUND(6371*ACOS(MIN(1.0,MAX(-1.0,
            SIN(RADIANS(g1.latitude))*SIN(RADIANS(g2.latitude))+
            COS(RADIANS(g1.latitude))*COS(RADIANS(g2.latitude))*
            COS(RADIANS(g2.longitude)-RADIANS(g1.longitude))))),0) dist
        FROM g g1 JOIN g g2 ON g1.account_id=g2.account_id
            AND g2.txn_timestamp>g1.txn_timestamp AND g1.city<>g2.city
        JOIN accounts a ON g1.account_id=a.account_id
        WHERE ABS(julianday(g2.txn_timestamp)-julianday(g1.txn_timestamp))*1440<=60)
    SELECT account_id,owner_name,t1,t2,c1,c2,ts1,ts2,mins,dist,
        ROUND(dist/(mins/60.0),0) spd,
        CASE WHEN dist>5000 THEN 'CRITICAL' WHEN dist>2000 THEN 'HIGH' ELSE 'MEDIUM' END sev
    FROM p WHERE dist>500 ORDER BY dist DESC""").fetchall()
    for row in rows:
        conn.execute("INSERT INTO fraud_alerts(account_id,rule_name,severity,details) VALUES(?,?,?,?)",
                     (row[0],"GEO_IMPOSSIBLE",row[11],f"{row[4]}->{row[5]} {row[9]}km in {row[8]}min"))

    # Phase 5: Smurfing
    rows = cur.execute("""
    WITH i AS(SELECT recipient_account_id recv,account_id sender,amount,DATE(txn_timestamp) d
        FROM transactions WHERE txn_type='transfer' AND recipient_account_id IS NOT NULL),
    dy AS(SELECT recv,d,COUNT(DISTINCT sender) us,COUNT(*) tc,ROUND(SUM(amount),2) tot,ROUND(AVG(amount),2) avg
        FROM i GROUP BY recv,d HAVING us>=5)
    SELECT dy.recv,a.owner_name,dy.d,dy.us,dy.tc,dy.tot,dy.avg,
        CASE WHEN dy.us>=10 THEN 'CRITICAL' WHEN dy.us>=7 THEN 'HIGH' ELSE 'MEDIUM' END sev
    FROM dy JOIN accounts a ON dy.recv=a.account_id
    ORDER BY dy.us DESC""").fetchall()
    for row in rows:
        conn.execute("INSERT INTO fraud_alerts(account_id,rule_name,severity,details) VALUES(?,?,?,?)",
                     (row[0],"SMURFING",row[7],f"{row[3]} senders on {row[2]}, total ${row[5]}"))

    # Phase 6: Laundering
    rows = cur.execute("""
    WITH RECURSIVE c(origin,current,path,depth,amount,start_ts,end_ts) AS(
        SELECT account_id,recipient_account_id,
            CAST(account_id AS TEXT)||'->'||CAST(recipient_account_id AS TEXT),
            1,amount,txn_timestamp,txn_timestamp
        FROM transactions WHERE txn_type='transfer' AND recipient_account_id IS NOT NULL
        UNION ALL
        SELECT c.origin,t.recipient_account_id,
            c.path||'->'||CAST(t.recipient_account_id AS TEXT),
            c.depth+1,MIN(c.amount,t.amount),c.start_ts,t.txn_timestamp
        FROM c JOIN transactions t ON t.account_id=c.current
            AND t.txn_type='transfer' AND t.recipient_account_id IS NOT NULL
            AND t.txn_timestamp>c.end_ts AND t.recipient_account_id<>c.origin
            AND INSTR(c.path,CAST(t.recipient_account_id AS TEXT))=0
        WHERE c.depth<5)
    SELECT c.origin,ao.owner_name,c.current,af.owner_name,c.path,c.depth,
        ROUND(c.amount,2),c.start_ts,c.end_ts,
        ROUND((julianday(c.end_ts)-julianday(c.start_ts))*24,1),
        CASE WHEN c.depth>=4 THEN 'CRITICAL' WHEN c.depth=3 THEN 'HIGH' ELSE 'MEDIUM' END sev
    FROM c JOIN accounts ao ON c.origin=ao.account_id
           JOIN accounts af ON c.current=af.account_id
    WHERE c.depth>=3 ORDER BY c.depth DESC,c.amount DESC LIMIT 20""").fetchall()
    for row in rows:
        conn.execute("INSERT INTO fraud_alerts(account_id,rule_name,severity,details) VALUES(?,?,?,?)",
                     (row[0],"LAUNDERING_CHAIN",row[10],f"chain:{row[4]} {row[5]}hops ${row[6]}"))

    # Indexes
    conn.executescript("""
    CREATE INDEX IF NOT EXISTS idx_txn_account_ts ON transactions(account_id,txn_timestamp);
    CREATE INDEX IF NOT EXISTS idx_txn_type ON transactions(txn_type);
    CREATE INDEX IF NOT EXISTS idx_txn_recipient ON transactions(recipient_account_id);
    CREATE INDEX IF NOT EXISTS idx_txn_location ON transactions(location_id);
    CREATE INDEX IF NOT EXISTS idx_accounts_name ON accounts(owner_name);
    CREATE INDEX IF NOT EXISTS idx_locations_city ON locations(city);
    ANALYZE;""")

    conn.commit(); conn.close()

# ─────────────────────────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────────────────────────
@app.route("/api/seed", methods=["POST"])
def api_seed():
    try:
        seed_database()
        run_all_detections()
        return jsonify({"ok": True, "msg": "Database seeded and all phases executed."})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/api/status")
def api_status():
    if not db_exists():
        return jsonify({"ready": False})
    conn = get_conn()
    cur = conn.cursor()
    txns   = cur.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    accts  = cur.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    alerts = cur.execute("SELECT COUNT(*) FROM fraud_alerts").fetchone()[0]
    conn.close()
    return jsonify({"ready": True, "transactions": txns, "accounts": accts, "alerts": alerts})

@app.route("/api/summary")
def api_summary():
    if not db_exists(): return jsonify([])
    conn = get_conn()
    rows = conn.execute("""
        SELECT rule_name,severity,COUNT(*) cnt
        FROM fraud_alerts GROUP BY rule_name,severity
        ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                               WHEN 'MEDIUM' THEN 3 ELSE 4 END""").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/dashboard")
def api_dashboard():
    if not db_exists(): return jsonify([])
    conn = get_conn()
    rows = conn.execute("""
    WITH rf AS(SELECT account_id,COUNT(*) v FROM fraud_alerts WHERE rule_name='RAPID_FIRE' GROUP BY account_id),
         ua AS(SELECT account_id,COUNT(*) v FROM fraud_alerts WHERE rule_name='UNUSUAL_AMOUNT' GROUP BY account_id),
         gi AS(SELECT account_id,COUNT(*) v FROM fraud_alerts WHERE rule_name='GEO_IMPOSSIBLE' GROUP BY account_id),
         sm AS(SELECT account_id,COUNT(*) v FROM fraud_alerts WHERE rule_name='SMURFING' GROUP BY account_id),
         lc AS(SELECT account_id,COUNT(*) v FROM fraud_alerts WHERE rule_name='LAUNDERING_CHAIN' GROUP BY account_id)
    SELECT a.account_id,a.owner_name,a.account_type,
           COALESCE(rf.v,0) rapid,COALESCE(ua.v,0) unusual,
           COALESCE(gi.v,0) geo,COALESCE(sm.v,0) smurf,COALESCE(lc.v,0) chain,
           (COALESCE(rf.v,0)*10+COALESCE(ua.v,0)*15+COALESCE(gi.v,0)*25+
            COALESCE(sm.v,0)*20+COALESCE(lc.v,0)*30) score,
           CASE WHEN (COALESCE(rf.v,0)*10+COALESCE(ua.v,0)*15+COALESCE(gi.v,0)*25+
                      COALESCE(sm.v,0)*20+COALESCE(lc.v,0)*30)>=100 THEN 'CRITICAL'
                WHEN (COALESCE(rf.v,0)*10+COALESCE(ua.v,0)*15+COALESCE(gi.v,0)*25+
                      COALESCE(sm.v,0)*20+COALESCE(lc.v,0)*30)>=50  THEN 'HIGH'
                WHEN (COALESCE(rf.v,0)*10+COALESCE(ua.v,0)*15+COALESCE(gi.v,0)*25+
                      COALESCE(sm.v,0)*20+COALESCE(lc.v,0)*30)>=20  THEN 'MEDIUM'
                ELSE 'LOW' END risk
    FROM accounts a
    LEFT JOIN rf USING(account_id) LEFT JOIN ua USING(account_id)
    LEFT JOIN gi USING(account_id) LEFT JOIN sm USING(account_id)
    LEFT JOIN lc USING(account_id)
    WHERE (COALESCE(rf.v,0)+COALESCE(ua.v,0)+COALESCE(gi.v,0)+
           COALESCE(sm.v,0)+COALESCE(lc.v,0))>0
    ORDER BY score DESC""").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/phase/<int:phase>")
def api_phase(phase):
    if not db_exists(): return jsonify([])
    conn = get_conn()
    cur = conn.cursor()

    if phase == 2:
        rows = cur.execute("""
        WITH p AS(SELECT account_id,txn_timestamp,
            LAG(txn_timestamp) OVER(PARTITION BY account_id ORDER BY txn_timestamp) prev
            FROM transactions WHERE txn_type IN('debit','transfer')),
        r AS(SELECT account_id,
            CAST((julianday(txn_timestamp)-julianday(prev))*86400 AS INTEGER) secs,
            txn_timestamp,prev FROM p
            WHERE prev IS NOT NULL AND (julianday(txn_timestamp)-julianday(prev))*86400<=30)
        SELECT r.account_id,a.owner_name,COUNT(*) rapid_pairs,MIN(r.secs) min_gap_sec,
               MIN(r.prev) window_start,MAX(r.txn_timestamp) window_end
        FROM r JOIN accounts a USING(account_id)
        GROUP BY r.account_id,a.owner_name ORDER BY rapid_pairs DESC""").fetchall()

    elif phase == 3:
        rows = cur.execute("""
        WITH s AS(SELECT account_id,AVG(amount) mu,
            SQRT(MAX(0,AVG(amount*amount)-AVG(amount)*AVG(amount))) sigma
            FROM transactions WHERE txn_type IN('debit','transfer')
            GROUP BY account_id HAVING COUNT(*)>=5)
        SELECT t.txn_id,t.account_id,a.owner_name,ROUND(t.amount,2) amount,
               ROUND(s.mu,2) user_avg,ROUND(s.sigma,2) user_stddev,
               ROUND((t.amount-s.mu)/s.sigma,2) z_score,
               ROUND(s.mu+3*s.sigma,2) threshold,t.txn_timestamp,t.merchant
        FROM transactions t JOIN s USING(account_id) JOIN accounts a USING(account_id)
        WHERE t.txn_type IN('debit','transfer') AND s.sigma>0
          AND t.amount>s.mu+3*s.sigma ORDER BY z_score DESC LIMIT 30""").fetchall()

    elif phase == 4:
        rows = cur.execute("""
        WITH g AS(SELECT t.txn_id,t.account_id,t.txn_timestamp,l.city,l.latitude,l.longitude
            FROM transactions t JOIN locations l ON t.location_id=l.location_id
            WHERE t.txn_type IN('debit','transfer')),
        p AS(SELECT g1.account_id,a.owner_name,g1.txn_id txn1,g2.txn_id txn2,
            g1.city city1,g2.city city2,g1.txn_timestamp ts1,g2.txn_timestamp ts2,
            ROUND(ABS(julianday(g2.txn_timestamp)-julianday(g1.txn_timestamp))*1440,1) mins,
            ROUND(6371*ACOS(MIN(1.0,MAX(-1.0,
                SIN(RADIANS(g1.latitude))*SIN(RADIANS(g2.latitude))+
                COS(RADIANS(g1.latitude))*COS(RADIANS(g2.latitude))*
                COS(RADIANS(g2.longitude)-RADIANS(g1.longitude))))),0) dist_km
            FROM g g1 JOIN g g2 ON g1.account_id=g2.account_id
                AND g2.txn_timestamp>g1.txn_timestamp AND g1.city<>g2.city
            JOIN accounts a ON g1.account_id=a.account_id
            WHERE ABS(julianday(g2.txn_timestamp)-julianday(g1.txn_timestamp))*1440<=60)
        SELECT account_id,owner_name,txn1,txn2,city1,city2,ts1,ts2,mins,dist_km,
            ROUND(dist_km/(mins/60.0),0) req_speed_kmh,
            CASE WHEN dist_km>5000 THEN 'CRITICAL' WHEN dist_km>2000 THEN 'HIGH' ELSE 'MEDIUM' END severity
        FROM p WHERE dist_km>500 ORDER BY dist_km DESC""").fetchall()

    elif phase == 5:
        rows = cur.execute("""
        WITH i AS(SELECT recipient_account_id recv,account_id sender,amount,DATE(txn_timestamp) d
            FROM transactions WHERE txn_type='transfer' AND recipient_account_id IS NOT NULL),
        dy AS(SELECT recv,d,COUNT(DISTINCT sender) uniq_senders,COUNT(*) transfers,
            ROUND(SUM(amount),2) total_recv,ROUND(AVG(amount),2) avg_transfer,
            COUNT(CASE WHEN amount BETWEEN 8000 AND 9999 THEN 1 END) near_threshold
            FROM i GROUP BY recv,d HAVING uniq_senders>=5)
        SELECT dy.recv account_id,a.owner_name,dy.d txn_date,
               dy.uniq_senders,dy.transfers,dy.total_recv,dy.avg_transfer,dy.near_threshold,
               CASE WHEN dy.uniq_senders>=10 THEN 'CRITICAL'
                    WHEN dy.uniq_senders>=7  THEN 'HIGH' ELSE 'MEDIUM' END severity
        FROM dy JOIN accounts a ON dy.recv=a.account_id
        ORDER BY dy.uniq_senders DESC""").fetchall()

    elif phase == 6:
        rows = cur.execute("""
        WITH RECURSIVE c(origin,current,path,depth,amount,start_ts,end_ts) AS(
            SELECT account_id,recipient_account_id,
                CAST(account_id AS TEXT)||'->'||CAST(recipient_account_id AS TEXT),
                1,amount,txn_timestamp,txn_timestamp
            FROM transactions WHERE txn_type='transfer' AND recipient_account_id IS NOT NULL
            UNION ALL
            SELECT c.origin,t.recipient_account_id,
                c.path||'->'||CAST(t.recipient_account_id AS TEXT),
                c.depth+1,MIN(c.amount,t.amount),c.start_ts,t.txn_timestamp
            FROM c JOIN transactions t ON t.account_id=c.current
                AND t.txn_type='transfer' AND t.recipient_account_id IS NOT NULL
                AND t.txn_timestamp>c.end_ts AND t.recipient_account_id<>c.origin
                AND INSTR(c.path,CAST(t.recipient_account_id AS TEXT))=0
            WHERE c.depth<5)
        SELECT c.origin,ao.owner_name origin_name,c.current final_account,
               af.owner_name final_name,c.path,c.depth hops,
               ROUND(c.amount,2) min_amount,c.start_ts,c.end_ts,
               ROUND((julianday(c.end_ts)-julianday(c.start_ts))*24,1) duration_hrs,
               CASE WHEN c.depth>=4 THEN 'CRITICAL' WHEN c.depth=3 THEN 'HIGH' ELSE 'MEDIUM' END severity
        FROM c JOIN accounts ao ON c.origin=ao.account_id
               JOIN accounts af ON c.current=af.account_id
        WHERE c.depth>=3 ORDER BY c.depth DESC,c.amount DESC LIMIT 20""").fetchall()
    else:
        rows = []

    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/chart/severity")
def api_chart_severity():
    if not db_exists(): return jsonify({})
    conn = get_conn()
    rows = conn.execute("""
        SELECT severity, COUNT(*) cnt FROM fraud_alerts
        GROUP BY severity""").fetchall()
    conn.close()
    return jsonify({r["severity"]: r["cnt"] for r in rows})

@app.route("/api/chart/rules")
def api_chart_rules():
    if not db_exists(): return jsonify({})
    conn = get_conn()
    rows = conn.execute("""
        SELECT rule_name, COUNT(*) cnt FROM fraud_alerts
        GROUP BY rule_name""").fetchall()
    conn.close()
    return jsonify({r["rule_name"]: r["cnt"] for r in rows})

# ─────────────────────────────────────────────────────────────────
# MAIN HTML
# ─────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SQL Fraud Detection Engine</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#0a0e1a;--card:#111827;--card2:#1a2235;--border:#1e2d45;
    --text:#e2e8f0;--muted:#64748b;--accent:#3b82f6;
    --red:#ef4444;--orange:#f97316;--yellow:#eab308;--green:#22c55e;
    --critical:#ff2d55;--high:#ff9500;--medium:#ffd60a;--low:#30d158;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh}

  /* NAV */
  nav{background:var(--card);border-bottom:1px solid var(--border);
      padding:0 24px;display:flex;align-items:center;gap:16px;height:60px;
      position:sticky;top:0;z-index:100}
  .nav-logo{font-size:18px;font-weight:700;letter-spacing:-0.5px}
  .nav-logo span{color:var(--accent)}
  .nav-badge{background:#1e293b;border:1px solid var(--border);
             border-radius:20px;padding:3px 12px;font-size:12px;color:var(--muted)}
  .nav-right{margin-left:auto;display:flex;gap:10px;align-items:center}

  /* BUTTONS */
  .btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;
       border-radius:8px;border:none;cursor:pointer;font-size:13px;
       font-weight:600;transition:all .15s;text-decoration:none}
  .btn-primary{background:var(--accent);color:#fff}
  .btn-primary:hover{background:#2563eb}
  .btn-danger{background:var(--critical);color:#fff}
  .btn-danger:hover{background:#cc0033}
  .btn-ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
  .btn-ghost:hover{color:var(--text);border-color:var(--accent)}
  .btn:disabled{opacity:.5;cursor:not-allowed}

  /* LAYOUT */
  .container{max-width:1400px;margin:0 auto;padding:24px}
  .hero{text-align:center;padding:48px 24px 32px;
        background:linear-gradient(180deg,rgba(59,130,246,.08) 0%,transparent 100%)}
  .hero h1{font-size:32px;font-weight:800;letter-spacing:-1px;margin-bottom:8px}
  .hero h1 span{color:var(--accent)}
  .hero p{color:var(--muted);font-size:15px;max-width:600px;margin:0 auto 24px}

  /* STATUS BAR */
  #status-bar{display:flex;gap:16px;justify-content:center;flex-wrap:wrap;margin-bottom:32px}
  .stat-pill{background:var(--card);border:1px solid var(--border);
             border-radius:12px;padding:12px 20px;text-align:center;min-width:130px}
  .stat-pill .val{font-size:24px;font-weight:800;color:var(--accent)}
  .stat-pill .lbl{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}

  /* TABS */
  .tabs{display:flex;gap:2px;border-bottom:1px solid var(--border);margin-bottom:24px;overflow-x:auto}
  .tab{padding:10px 18px;cursor:pointer;font-size:13px;font-weight:600;
       color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;
       transition:all .15s}
  .tab:hover{color:var(--text)}
  .tab.active{color:var(--accent);border-bottom-color:var(--accent)}
  .tab-content{display:none}.tab-content.active{display:block}

  /* CARDS */
  .grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
  @media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr}}
  .card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px}
  .card-title{font-size:13px;font-weight:700;text-transform:uppercase;
              letter-spacing:.5px;color:var(--muted);margin-bottom:16px}

  /* PHASE CARDS */
  .phase-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-bottom:28px}
  .phase-card{background:var(--card);border:1px solid var(--border);border-radius:12px;
              padding:18px;cursor:pointer;transition:all .2s;position:relative;overflow:hidden}
  .phase-card::before{content:'';position:absolute;inset:0;
                      background:linear-gradient(135deg,var(--accent-c,#3b82f620),transparent);
                      opacity:0;transition:opacity .2s}
  .phase-card:hover::before{opacity:1}
  .phase-card:hover{border-color:var(--accent);transform:translateY(-2px)}
  .phase-num{font-size:11px;font-weight:700;color:var(--accent);text-transform:uppercase;
             letter-spacing:1px;margin-bottom:6px}
  .phase-title{font-size:15px;font-weight:700;margin-bottom:4px}
  .phase-tech{font-size:11px;color:var(--muted);margin-bottom:12px}
  .phase-badge{display:inline-block;padding:2px 8px;border-radius:20px;
               font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
  .badge-critical{background:rgba(255,45,85,.15);color:var(--critical);border:1px solid rgba(255,45,85,.3)}
  .badge-high{background:rgba(255,149,0,.15);color:var(--high);border:1px solid rgba(255,149,0,.3)}
  .badge-medium{background:rgba(255,214,10,.15);color:var(--medium);border:1px solid rgba(255,214,10,.3)}
  .badge-low{background:rgba(48,209,88,.15);color:var(--low);border:1px solid rgba(48,209,88,.3)}
  .badge-clean{background:rgba(100,116,139,.15);color:var(--muted);border:1px solid rgba(100,116,139,.3)}

  /* TABLE */
  .tbl-wrap{overflow-x:auto;border-radius:8px;border:1px solid var(--border)}
  table{width:100%;border-collapse:collapse;font-size:12px}
  th{background:var(--card2);padding:10px 12px;text-align:left;font-size:11px;
     font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;
     border-bottom:1px solid var(--border);white-space:nowrap}
  td{padding:9px 12px;border-bottom:1px solid rgba(30,45,69,.6);white-space:nowrap}
  tr:last-child td{border-bottom:none}
  tr:hover td{background:rgba(59,130,246,.04)}
  .score-bar{height:6px;border-radius:3px;background:var(--border);overflow:hidden;min-width:80px}
  .score-fill{height:100%;border-radius:3px;transition:width .6s ease}

  /* LOADER */
  .loader{display:inline-block;width:16px;height:16px;border:2px solid rgba(59,130,246,.3);
          border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite}
  @keyframes spin{to{transform:rotate(360deg)}}

  /* ALERT FLASH */
  #toast{position:fixed;bottom:24px;right:24px;background:var(--card2);
         border:1px solid var(--border);border-radius:10px;padding:14px 20px;
         font-size:13px;z-index:999;transform:translateY(80px);opacity:0;
         transition:all .3s;max-width:340px}
  #toast.show{transform:translateY(0);opacity:1}
  #toast.ok{border-left:3px solid var(--green)}
  #toast.err{border-left:3px solid var(--red)}

  /* DETAIL PANEL */
  #detail-panel{background:var(--card);border:1px solid var(--border);
                border-radius:12px;padding:20px;margin-top:16px;display:none}
  #detail-panel h3{font-size:14px;font-weight:700;margin-bottom:14px}

  canvas{max-height:260px}
  .empty{text-align:center;padding:40px;color:var(--muted);font-size:14px}
  code{background:#1e293b;padding:2px 6px;border-radius:4px;font-family:monospace;font-size:11px;color:#93c5fd}
</style>
</head>
<body>

<nav>
  <div class="nav-logo">&#128373;&#65039; SQL Fraud <span>Detection</span></div>
  <div class="nav-badge" id="db-badge">DB: Not loaded</div>
  <div class="nav-right">
    <button class="btn btn-primary" onclick="runSeed()" id="btn-seed">
      <span id="seed-icon">&#9654;</span> Seed &amp; Run All Phases
    </button>
  </div>
</nav>

<div class="hero">
  <h1>SQL Fraud <span>Detection Engine</span></h1>
  <p>Banking transaction anomaly detection using pure SQL — CTEs, window functions, recursive CTEs, self-joins, and Z-score analytics.</p>
  <div id="status-bar">
    <div class="stat-pill"><div class="val" id="s-accts">—</div><div class="lbl">Accounts</div></div>
    <div class="stat-pill"><div class="val" id="s-txns">—</div><div class="lbl">Transactions</div></div>
    <div class="stat-pill"><div class="val" id="s-alerts">—</div><div class="lbl">Alerts</div></div>
    <div class="stat-pill"><div class="val" style="color:var(--critical)" id="s-crit">—</div><div class="lbl">Critical</div></div>
  </div>
</div>

<div class="container">

  <!-- PHASE OVERVIEW CARDS -->
  <div class="phase-grid">
    <div class="phase-card" onclick="switchTab('p2');loadPhase(2)">
      <div class="phase-num">Phase 2</div>
      <div class="phase-title">&#9889; Rapid-Fire Transactions</div>
      <div class="phase-tech">LAG() window function · CTE</div>
      <span class="phase-badge badge-critical">Card Testing</span>
    </div>
    <div class="phase-card" onclick="switchTab('p3');loadPhase(3)">
      <div class="phase-num">Phase 3</div>
      <div class="phase-title">&#128200; Unusual Amounts</div>
      <div class="phase-tech">Manual STDDEV · Z-Score · Subquery</div>
      <span class="phase-badge badge-high">Statistical</span>
    </div>
    <div class="phase-card" onclick="switchTab('p4');loadPhase(4)">
      <div class="phase-num">Phase 4</div>
      <div class="phase-title">&#9992;&#65039; Geo-Impossible Travel</div>
      <div class="phase-tech">Self-join · Haversine · SIN/COS/ACOS</div>
      <span class="phase-badge badge-critical">Impossible</span>
    </div>
    <div class="phase-card" onclick="switchTab('p5');loadPhase(5)">
      <div class="phase-num">Phase 5</div>
      <div class="phase-title">&#128184; Smurfing</div>
      <div class="phase-tech">COUNT(DISTINCT) · Date Bucketing</div>
      <span class="phase-badge badge-high">Structuring</span>
    </div>
    <div class="phase-card" onclick="switchTab('p6');loadPhase(6)">
      <div class="phase-num">Phase 6</div>
      <div class="phase-title">&#128279; Laundering Chains</div>
      <div class="phase-tech">WITH RECURSIVE · Cycle Guard · Depth-5</div>
      <span class="phase-badge badge-critical">A→B→C→D</span>
    </div>
    <div class="phase-card" onclick="switchTab('dash')">
      <div class="phase-num">Phase 7</div>
      <div class="phase-title">&#128202; Fraud Score Dashboard</div>
      <div class="phase-tech">Weighted scoring · Multiple CTEs · Indexes</div>
      <span class="phase-badge badge-medium">Composite</span>
    </div>
  </div>

  <!-- TABS -->
  <div class="tabs">
    <div class="tab active" data-tab="dash" onclick="switchTab('dash')">&#128202; Dashboard</div>
    <div class="tab" data-tab="p2" onclick="switchTab('p2');loadPhase(2)">&#9889; Rapid-Fire</div>
    <div class="tab" data-tab="p3" onclick="switchTab('p3');loadPhase(3)">&#128200; Unusual Amt</div>
    <div class="tab" data-tab="p4" onclick="switchTab('p4');loadPhase(4)">&#9992; Geo Travel</div>
    <div class="tab" data-tab="p5" onclick="switchTab('p5');loadPhase(5)">&#128184; Smurfing</div>
    <div class="tab" data-tab="p6" onclick="switchTab('p6');loadPhase(6)">&#128279; Chains</div>
  </div>

  <!-- DASHBOARD TAB -->
  <div class="tab-content active" id="tab-dash">
    <div class="grid2" style="margin-bottom:20px">
      <div class="card">
        <div class="card-title">Alerts by Rule</div>
        <canvas id="chartRules"></canvas>
      </div>
      <div class="card">
        <div class="card-title">Alerts by Severity</div>
        <canvas id="chartSev"></canvas>
      </div>
    </div>
    <div class="card">
      <div class="card-title">Fraud Score Leaderboard</div>
      <div class="tbl-wrap" id="dash-table"><div class="empty">Click "Seed &amp; Run All Phases" to begin.</div></div>
    </div>
  </div>

  <!-- PHASE 2 -->
  <div class="tab-content" id="tab-p2">
    <div class="card" style="margin-bottom:16px">
      <div class="card-title">&#9889; Rapid-Fire Detection — <code>LAG() OVER(PARTITION BY account_id ORDER BY txn_timestamp)</code></div>
      <p style="font-size:12px;color:var(--muted);margin-bottom:16px">Detects same-account transactions within 30 seconds — classic card-testing attack pattern.</p>
      <div class="tbl-wrap" id="p2-table"><div class="empty">Loading…</div></div>
    </div>
  </div>

  <!-- PHASE 3 -->
  <div class="tab-content" id="tab-p3">
    <div class="card" style="margin-bottom:16px">
      <div class="card-title">&#128200; Unusual Amount Detection — <code>Z = (amount − μ) / σ</code></div>
      <p style="font-size:12px;color:var(--muted);margin-bottom:16px">Flags transactions where amount > user's mean + 3×stddev. Stddev computed manually in SQL via variance formula.</p>
      <div class="tbl-wrap" id="p3-table"><div class="empty">Loading…</div></div>
    </div>
  </div>

  <!-- PHASE 4 -->
  <div class="tab-content" id="tab-p4">
    <div class="card" style="margin-bottom:16px">
      <div class="card-title">&#9992;&#65039; Geo-Impossible Travel — <code>6371×ACOS(SIN(lat1)×SIN(lat2)+COS(lat1)×COS(lat2)×COS(Δlon))</code></div>
      <p style="font-size:12px;color:var(--muted);margin-bottom:16px">Self-join finds transaction pairs from cities &gt;500 km apart within 60 minutes. Required travel speed exposes impossibility.</p>
      <div class="tbl-wrap" id="p4-table"><div class="empty">Loading…</div></div>
    </div>
  </div>

  <!-- PHASE 5 -->
  <div class="tab-content" id="tab-p5">
    <div class="card" style="margin-bottom:16px">
      <div class="card-title">&#128184; Smurfing Detection — <code>COUNT(DISTINCT sender) ≥ 5 per day</code></div>
      <p style="font-size:12px;color:var(--muted);margin-bottom:16px">One receiver getting funds from 5+ unrelated accounts in 24 hours indicates structuring to avoid bank reporting thresholds.</p>
      <div class="tbl-wrap" id="p5-table"><div class="empty">Loading…</div></div>
    </div>
  </div>

  <!-- PHASE 6 -->
  <div class="tab-content" id="tab-p6">
    <div class="card" style="margin-bottom:16px">
      <div class="card-title">&#128279; Money Laundering Chains — <code>WITH RECURSIVE</code> CTE, depth ≤ 5</div>
      <p style="font-size:12px;color:var(--muted);margin-bottom:16px">Recursive CTE follows transfer chains (A→B→C→D). Cycle guard via INSTR prevents infinite loops.</p>
      <div class="tbl-wrap" id="p6-table"><div class="empty">Loading…</div></div>
    </div>
  </div>

</div><!-- /container -->

<div id="toast"></div>

<script>
// ── utils ──────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function toast(msg, ok=true){
  const t=$('toast'); t.textContent=msg;
  t.className='show '+(ok?'ok':'err');
  setTimeout(()=>t.className='',3000);
}

function badge(sev){
  const m={CRITICAL:'critical',HIGH:'high',MEDIUM:'medium',LOW:'low',CLEAN:'clean'};
  return `<span class="phase-badge badge-${m[sev]||'clean'}">${sev}</span>`;
}

function switchTab(id){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  document.querySelector(`[data-tab="${id}"]`).classList.add('active');
  $(`tab-${id}`).classList.add('active');
}

function scoreColor(score){
  if(score>=100) return '#ff2d55';
  if(score>=50)  return '#ff9500';
  if(score>=20)  return '#ffd60a';
  return '#30d158';
}

// ── charts ────────────────────────────────────────────────────
let chartRules=null, chartSev=null;

function loadCharts(){
  Promise.all([
    fetch('/api/chart/rules').then(r=>r.json()),
    fetch('/api/chart/severity').then(r=>r.json())
  ]).then(([rules,sev])=>{
    // Rules bar
    const rLabels=Object.keys(rules), rVals=Object.values(rules);
    const rColors=['#3b82f6','#ef4444','#f97316','#eab308','#22c55e'];
    if(chartRules) chartRules.destroy();
    chartRules=new Chart($('chartRules'),{type:'bar',data:{labels:rLabels,
      datasets:[{data:rVals,backgroundColor:rColors.slice(0,rLabels.length),
                 borderRadius:6,borderSkipped:false}]},
      options:{plugins:{legend:{display:false}},scales:{
        y:{grid:{color:'rgba(30,45,69,.6)'},ticks:{color:'#64748b'}},
        x:{grid:{display:false},ticks:{color:'#64748b'}}},
        responsive:true,maintainAspectRatio:true}});

    // Severity doughnut
    const sevOrder=['CRITICAL','HIGH','MEDIUM','LOW'];
    const sevColors={'CRITICAL':'#ff2d55','HIGH':'#ff9500','MEDIUM':'#ffd60a','LOW':'#30d158'};
    const sLabels=sevOrder.filter(k=>sev[k]);
    const sVals=sLabels.map(k=>sev[k]);
    const sColors=sLabels.map(k=>sevColors[k]);
    if(chartSev) chartSev.destroy();
    chartSev=new Chart($('chartSev'),{type:'doughnut',
      data:{labels:sLabels,datasets:[{data:sVals,backgroundColor:sColors,
            borderWidth:2,borderColor:'#111827'}]},
      options:{plugins:{legend:{labels:{color:'#e2e8f0',padding:16}}},
               cutout:'65%',responsive:true,maintainAspectRatio:true}});
  });
}

// ── status ────────────────────────────────────────────────────
function loadStatus(){
  fetch('/api/status').then(r=>r.json()).then(d=>{
    if(d.ready){
      $('s-accts').textContent=d.accounts;
      $('s-txns').textContent=d.transactions.toLocaleString();
      $('s-alerts').textContent=d.alerts;
      $('db-badge').textContent='DB: Ready';
      loadCriticalCount();
      loadCharts();
      loadDashboard();
    } else {
      $('db-badge').textContent='DB: Not seeded';
      $('s-crit').textContent='—';
    }
  });
}

function loadCriticalCount(){
  fetch('/api/summary').then(r=>r.json()).then(rows=>{
    const crit=rows.filter(r=>r.severity==='CRITICAL').reduce((a,r)=>a+r.cnt,0);
    $('s-crit').textContent=crit||'0';
  });
}

// ── seed ──────────────────────────────────────────────────────
function runSeed(){
  const btn=$('btn-seed'), icon=$('seed-icon');
  btn.disabled=true;
  icon.innerHTML='<span class="loader"></span>';
  fetch('/api/seed',{method:'POST'}).then(r=>r.json()).then(d=>{
    if(d.ok){
      toast('All 7 phases executed successfully!');
      loadStatus();
      loadPhase(2);loadPhase(3);loadPhase(4);loadPhase(5);loadPhase(6);
    } else toast('Error: '+d.msg, false);
    btn.disabled=false; icon.textContent='\u25B6';
  }).catch(e=>{toast('Error: '+e,false);btn.disabled=false;icon.textContent='\u25B6';});
}

// ── dashboard ────────────────────────────────────────────────
function loadDashboard(){
  fetch('/api/dashboard').then(r=>r.json()).then(rows=>{
    if(!rows.length){$('dash-table').innerHTML='<div class="empty">No data yet — click Seed &amp; Run All Phases.</div>';return;}
    const maxScore=Math.max(...rows.map(r=>r.score),1);
    const html=`<table>
      <thead><tr>
        <th>#</th><th>Account</th><th>Owner</th><th>Type</th>
        <th>&#9889; Rapid</th><th>&#128200; Unusual</th><th>&#9992; Geo</th>
        <th>&#128184; Smurf</th><th>&#128279; Chain</th>
        <th>Score</th><th>Risk</th>
      </tr></thead><tbody>
      ${rows.map((r,i)=>`<tr>
        <td style="color:var(--muted)">${i+1}</td>
        <td><code>#${r.account_id}</code></td>
        <td style="font-weight:600">${r.owner_name}</td>
        <td style="color:var(--muted)">${r.account_type}</td>
        <td style="text-align:center">${r.rapid||'—'}</td>
        <td style="text-align:center">${r.unusual||'—'}</td>
        <td style="text-align:center">${r.geo||'—'}</td>
        <td style="text-align:center">${r.smurf||'—'}</td>
        <td style="text-align:center">${r.chain||'—'}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <div class="score-bar" style="width:80px">
              <div class="score-fill" style="width:${(r.score/maxScore*100).toFixed(0)}%;background:${scoreColor(r.score)}"></div>
            </div>
            <span style="font-weight:700;color:${scoreColor(r.score)}">${r.score}</span>
          </div>
        </td>
        <td>${badge(r.risk)}</td>
      </tr>`).join('')}
      </tbody></table>`;
    $('dash-table').innerHTML=html;
  });
}

// ── phase tables ─────────────────────────────────────────────
function loadPhase(n){
  const el=$(`p${n}-table`);
  el.innerHTML='<div class="empty"><span class="loader"></span> Running SQL query…</div>';
  fetch(`/api/phase/${n}`).then(r=>r.json()).then(rows=>{
    if(!rows.length){el.innerHTML='<div class="empty">No results returned.</div>';return;}
    const keys=Object.keys(rows[0]);
    el.innerHTML=`<table><thead><tr>${keys.map(k=>`<th>${k.replace(/_/g,' ')}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r=>`<tr>${keys.map(k=>{
      const v=r[k];
      if(k==='severity'||k==='sev') return `<td>${badge(v)}</td>`;
      if(k==='risk') return `<td>${badge(v)}</td>`;
      if(k==='amount'||k==='total_recv'||k==='min_amount') return `<td style="font-weight:600;color:#34d399">$${v}</td>`;
      if(k==='dist_km') return `<td style="font-weight:600;color:var(--high)">${v} km</td>`;
      if(k==='req_speed_kmh') return `<td style="color:var(--critical)">${v} km/h</td>`;
      if(k==='z_score') return `<td style="color:${parseFloat(v)>10?'var(--critical)':'var(--high)'}">${v}</td>`;
      if(k==='path') return `<td><code>${v}</code></td>`;
      if(k==='hops') return `<td style="font-weight:700;color:var(--accent)">${v}</td>`;
      return `<td>${v??'—'}</td>`;
    }).join('')}</tr>`).join('')}</tbody></table>`;
  }).catch(()=>el.innerHTML='<div class="empty">Query error.</div>');
}

// ── init ─────────────────────────────────────────────────────
loadStatus();
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  SQL Fraud Detection Dashboard")
    print("  http://localhost:5000")
    print("="*55 + "\n")
    app.run(debug=False, port=5000, use_reloader=False)
