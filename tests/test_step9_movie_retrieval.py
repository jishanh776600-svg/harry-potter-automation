"""
Unit and Integration Tests for Step 9: Movie Visual Retrieval & Clip Extraction
================================================================================
Validates:
  1. Visual beat query building and deduplication.
  2. Movie subtitle FTS5 search and candidate discovery.
  3. Candidate context expansion (prev/next scene dialogue).
  4. Multi-factor scoring and reranking (character, action, location, BM25, movie, duration).
  5. Confidence gate enforcement (>= 50.0 accepted, < 50.0 rejected).
  6. Visual source policy enforcement (MOVIE FOOTAGE ONLY, no AI, no stock).
  7. Audio muting invariant (-an strictly enforced, ffprobe confirms 0 audio streams).
  8. Persistence to hp_movie_clips with full lineage.
"""

import os
import json
import pytest
import sqlite3
import subprocess
from pathlib import Path

from config.settings import DB_PATH
from core.models import HPMovieClip, HarryPotterScript, MovieSubtitleChunk
from engines.movie_retrieval_engine import MovieRetrievalEngine, MIN_CONFIDENCE_THRESHOLD
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_MOVIES_DIR = Path("data/movies")
TEST_CLIPS_DIR = Path("data/clips")


@pytest.fixture(scope="module")
def engine():
    return MovieRetrievalEngine()


def test_query_builder(engine):
    beat = {
        "retrieval_hints": ["Neville", "sword", "courage", "hero"],
        "characters": ["Neville Longbottom"],
        "location": "Hogwarts courtyard ruins",
        "action": "Neville standing tall facing Voldemort's army",
        "visual_requirement": "Neville in Movie 8 standing bravely bloodied with sword of Gryffindor",
        "preferred_movie_number": 8
    }
    queries = engine.build_queries_for_beat(beat)
    assert len(queries) > 0
    assert any("Neville" in q for q in queries)
    assert any("sword" in q for q in queries)


def test_subtitle_search_and_context_expansion(engine):
    beat = {
        "retrieval_hints": ["Neville", "Longbottom"],
        "characters": ["Neville Longbottom"],
        "location": "Great Hall",
        "action": "Neville walking forward",
        "visual_requirement": "Young Neville walking up to Sorting stool",
        "preferred_movie_number": 1
    }
    candidates = engine.search_candidates_for_beat(beat, max_candidates=5)
    assert len(candidates) > 0
    first = candidates[0]
    assert "chunk_id" in first
    assert "start_seconds" in first
    assert "end_seconds" in first

    expanded = engine.expand_candidate_context(first)
    assert "expanded_context" in expanded
    assert "[SCENE:" in expanded["expanded_context"]


def test_multi_factor_scoring(engine):
    beat = {
        "retrieval_hints": ["Filch", "lantern"],
        "characters": ["Argus Filch"],
        "location": "corridor",
        "action": "Filch holding lantern prowling for troublemakers",
        "visual_requirement": "Filch prowling dark corridor",
        "preferred_movie_number": 1
    }
    # Candidate mentioning Filch in Movie 1
    good_cand = {
        "chunk_id": "hp_m1_sc_0181",
        "movie_number": 1,
        "movie_title": "Harry Potter and the Sorcerer's Stone",
        "start_seconds": 2547.0,
        "end_seconds": 2559.0,
        "duration_seconds": 12.0,
        "text": "Also, our caretaker, Mr. Filch, has asked me to remind you...",
        "relevance_rank": -2.5,
        "matched_query": "Filch"
    }
    scored = engine.score_candidate(good_cand, beat)
    assert scored["score"] >= 50.0
    assert scored["score_details"]["character_score"] > 0
    assert scored["score_details"]["preferred_movie_score"] == 15.0

    # Irrelevant candidate
    bad_cand = {
        "chunk_id": "hp_m1_sc_9999",
        "movie_number": 2,
        "movie_title": "Harry Potter and the Chamber of Secrets",
        "start_seconds": 10.0,
        "end_seconds": 12.0,
        "duration_seconds": 2.0,
        "text": "Eat your porridge, Dudley.",
        "relevance_rank": 0.0,
        "matched_query": "Dudley"
    }
    scored_bad = engine.score_candidate(bad_cand, beat)
    assert scored_bad["score"] < 50.0


def test_confidence_gate_and_visual_policy(engine):
    # Accepted candidate
    good_cand = {"movie_number": 8, "score": 75.0}
    is_acc, status, reason = engine.evaluate_confidence_gate(good_cand)
    assert is_acc is True
    assert status == "ACCEPTED"

    # Low score rejected
    low_cand = {"movie_number": 1, "score": 35.0}
    is_acc, status, reason = engine.evaluate_confidence_gate(low_cand)
    assert is_acc is False
    assert status == "REJECTED"
    assert "LOW_RETRIEVAL_CONFIDENCE" in reason

    # Non-canonical movie number rejected (simulating external video or bad input)
    invalid_cand = {"movie_number": 99, "score": 90.0}
    is_acc, status, reason = engine.evaluate_confidence_gate(invalid_cand)
    assert is_acc is False
    assert status == "REJECTED"

    # No candidate rejected
    is_acc, status, reason = engine.evaluate_confidence_gate(None)
    assert is_acc is False
    assert status == "REJECTED"


def test_extracted_clip_audio_muting_invariant():
    """Verifies that extracted clips on disk have ZERO audio streams."""
    clip_path = TEST_CLIPS_DIR / "hps_disc_neville_hufflepuff_sorting_b1_beat_4.mp4"
    if not clip_path.exists():
        pytest.skip("Movie 8 clip not yet extracted")

    # Run ffprobe to check streams
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,codec_name,width,height",
        "-of", "json",
        str(clip_path)
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    streams = data.get("streams", [])

    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    video_streams = [s for s in streams if s.get("codec_type") == "video"]

    # HARD INVARIANTS:
    assert len(video_streams) == 1, "Clip must contain exactly 1 video stream"
    assert len(audio_streams) == 0, "AUDIO MUTING INVARIANT VIOLATION: Audio stream found in movie clip!"
    assert video_streams[0]["width"] == 1080
    assert video_streams[0]["height"] == 1920


def test_hp_movie_clips_db_persistence():
    """Verifies all 16 visual beats are persisted in hp_movie_clips table with valid lineage."""
    engine_sa = create_engine(f"sqlite:///{DB_PATH}")
    Session = sessionmaker(bind=engine_sa)

    with Session() as session:
        clips = session.query(HPMovieClip).all()
        assert len(clips) == 16, f"Expected 16 clips in DB, found {len(clips)}"

        for c in clips:
            assert c.script_id.startswith("hps_")
            assert c.beat_id.startswith("beat_")
            assert 1 <= c.movie_number <= 8
            assert c.visual_source_policy == "MOVIE_FOOTAGE_ONLY"
            assert c.audio_stream_count == 0
            assert c.match_status in ("ACCEPTED", "REJECTED")
            assert c.duration_seconds > 0.0
            assert c.clip_start_seconds >= 0.0
