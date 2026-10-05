"""
STORY FORGE — Franchise Vault Batch Harvester (Part 2: Movies 1, 2, 3)
======================================================================
Systematically scans narrative blocks across Harry Potter Movies 1, 2, and 3.
Detects camera shot cuts via accelerated FFmpeg filter, inspects frames with
Llama-3.2 Vision AI on NVIDIA NIM, cuts audio-muted 1080x1920 vertical clips,
saves .meta.json sidecars, records in SQLite FTS5 database, and uploads to
Google Drive Vault (04_FRANCHISE_CLIPS_VAULT).
"""
import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import MOVIES_DIR
from engines.franchise_visual_harvester import FranchiseVisualHarvester
from core.franchise_clip_db import get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / "data" / "logs" / "franchise_harvest.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("VaultBatch")

MOVIE_SPECS = [
    {
        "movie_number": 1,
        "title": "Harry Potter and the Sorcerer's Stone",
        "filename": "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv",
        # Narrative sequence blocks (start_sec, duration_sec, block_name)
        "blocks": [
            (60.0, 480.0, "Privet Drive & Delivery"),
            (700.0, 500.0, "Zoo Snake & Letters"),
            (1300.0, 600.0, "Hagrid Cabin & Diagon Alley"),
            (2100.0, 500.0, "Gringotts Vault & Ollivanders"),
            (2700.0, 500.0, "Platform 9 3/4 & Hogwarts Express"),
            (3300.0, 600.0, "Sorting Hat & Feast"),
            (3900.0, 600.0, "Snape Potions & Flying Lesson"),
            (4800.0, 600.0, "Fluffy & Halloween Troll"),
            (5600.0, 600.0, "Quidditch Match & Cloak of Invisibility"),
            (6400.0, 600.0, "Mirror of Erised & Norbert"),
            (7200.0, 600.0, "Forbidden Forest & Voldemort Unicorn"),
            (7900.0, 700.0, "Chessboard & Quirrell Voldemort Climax")
        ]
    },
    {
        "movie_number": 2,
        "title": "Harry Potter and the Chamber of Secrets",
        "filename": "Harry Potter and the Chamber of Secrets (2002) Dual Audio {Hindi-English} 1080p.mkv",
        "blocks": [
            (60.0, 500.0, "Dobby in Bedroom & Flying Car"),
            (700.0, 600.0, "The Burrow & Weasley Clock"),
            (1400.0, 500.0, "Borgin & Burkes & Knockturn Alley"),
            (2000.0, 600.0, "Whomping Willow & Howler"),
            (2800.0, 500.0, "Lockhart Pixies & Writing on Wall"),
            (3500.0, 600.0, "Rogue Bludger & Dueling Club Parseltongue"),
            (4400.0, 600.0, "Polyjuice Potion & Malfoy Common Room"),
            (5300.0, 600.0, "Tom Riddle Diary Memory"),
            (6200.0, 600.0, "Aragog in Forbidden Forest"),
            (7100.0, 700.0, "Chamber of Secrets Entrance"),
            (7900.0, 800.0, "Basilisk, Fawkes & Diary Destruction")
        ]
    },
    {
        "movie_number": 3,
        "title": "Harry Potter and the Prisoner of Azkaban",
        "filename": "3. Harry Potter and the Prisoner of Azkaban 2004 BluRay x265 [Org DD Hindi + DD 5.1 Eng] ESubs 1080p.mkv",
        "blocks": [
            (60.0, 500.0, "Aunt Marge & Knight Bus"),
            (700.0, 500.0, "Leaky Cauldron & Sirius Warning"),
            (1300.0, 500.0, "Hogwarts Express Dementor & Lupin"),
            (2000.0, 600.0, "Boggart Wardrobe & Snape Dress"),
            (2800.0, 600.0, "Buckbeak Flight & Draco Attack"),
            (3600.0, 600.0, "Fat Lady Slashing & Marauder's Map"),
            (4500.0, 600.0, "Patronus Lesson with Lupin"),
            (5300.0, 600.0, "Shrieking Shack Scabbers & Sirius Reveal"),
            (6100.0, 600.0, "Lupin Werewolf Transformation"),
            (6900.0, 700.0, "Dementors at Black Lake"),
            (7600.0, 800.0, "Time-Turner Execution & Rescue")
        ]
    }
]

def run_batch(movie_filter: int = 1, max_clips_per_block: int = 4):
    harvester = FranchiseVisualHarvester()
    
    # Filter movie
    spec = next((m for m in MOVIE_SPECS if m["movie_number"] == movie_filter), None)
    if not spec:
        logger.error(f"Movie {movie_filter} not found in specifications.")
        return

    movie_path = MOVIES_DIR / spec["filename"]
    if not movie_path.exists():
        logger.error(f"Movie file not found on disk: {movie_path}")
        return

    logger.info(f"============================================================")
    logger.info(f"STARTING FRANCHISE BATCH HARVEST: Movie {spec['movie_number']} - {spec['title']}")
    logger.info(f"File: {movie_path.name} ({movie_path.stat().st_size // (1024*1024)} MB)")
    logger.info(f"Total Blocks: {len(spec['blocks'])} | Max clips per block: {max_clips_per_block}")
    logger.info(f"============================================================")

    total_harvested = 0
    t0_all = time.time()

    for b_idx, (st_sec, dur_sec, block_name) in enumerate(spec["blocks"], start=1):
        logger.info(f"\n>>> [Block {b_idx}/{len(spec['blocks'])}] {block_name} ({st_sec:.0f}s - {st_sec+dur_sec:.0f}s) <<<")
        try:
            clips = harvester.harvest_movie(
                movie_number=spec["movie_number"],
                movie_title=spec["title"],
                movie_path=movie_path,
                max_clips=max_clips_per_block,
                start_offset_sec=st_sec,
                scan_window_sec=dur_sec
            )
            total_harvested += len(clips)
            logger.info(f"[+] Harvested {len(clips)} clips for '{block_name}' (Total Movie {movie_filter} so far: {total_harvested})")
        except Exception as e:
            logger.error(f"Error harvesting block '{block_name}': {e}", exc_info=True)

    t1_all = time.time()
    logger.info(f"\n============================================================")
    logger.info(f"FINISHED Movie {spec['movie_number']} ({spec['title']})")
    logger.info(f"Total Clips Harvested & Uploaded to Drive: {total_harvested}")
    logger.info(f"Time Taken: {(t1_all - t0_all)/60:.1f} minutes")
    logger.info(f"============================================================")

if __name__ == "__main__":
    m_target = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    max_c = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    run_batch(movie_filter=m_target, max_clips_per_block=max_c)
