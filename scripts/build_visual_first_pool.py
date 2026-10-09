import sys
sys.path.insert(0, ".")
import sqlite3
import json

conn = sqlite3.connect("data/database/franchise_visual_vault.db")
conn.row_factory = sqlite3.Row

# Let's inspect prominent props and scenes across Movies 1-5
queries = [
    # 1. Letters from Fireplace (M1)
    ("Letters from Fireplace", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE visible_objects_props LIKE '%fireplace%' OR action_description LIKE '%letter%' OR visible_objects_props LIKE '%letter%' OR visible_objects_props LIKE '%envelope%'"),
    # 2. Zoo Snake / Vanishing Glass (M1)
    ("Zoo Snake", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE action_description LIKE '%snake%' OR visible_objects_props LIKE '%snake%'"),
    # 3. Sorting Hat (M1)
    ("Sorting Hat", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE primary_subject LIKE '%Sorting Hat%' OR visible_objects_props LIKE '%Sorting Hat%'"),
    # 4. Mirror of Erised (M1)
    ("Mirror of Erised", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE primary_subject LIKE '%Erised%' OR visible_objects_props LIKE '%Erised%'"),
    # 5. Flying Ford Anglia (M2)
    ("Ford Anglia", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE action_description LIKE '%car%' OR action_description LIKE '%Anglia%' OR visible_objects_props LIKE '%car%'"),
    # 6. Dobby (M2)
    ("Dobby", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE primary_subject LIKE '%Dobby%' OR characters_present LIKE '%Dobby%'"),
    # 7. Tom Riddle's Diary / Basilisk (M2)
    ("Riddle Diary", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE primary_subject LIKE '%diary%' OR visible_objects_props LIKE '%diary%' OR action_description LIKE '%diary%'"),
    # 8. Dueling Club (M2)
    ("Dueling Club", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE action_description LIKE '%duel%' OR (movie_number=2 AND action_description LIKE '%Malfoy%')"),
    # 9. Dementor Train (M3)
    ("Dementor Train", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE movie_number=3 AND (action_description LIKE '%Dementor%' OR primary_subject LIKE '%Dementor%')"),
    # 10. Marauder's Map (M3)
    ("Marauder's Map", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE primary_subject LIKE '%Marauder%' OR visible_objects_props LIKE '%Marauder%'"),
    # 11. Patronus Lake (M3)
    ("Patronus Lake", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE movie_number=3 AND (action_description LIKE '%Patronus%' OR action_description LIKE '%stag%')"),
    # 12. Barty Crouch Jr / Pensieve Trial (M4)
    ("Barty Crouch Jr", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE characters_present LIKE '%Crouch%' OR primary_subject LIKE '%Crouch%' OR action_description LIKE '%Crouch%'"),
    # 13. Triwizard Dragon / Horntail (M4)
    ("Dragon Task", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE movie_number=4 AND (action_description LIKE '%dragon%' OR action_description LIKE '%Horntail%')"),
    # 14. Graveyard Duel / Priori Incantatem (M4)
    ("Graveyard Duel", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE movie_number=4 AND (action_description LIKE '%graveyard%' OR action_description LIKE '%Voldemort%')"),
    # 15. Umbridge Blood Quill (M5)
    ("Umbridge Blood Quill", "SELECT clip_id, movie_number, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE movie_number=5 AND (characters_present LIKE '%Umbridge%' OR primary_subject LIKE '%Umbridge%')")
]

print("=== CHECKING VAULT SCENE CLUSTERS ===")
for name, sql in queries:
    rows = conn.execute(sql).fetchall()
    print(f"\n[{name}] -> {len(rows)} clips found")
    for r in rows[:3]:
        print(f"   {r['clip_id']} (M{r['movie_number']}): Subj: {r['primary_subject']} | Chars: {r['characters_present']} | Props: {r['visible_objects_props']} | Action: {r['action_description'][:75]}")

conn.close()
