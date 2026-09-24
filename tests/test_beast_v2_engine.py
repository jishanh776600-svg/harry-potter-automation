"""
STORY FORGE — BEAST V2 Proposition-Aware Visual Evidence Engine Test Suite
================================================================================
Comprehensive test suite covering all 26 required capabilities:
   1. exact subject match
   2. wrong subject rejection
   3. exact action match
   4. wrong action rejection
   5. object verification
   6. wrong object rejection
   7. context verification
   8. temporal action grounding
   9. before/during/after verification
  10. contradiction rejection
  11. wrong-era rejection
  12. wrong-character rejection
  13. emotional contradiction rejection
  14. orientation bridge acceptance
  15. orientation bridge >2s rejection
  16. contextual-vs-direct classification
  17. ironic contrast classification
  18. object/prop evidence
  19. book-vs-movie evidence separation
  20. Asset Acquisition fallback
  21. NO_VALID_VISUAL fail-closed behavior
  22. multiple candidate ranking
  23. anti-repetition
  24. proposition-to-beast contract
  25. proposition-to-acquisition contract
  26. fact-level coverage

Synthetic Canonical Benchmark Cases:
  CASE 1: Correct character + correct action + correct object + correct context -> ACCEPT_DIRECT
  CASE 2: Correct character + wrong action -> REJECT
  CASE 3: Correct character + correct location + wrong year/era -> REJECT
  CASE 4: Correct object + no character -> ACCEPT_OBJECT (when object-centric)
  CASE 5: Generic character footage -> ACCEPT_ORIENTATION only
  CASE 6: Orientation footage lasting >2s -> REJECT / invalid coverage
  CASE 7: Correct scene but action at different timestamp -> reject wrong interval, identify correct interval
  CASE 8: Book-only claim with movie footage -> reject as book evidence
  CASE 9: BTS claim with ordinary movie footage -> reject as BTS evidence
  CASE 10: No valid candidate -> NO_VALID_VISUAL fail-closed
"""

import pytest
from unittest.mock import MagicMock

from core.beast_v2_types import (
    EvidenceType,
    SourceEvidenceType,
    ActionCategory,
    BeastV2Decision,
    TemporalMicroInterval,
    BeastV2MatchResult,
    FactPropositionCoverage,
)
from core.beast_visual_types import (
    BeastCandidateShot,
    MultiFrameSample,
    NarrativeEra,
)
from core.multi_fact_types import VisualProposition
from engines.beast.beast_v2_proposition_engine import BeastV2PropositionEngine
from engines.beast.beast_v2_action_verifier import BeastV2ActionVerifier
from engines.beast.beast_v2_temporal_grounding import BeastV2TemporalGrounder
from engines.beast_visual_matching_engine import BeastVisualMatchingEngine


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def engine():
    return BeastV2PropositionEngine(min_confidence_threshold=65.0)


@pytest.fixture
def shot_neville_sorting_direct():
    return BeastCandidateShot(
        shot_id="shot_m1_neville_sorting_direct",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=2568.0,
        end_seconds=2573.0,
        duration=5.0,
        narrative_era=NarrativeEra.YEAR_1,
        scene_description="Neville Longbottom sits on the wooden stool in the Great Hall, begging and pleading with the Sorting Hat.",
        characters_present=["Neville Longbottom", "Sorting Hat"],
        objects_present=["Sorting Hat", "Stool"],
        actions_depicted=["pleading", "begging", "arguing"],
        environment="Great Hall",
    )


@pytest.fixture
def shot_neville_sorting_wrong_action():
    return BeastCandidateShot(
        shot_id="shot_m1_neville_sitting_passive",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=2560.0,
        end_seconds=2564.0,
        duration=4.0,
        narrative_era=NarrativeEra.YEAR_1,
        scene_description="Neville Longbottom sitting quietly waiting in the Great Hall.",
        characters_present=["Neville Longbottom"],
        objects_present=["Stool"],
        actions_depicted=["sitting", "waiting"],
        environment="Great Hall",
    )


