"""
Print full text of approved novel scripts.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/database/pipeline.db")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT id, part_marker, hook, development, payoff, full_text FROM hp_scripts WHERE id IN ('hps_ns_b1c01_gc0001_0003', 'hps_ns_b1c01_gc0004_0006')")
for row in cursor.fetchall():
    print(f"ID: {row[0]} | Part: {row[1]}")
    print(f"Hook: {row[2]}")
    print(f"Development: {row[3]}")
    print(f"Payoff: {row[4]}")
    print(f"Full Text:\n{row[5]}")
    print("-" * 60)
