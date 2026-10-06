"""
Production Franchise Visual Harvester for Movie 1 (Sorcerer's Stone)
====================================================================
Runs high-speed chapter-by-chapter shot detection, two-stage frame-accurate
vertical cutting, rich Vision AI lore metadata generation, SQLite FTS5 indexing,
and Google Drive vault uploading.
"""
import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import MOVIES_DIR
from engines.franchise_visual_harvester import FranchiseVisualHarvester, DRIVE_VAULT_CATEGORIES
from core.franchise_clip_db import get_clip_by_id, insert_or_update_clip

MOVIE_PATH = MOVIES_DIR / "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv"

CHAPTERS = [
    {"name": "01_Privet_Drive_Baby_Harry", "start": 30.0, "dur": 570.0},
    {"name": "02_Zoo_Letters_Dursleys", "start": 600.0, "dur": 600.0},
    {"name": "03_Hagrid_Diagon_Alley_Wand", "start": 1200.0, "dur": 600.0},
    {"name": "04_Platform934_Hogwarts_Express", "start": 1800.0, "dur": 600.0},
    {"name": "05_Boats_Great_Hall_Sorting", "start": 2400.0, "dur": 600.0},
    {"name": "06_Potions_Snape_Flying_Lesson", "start": 3000.0, "dur": 600.0},
    {"name": "07_Quidditch_Match_Snitch", "start": 3600.0, "dur": 600.0},
    {"name": "08_Halloween_Troll_Duel", "start": 4200.0, "dur": 600.0},
    {"name": "09_Library_Mirror_Of_Erised", "start": 4800.0, "dur": 600.0},
    {"name": "10_Norbert_Forbidden_Forest", "start": 5400.0, "dur": 600.0},
    {"name": "11_Fluffy_Devils_Snare_Keys", "start": 6000.0, "dur": 600.0},
    {"name": "12_Giant_Wizard_Chess", "start": 6600.0, "dur": 600.0},
    {"name": "13_Quirrell_Voldemort_Mirror", "start": 7200.0, "dur": 600.0},
    {"name": "14_Hospital_Wing_Dumbledore", "start": 7800.0, "dur": 600.0},
    {"name": "15_House_Cup_Feast_Departure", "start": 8400.0, "dur": 600.0},
]

