"""
STORY FORGE — BEAST Real Movie Retrieval Integration Tests
================================================================================
Verifies BEAST integration with real Harry Potter movie archive footage:
1. Archive catalog loading & caching
2. Strict era contradiction guard on real movie shots (M1 vs M8)
3. Direct evidence matching for key narrative beats
4. Fail-closed behavior on unfilmed events
"""

import pytest
from pathlib import Path
from config.settings import DATA_DIR
from core.beast_visual_types import (
    BeastVisualRequirement,
    BeastCandidateShot,
    NarrativeEra,
)
from core.composition_models import ShotScale
from core.storyboard_types import VisualRole
from engines.beast.beast_movie_archive import BeastMovieArchive
from engines.beast_visual_matching_engine import BeastVisualMatchingEngine


@pytest.fixture(scope="module")
def real_candidate_pool():
    archive = BeastMovieArchive()
    shots = archive.load_or_index_shots(force_reindex=False)
    assert len(shots) >= 50, f"Expected at least 50 real movie shots, got {len(shots)}"
    return shots


@pytest.fixture
def beast_engine():
    return BeastVisualMatchingEngine(min_confidence_threshold=65.0)


def test_real_movie_archive_metadata(real_candidate_pool):
    """Verifies that real movie shots have frame-accurate timestamps and valid eras."""
    m1_shots = [s for s in real_candidate_pool if s.movie_number == 1]
    m8_shots = [s for s in real_candidate_pool if s.movie_number == 8]

    assert len(m1_shots) > 0, "No Movie 1 shots loaded"
    assert len(m8_shots) > 0, "No Movie 8 shots loaded"

    for s in real_candidate_pool:
        assert s.start_seconds < s.end_seconds
        assert s.duration > 0.0
        assert s.narrative_era in (NarrativeEra.YEAR_1, NarrativeEra.YEAR_7)
        assert Path(s.source_video).exists(), f"Source video {s.source_video} missing"


def test_era_contradiction_guard_on_real_shots(beast_engine, real_candidate_pool):
    """Verifies that Year 7 battle shots are strictly disqualified for Year 1 beats."""
    req_year_1 = BeastVisualRequirement(
        beat_id="test_year_1",
        narration_text="Neville begged the Sorting Hat for Hufflepuff",
        narrative_phase="EVIDENCE",
        primary_subject="Neville Longbottom",
        secondary_subject="Sorting Hat",
        expected_era=NarrativeEra.YEAR_1,
        negative_constraints=["reject battle of hogwarts", "reject year 7", "reject sword combat"],
        confidence_threshold=65.0,
    )

    res = beast_engine.find_best_visual_match(req_year_1, real_candidate_pool, enable_vlm_gate=False)
    assert res is not None, "Failed to match Year 1 shot"
    best_shot, breakdown = res
    assert best_shot.movie_number == 1, f"Expected Movie 1 for Year 1 beat, got Movie {best_shot.movie_number}"
    assert best_shot.narrative_era == NarrativeEra.YEAR_1


def test_year_7_sword_and_nagini_matching(beast_engine, real_candidate_pool):
    """Verifies that Year 7 Nagini slaying matches Movie 8 sword combat footage."""
    req_nagini = BeastVisualRequirement(
        beat_id="test_nagini",
        narration_text="Neville pulled Godric's silver sword from that Hat to strike Nagini down",
        narrative_phase="PAYOFF",
        primary_subject="Neville Longbottom",
        secondary_subject="Nagini",
        required_objects=["Sword of Gryffindor"],
        required_action="striking Nagini",
        expected_era=NarrativeEra.YEAR_7,
        confidence_threshold=65.0,
    )

    res = beast_engine.find_best_visual_match(req_nagini, real_candidate_pool, enable_vlm_gate=False)
    assert res is not None, "Failed to match Nagini slaying shot"
    best_shot, breakdown = res
    assert best_shot.movie_number == 8, f"Expected Movie 8, got Movie {best_shot.movie_number}"
    assert "Neville Longbottom" in best_shot.characters_present
    assert "Sword of Gryffindor" in best_shot.objects_present
    assert breakdown.final_score >= 75.0


def test_fail_closed_on_unfilmed_event(beast_engine, real_candidate_pool):
    """Verifies fail-closed NO_VALID_VISUAL when impossible narrative criteria are required."""
    impossible_req = BeastVisualRequirement(
        beat_id="test_impossible",
        narration_text="Dobby danced the tango on top of the astronomy tower in a pink tutu",
        narrative_phase="EVIDENCE",
        primary_subject="Dobby",
        required_action="dancing tango in pink tutu",
        required_objects=["Pink Tutu"],
        required_location="Astronomy Tower",
        confidence_threshold=65.0,
    )

    res = beast_engine.find_best_visual_match(impossible_req, real_candidate_pool, enable_vlm_gate=False)
    assert res is None, "Expected NO_VALID_VISUAL for impossible requirement"
