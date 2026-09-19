"""
Inspect current Harry Potter automation state with schema.
"""
import sqlite3
import json
from pathlib import Path

DB_PATH = Path("data/database/pipeline.db")

def inspect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for table in ["chronology_state", "hp_renders", "hp_scripts", "nov_story_candidates", "discovery_candidates"]:
        print(f"\n==================== TABLE: {table} ====================")
        cursor.execute(f"PRAGMA table_info({table});")
        cols = [c["name"] for c in cursor.fetchall()]
        print("Columns:", cols)
        cursor.execute(f"SELECT * FROM {table};")
        rows = cursor.fetchall()
        print(f"Total rows: {len(rows)}")
        for r in rows:
            row_dict = {k: r[k] for k in cols}
            # truncate long fields
            for k, v in row_dict.items():
                if isinstance(v, str) and len(v) > 80:
                    row_dict[k] = v[:80] + "..."
            print(" ", row_dict)

if __name__ == "__main__":
    inspect_db()
