import sqlite3

conn = sqlite3.connect("data/database/franchise_visual_vault.db")
conn.row_factory = sqlite3.Row

print("--- Snake Clips ---")
for r in conn.execute("SELECT clip_id, movie_number, action_description FROM franchise_clips WHERE action_description LIKE '%snake%' OR visible_objects_props LIKE '%snake%'").fetchall():
    print(r["clip_id"], "| M", r["movie_number"], "|", r["action_description"][:70])

print("\n--- Fireplace / Letters Clips ---")
for r in conn.execute("SELECT clip_id, movie_number, action_description FROM franchise_clips WHERE visible_objects_props LIKE '%fireplace%' OR action_description LIKE '%letter%'").fetchall()[:8]:
    print(r["clip_id"], "| M", r["movie_number"], "|", r["action_description"][:70])

conn.close()
