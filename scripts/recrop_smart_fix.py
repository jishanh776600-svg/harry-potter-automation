"""
Smart Re-Cropping & Subject Re-centering Engine
===============================================
Takes clips where characters were cut off by blind center crop,
locates the characters in the original 16:9 movie,
applies Smart Subject-Aware Crop, and updates Drive vault.
"""
import os
import sys
import cv2
import json
import sqlite3
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.smart_crop_engine import SmartCropEngine
from config.settings import MOVIES_DIR
from engines.drive_engine import DriveEngine
from engines.franchise_visual_harvester import DRIVE_VAULT_CATEGORIES

DB_PATH = PROJECT_ROOT / "data" / "database" / "franchise_visual_vault.db"

MOVIES_MAP = {
    1: MOVIES_DIR / "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv",
    2: MOVIES_DIR / "Harry Potter and the Chamber of Secrets (2002) Dual Audio {Hindi-English} 1080p.mkv",
    3: MOVIES_DIR / "3. Harry Potter and the Prisoner of Azkaban 2004 BluRay x265 [Org DD Hindi + DD 5.1 Eng] ESubs 1080p.mkv",
    4: MOVIES_DIR / "Harry Potter And The Goblet Of Fire 2005 BluRay 720p Dual Audio Hindi.mkv",
}

def recrop_clip(clip_id: str, smart_engine: SmartCropEngine, drive_engine: DriveEngine):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM franchise_clips WHERE clip_id = ?", (clip_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return False, "Clip not found in DB"

    m_num = row["movie_number"]
    movie_path = MOVIES_MAP.get(m_num)
    if not movie_path or not movie_path.exists():
        return False, f"Movie {m_num} file not available"

    s_sec = row["start_seconds"]
    e_sec = row["end_seconds"]
    dur = max(1.2, e_sec - s_sec)
    center_t = (s_sec + e_sec) / 2.0
    out_mp4 = Path(row["local_path"])

    # 1. Extract temporary raw 16:9 keyframe
    tmp_frame = PROJECT_ROOT / "data" / "smart_crop_test" / f"raw_{clip_id}.jpg"
    tmp_frame.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{center_t:.2f}", "-i", str(movie_path),
        "-vframes", "1", "-q:v", "2", str(tmp_frame)
    ])

    img = cv2.imread(str(tmp_frame))
    if img is None:
        return False, "Could not extract raw frame"

    # 2. Compute Smart Crop filter
    filt, meta = smart_engine.get_crop_filter(img)

    # 3. Two-stage seek cut with Smart Crop filter
    pre_seek = max(0.0, s_sec - 2.0)
    in_seek = s_sec - pre_seek
    tmp_cut = out_mp4.with_suffix(".smart.mp4")

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
        return False, "FFmpeg smart cut failed"

    # Replace local clip
    if out_mp4.exists():
        out_mp4.unlink()
    tmp_cut.rename(out_mp4)

    # 4. Re-upload to Google Drive Vault
    cat = row["drive_category"] or "CHARACTERS"
    cat_folder_id = DRIVE_VAULT_CATEGORIES.get(cat, DRIVE_VAULT_CATEGORIES["CHARACTERS"])
    try:
        with open(out_mp4, "rb") as f_clip:
            drive_id = drive_engine.upload_raw_content(
                content=f_clip.read(),
                filename=out_mp4.name,
                parent_folder_id=cat_folder_id,
                mime_type="video/mp4"
            )
        # Update Drive ID in DB
        conn = sqlite3.connect(DB_PATH)
        c2 = conn.cursor()
        c2.execute("UPDATE franchise_clips SET drive_file_id = ? WHERE clip_id = ?", (str(drive_id), clip_id))
        conn.commit()
        conn.close()
        return True, f"Re-cropped ({meta.get('det_type')} at X={meta.get('subject_x')}) -> Drive ID: {drive_id}"
    except Exception as e:
        return True, f"Re-cropped locally ({meta.get('det_type')}), Drive upload notice: {e}"

def test_fix_first_5(flagged_ids):
    smart_engine = SmartCropEngine()
    drive_engine = DriveEngine()

    print(f"\n=======================================================")
    print(f"  TESTING SMART RE-CROP ON FIRST {len(flagged_ids)} FLAGGED CLIPS")
    print(f"=======================================================\n")

    for cid in flagged_ids:
        print(f"Fixing {cid}...", end=" ", flush=True)
        ok, msg = recrop_clip(cid, smart_engine, drive_engine)
        print(f"-> {'SUCCESS' if ok else 'FAILED'}: {msg}")

if __name__ == "__main__":
    test_cids = [
        "HP_M01_SHOT_0001_60S",
        "HP_M01_SHOT_0002_137S",
        "HP_M01_CH01_00137S",
        "HP_M01_SHOT_0003_210S",
        "HP_M01_CH01_00241S"
    ]
    test_fix_first_5(test_cids)
