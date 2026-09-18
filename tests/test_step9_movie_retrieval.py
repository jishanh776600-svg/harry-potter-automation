"""
Focused Sanity Checks for Step 9 Correction:
================================================================================
1. Step-9 shot-duration logic (1.5s - 3.0s).
2. Beat -> multiple-shot mapping (1 beat yields >= 2 rapid shots).
3. Movie-only enforcement (no AI, no stock, rejection of non-canonical movies).
4. Drive source resolution (all 8 movies have valid Google Drive file IDs).
5. Movie 8 cloud resolution (Movie 8 resolves from Drive ID, independent of local copy).
6. Audio-free extraction (FFmpeg -an verified with ffprobe, 0 audio streams).
7. 1080x1920 output (verified vertical 9:16 aspect ratio).
8. Idempotency / no duplicate clip records.
"""

import json
import pytest
import subprocess
from pathlib import Path

from config.settings import DB_PATH
from core.models import HPMovieClip
from core.movie_registry import CANONICAL_MOVIES, get_movie_by_number
from engines.movie_retrieval_engine import (
    MovieRetrievalEngine,
    MIN_SHOT_DURATION,
    MAX_SHOT_DURATION,
    MIN_CONFIDENCE_THRESHOLD,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

CLIPS_DIR = Path("data/clips")


@pytest.fixture(scope="module")
def engine():
    return MovieRetrievalEngine()


# 1. Step-9 shot-duration logic
def test_shot_duration_logic(engine):
    """Verifies that all resolved shots conform strictly to the 1.5s - 3.0s duration window."""
    beat = {
        "retrieval_hints": ["Neville", "sword"],
        "characters": ["Neville Longbottom"],
        "location": "Hogwarts ruins",
        "action": "Neville standing brave with sword",
        "preferred_movie_number": 8
    }
    candidates = engine.search_candidates_for_beat(beat)
    for c in candidates:
        engine.expand_candidate_context(c)
    ranked = engine.rerank_candidates(beat, candidates)
    shots = engine.resolve_beat_to_shots(beat, ranked, target_shots_per_beat=2)

    assert len(shots) >= 1
    for sh in shots:
        dur = sh["duration_seconds"]
        assert MIN_SHOT_DURATION <= dur <= MAX_SHOT_DURATION, f"Shot duration {dur} out of bounds [1.5, 3.0]"


# 2. Beat -> multiple-shot mapping
def test_beat_to_multiple_shots_mapping(engine):
    """Verifies that 1 visual beat decomposes into multiple rapid shot units."""
    beat = {
        "retrieval_hints": ["Filch", "corridor", "lantern"],
        "characters": ["Argus Filch"],
        "location": "corridor",
        "action": "Filch holding lantern prowling",
        "preferred_movie_number": 1
    }
    candidates = engine.search_candidates_for_beat(beat)
    for c in candidates:
        engine.expand_candidate_context(c)
    ranked = engine.rerank_candidates(beat, candidates)
    shots = engine.resolve_beat_to_shots(beat, ranked, target_shots_per_beat=2)

    assert len(shots) >= 2, f"Expected at least 2 shots per beat, got {len(shots)}"
    shot_ids = [s["shot_id"] for s in shots]
    assert "shot_1" in shot_ids
    assert "shot_2" in shot_ids


# 3. Movie-only enforcement
def test_movie_only_enforcement(engine):
    """Verifies that non-movie visuals and non-canonical movie numbers are strictly rejected."""
    # Score below threshold rejected
    low_cand = {"movie_number": 1, "score": 35.0}
    is_acc, status, reason = engine.evaluate_confidence_gate(low_cand)
    assert not is_acc
    assert status == "REJECTED"
    assert "LOW_RETRIEVAL_CONFIDENCE" in reason

    # Non-canonical movie number (simulating external or AI source) rejected
    external_cand = {"movie_number": 99, "score": 90.0}
    is_acc, status, reason = engine.evaluate_confidence_gate(external_cand)
    assert not is_acc
    assert status == "REJECTED"
    assert "NON_CANONICAL_MOVIE_NUMBER" in reason


# 4. Drive source resolution for all 8 movies
def test_drive_source_resolution_all_movies():
    """Verifies that every canonical movie has an authoritative Google Drive File ID configured."""
    assert len(CANONICAL_MOVIES) == 8
    for m in CANONICAL_MOVIES:
        fid = m.get("video_drive_id")
        assert fid and len(fid) > 10, f"Movie {m['movie_number']} missing valid video_drive_id"
        assert m.get("video_filename"), f"Movie {m['movie_number']} missing video_filename"


# 5. Movie 8 cloud resolution
def test_movie_8_cloud_resolution(engine):
    """Verifies that Movie 8 resolves via its dedicated Google Drive ID, not local disk dependency."""
    meta = get_movie_by_number(8)
    assert meta["video_drive_id"] == "1GHpEuPlHh8wFdXOKPYoWnyFx6d2dSOff"
    assert meta["movie_number"] == 8

    # Ensure engine resolution returns drive_id
    _, source_mode, drive_id = engine.resolve_movie_file(8, allow_download=False)
    assert drive_id == "1GHpEuPlHh8wFdXOKPYoWnyFx6d2dSOff"


# 6. Audio-free extraction
def test_audio_free_extraction():
    """Verifies that extracted movie clips have ZERO audio streams."""
    clip_path = CLIPS_DIR / "hps_disc_neville_hufflepuff_sorting_b1_beat_4_shot_1.mp4"
    if not clip_path.exists():
        pytest.skip("Test clip not found")

    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type",
        "-of", "json",
        str(clip_path)
    ]
    res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    assert len(audio_streams) == 0, "AUDIO MUTING INVARIANT VIOLATION: audio stream detected!"


# 7. 1080x1920 output
def test_vertical_resolution_output():
    """Verifies that extracted clips have 1080x1920 (9:16 vertical) dimensions."""
    clip_path = CLIPS_DIR / "hps_disc_neville_hufflepuff_sorting_b1_beat_4_shot_1.mp4"
    if not clip_path.exists():
        pytest.skip("Test clip not found")

    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,codec_type",
        "-of", "json",
        str(clip_path)
    ]
    res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    assert len(video_streams) == 1
    assert video_streams[0]["width"] == 1080
    assert video_streams[0]["height"] == 1920


# 8. Idempotency & no duplicate clip records
def test_idempotency_and_no_duplicates(engine):
    """Verifies that running process_launch_batch repeatedly updates records without duplicating primary keys."""
    engine_sa = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine_sa)

    with Session() as session:
        initial_count = session.query(HPMovieClip).count()
        assert initial_count > 0

    # Re-run for single script
    engine.process_script_shots("hps_disc_neville_hufflepuff_sorting_b1", allow_download=False)

    with Session() as session:
        after_count = session.query(HPMovieClip).count()
        assert after_count == initial_count, "Duplicate records were inserted on re-run!"
