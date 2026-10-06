"""
Master Autonomous Franchise Harvester (Movies 2 to 8)
======================================================
Automates the full-franchise visual vault build across all Harry Potter movies.
- Downloads missing movie files from Google Drive when needed
- High-speed native scene cut boundary detection
- Two-stage frame-accurate keyframe extraction and 1080x1920 9:16 vertical video clipping (-an)
- Multimodal Vision AI lore metadata generation (15 fields)
- Instant SQLite FTS5 database indexing
- Real-time Google Drive vault uploading (04_FRANCHISE_CLIPS_VAULT)
- Fully resumable and checkpointed
"""
import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import MOVIES_DIR
from engines.franchise_visual_harvester import (
    FranchiseVisualHarvester,
    DRIVE_VAULT_CATEGORIES,
    CLIPS_OUT_DIR,
    FRAMES_TMP_DIR
)
from core.franchise_clip_db import get_clip_by_id, insert_or_update_clip

MOVIES_MANIFEST = [
    {
        "number": 2,
        "title": "Harry Potter and the Chamber of Secrets",
        "filename": "Harry Potter and the Chamber of Secrets (2002) Dual Audio {Hindi-English} 1080p.mkv",
        "drive_id": "1dBbUg32r5OZ7uSSuJv6UdelE3z7-mfwX",
    },
    {
        "number": 3,
        "title": "Harry Potter and the Prisoner of Azkaban",
        "filename": "3. Harry Potter and the Prisoner of Azkaban 2004 BluRay x265 [Org DD Hindi + DD 5.1 Eng] ESubs 1080p.mkv",
        "drive_id": "16boYmZt0sfBvN3e9lSSuTz8Wd8Nia80_",
    },
    {
        "number": 4,
        "title": "Harry Potter and the Goblet of Fire",
        "filename": "Harry Potter And The Goblet Of Fire 2005 BluRay 720p Dual Audio Hindi.mkv",
        "drive_id": "1EmxX84TQW6CpxIdXtgTTe9u7Cc7HkDoQ",
    },
    {
        "number": 5,
        "title": "Harry Potter and the Order of the Phoenix",
        "filename": "Harry Potter And The Order Of The Phoenix 2007 Dual Audio Hindi 720p BluRay.mkv",
        "drive_id": "1pB-V9DdpiF6a1LwC23svVpg_D7esAKwA",
    },
    {
        "number": 6,
        "title": "Harry Potter and the Half-Blood Prince",
        "filename": "Harry Potter And The Half Blood Prince 2009 BluRay 720p Dual Audio Hindi.mkv",
        "drive_id": "12034RFo4SR-x1qIwNNw2S-EUEL4rL7jk",
    },
    {
        "number": 7,
        "title": "Harry Potter and the Deathly Hallows Part 1",
        "filename": "Harry Potter And The Deathly Hallows Part 1 2010 Dual Audio Hindi 720p BluRay.mkv",
        "drive_id": "1V8UTs2fnFZBI-ToDpQQfeKZhveRHRXE-",
    },
    {
        "number": 8,
        "title": "Harry Potter and the Deathly Hallows Part 2",
        "filename": "Harry Potter and the Deathly Hallows Part 2 2011 Dual Audio Hindi 720p BluRay (1).mkv",
        "drive_id": "1GHpEuPlHh8wFdXOKPYoWnyFx6d2dSOff",
    },
]

