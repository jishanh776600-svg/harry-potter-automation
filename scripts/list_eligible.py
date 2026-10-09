import sqlite3

conn = sqlite3.connect("data/database/pipeline.db")
rows = conn.execute("SELECT id, chapter_title, discovery_type, status FROM hp_scripts WHERE status NOT IN ('PUBLISHED', 'QUARANTINED')").fetchall()
print(f"Total eligible scripts: {len(rows)}")
for r in rows:
    print(f"  {r[0]} | Type: {r[2]} | Status: {r[3]} | Title: {r[1]}")
conn.close()
