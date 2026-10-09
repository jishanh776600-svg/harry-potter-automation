import sqlite3

db_path = "data/database/pipeline.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("--- Quarantining Dummy Boilerplate Scripts ---")
cur.execute("UPDATE hp_scripts SET status = 'QUARANTINED', qa_status = 'FAILED' WHERE full_text LIKE '%Something unforgettable%'")
print(f"Quarantined {cur.rowcount} boilerplate scripts.")

print("--- Quarantining Mismatched/Uncataloged Scripts ---")
cur.execute("UPDATE hp_scripts SET status = 'QUARANTINED', qa_status = 'FAILED' WHERE id IN ('hps_disc_neville_prophecy_b5', 'hps_disc_petunias_letter_b7', 'hps_disc_dudley_farewell_b7')")
print(f"Quarantined {cur.rowcount} mismatched scripts.")

print("--- Quarantining Scripts Requiring Movies > 5 ---")
cur.execute("UPDATE hp_scripts SET status = 'QUARANTINED', qa_status = 'FAILED' WHERE (corresponding_movie_number > 5 OR book_number > 5) AND status NOT IN ('PUBLISHED')")
print(f"Quarantined {cur.rowcount} scripts requiring movies > 5.")

print("--- Cleaning Rotten hp_movie_clips ---")
cur.execute("DELETE FROM hp_movie_clips WHERE script_id IN (SELECT id FROM hp_scripts WHERE status = 'QUARANTINED')")
print(f"Deleted {cur.rowcount} clip rows for quarantined scripts.")

cur.execute("DELETE FROM hp_movie_clips WHERE source_mode != 'CLOUD_MATERIALIZED' OR retrieval_score < 200.0 OR source_drive_id = '1pB-V9DdpiF6a1LwC23svVpg_D7esAKwA'")
print(f"Deleted {cur.rowcount} invalid/corrupt clip rows.")

print("--- Cleaning Renders for Quarantined Scripts ---")
cur.execute("DELETE FROM hp_renders WHERE script_id IN (SELECT id FROM hp_scripts WHERE status = 'QUARANTINED')")
print(f"Deleted {cur.rowcount} render rows for quarantined scripts.")

conn.commit()

print("\n--- Summary of Remaining Approved/Eligible Scripts ---")
rows = cur.execute("SELECT id, chapter_title, corresponding_movie_number, status, qa_status FROM hp_scripts WHERE status NOT IN ('PUBLISHED', 'QUARANTINED')").fetchall()
print(f"Count: {len(rows)}")
for r in rows:
    print(f"  {r[0]} | M{r[2]} | Status: {r[3]} | QA: {r[4]} | Title: {r[1]}")

conn.close()