@pytest.fixture
def shot_neville_battle_sword():
    return BeastCandidateShot(
        shot_id="shot_m8_neville_battle",
        source_video="data/movies/m8.mkv",
        movie_number=8,
        start_seconds=6168.0,
        end_seconds=6172.5,
        duration=4.5,
        narrative_era=NarrativeEra.YEAR_7,
        scene_description="Adult Neville Longbottom in battle ruins drawing the Sword of Gryffindor to fight Voldemort's army.",
        characters_present=["Neville Longbottom"],
        objects_present=["Sword of Gryffindor"],
        actions_depicted=["fighting", "drawing sword", "battle"],
        environment="Hogwarts Courtyard",
    )


@pytest.fixture
def shot_sword_prop_alone():
    return BeastCandidateShot(
        shot_id="shot_sword_prop",
        source_video="data/movies/m2.mkv",
        movie_number=2,
        start_seconds=7120.0,
        end_seconds=7123.0,
        duration=3.0,
        narrative_era=NarrativeEra.YEAR_2,
        scene_description="Extreme close-up of the Sword of Gryffindor gleaming with silver rubies in Dumbledore's office.",
        characters_present=[],
        objects_present=["Sword of Gryffindor", "Ruby"],
        actions_depicted=["gleaming"],
        environment="Headmaster Office",
    )


@pytest.fixture
def shot_diary_stabbing():
    return BeastCandidateShot(
        shot_id="shot_diary_destroy",
        source_video="data/movies/m2.mkv",
        movie_number=2,
        start_seconds=5000.0,
        end_seconds=5010.0,
        duration=10.0,
        narrative_era=NarrativeEra.YEAR_2,
        scene_description="Harry Potter stabs Tom Riddle's diary with a basilisk venom fang, destroying the horcrux as black ink pours out.",
        characters_present=["Harry Potter"],
        objects_present=["Tom Riddle Diary", "Basilisk Fang"],
        actions_depicted=["stabbing", "destroying", "crushing"],
        environment="Chamber of Secrets",
        metadata={
            "action_start": 5004.2,
            "action_peak": 5005.5,
            "action_end": 5006.8,
        }
    )


@pytest.fixture
def shot_diary_merely_holding():
    return BeastCandidateShot(
        shot_id="shot_diary_hold",
        source_video="data/movies/m2.mkv",
        movie_number=2,
        start_seconds=4200.0,
        end_seconds=4204.0,
        duration=4.0,
        narrative_era=NarrativeEra.YEAR_2,
        scene_description="Harry Potter holding Tom Riddle's black diary in hands, examining the blank pages.",
        characters_present=["Harry Potter"],
        objects_present=["Tom Riddle Diary"],
        actions_depicted=["holding", "looking"],
        environment="Girls Bathroom",
    )


# ==============================================================================
# 26 FOCUSED CAPABILITY TESTS
# ==============================================================================

def test_01_exact_subject_match(engine, shot_neville_sorting_direct):
    prop = VisualProposition(
        proposition_id="p1",
        subject="Neville Longbottom",
        action="pleading and begging",
        object="Sorting Hat",
        context="Great Hall",
        narrative_era="YEAR_1",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_neville_sorting_direct)
    assert result.decision == BeastV2Decision.ACCEPT_DIRECT
    assert result.alignment_scores.subject_alignment == 100.0


def test_02_wrong_subject_rejection(engine):
    shot_ron = BeastCandidateShot(
        shot_id="shot_ron_feast",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=100.0,
        end_seconds=104.0,
        duration=4.0,
        narrative_era=NarrativeEra.YEAR_1,
        scene_description="Ron Weasley eating chicken at the Gryffindor table.",
        characters_present=["Ron Weasley"],
        objects_present=["Chicken"],
        actions_depicted=["eating"],
        environment="Great Hall",
    )
    prop = VisualProposition(
        proposition_id="p2",
        subject="Harry Potter",
        action="casting spell",
        object="Wand",
        context="Classroom",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_ron)
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Wrong Character" in c for c in result.contradictions)


def test_03_exact_action_match(engine, shot_diary_stabbing):
    prop = VisualProposition(
        proposition_id="p3",
        subject="Harry Potter",
        action="destroying horcrux",
        object="Tom Riddle Diary",
        context="Chamber of Secrets",
        narrative_era="YEAR_2",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_diary_stabbing)
    assert result.decision == BeastV2Decision.ACCEPT_DIRECT
    assert result.alignment_scores.action_alignment >= 80.0


