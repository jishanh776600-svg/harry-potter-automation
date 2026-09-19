import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "database" / "pipeline.db"
conn = sqlite3.connect(str(db_path))
c = conn.cursor()

keywords = [
    "Dudley", "cake", "umbrella", "pig", "Dumbledore",
    "duel", "Alohomora", "corridor", "dog", "Fluffy",
    "potions", "chess", "fire",
    "Nimbus", "broomstick", "Wood", "parcel"
]

for kw in keywords:
    rows = c.execute(
        "SELECT start_seconds, end_seconds, text FROM movie_subtitle_chunks WHERE movie_number=1 AND text LIKE ? ORDER BY start_seconds LIMIT 4",
        (f"%{kw}%",)
    ).fetchall()
    print(f"\n--- Keyword: '{kw}' ({len(rows)} matches) ---")
    for r in rows:
        mins = int(r[0] // 60)
        secs = int(r[0] % 60)
        print(f"  [{mins:02d}:{secs:02d} | {r[0]:.1f}s - {r[1]:.1f}s]: {r[2][:80]}")

conn.close()
