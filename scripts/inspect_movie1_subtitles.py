"""
Inspect Movie 1 opening scenes.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/database/pipeline.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT id, start_timecode, end_timecode, start_seconds, end_seconds, text 
    FROM movie_subtitle_chunks 
    WHERE movie_number = 1 AND end_seconds <= 300
    ORDER BY start_seconds
""")
for r in cursor.fetchall():
    clean_text = r["text"].replace("\n", " ")
    print(f"{r['id']} [{r['start_timecode']} -> {r['end_timecode']} ({r['start_seconds']:.1f}s - {r['end_seconds']:.1f}s)]: {clean_text}")
