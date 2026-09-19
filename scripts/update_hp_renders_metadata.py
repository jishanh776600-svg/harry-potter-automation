import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parent.parent / "data" / "database" / "pipeline.db"
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

cursor.execute("""
    UPDATE hp_renders
    SET voice_id = 'af_sarah',
        voice_pitch = '+0Hz',
        voice_rate = '+0%',
        caption_style = 'HARRY_P_SAFE_ZONE'
""")
conn.commit()
print("Updated hp_renders rows:", cursor.rowcount)
conn.close()