def run_harvest(start_ch: int = 1, end_ch: int = 15, max_per_chapter: int = 40):
    if not MOVIE_PATH.exists():
        print(f"Error: Movie file not found at {MOVIE_PATH}")
        return

    harvester = FranchiseVisualHarvester()
    total_harvested_session = 0

    print(f"\n=======================================================")
    print(f"  LAUNCHING PRODUCTION VAULT HARVEST: MOVIE 1")
    print(f"  Chapters: {start_ch} to {end_ch} (Max {max_per_chapter} clips/chapter)")
    print(f"=======================================================\n")

    for ch_idx in range(start_ch - 1, min(end_ch, len(CHAPTERS))):
        ch = CHAPTERS[ch_idx]
        ch_num = ch_idx + 1
        print(f"\n>>> [Chapter {ch_num:02d}/15: {ch['name']}] (Start: {ch['start']}s, Dur: {ch['dur']}s)")
        
        # 1. Detect shot boundaries
        shots = harvester.detect_movie_shots(
            movie_path=MOVIE_PATH,
            start_time_sec=ch["start"],
            duration_sec=ch["dur"]
        )
        print(f"    Detected {len(shots)} true shot cuts in Chapter {ch_num:02d}.")

        # Step through shots to ensure diverse coverage
        selected_shots = []
        if len(shots) <= max_per_chapter:
            selected_shots = shots
        else:
            step = len(shots) / float(max_per_chapter)
            for i in range(max_per_chapter):
                selected_shots.append(shots[int(i * step)])

        print(f"    Processing {len(selected_shots)} selected shots...")

        for s_idx, (s_sec, e_sec) in enumerate(selected_shots, start=1):
            clip_id = f"HP_M01_CH{ch_num:02d}_{int(s_sec):05d}S"
            from engines.franchise_visual_harvester import CLIPS_OUT_DIR, FRAMES_TMP_DIR
            clip_file = CLIPS_OUT_DIR / f"{clip_id}.mp4"
            meta_file = CLIPS_OUT_DIR / f"{clip_id}.meta.json"
            frame_file = FRAMES_TMP_DIR / f"{clip_id}.jpg"

            # Check if already processed and uploaded in DB
            existing = get_clip_by_id(clip_id)
            if existing and existing.get("drive_file_id") and existing.get("primary_subject") != "Canonical Scene":
                print(f"    [{s_idx:02d}/{len(selected_shots)}] {clip_id} already exists in DB with Drive ID, skipping.")
                continue

            # 1. Extract Keyframe
            center_t = (s_sec + e_sec) / 2.0
            if not harvester.extract_keyframe(MOVIE_PATH, center_t, frame_file):
                print(f"    [{s_idx:02d}/{len(selected_shots)}] Could not extract frame for {clip_id}, skipping.")
                continue

            # 2. Analyze with Vision AI
            try:
                meta = harvester.analyze_frame_with_vision(frame_file, "Harry Potter and the Sorcerer's Stone", center_t)
            except Exception as e:
                print(f"    [{s_idx:02d}/{len(selected_shots)}] Vision analysis error: {e}")
                continue

            # 3. Cut Vertical 1080x1920 Clip
            if not harvester.cut_vertical_clip(MOVIE_PATH, s_sec, e_sec, clip_file):
                print(f"    [{s_idx:02d}/{len(selected_shots)}] FFmpeg cut failed for {clip_id}, skipping.")
                continue

            # 4. Form Record
            record = {
                "clip_id": clip_id,
                "movie_number": 1,
                "movie_title": "Harry Potter and the Sorcerer's Stone",
                "start_seconds": s_sec,
                "end_seconds": e_sec,
                "duration_seconds": round(e_sec - s_sec, 2),
                "primary_subject": meta.get("primary_subject", "Scene"),
                "characters_present": meta.get("characters_present", []),
                "character_expressions": meta.get("character_expressions", ""),
                "visible_objects_props": meta.get("visible_objects_props", []),
                "spells_magic_actions": meta.get("spells_magic_actions", "none"),
                "action_description": meta.get("action_description", ""),
                "lore_context": meta.get("lore_context", ""),
                "location_setting": meta.get("location_setting", "Hogwarts"),
                "shot_scale": meta.get("shot_scale", "MEDIUM_SHOT"),
                "camera_motion": meta.get("camera_motion", "STATIC"),
                "lighting_and_mood": meta.get("lighting_and_mood", "STANDARD"),
                "search_tags": meta.get("search_tags", []),
                "drive_category": meta.get("drive_category", "CHARACTERS"),
                "local_path": str(clip_file)
            }

            # 5. Save .meta.json Sidecar
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(record, f, indent=2)

            # 6. Save in SQLite DB
            insert_or_update_clip(record)

            # 7. Upload to Google Drive Vault
            cat = record["drive_category"]
            cat_folder_id = DRIVE_VAULT_CATEGORIES.get(cat, DRIVE_VAULT_CATEGORIES["CHARACTERS"])
            try:
                with open(clip_file, "rb") as f_clip:
                    drive_id = harvester.drive_engine.upload_raw_content(
                        content=f_clip.read(),
                        filename=clip_file.name,
                        parent_folder_id=cat_folder_id,
                        mime_type="video/mp4"
                    )
                with open(meta_file, "rb") as f_meta:
                    harvester.drive_engine.upload_raw_content(
                        content=f_meta.read(),
                        filename=meta_file.name,
                        parent_folder_id=cat_folder_id,
                        mime_type="application/json"
                    )
                record["drive_file_id"] = str(drive_id)
                insert_or_update_clip(record)
                upload_str = f"Drive ID={drive_id} [{cat}]"
            except Exception as e:
                upload_str = f"Upload deferred ({e})"

            total_harvested_session += 1
            print(f"    [{s_idx:02d}/{len(selected_shots)}] {clip_id} ({s_sec:.1f}s-{e_sec:.1f}s) -> Subj: {record['primary_subject']} | Chars: {record['characters_present']} -> {upload_str}")
            time.sleep(0.5)

    print(f"\n=======================================================")
    print(f"  PRODUCTION HARVEST SESSION FINISHED")
    print(f"  Total Clips Harvested & Uploaded: {total_harvested_session}")
    print(f"=======================================================\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Production Vault Harvester")
    parser.add_argument("--start_ch", type=int, default=1, help="Start chapter (1-15)")
    parser.add_argument("--end_ch", type=int, default=15, help="End chapter (1-15)")
    parser.add_argument("--max_per_ch", type=int, default=40, help="Max clips per chapter")
    args = parser.parse_args()

    run_harvest(start_ch=args.start_ch, end_ch=args.end_ch, max_per_chapter=args.max_per_ch)
