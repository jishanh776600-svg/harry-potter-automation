import sqlite3
from pathlib import Path

db_path = Path("data/database/pipeline.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Update all scripts to af_sarah
cur.execute("""
    UPDATE hp_scripts 
    SET voice_id = 'af_sarah', 
        voice_pitch = '+0Hz', 
        voice_rate = '+0%', 
        narrator_style = 'SARAH_MAX_CREATOR'
""")
updated_scripts = cur.rowcount

# Update or insert system_config
cur.execute("""
    INSERT INTO system_config (key, value, updated_at)
    VALUES ('active_voice', 'af_sarah', datetime('now'))
    ON CONFLICT(key) DO UPDATE SET value='af_sarah', updated_at=datetime('now')
""")

conn.commit()

print(f"Successfully updated {updated_scripts} scripts in hp_scripts table to af_sarah.")
rows = cur.execute("SELECT candidate_id, voice_id, narrator_style FROM hp_scripts").fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} ({r[2]})")

conn.close()
