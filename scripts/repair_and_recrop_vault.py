"""
Automated Vault Re-Crop & Subject Repair Tool
==============================================
Scans the entire Franchise Visual Vault for clips where characters
were cut off by blind center cropping, locates the character in the 16:9 movie,
applies Smart Subject-Aware Crop, and updates the local MP4 and Google Drive vault.
"""
import os
import sys
import cv2
import json
import sqlite3
import argparse
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from core.smart_crop_engine import SmartCropEngine
from config.settings import MOVIES_DIR
from engines.drive_engine import DriveEngine
from engines.franchise_visual_harvester import DRIVE_VAULT_CATEGORIES

DB_PATH = PROJECT_ROOT / "data" / "database" / "franchise_visual_vault.db"
BLAZE_MODEL = PROJECT_ROOT / "data" / "models" / "mediapipe" / "blaze_face_short_range.tflite"

MOVIES_MAP = {
    1: MOVIES_DIR / "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv",
    2: MOVIES_DIR / "Harry Potter and the Chamber of Secrets (2002) Dual Audio {Hindi-English} 1080p.mkv",
    3: MOVIES_DIR / "3. Harry Potter and the Prisoner of Azkaban 2004 BluRay x265 [Org DD Hindi + DD 5.1 Eng] ESubs 1080p.mkv",
    4: MOVIES_DIR / "Harry Potter And The Goblet Of Fire 2005 BluRay 720p Dual Audio Hindi.mkv",
}

def get_face_detector():
    base_options = mp_python.BaseOptions(model_asset_path=str(BLAZE_MODEL))
    options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.45)
    return vision.FaceDetector.create_from_options(options)

def check_clip_has_face(video_path: Path, detector) -> bool:
    if not video_path.exists():
        return False
    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames // 2))
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    res = detector.detect(mp_img)
    return len(res.detections) > 0 if res else False

def repair_vault(target_movie: Optional[int] = None, max_repairs: int = 100):
    detector = get_face_detector()
    smart_engine = SmartCropEngine()
    drive_engine = DriveEngine()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = "SELECT * FROM franchise_clips WHERE characters_present != '[]'"
    params = []
    if target_movie:
        query += " AND movie_number = ?"
        params.append(target_movie)
    query += " ORDER BY movie_number, start_seconds"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    print(f"\n=======================================================", flush=True)
    print(f"  VAULT SMART REPAIR: Scanning {len(rows)} character clips...", flush=True)
    print(f"=======================================================\n", flush=True)

    repaired_count = 0
    checked_count = 0

    for r in rows:
        if repaired_count >= max_repairs:
            break

        clip_id = r["clip_id"]
        m_num = r["movie_number"]
        mp4_path = Path(r["local_path"])
        movie_path = MOVIES_MAP.get(m_num)

        if not movie_path or not movie_path.exists():
            continue

        checked_count += 1
        has_face = check_clip_has_face(mp4_path, detector)

        if not has_face:
            print(f"[{repaired_count+1}] Flagged {clip_id} (Movie {m_num} at {r['start_seconds']:.1f}s) -> Re-cropping...", end=" ", flush=True)
            
            s_sec = r["start_seconds"]
            e_sec = r["end_seconds"]
            center_t = (s_sec + e_sec) / 2.0
            dur = max(1.2, e_sec - s_sec)

            # Extract raw 16:9 keyframe
            tmp_keyframe = PROJECT_ROOT / "data" / "smart_crop_test" / f"raw_{clip_id}.jpg"
            tmp_keyframe.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{center_t:.2f}", "-i", str(movie_path),
                "-vframes", "1", "-q:v", "2", str(tmp_keyframe)
            ])

            img = cv2.imread(str(tmp_keyframe))
            if img is None:
                print("Failed to read raw frame.", flush=True)
                continue

            filt, meta = smart_engine.get_crop_filter(img)

            # Two-stage seek cut with smart crop
            pre_seek = max(0.0, s_sec - 2.0)
            in_seek = s_sec - pre_seek
            tmp_cut = mp4_path.with_suffix(".repaired.mp4")

            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", f"{pre_seek:.2f}",
                "-i", str(movie_path),
                "-ss", f"{in_seek:.2f}",
                "-t", f"{dur:.2f}",
                "-vf", filt,
                "-an",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                str(tmp_cut)
            ]
            subprocess.run(cmd)

            if not tmp_cut.exists() or tmp_cut.stat().st_size < 50000:
                print("FFmpeg cut failed.", flush=True)
                continue

            # Replace local file
            if mp4_path.exists():
                mp4_path.unlink()
            tmp_cut.rename(mp4_path)

            # Re-upload to Drive
            cat = r["drive_category"] or "CHARACTERS"
            cat_folder_id = DRIVE_VAULT_CATEGORIES.get(cat, DRIVE_VAULT_CATEGORIES["CHARACTERS"])
            try:
                with open(mp4_path, "rb") as f_clip:
                    drive_id = drive_engine.upload_raw_content(
                        content=f_clip.read(),
                        filename=mp4_path.name,
                        parent_folder_id=cat_folder_id,
                        mime_type="video/mp4"
                    )
                # Update DB
                conn2 = sqlite3.connect(DB_PATH)
                c2 = conn2.cursor()
                c2.execute("UPDATE franchise_clips SET drive_file_id = ? WHERE clip_id = ?", (str(drive_id), clip_id))
                conn2.commit()
                conn2.close()
                print(f"REPAIRED & UPLOADED -> Drive ID: {drive_id} ({meta.get('det_type')} at X={meta.get('subject_x')})", flush=True)
            except Exception as e:
                print(f"Repaired locally, Drive notice: {e}", flush=True)

            repaired_count += 1

    print(f"\n[+] Smart Repair Session Complete! Total Repaired: {repaired_count}/{checked_count} clips.", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vault Smart Repair")
    parser.add_argument("--movie", type=int, default=None, help="Specific movie number (1-4)")
    parser.add_argument("--max", type=int, default=50, help="Max clips to repair in this session")
    args = parser.parse_args()

    repair_vault(target_movie=args.movie, max_repairs=args.max)
