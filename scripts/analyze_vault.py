import sqlite3
from collections import Counter
import json

conn = sqlite3.connect("data/database/franchise_visual_vault.db")
conn.row_factory = sqlite3.Row

print("=== VAULT STATISTICS ===")
total = conn.execute("SELECT COUNT(*) FROM franchise_clips").fetchone()[0]
print(f"Total Clips in Vault: {total}")

subjects = Counter()
for row in conn.execute("SELECT primary_subject FROM franchise_clips"):
    subjects[row[0]] += 1

print("\nTop 30 Primary Subjects:")
for s, c in subjects.most_common(30):
    print(f"  {s}: {c} clips")

# Movies
for m in range(1, 9):
    cnt = conn.execute("SELECT COUNT(*) FROM franchise_clips WHERE movie_number = ?", (m,)).fetchone()[0]
    print(f"Movie {m}: {cnt} clips")

# Notable props & items
props_counter = Counter()
for row in conn.execute("SELECT visible_objects_props FROM franchise_clips"):
    if row[0]:
        try:
            pl = json.loads(row[0]) if row[0].startswith("[") else [p.strip() for p in row[0].split(",")]
            for p in pl:
                if len(p) > 2:
                    props_counter[p.strip()] += 1
        except Exception:
            pass

print("\nTop 25 Visible Props/Objects:")
for p, c in props_counter.most_common(25):
    print(f"  {p}: {c}")

conn.close()
