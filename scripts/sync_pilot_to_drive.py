import os
import sys
import glob
import json
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.franchise_clip_db import DB_PATH, insert_or_update_clip
from engines.franchise_visual_harvester import FranchiseVisualHarvester, DRIVE_VAULT_CATEGORIES

def sync_remaining():
    harvester = FranchiseVisualHarvester()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM franchise_clips WHERE length(drive_file_id) <= 5 OR drive_file_id IS NULL")
    rows = c.fetchall()
    print(f"Syncing {len(rows)} clips to Drive...")

    for i, r in enumerate(rows, 1):
        clip_id = r["clip_id"]
        mp4_path = Path(r["local_path"])
        meta_path = mp4_path.with_suffix(".meta.json")
        cat = r["drive_category"] or "CHARACTERS"
        cat_folder = DRIVE_VAULT_CATEGORIES.get(cat, DRIVE_VAULT_CATEGORIES["CHARACTERS"])

        if mp4_path.exists():
            try:
                with open(mp4_path, "rb") as f_clip:
                    drive_id = harvester.drive_engine.upload_raw_content(
                        content=f_clip.read(),
                        filename=mp4_path.name,
                        parent_folder_id=cat_folder,
                        mime_type="video/mp4"
                    )
                if meta_path.exists():
                    with open(meta_path, "rb") as f_meta:
                        harvester.drive_engine.upload_raw_content(
                            content=f_meta.read(),
                            filename=meta_path.name,
                            parent_folder_id=cat_folder,
                            mime_type="application/json"
                        )
                # Update DB
                cur2 = conn.cursor()
                cur2.execute("UPDATE franchise_clips SET drive_file_id = ? WHERE clip_id = ?", (str(drive_id), clip_id))
                conn.commit()
                print(f"[{i}/{len(rows)}] Uploaded {clip_id} -> Drive ID: {drive_id}")
            except Exception as e:
                print(f"[{i}/{len(rows)}] Error uploading {clip_id}: {e}")

    conn.close()
    print("All clips synced to Google Drive successfully!")

if __name__ == "__main__":
    sync_remaining()
