"""
Comprehensive Unit Tests for Revised Natural Cinematic Framing & Visual-Semantic Ranking
==========================================================================================
Validates the NEW FRAMING POLICY:
1. Normal character mention prefers natural MEDIUM / MEDIUM-WIDE over unnecessary close-up.
2. Normal character action prefers MEDIUM / MEDIUM-WIDE shot preserving context.
3. Character emotional reaction prefers CLOSE_UP / MCU ONLY when facial emotion is specified.
4. Environmental narration prefers WIDE shot.
5. Two-character interaction prefers TWO_SHOT.
6. Semantic relevance dominates across candidate scoring.
7. Anti-loop constraint (100 pt penalty for overlapping footage).
8. Movie-only policy (non-canonical movies rejected with 0 score).
9. No artificial zoom / tighter crop invariant.
10. Before/After demonstration that close-ups are NOT systematically favored.
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


# 1. TARGET SHOT SCALE INFERENCE ACROSS DIVERSE NARRATION TYPES
def test_target_shot_scale_inference(engine):
    # A. Normal character mention / action -> MEDIUM_SHOT (NOT close-up!)
    beat_action = {
        "text": "Neville picked up the glass Remembrall and held it in his hand.",
        "action": "picking up the Remembrall",
        "characters": ["Neville Longbottom"]
    }
    assert engine.infer_target_shot_scale(beat_action) == ShotScale.MEDIUM_SHOT

    # B. Character traversal through environment -> MEDIUM_WIDE
    beat_walk = {
        "text": "Harry walked into the Great Hall as dinner was being served.",
        "action": "Harry walks into the Great Hall",
        "characters": ["Harry Potter"],
        "location": "Great Hall"
    }
    assert engine.infer_target_shot_scale(beat_walk) == ShotScale.MEDIUM_WIDE

    # C. Explicit emotional reaction -> CLOSE_UP
    beat_emotion = {
        "text": "Harry's face filled with fear as the dark shadow crept forward.",
        "action": "facial expression of terror and fear",
        "shot_hint": "close-up of Harry's face filled with fear",
        "characters": ["Harry Potter"]
    }
    assert engine.infer_target_shot_scale(beat_emotion) == ShotScale.CLOSE_UP

    # D. Two-character interaction -> TWO_SHOT
    beat_two = {
        "text": "Dumbledore and Professor McGonagall conferred quietly outside number four.",
        "action": "two wizards conversing in low tones",
        "characters": ["Albus Dumbledore", "Minerva McGonagall"]
    }
    assert engine.infer_target_shot_scale(beat_two) == ShotScale.TWO_SHOT

    # E. Pure environmental narration -> WIDE_SHOT
    beat_env = {
        "text": "The massive Hogwarts castle stood against the starry night sky over the black lake.",
        "action": "establishing landscape view of the illuminated castle",
        "location": "Hogwarts landscape"
    }
    assert engine.infer_target_shot_scale(beat_env) == ShotScale.WIDE_SHOT


# 2. NORMAL CHARACTER MENTION PREFERS MEDIUM OVER UNNECESSARY CLOSE-UP
def test_normal_mention_prefers_medium_over_close_up(engine):
    beat = {
        "text": "Harry sat quietly by the fireplace in the Gryffindor common room.",
        "characters": ["Harry Potter"],
        "action": "Harry sitting by the hearth",
        "location": "Gryffindor common room"
    }

    # Candidate A: Natural medium shot showing Harry sitting + hearth context
    cand_medium = {
        "movie_number": 1,
        "text": "Harry sat by the fire, looking into the warm embers.",
        "matched_query": "Harry fire",
        "start_seconds": 1500.0,
        "end_seconds": 1503.0
    }

    # Candidate B: Unnecessary extreme close-up of Harry's face
    cand_close = {
        "movie_number": 1,
        "text": "Harry face in close-up, eyes reflecting light.",
        "matched_query": "Harry",
        "start_seconds": 1520.0,
        "end_seconds": 1523.0
    }

    score_med = engine.score_candidate(cand_medium, beat)
    score_close = engine.score_candidate(cand_close, beat)

    # Natural medium shot MUST outrank unnecessary close-up
    assert score_med["total_score"] > score_close["total_score"]
    # Medium shot receives full prominence (15 pts) while unnecessary close-up is penalized (8 pts)
    assert score_med["score_details"]["C_character_prominence"] > score_close["score_details"]["C_character_prominence"]
    assert score_med["score_details"]["F_shot_scale_suitability"] > score_close["score_details"]["F_shot_scale_suitability"]


# 3. NORMAL CHARACTER ACTION PREFERS MEDIUM / MEDIUM-WIDE
def test_normal_action_prefers_medium_wide(engine):
    beat = {
        "text": "Harry walked into the Great Hall surrounded by his peers.",
        "characters": ["Harry Potter"],
        "action": "walks into the Great Hall",
        "location": "Great Hall"
    }

    # Candidate 1: Medium-wide showing Harry walking + Great Hall architecture
    cand_mw = {
        "movie_number": 1,
        "text": "Harry walked into the hall, looking up at the floating candles.",
        "matched_query": "Harry hall",
        "start_seconds": 900.0,
        "end_seconds": 903.0
    }

    # Candidate 2: Tight close-up of face
    cand_cu = {
        "movie_number": 1,
        "text": "Harry face filled with wonder in extreme close-up.",
        "matched_query": "Harry",
        "start_seconds": 920.0,
        "end_seconds": 923.0
    }

    score_mw = engine.score_candidate(cand_mw, beat)
    score_cu = engine.score_candidate(cand_cu, beat)

    assert score_mw["total_score"] > score_cu["total_score"]
    assert score_mw["score_details"]["F_shot_scale_suitability"] >= 8.5
    assert score_cu["score_details"]["F_shot_scale_suitability"] <= 3.0


# 4. EMOTIONAL REACTION SPECIFICALLY CALLING FOR CLOSE-UP PREFERS CLOSE-UP
def test_emotional_reaction_prefers_close_up(engine):
    beat = {
        "text": "Harry's face filled with terror as he realized the truth.",
        "characters": ["Harry Potter"],
        "action": "facial expression of pure shock and horror",
        "emotional_context": "terror, shock, tears welling"
    }

    # Candidate 1: Close-up showing facial reaction
    cand_cu = {
        "movie_number": 1,
        "text": "Harry stared in disbelief, tears welling in his eyes in shock.",
        "matched_query": "Harry shock",
        "start_seconds": 3200.0,
        "end_seconds": 3203.0
    }

    # Candidate 2: Wide establishing shot of room
    cand_wide = {
        "movie_number": 1,
        "text": "A distant view of the classroom corridor.",
        "matched_query": "classroom",
        "start_seconds": 3220.0,
        "end_seconds": 3223.0
    }

    score_cu = engine.score_candidate(cand_cu, beat)
    score_wide = engine.score_candidate(cand_wide, beat)

    assert score_cu["total_score"] > score_wide["total_score"]
    assert score_cu["score_details"]["E_reaction_emotion_relevance"] == 10.0
    assert score_wide["score_details"]["E_reaction_emotion_relevance"] == 2.0


# 5. ENVIRONMENTAL NARRATION PREFERS WIDE SHOT
def test_environmental_narration_prefers_wide(engine):
    beat = {
        "text": "The illuminated castle of Hogwarts stood tall above the black lake.",
        "characters": [],
        "action": "establishing landscape view of the illuminated castle",
        "location": "Hogwarts landscape"
    }

    # Candidate 1: Wide landscape
    cand_wide = {
        "movie_number": 1,
        "text": "A panoramic wide shot of Hogwarts castle above the dark water.",
        "matched_query": "Hogwarts castle",
        "start_seconds": 1800.0,
        "end_seconds": 1803.0
    }

    # Candidate 2: Tight close-up
    cand_cu = {
        "movie_number": 1,
        "text": "Harry looking at a lantern in close-up.",
        "matched_query": "lantern",
        "start_seconds": 1820.0,
        "end_seconds": 1823.0
    }

    score_wide = engine.score_candidate(cand_wide, beat)
    score_cu = engine.score_candidate(cand_cu, beat)

    assert score_wide["total_score"] > score_cu["total_score"]
    assert score_wide["score_details"]["F_shot_scale_suitability"] == 10.0
    assert score_cu["score_details"]["F_shot_scale_suitability"] == 1.0


# 6. SEMANTIC RELEVANCE DOMINATES SCORING
def test_semantic_relevance_dominates(engine):
    beat = {
        "text": "Dumbledore held up the silver Deluminator and clicked it.",
        "characters": ["Albus Dumbledore"],
        "action": "clicking the Deluminator to extinguish the lamp",
        "preferred_movie_number": 1
    }

    # Candidate 1: Exact semantic match (Dumbledore with Deluminator)
    cand_sem = {
        "movie_number": 1,
        "text": "Dumbledore held up the silver Deluminator and clicked it.",
        "matched_query": "Dumbledore Deluminator",
        "start_seconds": 65.0,
        "end_seconds": 68.0
    }

    # Candidate 2: Random medium shot from same movie with zero semantic connection
    cand_unrelated = {
        "movie_number": 1,
        "text": "The owls fluttered around the rafters of the owlery.",
        "matched_query": "owls rafters",
        "start_seconds": 4500.0,
        "end_seconds": 4503.0
    }

    score_sem = engine.score_candidate(cand_sem, beat)
    score_unrelated = engine.score_candidate(cand_unrelated, beat)

    assert score_sem["total_score"] >= 70.0
    assert score_unrelated["total_score"] < 40.0
    assert score_sem["score_details"]["A_semantic_relevance"] > score_unrelated["score_details"]["A_semantic_relevance"]
    assert score_sem["score_details"]["B_named_character_presence"] > score_unrelated["score_details"]["B_named_character_presence"]


# 7. ANTI-LOOP CONSTRAINT ENFORCEMENT
def test_anti_loop_penalty_deduction(engine):
    beat = {
        "text": "Neville gripped his wand firmly.",
        "characters": ["Neville Longbottom"]
    }
    cand = {
        "movie_number": 1,
        "text": "Neville stood with his wand raised.",
        "matched_query": "Neville wand",
        "start_seconds": 2100.0,
        "end_seconds": 2103.0
    }

    # Clean run
    score_clean = engine.score_candidate(cand, beat, used_intervals=[])
    assert score_clean["score_details"]["H_anti_loop_penalty"] == 0.0
    assert score_clean["total_score"] >= 60.0

    # Looped run (overlapping footage)
    score_looped = engine.score_candidate(cand, beat, used_intervals=[(1, 2099.5, 2102.5)])
    assert score_looped["score_details"]["H_anti_loop_penalty"] == 100.0
    assert score_looped["total_score"] == 0.0


# 8. NON-CANONICAL MOVIE CANDIDATE REJECTION
def test_non_movie_candidate_rejection(engine):
    beat = {"text": "Harry stared in wonder.", "characters": ["Harry Potter"]}
    cand_invalid = {
        "movie_number": 99,
        "text": "Harry Potter animated fan film",
        "matched_query": "Harry"
    }
    res = engine.score_candidate(cand_invalid, beat)
    assert res["total_score"] == 0.0
    assert "REJECTED" in res["score_details"]["selection_reasoning"]


# 9. FACTOR BREAKDOWN INTEGRITY (A THROUGH H)
def test_factor_breakdown_integrity(engine):
    beat = {
        "text": "Harry walked into the potions dungeon.",
        "characters": ["Harry Potter"],
        "action": "Harry walking into the dark dungeon",
        "location": "Dungeon"
    }
    cand = {
        "movie_number": 1,
        "text": "Harry walked down the stone stairs into the dungeon.",
        "matched_query": "Harry dungeon",
        "start_seconds": 1400.0,
        "end_seconds": 1403.0
    }
    res = engine.score_candidate(cand, beat)
    details = res["score_details"]

    factors = [
        "A_semantic_relevance",
        "B_named_character_presence",
        "C_character_prominence",
        "D_action_relevance",
        "E_reaction_emotion_relevance",
        "F_shot_scale_suitability",
        "G_temporal_context_relevance",
        "H_anti_loop_penalty"
    ]
    for f in factors:
        assert f in details, f"Missing score factor {f}"


# 10. BEFORE/AFTER RANKING DEMONSTRATION
def test_before_after_ranking_demonstration(engine):
    """
    Demonstrates that for an ordinary character action beat,
    the system ranks natural medium framing higher than unnecessary close-ups.
    """
    beat = {
        "text": "Neville picked up the Remembrall from the grass.",
        "characters": ["Neville Longbottom"],
        "action": "Neville picking up the Remembrall",
        "location": "Flying grounds"
    }

    cands = [
        # Candidate 1: Unnecessary extreme close-up of Neville's face
        {
            "movie_number": 1,
            "text": "Neville face in extreme close-up with worried expression.",
            "matched_query": "Neville",
            "start_seconds": 2090.0,
            "end_seconds": 2093.0
        },
        # Candidate 2: Natural medium shot showing Neville + Remembrall + action
        {
            "movie_number": 1,
            "text": "Neville picked up the Remembrall from the grass, holding it up.",
            "matched_query": "Neville Remembrall",
            "start_seconds": 2100.0,
            "end_seconds": 2103.0
        },
        # Candidate 3: Distant wide shot of the grounds
        {
            "movie_number": 1,
            "text": "A wide view of the flying grounds with all the students gathered in the distance.",
            "matched_query": "grounds",
            "start_seconds": 2050.0,
            "end_seconds": 2053.0
        }
    ]

    for c in cands:
        engine.expand_candidate_context(c)

    ranked = engine.rerank_candidates(beat, cands)

    # Top candidate MUST be the natural medium shot showing Neville + action + context
    top = ranked[0]
    assert "picked up the Remembrall" in top["text"]
    assert top["framing"]["shot_scale"] in (ShotScale.MEDIUM_SHOT, ShotScale.MEDIUM_WIDE)
    # Confirm unnecessary close-up does NOT win
    assert top["score"] > ranked[1]["score"]