def test_04_wrong_action_rejection(engine, shot_neville_sorting_wrong_action):
    prop = VisualProposition(
        proposition_id="p4",
        subject="Neville Longbottom",
        action="pleading and begging",
        object="Sorting Hat",
        context="Great Hall",
        narrative_era="YEAR_1",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_neville_sorting_wrong_action)
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Action" in c for c in result.contradictions)


def test_05_object_verification(engine, shot_sword_prop_alone):
    prop = VisualProposition(
        proposition_id="p5",
        subject="None",
        action="gleaming",
        object="Sword of Gryffindor",
        context="Headmaster Office",
        visual_role="OBJECT_PROP",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_sword_prop_alone)
    assert result.decision == BeastV2Decision.ACCEPT_OBJECT
    assert result.alignment_scores.object_alignment == 100.0


def test_06_wrong_object_rejection(engine, shot_sword_prop_alone):
    prop = VisualProposition(
        proposition_id="p6",
        subject="None",
        action="displaying memories",
        object="Pensieve",
        context="Headmaster Office",
        visual_role="OBJECT_PROP",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_sword_prop_alone)
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Missing Object" in c for c in result.contradictions)


def test_07_context_verification(engine, shot_neville_sorting_direct):
    prop = VisualProposition(
        proposition_id="p7",
        subject="Neville Longbottom",
        action="pleading",
        object="Sorting Hat",
        context="Great Hall",
        narrative_era="YEAR_1",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_neville_sorting_direct)
    assert result.alignment_scores.context_alignment == 100.0


def test_08_temporal_action_grounding(shot_diary_stabbing):
    interval, is_valid, reason = BeastV2TemporalGrounder.ground_action_interval(
        shot=shot_diary_stabbing,
        action_category=ActionCategory.DESTROY,
        target_duration=1.8,
    )
    assert is_valid is True
    # Action peak is 5005.5 -> window should encompass 5005.5
    assert interval.source_start <= 5005.5 <= interval.source_end
    assert 1.2 <= interval.duration <= 1.8


def test_09_before_during_after_verification(shot_diary_stabbing):
    analyses, during_confirmed = BeastV2ActionVerifier.inspect_temporal_phases(
        shot=shot_diary_stabbing,
        required_action="destroying",
    )
    assert len(analyses) == 3
    assert during_confirmed is True
    phases = [a.phase.value for a in analyses]
    assert phases == ["BEFORE", "DURING", "AFTER"]


def test_10_contradiction_rejection(engine, shot_diary_merely_holding):
    # Action state contradiction: DESTROY vs HOLD
    prop = VisualProposition(
        proposition_id="p10",
        subject="Harry Potter",
        action="destroying the diary",
        object="Tom Riddle Diary",
        context="Chamber",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_diary_merely_holding)
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Action State Contradiction" in c for c in result.contradictions)


def test_11_wrong_era_rejection(engine, shot_neville_battle_sword):
    # Neville in Year 7 cannot prove Year 1 Sorting
    prop = VisualProposition(
        proposition_id="p11",
        subject="Neville Longbottom",
        action="arguing with hat",
        object="Sorting Hat",
        context="Great Hall",
        narrative_era="YEAR_1",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_neville_battle_sword)
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Narrative Era Contradiction" in c for c in result.contradictions)


def test_12_wrong_character_rejection(engine, shot_neville_sorting_direct):
    prop = VisualProposition(
        proposition_id="p12",
        subject="Hermione Granger",
        action="answering questions",
        object="None",
        context="Classroom",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_neville_sorting_direct)
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Wrong Character" in c for c in result.contradictions)


