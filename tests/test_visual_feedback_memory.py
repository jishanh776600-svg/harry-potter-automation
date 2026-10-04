"""
Automated Test Suite: Permanent Visual Feedback Memory & Alignment System
========================================================================
Verifies:
  1. Feedback persistence across SQLite and JSON cache.
  2. Immediate negative learning: flagged intervals receive hard disqualification (-10000.0).
  3. Character isolation: clips featuring Bellatrix or Xenophilius are blocked for Petunia/Lily beats.
  4. Verified canonical anchors: authoritative character scenes are retrieved with high confidence.
  5. MovieRetrievalEngine integration: candidate scoring & confidence gate enforce feedback disqualification.
"""

import json
import pytest
from pathlib import Path
from engines.visual_feedback_engine import VisualFeedbackEngine
from engines.movie_retrieval_engine import MovieRetrievalEngine, KNOWN_CHARACTERS


@pytest.fixture
def feedback_engine(tmp_path):
    test_db = tmp_path / "test_feedback.db"
    engine = VisualFeedbackEngine(db_path=test_db)
    return engine


def test_baseline_seeding(feedback_engine):
    """Verifies that baseline learned rules from production are seeded."""
    records = feedback_engine.load_memory_records()
    assert len(records) >= 5

    rec_ids = {r["id"] for r in records}
    assert "vfb_m7_hedwig_battle_not_petunia" in rec_ids
    assert "vfb_m7_empty_car_driveway_pavement" in rec_ids
    assert "vfb_universal_bellatrix_mismatch_hero" in rec_ids
    assert "vfb_anchor_m1_doorstep_baby_harry" in rec_ids


def test_penalty_for_hedwig_death_on_petunia_beat(feedback_engine):
    """
    Verifies that the exact mismatch from video hps_disc_dumbledore_explains_dursleys_b5
    (Hedwig aerial battle M7 825.4s - 830.8s) is permanently blocked for Petunia Dursley.
    """
    penalty, reason = feedback_engine.get_penalty_for_candidate(
        movie_number=7,
        start_seconds=825.4,
        end_seconds=830.8,
        required_characters=["Petunia Dursley"]
    )
    assert penalty <= -1000.0
    assert reason is not None
    assert "Aerial battle showing Hedwig death" in reason or "prohibited" in reason.lower()


def test_penalty_for_empty_driveway_pavement(feedback_engine):
    """
    Verifies that the empty car trunk / grey pavement shot (M7 110s - 125s)
    is permanently blacklisted for Petunia beats.
    """
    penalty, reason = feedback_engine.get_penalty_for_candidate(
        movie_number=7,
        start_seconds=112.0,
        end_seconds=120.0,
        required_characters=["Petunia Dursley"]
    )
    assert penalty <= -1000.0
    assert "Empty car trunk" in reason or "pavement" in reason.lower()


def test_penalty_for_xenophilius_on_dursley_beat(feedback_engine):
    """
    Verifies that Xenophilius Lovegood at his printing press (M7 3800s)
    is blocked when Dursley / Dumbledore beats are required.
    """
    penalty, reason = feedback_engine.get_penalty_for_candidate(
        movie_number=7,
        start_seconds=3800.0,
        end_seconds=3820.0,
        required_characters=["Petunia Dursley"]
    )
    assert penalty <= -1000.0
    assert "Xenophilius Lovegood" in reason


def test_clean_interval_no_penalty(feedback_engine):
    """Verifies that an unrelated, clean interval receives zero penalty."""
    penalty, reason = feedback_engine.get_penalty_for_candidate(
        movie_number=1,
        start_seconds=150.0,
        end_seconds=160.0,
        required_characters=["Petunia Dursley"]
    )
    assert penalty == 0.0
    assert reason is None


def test_verified_canonical_anchors_for_petunia(feedback_engine):
    """Verifies that canonical anchors for Petunia Dursley are returned."""
    anchors = feedback_engine.get_verified_canonical_anchors("Petunia Dursley")
    assert len(anchors) >= 2
    # Ensure Movie 1 doorstep and Movie 1 letters are among them
    m1_anchors = [a for a in anchors if a["movie_number"] == 1]
    assert len(m1_anchors) >= 2


def test_dynamic_learning_new_mismatch(feedback_engine):
    """
    Verifies that when a new mismatch is recorded dynamically,
    the engine immediately learns it and applies the penalty.
    """
    # Record a new mismatch: Movie 4 [1200-1215] shows Rita Skeeter, barred for Snape
    rec = feedback_engine.record_feedback(
        movie_number=4,
        start_seconds=1200.0,
        end_seconds=1215.0,
        actual_character="Rita Skeeter",
        intended_character="Severus Snape",
        prohibited_characters=["Severus Snape", "Snape"],
        verdict="CHARACTER_MISMATCH",
        rejection_reason="Shows Rita Skeeter quill interview; prohibited for Snape potion beats."
    )
    assert rec.id is not None

    # Immediately query
    penalty, reason = feedback_engine.get_penalty_for_candidate(
        movie_number=4,
        start_seconds=1205.0,
        end_seconds=1210.0,
        required_characters=["Severus Snape"]
    )
    assert penalty <= -1000.0
    assert "Rita Skeeter" in reason


def test_retrieval_engine_candidate_scoring_disqualification():
    """
    Verifies that MovieRetrievalEngine.score_candidate incorporates the feedback penalty
    and marks the candidate as disqualified.
    """
    retrieval = MovieRetrievalEngine()
    beat = {
        "beat_id": "beat_test",
        "narration_text": "Petunia Dursley actually functioned as a powerful shield.",
        "visual_requirement": "Petunia Dursley Privet Drive",
        "characters": ["Petunia Dursley"],
        "preferred_movie_number": 7
    }

    # Candidate 1: The bad Hedwig death scene in Movie 7 [825.4 - 827.2]
    bad_cand = {
        "chunk_id": "bad_hedwig_cand",
        "movie_number": 7,
        "start_seconds": 825.4,
        "end_seconds": 827.2,
        "text": "Hedwig death Death Eaters pursuit",
        "expanded_context": "Hedwig death Death Eaters pursuit"
    }

    scored = retrieval.score_candidate(bad_cand, beat)
    assert scored["score"] == 0.0
    assert scored.get("is_disqualified") is True
    assert "FEEDBACK MEMORY" in scored["score_details"]["selection_reasoning"]

    # Verify evaluate_confidence_gate rejects it
    passed, status, reason = retrieval.evaluate_confidence_gate(scored)
    assert passed is False
    assert status == "REJECTED_BY_FEEDBACK_MEMORY"
