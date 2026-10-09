import sqlite3
import json

conn = sqlite3.connect("data/database/franchise_visual_vault.db")
conn.row_factory = sqlite3.Row

def search_clips(query):
    return conn.execute(
        "SELECT clip_id, movie_number, movie_title, primary_subject, characters_present, visible_objects_props, action_description, drive_file_id "
        "FROM franchise_clips WHERE " + query + " LIMIT 10"
    ).fetchall()

scenes_to_check = {
    "M1_Zoo": "action_description LIKE '%snake%' OR visible_objects_props LIKE '%snake%'",
    "M1_Fireplace_Letters": "visible_objects_props LIKE '%fireplace%' OR action_description LIKE '%letter%' OR visible_objects_props LIKE '%letter%'",
    "M1_Sorting_Hat": "primary_subject LIKE '%Sorting Hat%' OR visible_objects_props LIKE '%Sorting Hat%'",
    "M1_Mirror_of_Erised": "primary_subject LIKE '%Erised%' OR visible_objects_props LIKE '%Erised%'",
    "M2_Dobby": "primary_subject LIKE '%Dobby%' OR characters_present LIKE '%Dobby%'",
    "M2_Ford_Anglia": "action_description LIKE '%car%' OR action_description LIKE '%Anglia%'",
    "M2_Dueling_Club": "action_description LIKE '%duel%' OR (movie_number=2 AND action_description LIKE '%Malfoy%')",
    "M2_Riddle_Diary": "primary_subject LIKE '%diary%' OR visible_objects_props LIKE '%diary%'",
    "M3_Dementor_Train": "movie_number=3 AND (action_description LIKE '%Dementor%' OR primary_subject LIKE '%Dementor%')",
    "M3_Marauders_Map": "movie_number=3 AND (primary_subject LIKE '%Marauder%' OR visible_objects_props LIKE '%Marauder%')",
    "M4_Barty_Crouch_Trial": "movie_number=4 AND (characters_present LIKE '%Crouch%' OR primary_subject LIKE '%Crouch%' OR action_description LIKE '%Crouch%')",
    "M4_Dragon_Task": "movie_number=4 AND (action_description LIKE '%dragon%' OR action_description LIKE '%Horntail%')",
    "M5_Umbridge": "movie_number=5 AND (characters_present LIKE '%Umbridge%' OR primary_subject LIKE '%Umbridge%')"
}

print("=== EXACT CLIPS FOR VISUAL-FIRST SCENES ===")
for name, q in scenes_to_check.items():
    rows = search_clips(q)
    print(f"\n[{name}] ({len(rows)} clips):")
    for r in rows[:4]:
        print(f"  {r['clip_id']} | Subj: {r['primary_subject']} | DriveID: {r['drive_file_id']} | Action: {r['action_description'][:80]}")

conn.close()
