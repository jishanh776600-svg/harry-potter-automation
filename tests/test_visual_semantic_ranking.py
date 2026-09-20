"""
Comprehensive Unit Tests for Visual-Semantic Match & Character Framing Ranking
================================================================================
Validates:
1. Target shot scale inference (CLOSE_UP, MEDIUM_CLOSE_UP, MEDIUM_SHOT, TWO_SHOT, WIDE_SHOT).
2. Candidate framing & scale inference.
3. Character prominence scoring (Close-up/Medium beats Wide shots for character focus).
4. Visual-semantic matching scoring (Character action/emotion vs generic crowd/scene).
5. Anti-loop penalty (100-point penalty for overlapping footage).
6. Movie-only gate (Non-movie candidates rejected).
7. Complete factor breakdown (A to H).
8. Deterministic ranking on sample story beats.
"""

import pytest
from typing import Dict, Any

from engines.movie_retrieval_engine import (
    MovieRetrievalEngine,
    ShotScale,
    MIN_CONFIDENCE_THRESHOLD,
)


@pytest.fixture(scope="module")
def engine():
    return MovieRetrievalEngine()


# 1. TARGET SHOT SCALE INFERENCE
def test_target_shot_scale_inference(engine):
    # A. Close-up: emotion, realization, surprise, fear
    beat_cu = {
        "text": "Harry stared in pure shock and disbelief as the mirror revealed his family.",
        "action": "gazing with astonishment and tearful emotion",
        "shot_hint": "extreme close-up of Harry's eyes and face"
    }
    assert engine.infer_target_shot_scale(beat_cu) == ShotScale.CLOSE_UP

    # B. Two-shot: interaction between two characters
    beat_two = {
        "text": "Dumbledore and Professor McGonagall conferred quietly outside number four.",
        "action": "two wizards conversing in low tones",
        "characters": ["Albus Dumbledore", "Minerva McGonagall"]
    }
    assert engine.infer_target_shot_scale(beat_two) == ShotScale.TWO_SHOT

    # C. Medium shot: character action / gesture
    beat_ms = {
        "text": "Neville clutched the glass sphere tightly as smoke swirled inside it.",
        "action": "holding up the remembrall and gesturing to his classmates",
        "characters": ["Neville Longbottom"]
    }
    assert engine.infer_target_shot_scale(beat_ms) in (ShotScale.MEDIUM_SHOT, ShotScale.MEDIUM_CLOSE_UP)

    # D. Wide shot: landscape / environment / group
    beat_ws = {
        "text": "The massive Hogwarts castle stood against the starry night sky over the black lake.",
        "action": "establishing landscape view of the illuminated castle",
        "location": "Hogwarts landscape"
    }
    assert engine.infer_target_shot_scale(beat_ws) == ShotScale.WIDE_SHOT


# 2. CANDIDATE FRAMING INFERENCE
def test_candidate_framing_inference(engine):
    # Close-up candidate
    cand_cu = {
        "text": "Harry looked closely, his eyes widening in recognition.",
        "chunk_id": "c_001",
        "movie_number": 1
    }
    beat = {"characters": ["Harry Potter"], "text": "Harry stared in shock"}
    framing_cu = engine.infer_candidate_framing_and_scale(cand_cu, beat)
    assert framing_cu["shot_scale"] in (ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE_UP)

    # Wide shot candidate
    cand_ws = {
        "text": "The Great Hall was packed with students from all four houses seated across long tables.",
        "chunk_id": "c_002",
        "movie_number": 1
    }
    framing_ws = engine.infer_candidate_framing_and_scale(cand_ws, beat)
    assert framing_ws["shot_scale"] == ShotScale.WIDE_SHOT


# 3. FACTOR BREAKDOWN (A TO H) INTEGRITY
def test_score_breakdown_structure(engine):
    beat = {
        "text": "Harry gasped as the Sorting Hat shouted his destiny.",
        "characters": ["Harry Potter"],
        "action": "gasping in suspense"
    }
    cand = {
        "movie_number": 1,
        "text": "Harry took a deep breath, sitting anxiously upon the stool.",
        "matched_query": "Harry",
        "start_seconds": 120.0,
        "end_seconds": 123.0
    }
    result = engine.score_candidate(cand, beat)
    assert "total_score" in result
    details = result["score_details"]

    required_keys = [
        "A_semantic_relevance",
        "B_named_character_presence",
        "C_character_prominence",
        "D_action_relevance",
        "E_reaction_emotion_relevance",
        "F_shot_scale_suitability",
        "G_temporal_context_relevance",
        "H_anti_loop_penalty"
    ]
    for k in required_keys:
        assert k in details, f"Missing score factor {k}"

    assert details["H_anti_loop_penalty"] == 0.0


