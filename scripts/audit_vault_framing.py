"""
Vault Quality Audit & Subject Framing Verification
===================================================
Scans harvested clips in the vault:
1. Checks if the metadata claims named characters are present.
2. Runs face & subject detection on the cropped 9:16 clip.
3. Flags any clips where the character was sliced off or missing.
"""
import os
import sys
import cv2
import json
import sqlite3
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

DB_PATH = PROJECT_ROOT / "data" / "database" / "franchise_visual_vault.db"
MODEL_PATH = PROJECT_ROOT / "data" / "models" / "mediapipe" / "blaze_face_short_range.tflite"

def get_detector():
    base_options = mp_python.BaseOptions(model_asset_path=str(MODEL_PATH))
    options = vision.FaceDetectorOptions(base_options=base_options, min_detection_confidence=0.45)
    return vision.FaceDetector.create_from_options(options)

def audit_clips(movie_number: int = 1, limit: int = 50):
    detector = get_detector()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("""
        SELECT clip_id, movie_number, start_seconds, end_seconds, primary_subject,
               characters_present, local_path, drive_file_id
        FROM franchise_clips
        WHERE movie_number = ? AND characters_present != '[]'
        ORDER BY start_seconds
        LIMIT ?
    """, (movie_number, limit))
    rows = c.fetchall()

    print(f"\n=======================================================")
    print(f"  RUNNING QUALITY AUDIT ON MOVIE {movie_number} ({len(rows)} clips)")
    print(f"=======================================================\n")

    passed_count = 0
    missing_subject_count = 0
    missing_files = 0
    flagged = []

    for idx, r in enumerate(rows, 1):
        clip_id = r["clip_id"]
        local_p = Path(r["local_path"])
        chars = json.loads(r["characters_present"]) if r["characters_present"] else []
        subj = r["primary_subject"]

        if not local_p.exists():
            missing_files += 1
            continue

        # Extract middle frame of cropped clip
        cap = cv2.VideoCapture(str(local_p))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames // 2))
        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            continue

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = detector.detect(mp_img)

        num_faces = len(res.detections) if res else 0

        # Check if characters were expected but no face is in the vertical cropped video
        if len(chars) > 0 and num_faces == 0:
            missing_subject_count += 1
            flagged.append({
                "clip_id": clip_id,
                "subject": subj,
                "expected_chars": chars,
                "time": f"{r['start_seconds']:.1f}s - {r['end_seconds']:.1f}s",
                "reason": "Character expected in metadata but NO face found in cropped 9:16 frame!"
            })
            print(f"  [FLAGGED {missing_subject_count:02d}] {clip_id} ({r['start_seconds']:.1f}s) -> Expected: {chars} | Cropped Faces: 0")
        else:
            passed_count += 1

    print(f"\nAudit Summary for Movie {movie_number}:")
    print(f"  Total Audited: {len(rows)}")
    print(f"  Passed (Subject visible in vertical frame): {passed_count} ({passed_count/max(1, len(rows))*100:.1f}%)")
    print(f"  Flagged (Subject cut off / empty frame): {missing_subject_count} ({missing_subject_count/max(1, len(rows))*100:.1f}%)")
    return flagged

if __name__ == "__main__":
    audit_clips(movie_number=1, limit=50)
