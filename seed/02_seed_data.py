"""
Phase 1 — Seed Data Generator
SQL Fraud Detection Engine

Generates realistic banking data using Faker and injects:
- 50 accounts
- 20 locations (real cities with lat/lon)
- ~2000 normal transactions
- ~150 deliberately fraudulent transactions (for each detection rule)
"""

import sqlite3
import random
import math
from datetime import datetime, timedelta
from faker import Faker

fake = Faker()
random.seed(42)

DB_PATH = "db/fraud.db"

# ── Locations: real cities with coordinates ──────────────────────────────────
CITIES = [
    (1,  "New York",       "US",  40.7128,  -74.0060),
    (2,  "Los Angeles",    "US",  34.0522, -118.2437),
    (3,  "Chicago",        "US",  41.8781,  -87.6298),
    (4,  "Houston",        "US",  29.7604,  -95.3698),
    (5,  "Miami",          "US",  25.7617,  -80.1918),
    (6,  "London",         "UK",  51.5074,   -0.1278),
    (7,  "Paris",          "FR",  48.8566,    2.3522),
    (8,  "Berlin",         "DE",  52.5200,   13.4050),
    (9,  "Tokyo",          "JP",  35.6762,  139.6503),
    (10, "Sydney",         "AU", -33.8688,  151.2093),
    (11, "Dubai",          "AE",  25.2048,   55.2708),
    (12, "Singapore",      "SG",   1.3521,  103.8198),
    (13, "Toronto",        "CA",  43.6510,  -79.3470),
    (14, "Mexico City",    "MX",  19.4326,  -99.1332),
    (15, "Sao Paulo",      "BR", -23.5505,  -46.6333),
    (16, "Moscow",         "RU",  55.7558,   37.6173),
    (17, "Cape Town",      "ZA", -33.9249,   18.4241),
    (18, "Lagos",          "NG",   6.5244,    3.3792),
    (19, "Mumbai",         "IN",  19.0760,   72.8777),
    (20, "Beijing",        "CN",  39.9042,  116.4074),
]

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def rand_ts(base: datetime, delta_seconds_range=(-3600*24*180, 0)) -> str:
    offset = random.randint(*delta_seconds_range)
    return (base + timedelta(seconds=offset)).strftime("%Y-%m-%d %H:%M:%S")

def seed(conn: sqlite3.Connection):
    cur = conn.cursor()
    base_ts = datetime(2025, 9, 1, 12, 0, 0)

    # ── Accounts ─────────────────────────────────────────────────────────────
    account_types = ["checking", "savings", "business"]
    accounts = []
    for i in range(1, 51):
        accounts.append((
            i,
            fake.name(),
            random.choice(account_types),
            rand_ts(base_ts, (-3600*24*365, -3600*24*30)),
            "US",
            0
        ))
    cur.executemany(
        "INSERT OR IGNORE INTO accounts VALUES (?,?,?,?,?,?)", accounts
    )

    # ── Locations ────────────────────────────────────────────────────────────
    cur.executemany(
        "INSERT OR IGNORE INTO locations VALUES (?,?,?,?,?)", CITIES
    )

    # ── Normal transactions ───────────────────────────────────────────────────
    merchants = ["Amazon","Walmart","Netflix","Uber","Starbucks","Shell","Airbnb",
                 "McDonald's","CVS","Target","Best Buy","Apple Store","Spotify"]
    txn_id = 1
    normal_txns = []
    us_locs = [c[0] for c in CITIES if c[2] == "US"]   # US location IDs

    for acc_id in range(1, 51):
        n = random.randint(30, 60)
        for _ in range(n):
            amount = round(random.lognormvariate(3.5, 0.8), 2)  # realistic spend distribution
            normal_txns.append((
                txn_id, acc_id, "debit", amount, "USD",
                rand_ts(base_ts), random.choice(us_locs),
                random.choice(merchants), None, None
            ))
            txn_id += 1
    cur.executemany(
        "INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)", normal_txns
    )

    # ── FRAUD SCENARIO 1: Rapid-fire (card testing) ──────────────────────────
    # Account 5: 6 small transactions within 20 seconds
    rapid_base = datetime(2025, 8, 15, 3, 0, 0)
    for i in range(6):
        ts = (rapid_base + timedelta(seconds=i*3)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (txn_id, 5, "debit", round(random.uniform(0.5, 2.0), 2),
             "USD", ts, 1, "Unknown Vendor", "RAPID_FIRE_TEST", None)
        )
        txn_id += 1

    # ── FRAUD SCENARIO 2: Unusual amount ─────────────────────────────────────
    # Account 10: history of ~$30-50 purchases; then one $8500 charge
    for _ in range(20):
        cur.execute(
            "INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (txn_id, 10, "debit", round(random.uniform(25, 55), 2),
             "USD", rand_ts(base_ts), 3, "Grocery Store", None, None)
        )
        txn_id += 1
    cur.execute(
        "INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
        (txn_id, 10, "debit", 8500.00, "USD",
         datetime(2025, 8, 20, 14, 0, 0).strftime("%Y-%m-%d %H:%M:%S"),
         2, "Luxury Shop", "UNUSUAL_AMOUNT_TEST", None)
    )
    txn_id += 1

    # ── FRAUD SCENARIO 3: Geo-impossible travel ───────────────────────────────
    # Account 15: txn in New York, then 40 minutes later in Tokyo (>10,000 km!)
    geo_base = datetime(2025, 7, 10, 9, 0, 0)
    cur.execute(
        "INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
        (txn_id, 15, "debit", 120.00, "USD",
         geo_base.strftime("%Y-%m-%d %H:%M:%S"), 1, "JFK Airport Shop", "GEO_TEST", None)
    )
    txn_id += 1
    cur.execute(
        "INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
        (txn_id, 15, "debit", 340.00, "USD",
         (geo_base + timedelta(minutes=40)).strftime("%Y-%m-%d %H:%M:%S"),
         9, "Tokyo Mart", "GEO_TEST", None)   # location_id=9 → Tokyo
    )
    txn_id += 1

    # ── FRAUD SCENARIO 4: Smurfing (many → one) ───────────────────────────────
    # Accounts 20-27 each send small transfers to account 30 within 6 hours
    smurf_base = datetime(2025, 6, 5, 10, 0, 0)
    for sender in range(20, 28):
        ts = (smurf_base + timedelta(minutes=random.randint(0, 360))).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (txn_id, sender, "transfer", round(random.uniform(900, 9999), 2),
             "USD", ts, 1, None, "SMURFING_TEST", 30)
        )
        txn_id += 1

    # ── FRAUD SCENARIO 5: Laundering chain A→B→C→D ───────────────────────────
    # Transfer: 40 → 41 → 42 → 43 → 44  within 2 days
    chain_base = datetime(2025, 5, 1, 8, 0, 0)
    chain = [(40,41), (41,42), (42,43), (43,44)]
    for i, (src, dst) in enumerate(chain):
        ts = (chain_base + timedelta(hours=i*10)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT OR IGNORE INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?)",
            (txn_id, src, "transfer", 5000.00 - i*200,
             "USD", ts, 1, None, "LAUNDERING_CHAIN_TEST", dst)
        )
        txn_id += 1

    conn.commit()
    print(f"✅ Seeded database: {txn_id-1} total transactions across 50 accounts.")
    print(f"   📁 DB path: {DB_PATH}")


if __name__ == "__main__":
    import os
    os.makedirs("db", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # Apply schema first
    with open("schema/01_create_tables.sql") as f:
        conn.executescript(f.read())
    seed(conn)
    conn.close()