# 4. CHARACTER PROMINENCE SCORING: CLOSE-UP OUTRANKS DISTANT WIDE
def test_character_prominence_beats_distant_wide(engine):
    beat = {
        "text": "Neville looked down in intense embarrassment as Malfoy snatched the Remembrall.",
        "characters": ["Neville Longbottom"],
        "action": "Neville reacting with dismay and shame",
        "location": "Flying grounds"
    }

    # Candidate 1: Close-up / medium reaction of Neville
    cand_close = {
        "movie_number": 1,
        "text": "Neville's face dropped in despair, watching the glass ball.",
        "matched_query": "Neville",
        "start_seconds": 2100.0,
        "end_seconds": 2103.0
    }

    # Candidate 2: Distant wide establishing crowd shot of the grounds
    cand_wide = {
        "movie_number": 1,
        "text": "A wide view of the flying grounds lawn with all the students gathered in the distance.",
        "matched_query": "Neville",
        "start_seconds": 2080.0,
        "end_seconds": 2083.0
    }

    score_close = engine.score_candidate(cand_close, beat)
    score_wide = engine.score_candidate(cand_wide, beat)

    assert score_close["total_score"] > score_wide["total_score"]
    # Close candidate should have higher prominence (C) and emotion (E) scores
    assert score_close["score_details"]["C_character_prominence"] > score_wide["score_details"]["C_character_prominence"]
    assert score_close["score_details"]["E_reaction_emotion_relevance"] > score_wide["score_details"]["E_reaction_emotion_relevance"]


# 5. ANTI-LOOP PENALTY
def test_anti_loop_penalty_deduction(engine):
    beat = {
        "text": "Dumbledore raised his Deluminator to extinguish the lamp.",
        "characters": ["Albus Dumbledore"],
        "action": "clicking deluminator"
    }
    cand = {
        "movie_number": 1,
        "text": "Dumbledore held up the silver Deluminator and clicked it.",
        "matched_query": "Dumbledore Deluminator",
        "start_seconds": 65.0,
        "end_seconds": 68.0
    }

    # Without prior intervals
    score_clean = engine.score_candidate(cand, beat, used_intervals=[])
    assert score_clean["score_details"]["H_anti_loop_penalty"] == 0.0
    assert score_clean["total_score"] >= 60.0

    # With overlapping interval in the same movie
    used = [(1, 64.0, 67.5)]  # Overlaps significantly
    score_looped = engine.score_candidate(cand, beat, used_intervals=used)
    assert score_looped["score_details"]["H_anti_loop_penalty"] == 100.0
    assert score_looped["total_score"] == 0.0  # Penalized to 0


# 6. NON-CANONICAL MOVIE CANDIDATE REJECTION
def test_non_movie_candidate_rejection(engine):
    beat = {
        "text": "Harry stared in amazement.",
        "characters": ["Harry Potter"]
    }
    cand_invalid = {
        "movie_number": 99,  # Not in 1..8
        "text": "Harry Potter animated clip",
        "matched_query": "Harry"
    }
    res = engine.score_candidate(cand_invalid, beat)
    assert res["total_score"] == 0.0
    assert res["score_details"]["A_semantic_relevance"] == 0.0


# 7. RERANKING CANDIDATES WITH PREFERENCE SYSTEM
def test_reranking_selects_most_prominent_match(engine):
    beat = {
        "text": "Harry gazed deeply into the Mirror of Erised, mesmerized by his mother's smile.",
        "characters": ["Harry Potter"],
        "action": "Harry gazing at his reflection in the mirror with tender emotion",
        "location": "Secret classroom"
    }

    cands = [
        {
            "movie_number": 1,
            "text": "The dark empty abandoned classroom stood silent with cold stone walls.",
            "matched_query": "classroom",
            "start_seconds": 3600.0,
            "end_seconds": 3603.0
        },
        {
            "movie_number": 1,
            "text": "Harry stepped closer, gazing into the glass, tears welling in his eyes as he saw Lily Potter.",
            "matched_query": "Harry mirror",
            "start_seconds": 3620.0,
            "end_seconds": 3624.0
        },
        {
            "movie_number": 1,
            "text": "A full room view showing the massive ornate gold frame of the Mirror of Erised.",
            "matched_query": "Mirror of Erised",
            "start_seconds": 3605.0,
            "end_seconds": 3608.0
        }
    ]

    for c in cands:
        engine.expand_candidate_context(c)

    ranked = engine.rerank_candidates(beat, cands)

    # Top candidate should be the intimate, character-focused shot showing Harry's emotion
    top = ranked[0]
    assert "gazing into the glass" in top["text"]
    assert top["framing"]["shot_scale"] in (ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE_UP)
    assert top["score"] > ranked[1]["score"]
