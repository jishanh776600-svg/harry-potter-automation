"""
Check QA details.
"""
import sqlite3, json
from pathlib import Path

conn = sqlite3.connect("data/database/pipeline.db")
cursor = conn.cursor()
cursor.execute("SELECT qa_report_json FROM hp_renders WHERE id='render_hps_ns_b1c01_gc0007_0009'")
row = cursor.fetchone()
if row and row[0]:
    data = json.loads(row[0])
    print(json.dumps(data, indent=2))
else:
    print("No record found.")