def test_13_emotional_contradiction_rejection(engine):
    shot_laughing = BeastCandidateShot(
        shot_id="shot_laugh",
        source_video="data/movies/m3.mkv",
        movie_number=3,
        start_seconds=120.0,
        end_seconds=123.0,
        duration=3.0,
        scene_description="Harry laughing and smiling cheerfully.",
        characters_present=["Harry Potter"],
        actions_depicted=["laughing", "smiling"],
    )
    prop = VisualProposition(
        proposition_id="p13",
        subject="Harry Potter",
        action="crying and weeping",
        object="None",
        context="Dormitory",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_laughing)
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Emotional contradiction" in c for c in result.contradictions)


def test_14_orientation_bridge_acceptance(engine):
    shot_bridge = BeastCandidateShot(
        shot_id="shot_bridge_ok",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=50.0,
        end_seconds=51.8,
        duration=1.8,
        scene_description="Hogwarts Castle exterior at twilight establishing mood.",
        characters_present=[],
        objects_present=[],
        actions_depicted=["establishing"],
        environment="Hogwarts Exterior",
    )
    prop = VisualProposition(
        proposition_id="p14",
        subject="None",
        action="establishing",
        object="None",
        context="Hogwarts Exterior",
        visual_role="ORIENTATION_BRIDGE",
        estimated_duration_sec=1.8,
    )
    result = engine.verify_candidate_against_proposition(prop, shot_bridge, target_duration=1.8)
    assert result.decision == BeastV2Decision.ACCEPT_ORIENTATION
    assert result.evidence_type == EvidenceType.ORIENTATION_BRIDGE


def test_15_orientation_bridge_over_2s_rejection(engine):
    shot_long_bridge = BeastCandidateShot(
        shot_id="shot_bridge_toolong",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=50.0,
        end_seconds=54.5,
        duration=4.5,
        scene_description="Long lingering shot of castle exterior.",
        environment="Hogwarts",
    )
    prop = VisualProposition(
        proposition_id="p15",
        subject="None",
        action="establishing",
        object="None",
        context="Hogwarts",
        visual_role="ORIENTATION_BRIDGE",
        estimated_duration_sec=3.5,
    )
    result = engine.verify_candidate_against_proposition(prop, shot_long_bridge, target_duration=3.5)
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert "exceeds" in result.reason and "2.0s" in result.reason


def test_16_contextual_vs_direct_classification(engine):
    shot_context = BeastCandidateShot(
        shot_id="shot_potions_env",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=800.0,
        end_seconds=803.0,
        duration=3.0,
        scene_description="Dark gloomy potions dungeon with bubbling cauldrons.",
        characters_present=[],
        environment="Dungeons",
        actions_depicted=["bubbling"],
    )
    prop = VisualProposition(
        proposition_id="p16",
        subject="None",
        action="ambient",
        object="Cauldrons",
        context="Dungeons",
        visual_role="CONTEXTUAL_EVIDENCE",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_context)
    assert result.decision == BeastV2Decision.ACCEPT_CONTEXT
    assert result.evidence_type == EvidenceType.CONTEXTUAL_EVIDENCE


def test_17_ironic_contrast_classification(engine):
    shot_lighthearted = BeastCandidateShot(
        shot_id="shot_light",
        source_video="data/movies/m6.mkv",
        movie_number=6,
        start_seconds=300.0,
        end_seconds=303.0,
        duration=3.0,
        scene_description="Harry and Ron playfully joking in common room.",
        characters_present=["Harry Potter", "Ron Weasley"],
        actions_depicted=["laughing", "joking"],
    )
    prop = VisualProposition(
        proposition_id="p17",
        subject="Harry Potter",
        action="joking",
        object="None",
        context="Common Room",
        visual_role="IRONIC_CONTRAST",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_lighthearted)
    assert result.decision == BeastV2Decision.ACCEPT_CONTRAST
    assert result.evidence_type == EvidenceType.IRONIC_CONTRAST


def test_18_object_prop_evidence(engine, shot_sword_prop_alone):
    prop = VisualProposition(
        proposition_id="p18",
        subject="None",
        action="gleaming",
        object="Sword of Gryffindor",
        context="Headmaster Office",
        visual_role="OBJECT_PROP",
    )
    result = engine.verify_candidate_against_proposition(prop, shot_sword_prop_alone)
    assert result.decision == BeastV2Decision.ACCEPT_OBJECT


