import sqlite3

conn = sqlite3.connect("data/database/franchise_visual_vault.db")
conn.row_factory = sqlite3.Row

print("--- Dobby Clips ---")
for r in conn.execute("SELECT clip_id, movie_number, action_description FROM franchise_clips WHERE primary_subject LIKE '%Dobby%' OR characters_present LIKE '%Dobby%'").fetchall():
    print(r["clip_id"], "| M", r["movie_number"], "|", r["action_description"][:70])

print("\n--- Mirror of Erised Clips ---")
for r in conn.execute("SELECT clip_id, movie_number, action_description FROM franchise_clips WHERE primary_subject LIKE '%Erised%' OR visible_objects_props LIKE '%Erised%'").fetchall():
    print(r["clip_id"], "| M", r["movie_number"], "|", r["action_description"][:70])

print("\n--- Riddle Diary Clips ---")
for r in conn.execute("SELECT clip_id, movie_number, action_description FROM franchise_clips WHERE primary_subject LIKE '%diary%' OR visible_objects_props LIKE '%diary%'").fetchall():
    print(r["clip_id"], "| M", r["movie_number"], "|", r["action_description"][:70])

print("\n--- Marauder's Map Clips ---")
for r in conn.execute("SELECT clip_id, movie_number, action_description FROM franchise_clips WHERE primary_subject LIKE '%Marauder%' OR visible_objects_props LIKE '%Marauder%'").fetchall()[:8]:
    print(r["clip_id"], "| M", r["movie_number"], "|", r["action_description"][:70])

conn.close()
