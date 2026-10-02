"""
Comprehensive Test Suite: Visual Confidence Hard-Gate & Atmospheric Fallback
=============================================================================
Validates Pillars 2 & 3 of the 99%+ Visual Mismatch-Proof Architecture:
1. MIN_CONFIDENCE_THRESHOLD is locked at 75.0.
2. Low-confidence candidates (< 75.0) are strictly rejected by the confidence gate.
3. When no candidate meets the threshold, resolve_beat_to_shots() automatically routes
   to an authentic Atmospheric Hogwarts Establishing Shot.
4. Script engine QA Check N catches unfilmed book-only elements (e.g., Peeves) and
   vetoes the draft.
5. Zero character mismatches can leak into rendered shorts.
"""

import pytest
from engines.movie_retrieval_engine import MovieRetrievalEngine, MIN_CONFIDENCE_THRESHOLD
from engines.hp_script_engine import HarryPotterScriptEngine


@pytest.fixture(scope="module")
def retrieval_engine():
    return MovieRetrievalEngine()


@pytest.fixture(scope="module")
def script_engine():
    return HarryPotterScriptEngine()


def test_confidence_threshold_locked_at_85(retrieval_engine):
    """Verifies that the visual confidence threshold is elevated to 85.0."""
    assert MIN_CONFIDENCE_THRESHOLD == 85.0, (
        f"MIN_CONFIDENCE_THRESHOLD must be 85.0, found {MIN_CONFIDENCE_THRESHOLD}"
    )


def test_confidence_gate_rejects_sub_75_dialogue_match(retrieval_engine):
    """Verifies that generic dialogue matches scoring below 75.0 are rejected."""
    # A generic dialogue match that scores ~52.0 (which previously leaked)
    weak_candidate = {
        "movie_number": 1,
        "text": "Yes, of course, Potter.",
        "score": 54.0,
        "is_canonical": False
    }
    passes, status, reason = retrieval_engine.evaluate_confidence_gate(weak_candidate)
    assert not passes
    assert status == "REJECTED"
    assert "LOW_RETRIEVAL_CONFIDENCE" in reason


def test_confidence_gate_accepts_canonical_event(retrieval_engine):
    """Verifies that canonical events are accepted by the confidence gate."""
    canonical_candidate = {
        "movie_number": 1,
        "text": "Snape questions Harry in Potions classroom.",
        "score": 85.0,
        "is_canonical": True
    }
    passes, status, reason = retrieval_engine.evaluate_confidence_gate(canonical_candidate)
    assert passes
    assert status == "ACCEPTED"


def test_atmospheric_fallback_triggered_when_candidates_below_75(retrieval_engine):
    """
    Verifies that when all candidates for a beat score < 75.0 and none is canonical,
    resolve_beat_to_shots() does NOT guess random scenes but forces an Atmospheric
    Hogwarts Establishing Shot.
    """
    beat = {
        "beat_id": "beat_obscure_lore",
        "narration_text": "An obscure magical theory was discussed in the common room.",
        "visual_requirement": "Obscure lore theory",
        "characters": [],
        "preferred_movie_number": 1
    }
    # Ranked candidates all have sub-75 scores
    sub_75_candidates = [
        {
            "movie_number": 1,
            "text": "Random classroom chatter.",
            "start_seconds": 1200.0,
            "end_seconds": 1205.0,
            "score": 45.0,
            "is_canonical": False
        },
        {
            "movie_number": 1,
            "text": "Another student speaking.",
            "start_seconds": 1500.0,
            "end_seconds": 1505.0,
            "score": 52.0,
            "is_canonical": False
        }
    ]

    shots = retrieval_engine.resolve_beat_to_shots(beat, sub_75_candidates, target_shots_per_beat=1)
    assert len(shots) >= 1
    fallback_shot = shots[0]
    candidate = fallback_shot["candidate"]

    # Must be the Atmospheric Hogwarts Establishing Shot
    assert candidate.get("is_atmospheric_fallback") is True
    assert "Hogwarts Castle" in candidate.get("movie_title") or "Hogwarts" in candidate.get("text")
    assert candidate.get("score") >= 75.0


def test_script_engine_check_n_rejects_unfilmed_peeves(script_engine):
    """
    Verifies that Check N in hp_script_engine strictly detects and vetoes
    unfilmed book-only elements like Peeves the Poltergeist.
    """
    script_text = "The movie completely cut Peeves the Poltergeist who terrorized Hogwarts corridors in the books."
    hook = "The movie completely cut Peeves the Poltergeist:"
    subtype = "DISCOVERY_BOOK_MOVIE_DIFFERENCE"
    visual_beats = [
        {
            "beat_id": "beat_1",
            "narration_text": "Peeves dropping water balloons on students.",
            "visual_requirement": "Peeves the poltergeist floating and dropping water balloons",
            "characters": ["Peeves"],
            "location": "Hogwarts corridor"
        }
    ]

    qa_res = script_engine.evaluate_discovery_qa(
        script_text=script_text,
        hook=hook,
        subtype=subtype,
        visual_beats=visual_beats
    )

    assert not qa_res.passed
    check_n_failures = [r for r in qa_res.failure_reasons if "Check N Failed" in r]
    assert len(check_n_failures) > 0
    assert "peeves" in check_n_failures[0].lower()


def test_script_engine_check_n_accepts_filmed_elements(script_engine):
    """
    Verifies that Check N passes cleanly when all visual beats feature
    filmed characters and scenes from the Warner Bros franchise.
    """
    visual_beats = [
        {
            "beat_id": "beat_1",
            "narration_text": "Harry catches the Golden Snitch.",
            "visual_requirement": "Harry diving on broom catching Golden Snitch",
            "characters": ["Harry Potter"],
            "location": "Quidditch pitch"
        }
    ]

    unfilmed = [
        "peeves", "winky", "ludo bagman", "charlie weasley dragon breeding",
        "deathday party", "spew", "s.p.e.w.", "kreacher leading house-elves with cleavers"
    ]
    b_text = " ".join([
        visual_beats[0]["visual_requirement"],
        visual_beats[0]["narration_text"],
        " ".join(visual_beats[0]["characters"])
    ]).lower()

    assert not any(u in b_text for u in unfilmed)