def test_19_book_vs_movie_evidence_separation(engine, shot_neville_sorting_direct):
    prop = VisualProposition(
        proposition_id="p19",
        subject="Neville Longbottom",
        action="arguing with hat",
        object="Sorting Hat",
        context="Great Hall",
    )
    # Claim is Book-only; movie footage must NOT be accepted as book evidence
    result = engine.verify_candidate_against_proposition(
        prop,
        shot_neville_sorting_direct,
        is_book_only_claim=True,
    )
    assert result.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Movie footage cannot prove book-only events" in f for f in result.alignment_scores.gating_failures)


def test_20_asset_acquisition_fallback(shot_neville_sorting_wrong_action):
    # Mock asset acquisition engine
    mock_acq = MagicMock()
    mock_rec = MagicMock()
    mock_rec.asset_id = "test_acq_12345"
    mock_rec.filename = "neville_book_illustration.jpg"
    mock_rec.local_cached_path = "data/cache/acq_img.jpg"
    mock_rec.cloud_path = "drive://acq_img.jpg"
    mock_acq.acquire_asset.return_value = MagicMock(success=True, asset_records=[mock_rec])

    engine = BeastV2PropositionEngine(min_confidence_threshold=65.0, asset_acquisition_engine=mock_acq)
    prop = VisualProposition(
        proposition_id="p20",
        subject="Neville Longbottom",
        action="pleading",
        object="Sorting Hat",
        context="Great Hall",
    )
    # Only wrong action candidate in archive -> triggers acquisition fallback
    res = engine.find_best_proposition_match(
        proposition=prop,
        candidates=[shot_neville_sorting_wrong_action],
        allow_acquisition_fallback=True,
    )
    assert res.decision != BeastV2Decision.NO_VALID_VISUAL
    assert res.source == "ASSET_ACQUISITION"


def test_21_no_valid_visual_fail_closed(engine, shot_neville_battle_sword):
    prop = VisualProposition(
        proposition_id="p21",
        subject="Neville Longbottom",
        action="pleading and begging on stool",
        object="Sorting Hat",
        context="Great Hall",
        narrative_era="YEAR_1",
    )
    # Only Year 7 battle shot provided
    res = engine.find_best_proposition_match(prop, [shot_neville_battle_sword])
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL
    assert res.candidate_id == "none"


def test_22_multiple_candidate_ranking(engine, shot_neville_sorting_direct, shot_neville_sorting_wrong_action):
    prop = VisualProposition(
        proposition_id="p22",
        subject="Neville Longbottom",
        action="pleading and begging",
        object="Sorting Hat",
        context="Great Hall",
        narrative_era="YEAR_1",
    )
    # Give both shots in random order
    best = engine.find_best_proposition_match(prop, [shot_neville_sorting_wrong_action, shot_neville_sorting_direct])
    assert best.decision == BeastV2Decision.ACCEPT_DIRECT
    assert best.candidate_id == shot_neville_sorting_direct.shot_id


def test_23_anti_repetition(engine, shot_neville_sorting_direct):
    prop = VisualProposition(
        proposition_id="p23",
        subject="Neville Longbottom",
        action="pleading and begging",
        object="Sorting Hat",
        context="Great Hall",
        narrative_era="YEAR_1",
    )
    # First use
    res1 = engine.find_best_proposition_match(prop, [shot_neville_sorting_direct])
    assert res1.decision == BeastV2Decision.ACCEPT_DIRECT

    # Immediate second use with same pool should register repetition penalty
    res2 = engine.find_best_proposition_match(prop, [shot_neville_sorting_direct])
    assert "Repetition Penalty" in res2.reason


def test_24_proposition_to_beast_contract():
    prop = VisualProposition(
        proposition_id="p24",
        subject="Harry Potter",
        action="stabbing diary",
        object="Diary",
        context="Chamber",
        visual_role="DIRECT_EVIDENCE",
    )
    req = prop.to_beast_requirement("beat_01")
    assert req["beat_id"] == "beat_01"
    assert req["primary_subject"] == "Harry Potter"
    assert req["required_action"] == "stabbing diary"
    assert "Diary" in req["required_objects"]


