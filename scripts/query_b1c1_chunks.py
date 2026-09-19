"""
Inspect Book 1 Chapter 1 novel chunks.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/database/pipeline.db")
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("""
    SELECT id, chunk_index, global_chronology_index, text 
    FROM novel_chunks 
    WHERE book_number = 1 AND chapter_number = 1 
    ORDER BY chunk_index
""")
rows = cursor.fetchall()
print(f"Total chunks in B1C1: {len(rows)}")
for r in rows:
    snippet = r[3].replace("\n", " ")[:140]
    print(f"Chunk {r[1]} ({r[0]} | global {r[2]}): {snippet}...")
