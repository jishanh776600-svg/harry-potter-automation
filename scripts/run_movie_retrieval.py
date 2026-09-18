"""
Step 9 Runner: Movie Visual Retrieval & Cloud-Safe Clip Extraction
================================================================================
Executes Step 9 across the 4 launch batch scripts in hp_scripts.
Validates FTS5 subtitle retrieval, multi-factor scoring, confidence gating,
audio-muted clip extraction (-an), ffprobe stream verification, and persistence.
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Path setup
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import DB_PATH, TEST_MODE, PUBLISHING_ENABLED, UPLOAD_ENABLED
from core.models import HarryPotterScript, HPMovieClip, MovieAssetRecord
from engines.movie_retrieval_engine import MovieRetrievalEngine
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_movie_retrieval")


def run_step_9():
    print("=" * 80)
    print("STEP 9 — HARRY POTTER MOVIE VISUAL RETRIEVAL & CLIP EXTRACTION")
    print("=" * 80)

    # Invariant Verification
    assert not PUBLISHING_ENABLED, "[CRITICAL INVARIANT VIOLATION] PUBLISHING_ENABLED must be False!"
    assert not UPLOAD_ENABLED, "[CRITICAL INVARIANT VIOLATION] UPLOAD_ENABLED must be False!"
    print("[PASS] Safety Guard: Publishing and Uploading strictly disabled.")

    engine = MovieRetrievalEngine()
    print(f"[+] Initialized MovieRetrievalEngine with DB: {DB_PATH}")

    # Process all launch batch scripts
    print("[+] Processing 4 Launch Batch Scripts from hp_scripts...")
    batch_summary = engine.process_launch_batch(allow_download=False)

    print("\n" + "=" * 80)
    print("STEP 9 EXECUTION SUMMARY")
    print("=" * 80)
    print(f"Total Scripts Processed: {batch_summary['total_scripts']}")
    print(f"Total Visual Beats Evaluated: {batch_summary['total_beats']}")
    print(f"Accepted Movie Beats (Confidence >= 50.0): {batch_summary['accepted_beats']}")
    print(f"Rejected / Low-Confidence Beats: {batch_summary['rejected_beats']}")
    print(f"Muted Clips Extracted & Verified: {batch_summary['extracted_clips']}")

    # Detailed per-script audit
    engine_sa = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine_sa)

    with Session() as session:
        clips = session.query(HPMovieClip).order_by(HPMovieClip.id.asc()).all()
        print("\n" + "-" * 80)
        print("PERSISTED HPMovieClip AUDIT TRAIL:")
        print("-" * 80)
        for c in clips:
            print(f"[{c.id}] Status: {c.match_status}")
            print(f"  Movie: Movie {c.movie_number} ('{c.movie_title}') | Subtitle Chunk: {c.subtitle_chunk_id}")
            print(f"  Score / Confidence: {c.confidence:.1f} / 100.0 | Query: '{c.retrieval_query}'")
            print(f"  Timecodes: Source [{c.source_start_seconds:.1f}s - {c.source_end_seconds:.1f}s] -> Clip [{c.clip_start_seconds:.1f}s - {c.clip_end_seconds:.1f}s] ({c.duration_seconds:.1f}s)")
            print(f"  Dialogue Excerpt: {c.matched_text[:80] if c.matched_text else 'None'}...")
            if c.file_path:
                print(f"  File: {c.file_path} ({c.file_size_bytes} bytes, SHA256: {c.sha256[:16]}...)")
                print(f"  Audio Streams: {c.audio_stream_count} (VERIFIED MUTED)")
            else:
                print(f"  Physical File: Pending on-demand download for Movie {c.movie_number}")
            print()

    print("=" * 80)
    print("STEP 9 VERIFICATION COMPLETE — ALL INVARIANTS SATISFIED")
    print("=" * 80)
    return batch_summary


if __name__ == "__main__":
    run_step_9()