def test_25_proposition_to_acquisition_contract():
    from engines.acquisition.query_generator import AcquisitionQueryGenerator
    from core.acquisition_types import MediaCategory
    prop = VisualProposition(
        proposition_id="p25",
        subject="Severus Snape",
        action="brewing potion",
        object="Cauldron",
        context="Dungeons",
    )
    queries = AcquisitionQueryGenerator.generate_queries(prop, MediaCategory.IMAGE)
    assert len(queries) >= 1
    assert any("Severus Snape" in q for q in queries)


def test_26_fact_level_coverage(shot_neville_sorting_direct):
    props = [
        VisualProposition("p1", "Neville Longbottom", "pleading", "Sorting Hat", "Great Hall"),
        VisualProposition("p2", "Sorting Hat", "talking", "None", "Great Hall"),
    ]
    matches = [
        BeastV2MatchResult(
            candidate_id="c1",
            asset_id="a1",
            source="MOVIE_ARCHIVE",
            source_start=0.0,
            source_end=2.0,
            decision=BeastV2Decision.ACCEPT_DIRECT,
        )
    ]
    coverages = BeastV2PropositionEngine.evaluate_fact_coverage(
        short_id="short_01",
        fact_id="fact_01",
        propositions=props,
        match_results=matches,
    )
    assert len(coverages) == 2
    assert coverages[0].covered is True
    assert coverages[0].decision == BeastV2Decision.ACCEPT_DIRECT


# ==============================================================================
# 10 REALISTIC SYNTHETIC CANONICAL BENCHMARK CASES
# ==============================================================================

def test_synthetic_case_1_correct_all_direct_accept(engine, shot_neville_sorting_direct):
    """CASE 1: Correct character + correct action + correct object + correct context -> ACCEPT_DIRECT."""
    prop = VisualProposition(
        proposition_id="c1",
        subject="Neville Longbottom",
        action="pleading and begging",
        object="Sorting Hat",
        context="Great Hall",
        narrative_era="YEAR_1",
    )
    res = engine.verify_candidate_against_proposition(prop, shot_neville_sorting_direct)
    assert res.decision == BeastV2Decision.ACCEPT_DIRECT
    assert res.alignment_scores.gating_passed is True


def test_synthetic_case_2_correct_character_wrong_action_reject(engine, shot_neville_sorting_wrong_action):
    """CASE 2: Correct character + wrong action -> REJECT."""
    prop = VisualProposition(
        proposition_id="c2",
        subject="Neville Longbottom",
        action="pleading with hat",
        object="Sorting Hat",
        context="Great Hall",
    )
    res = engine.verify_candidate_against_proposition(prop, shot_neville_sorting_wrong_action)
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL


def test_synthetic_case_3_correct_character_location_wrong_era_reject(engine, shot_neville_battle_sword):
    """CASE 3: Correct character + correct location + wrong year/era -> REJECT."""
    prop = VisualProposition(
        proposition_id="c3",
        subject="Neville Longbottom",
        action="fighting",
        object="Sword of Gryffindor",
        context="Hogwarts Courtyard",
        narrative_era="YEAR_1",  # Claim specifies Year 1, shot is Year 7!
    )
    res = engine.verify_candidate_against_proposition(prop, shot_neville_battle_sword)
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Narrative Era Contradiction" in c for c in res.contradictions)


def test_synthetic_case_4_correct_object_no_character_accept_object(engine, shot_sword_prop_alone):
    """CASE 4: Correct object + no character -> ACCEPT_OBJECT when proposition is object-centric."""
    prop = VisualProposition(
        proposition_id="c4",
        subject="None",
        action="gleaming",
        object="Sword of Gryffindor",
        context="Office",
        visual_role="OBJECT_PROP",
    )
    res = engine.verify_candidate_against_proposition(prop, shot_sword_prop_alone)
    assert res.decision == BeastV2Decision.ACCEPT_OBJECT


