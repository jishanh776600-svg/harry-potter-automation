import sqlite3
import json

db_path = "data/database/pipeline.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

scripts = [
    "hps_disc_marauders_map_origins_b3",
    "hps_disc_neville_prophecy_b5",
    "hps_disc_petunias_letter_b7",
    "hps_disc_dudley_farewell_b7"
]

print("=== CHECKING SCRIPTS & CLIPS ===")
for s_id in scripts:
    s_row = conn.execute("SELECT id, suggested_title, chapter_title, full_text, status, visual_beats_json FROM hp_scripts WHERE id = ?", (s_id,)).fetchone()
    if not s_row:
        print(f"Script {s_id} NOT FOUND")
        continue
    print(f"\n=======================================================")
    print(f"--- Script: {s_id} ---")
    print(f"Title: {s_row['suggested_title']} | Chapter: {s_row['chapter_title']}")
    print(f"Status: {s_row['status']}")
    print(f"Full Text: {s_row['full_text']}")
    beats = json.loads(s_row['visual_beats_json']) if s_row['visual_beats_json'] else []
    print(f"Visual Beats Count: {len(beats)}")
    for b in beats:
        print(f"  Beat: {b.get('beat_id')} | Focus: {b.get('visual_focus')} | Entity: {b.get('primary_entity')} | Shot Type: {b.get('shot_type')} | Mood: {b.get('lighting_mood')}")
        print(f"    Text: {b.get('narration_chunk')}")

    clips = conn.execute(
        "SELECT id, beat_id, shot_id, source_asset_id, source_drive_id, source_mode, retrieval_score, retrieval_query, file_path "
        "FROM hp_movie_clips WHERE script_id = ? ORDER BY beat_id, shot_index",
        (s_id,)
    ).fetchall()
    print(f"\nClips stored in hp_movie_clips: {len(clips)}")
    for c in clips:
        print(f"  Beat: {c['beat_id']} | Asset: {c['source_asset_id']} | Score: {c['retrieval_score']} | Mode: {c['source_mode']}")
        print(f"    Query: {c['retrieval_query']}")
        print(f"    DriveID: {c['source_drive_id']}")
        print(f"    LocalFile: {c['file_path']}")
conn.close()

v_conn = sqlite3.connect("data/database/franchise_visual_vault.db")
v_conn.row_factory = sqlite3.Row
print("\n=== VAULT DB METADATA FOR MATCHED CLIPS ===")
for s_id in scripts:
    c_conn = sqlite3.connect(db_path)
    c_conn.row_factory = sqlite3.Row
    clips = c_conn.execute("SELECT beat_id, source_asset_id FROM hp_movie_clips WHERE script_id = ?", (s_id,)).fetchall()
    print(f"\nDetails for {s_id}:")
    for c in clips:
        clip_id = c["source_asset_id"]
        v_row = v_conn.execute("SELECT clip_id, movie_title, primary_subject, characters_present, visible_objects_props, action_description FROM franchise_clips WHERE clip_id = ?", (clip_id,)).fetchone()
        if v_row:
            print(f"  [{c['beat_id']}] Clip: {v_row['clip_id']} ({v_row['movie_title']})")
            print(f"       Subject: {v_row['primary_subject']}")
            print(f"       Characters: {v_row['characters_present']}")
            print(f"       Props: {v_row['visible_objects_props']}")
            print(f"       Action: {v_row['action_description']}")
        else:
            print(f"  [{c['beat_id']}] Clip {clip_id} NOT FOUND IN VAULT DB!")
    c_conn.close()
v_conn.close()
