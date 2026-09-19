"""
Search Movie 1 subtitles for Remembrall and Mirror of Erised.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/database/pipeline.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("--- REMEMBRALL / NEVILLE ---")
cursor.execute("""
    SELECT id, start_timecode, end_timecode, start_seconds, end_seconds, text 
    FROM movie_subtitle_chunks 
    WHERE movie_number = 1 AND (text LIKE '%Remembrall%' OR text LIKE '%forgot%')
""")
for r in cursor.fetchall():
    print(f"{r['id']} [{r['start_seconds']:.1f}s - {r['end_seconds']:.1f}s]: {r['text'].replace(chr(10), ' ')}")

print("\n--- MIRROR OF ERISED ---")
cursor.execute("""
    SELECT id, start_timecode, end_timecode, start_seconds, end_seconds, text 
    FROM movie_subtitle_chunks 
    WHERE movie_number = 1 AND (text LIKE '%Mirror%' OR text LIKE '%Erised%' OR text LIKE '%desire%')
""")
for r in cursor.fetchall():
    print(f"{r['id']} [{r['start_seconds']:.1f}s - {r['end_seconds']:.1f}s]: {r['text'].replace(chr(10), ' ')}")