def test_synthetic_case_5_generic_character_accept_orientation_only(engine):
    """CASE 5: Generic character footage -> ACCEPT_ORIENTATION only."""
    shot_walking = BeastCandidateShot(
        shot_id="shot_neville_walk",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=10.0,
        end_seconds=11.5,
        duration=1.5,
        scene_description="Neville walking through entrance doors.",
        characters_present=["Neville Longbottom"],
        actions_depicted=["walking"],
        environment="Entrance Hall",
    )
    prop = VisualProposition(
        proposition_id="c5",
        subject="Neville Longbottom",
        action="walking",
        object="None",
        context="Entrance Hall",
        visual_role="ORIENTATION_BRIDGE",
        estimated_duration_sec=1.5,
    )
    res = engine.verify_candidate_against_proposition(prop, shot_walking, target_duration=1.5)
    assert res.decision == BeastV2Decision.ACCEPT_ORIENTATION


def test_synthetic_case_6_orientation_over_2s_reject(engine):
    """CASE 6: Orientation footage lasting >2 seconds without evidence -> REJECT / invalid coverage."""
    shot_long_bridge = BeastCandidateShot(
        shot_id="shot_long_bridge",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=10.0,
        end_seconds=14.0,
        duration=4.0,
        scene_description="Neville standing in corridor for 4 seconds.",
        characters_present=["Neville Longbottom"],
        actions_depicted=["standing"],
        environment="Corridor",
    )
    prop = VisualProposition(
        proposition_id="c6",
        subject="Neville Longbottom",
        action="standing",
        object="None",
        context="Corridor",
        visual_role="ORIENTATION_BRIDGE",
        estimated_duration_sec=3.0,
    )
    res = engine.verify_candidate_against_proposition(prop, shot_long_bridge, target_duration=3.0)
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL
    assert "exceeds" in res.reason


def test_synthetic_case_7_correct_scene_wrong_interval_rejection_and_correction(shot_diary_stabbing):
    """CASE 7: Correct scene but action occurs at a different timestamp -> reject wrong interval, identify correct."""
    # Stabbing happens at 5004.2-5006.8. User tests interval [5000.0, 5002.0]
    corrected_interval, is_valid, reason = BeastV2TemporalGrounder.ground_action_interval(
        shot=shot_diary_stabbing,
        action_category=ActionCategory.DESTROY,
        target_duration=1.8,
        candidate_interval=(5000.0, 5002.0),
    )
    # The candidate interval was invalid
    assert is_valid is False
    assert "Wrong Interval" in reason
    # The grounder identified the corrected interval around action_peak (5005.5)
    assert corrected_interval.source_start <= 5005.5 <= corrected_interval.source_end


def test_synthetic_case_8_book_only_claim_movie_footage_reject(engine, shot_neville_sorting_direct):
    """CASE 8: Book-only claim with movie footage -> reject as book evidence."""
    prop = VisualProposition(
        proposition_id="c8",
        subject="Neville Longbottom",
        action="pleading with hat",
        object="Sorting Hat",
        context="Great Hall",
    )
    res = engine.verify_candidate_against_proposition(
        prop,
        shot_neville_sorting_direct,
        is_book_only_claim=True,
    )
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("Movie footage cannot prove book-only" in f for f in res.alignment_scores.gating_failures)


def test_synthetic_case_9_bts_claim_movie_footage_reject(engine, shot_diary_stabbing):
    """CASE 9: BTS claim with ordinary movie footage -> reject as BTS evidence."""
    prop = VisualProposition(
        proposition_id="c9",
        subject="Daniel Radcliffe",
        action="improvised stunt with fake ink",
        object="Prop Diary",
        context="Film Set",
    )
    res = engine.verify_candidate_against_proposition(
        prop,
        shot_diary_stabbing,
        is_bts_claim=True,
    )
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL
    assert any("BTS proposition requires behind-the-scenes" in f for f in res.alignment_scores.gating_failures)


def test_synthetic_case_10_no_valid_candidate_fail_closed(engine):
    """CASE 10: No valid candidate -> NO_VALID_VISUAL."""
    prop = VisualProposition(
        proposition_id="c10",
        subject="Peeves",
        action="dropping water balloons on students",
        object="Water Balloons",
        context="Entrance Hall",
    )
    # Empty candidate pool
    res = engine.find_best_proposition_match(prop, candidates=[])
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL
    assert res.candidate_id == "none"
    assert "Fail-Closed" in res.reason