def get_movie_duration(movie_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(movie_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception as e:
        print(f"Warning: could not probe duration for {movie_path.name}: {e}. Defaulting to 8000s.", flush=True)
        return 8000.0

def ensure_movie_available(entry: dict, harvester: FranchiseVisualHarvester) -> Path:
    local_path = MOVIES_DIR / entry["filename"]
    if local_path.exists() and local_path.stat().st_size > 500_000_000:
        print(f"Movie {entry['number']} is available locally: {local_path.name} ({local_path.stat().st_size // (1024*1024)} MB)", flush=True)
        return local_path

    print(f"Movie {entry['number']} not found locally. Downloading from Google Drive (ID: {entry['drive_id']})...", flush=True)
    MOVIES_DIR.mkdir(parents=True, exist_ok=True)
    harvester.drive_engine.download_video_from_vault(entry["drive_id"], local_path)
    print(f"Downloaded Movie {entry['number']} to {local_path.name} ({local_path.stat().st_size // (1024*1024)} MB)", flush=True)
    return local_path

def harvest_single_movie(entry: dict, harvester: FranchiseVisualHarvester, clips_per_chapter: int = 20, num_chapters: int = 15):
    m_num = entry["number"]
    m_title = entry["title"]
    print(f"\n=======================================================", flush=True)
    print(f"  STARTING HARVEST FOR MOVIE {m_num}: {m_title}", flush=True)
    print(f"=======================================================\n", flush=True)

    movie_path = ensure_movie_available(entry, harvester)
    duration = get_movie_duration(movie_path)
    chapter_len = (duration - 120.0) / float(num_chapters)

    total_movie_clips = 0

    for ch_idx in range(num_chapters):
        ch_num = ch_idx + 1
        ch_start = 60.0 + (ch_idx * chapter_len)
        ch_dur = chapter_len

        print(f"\n>>> [Movie {m_num:02d} | Chapter {ch_num:02d}/{num_chapters:02d}] (Start: {ch_start:.1f}s, Dur: {ch_dur:.1f}s)", flush=True)
        shots = harvester.detect_movie_shots(movie_path, start_time_sec=ch_start, duration_sec=ch_dur)
        print(f"    Detected {len(shots)} true camera cuts in Chapter {ch_num:02d}.", flush=True)

        if not shots:
            continue

        # Select evenly spaced shots
        if len(shots) <= clips_per_chapter:
            selected_shots = shots
        else:
            step = len(shots) / float(clips_per_chapter)
            selected_shots = [shots[int(i * step)] for i in range(clips_per_chapter)]

        print(f"    Processing {len(selected_shots)} selected shots...", flush=True)

        for s_idx, (s_sec, e_sec) in enumerate(selected_shots, start=1):
            clip_id = f"HP_M{m_num:02d}_CH{ch_num:02d}_{int(s_sec):05d}S"
            clip_file = CLIPS_OUT_DIR / f"{clip_id}.mp4"
            meta_file = CLIPS_OUT_DIR / f"{clip_id}.meta.json"
            frame_file = FRAMES_TMP_DIR / f"{clip_id}.jpg"

            # Check if already processed and uploaded in DB
            existing = get_clip_by_id(clip_id)
            if existing and existing.get("drive_file_id") and existing.get("primary_subject") != "Canonical Scene":
                print(f"    [{s_idx:02d}/{len(selected_shots)}] {clip_id} already exists in DB with Drive ID, skipping.", flush=True)
                continue

            # 1. Extract Keyframe
            center_t = (s_sec + e_sec) / 2.0
            if not harvester.extract_keyframe(movie_path, center_t, frame_file):
                print(f"    [{s_idx:02d}/{len(selected_shots)}] Keyframe extraction failed for {clip_id}, skipping.", flush=True)
                continue

            # 2. Vision AI Analysis
            try:
                meta = harvester.analyze_frame_with_vision(frame_file, m_title, center_t)
            except Exception as e:
                print(f"    [{s_idx:02d}/{len(selected_shots)}] Vision error: {e}", flush=True)
                continue

            # 3. Cut Vertical Video Clip with Smart Subject Crop
            if not harvester.cut_vertical_clip(movie_path, s_sec, e_sec, clip_file, keyframe_path=frame_file):
                print(f"    [{s_idx:02d}/{len(selected_shots)}] FFmpeg cut failed for {clip_id}, skipping.", flush=True)
                continue

            # 4. Form Record
            record = {
                "clip_id": clip_id,
                "movie_number": m_num,
                "movie_title": m_title,
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
                upload_str = f"Drive upload deferred ({e})"

            total_movie_clips += 1
            print(f"    [{s_idx:02d}/{len(selected_shots)}] {clip_id} ({s_sec:.1f}s-{e_sec:.1f}s) -> Subj: {record['primary_subject']} | Chars: {record['characters_present']} -> {upload_str}", flush=True)
            time.sleep(0.5)

    print(f"\n[+] FINISHED MOVIE {m_num}: {total_movie_clips} clips harvested & uploaded to Drive Vault.", flush=True)
    return total_movie_clips

def main():
    parser = argparse.ArgumentParser(description="Master Franchise Harvester (Movies 2-8)")
    parser.add_argument("--start_movie", type=int, default=2, help="Start movie number (2-8)")
    parser.add_argument("--end_movie", type=int, default=8, help="End movie number (2-8)")
    parser.add_argument("--clips_per_ch", type=int, default=20, help="Clips per chapter (default 20)")
    args = parser.parse_args()

    harvester = FranchiseVisualHarvester()
    total_all_movies = 0

    print(f"\n=======================================================", flush=True)
    print(f"  LAUNCHING MASTER FRANCHISE HARVEST MARATHON", flush=True)
    print(f"  Target: Movies {args.start_movie} to {args.end_movie}", flush=True)
    print(f"  Rate: ~{args.clips_per_ch * 15} clips per movie", flush=True)
    print(f"=======================================================\n", flush=True)

    for entry in MOVIES_MANIFEST:
        if args.start_movie <= entry["number"] <= args.end_movie:
            try:
                count = harvest_single_movie(entry, harvester, clips_per_chapter=args.clips_per_ch)
                total_all_movies += count
            except Exception as e:
                print(f"Error during harvest of Movie {entry['number']}: {e}", flush=True)

    print(f"\n=======================================================", flush=True)
    print(f"  MASTER FRANCHISE HARVEST COMPLETE!", flush=True)
    print(f"  Grand Total Clips Harvested in this session: {total_all_movies}", flush=True)
    print(f"=======================================================\n", flush=True)

if __name__ == "__main__":
    main()
