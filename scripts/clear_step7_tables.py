"""Clear Step 7 tables to allow re-running the planner cleanly."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
from config.settings import DB_PATH

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

tables = ["nov_story_candidates", "discovery_candidates", "chronology_state"]
for t in tables:
    try:
        cursor.execute(f"DELETE FROM {t}")
        count = cursor.rowcount
        print(f"  Cleared {t}: {count} rows deleted")
    except sqlite3.OperationalError as e:
        print(f"  Table {t} not found or error: {e}")

conn.commit()
conn.close()
print("Done. All Step 7 tables cleared.")
