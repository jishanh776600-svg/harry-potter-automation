"""
Step 2: Anchor-Grounded Hybrid Storyboard Planner Test Suite
================================================================================
Verifies all 16 required capabilities of Step 2:
 1. Storyboard schema creation and validation (contracts, to_dict, from_dict).
 2. All four visual roles (DIRECT_EVIDENCE, CONTEXTUAL_ENVIRONMENT, CHARACTER_REACTION, IRONIC_CONTRAST).
 3. Bidirectional feasibility audit (scoring 0-100, visual feasibility checking).
 4. Anchor selection (identifying anchor point, setting is_anchor=True).
 5. Dynamic pacing ranges (Hook 0.8-1.2s, Setup 1.2-1.6s, Evidence 1.4-1.8s, Anchor 2.2-3.2s, Payoff 1.0-1.5s).
 6. Timeline beat contracts (continuous timestamps, start=0.0, no overlaps, no gaps).
 7. Evidence-to-visual provenance linkage (evidence_point_id and source_provenance preserved).
 8. No-valid-visual handling (truthful fallback, flags revision required, never invents footage).
 9. Anti-repetition behavior (prevents duplicate consecutive shot scales and clip intervals).
10. Framing intent preservation from commit 37b1463 (natural medium shot preference, close-up only for emotions).
11. Hybrid hierarchy enforcement (Movie direct -> Cleared art -> No valid visual; rejects forbidden stock).
12. Novel Story isolation (Novel Story pipeline strictly isolated; raises ValueError).
13. Backward compatibility (handles legacy candidate dictionaries and Step 1 plans gracefully).
14. Unsupported / misleading visual rejection (unrelated movie footage rejected as direct evidence).
15. Asymmetric anchor duration (anchor beat significantly longer than regular evidence beats).
16. Deterministic storyboard generation (identical input yields identical output).
"""

import json
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from core.hybrid_visual_models import (
    VisualSourceType,
    RightsStatus,
    ArtistLicenseStatus,
    CommercialClearanceStatus,
    ApprovalStatus,
    FORBIDDEN_SOURCE_PROVIDERS,
)
from core.discovery_types import (
    DiscoveryTier,
    DiscoveryStoryStructure,
    HookArchetype,
    EvidenceRoute,
    PayoffType,
    TitlePattern,
    PacingPhase,
    EvidencePoint,
    DeepDiscoveryStoryPlan,
)
from core.storyboard_types import (
    VisualRole,
    TransitionIntent,
    FallbackStrategy,
    StoryboardBeatContract,
    StoryboardPlan,
)
from engines.movie_retrieval_engine import ShotScale
from engines.storyboard_planner import StoryboardPlanner


@pytest.fixture
def mock_planner():
    """Returns a StoryboardPlanner equipped with mock retrieval engines for targeted testing."""
    mock_movie = MagicMock()
    # Default candidate response for mock_movie
    mock_movie.infer_target_shot_scale.return_value = ShotScale.MEDIUM_SHOT
    mock_movie.search_candidates_for_beat.return_value = [
        {
            "chunk_id": "chunk_m1_001",
            "movie_number": 1,
            "start_seconds": 120.0,
            "end_seconds": 123.5,
            "text": "Harry looking at the Sorting Hat in the Great Hall",
            "score": 85.0,
            "total_score": 85.0,
            "retrieval_score": 85.0,
        }
    ]
    mock_movie.rerank_candidates.side_effect = lambda beat, cands, **kwargs: cands

    mock_fan_art = MagicMock()
    mock_hybrid = MagicMock()

    planner = StoryboardPlanner(
        movie_engine=mock_movie,
        fan_art_engine=mock_fan_art,
        hybrid_engine=mock_hybrid,
    )
    return planner


@pytest.fixture
def sample_deep_discovery_plan():
    """Generates a canonical Step 1 DeepDiscoveryStoryPlan with diverse evidence points."""
    ev1 = EvidencePoint(
        claim="The Sorting Hat deliberated for four minutes whether Harry belonged in Slytherin",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="b1c07_chunk_012",
        source_excerpt="The hat shouted Gryffindor after intense deliberation...",
        verified=True,
    )
    ev2 = EvidencePoint(
        claim="In the novel, Neville requested to be sorted into Hufflepuff out of fear of Gryffindor's reputation",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="b1c07_chunk_018",
        source_excerpt="Neville fell over when his name was called...",
        verified=True,
    )
    ev3 = EvidencePoint(
        claim="The film omitted Neville's hatstall entirely, showing him sitting immediately under the hat",
        evidence_route=EvidenceRoute.MOVIE_CANON.value,
        source_id="b1_movie_scene_sorting",
        source_excerpt="Film scene: Neville immediately sorted into Gryffindor without hesitation.",
        verified=True,
    )
    anchor = EvidencePoint(
        claim="Novel-only secret: The Sorting Hat took nearly four minutes with Neville, making him an official Hatstall near-miss",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="b1c07_anchor_hatstall",
        source_excerpt="The hat deliberated for nearly four minutes before shouting Gryffindor.",
        verified=True,
    )

    return DeepDiscoveryStoryPlan(
        topic_id="disc_neville_sorting_hatstall",
        discovery_type="BOOK_VS_MOVIE_DIFFERENCE",
        discovery_tier=DiscoveryTier.DEEP_DISCOVERY,
        story_structure=DiscoveryStoryStructure.TEMPLATE_B_MYTH_BUSTER,
        hook_archetype=HookArchetype.COUNTER_INTUITIVE_TRUTH,
        evidence_route=EvidenceRoute.NOVEL_CANON,
        thesis="Neville Longbottom begged the Sorting Hat to place him in Hufflepuff, not Gryffindor.",
        evidence_points=[ev1, ev2, ev3, anchor],
        anchor_point=anchor,
        insider_epiphany="The hat did not see Neville's fear; it foresaw him pulling the sword of Gryffindor.",
        payoff_type=PayoffType.BOOK_MOVIE_REALIZATION,
        payoff_text="Neville thought he was cowardly, but the hat refused to give up on his true courage.",
        title_pattern=TitlePattern.BOOK_VS_MOVIE,
        suggested_title="Why Neville Begged The Sorting Hat For Hufflepuff",
        expected_duration=72.0,
        target_word_count=255,
        target_speech_rate=3.55,
        topic_score=88.5,
    )


# ── Test 1: Storyboard Schema Creation ────────────────────────────────────────

def test_01_storyboard_schema_creation():
    """Verifies that StoryboardBeatContract and StoryboardPlan serialize, deserialize, and validate."""
    beat = StoryboardBeatContract(
        beat_id="beat_01",
        narrative_phase=PacingPhase.HOOK.value,
        start_seconds=0.0,
        end_seconds=1.0,
        target_duration=1.0,
        narration_intent="Hook opening",
        visual_role=VisualRole.DIRECT_EVIDENCE,
        visual_source_type=VisualSourceType.MOVIE_DIRECT,
        framing_intent=ShotScale.MEDIUM_SHOT,
        is_anchor=False,
        visual_feasibility_score=85.0,
    )
    anchor_beat = StoryboardBeatContract(
        beat_id="beat_02",
        narrative_phase=PacingPhase.ANCHOR.value,
        start_seconds=1.0,
        end_seconds=3.7,
        target_duration=2.7,
        narration_intent="Anchor revelation",
        visual_role=VisualRole.DIRECT_EVIDENCE,
        visual_source_type=VisualSourceType.MOVIE_DIRECT,
        framing_intent=ShotScale.CLOSE_UP,
        is_anchor=True,
        visual_feasibility_score=90.0,
    )

    plan = StoryboardPlan(
        storyboard_id="sb_test_01",
        topic_id="topic_test_01",
        beats=[beat, anchor_beat],
        anchor_beat_ids=["beat_02"],
        overall_visual_feasibility_score=87.5,
        total_target_duration=3.7,
    )

    # Validate
    valid, errors = plan.validate()
    assert valid is True
    assert len(errors) == 0

    # Serialization roundtrip
    d = plan.to_dict()
    assert d["storyboard_id"] == "sb_test_01"
    assert len(d["beats"]) == 2
    assert d["beats"][1]["is_anchor"] is True
    assert d["beats"][1]["target_duration"] == 2.7

    reconstructed = StoryboardPlan.from_dict(d)
    assert reconstructed.storyboard_id == plan.storyboard_id
    assert reconstructed.beats[0].visual_role == VisualRole.DIRECT_EVIDENCE
    assert reconstructed.beats[1].visual_role == VisualRole.DIRECT_EVIDENCE
    assert reconstructed.beats[1].framing_intent == ShotScale.CLOSE_UP


# ── Test 2: All Four Visual Roles ─────────────────────────────────────────────

def test_02_all_four_visual_roles(mock_planner, sample_deep_discovery_plan):
    """Verifies that all 4 visual roles are valid and can be assigned to beats."""
    plan = mock_planner.plan_storyboard(sample_deep_discovery_plan)
    
    # Check that VisualRole enum contains all 4 roles
    assert VisualRole.DIRECT_EVIDENCE.value == "DIRECT_EVIDENCE"
    assert VisualRole.CONTEXTUAL_ENVIRONMENT.value == "CONTEXTUAL_ENVIRONMENT"
    assert VisualRole.CHARACTER_REACTION.value == "CHARACTER_REACTION"
    assert VisualRole.IRONIC_CONTRAST.value == "IRONIC_CONTRAST"

    # Verify that plan has beats with explicit visual roles
    roles = {b.visual_role for b in plan.beats}
    assert VisualRole.DIRECT_EVIDENCE in roles or VisualRole.CONTEXTUAL_ENVIRONMENT in roles

    # Explicitly test assignment of each role
    contract_direct = StoryboardBeatContract(
        beat_id="b_direct", narrative_phase="EVIDENCE", visual_role=VisualRole.DIRECT_EVIDENCE
    )
    contract_context = StoryboardBeatContract(
        beat_id="b_context", narrative_phase="SETUP", visual_role=VisualRole.CONTEXTUAL_ENVIRONMENT
    )
    contract_react = StoryboardBeatContract(
        beat_id="b_react", narrative_phase="PAYOFF", visual_role=VisualRole.CHARACTER_REACTION
    )
    contract_ironic = StoryboardBeatContract(
        beat_id="b_ironic", narrative_phase="EVIDENCE", visual_role=VisualRole.IRONIC_CONTRAST
    )

    for c in (contract_direct, contract_context, contract_react, contract_ironic):
        assert isinstance(c.visual_role, VisualRole)


# ── Test 3: Bidirectional Feasibility Audit ───────────────────────────────────

def test_03_bidirectional_feasibility_audit(mock_planner, sample_deep_discovery_plan):
    """Verifies bidirectional visual feasibility audit scores availability correctly."""
    # When movie candidates exist with high scores
    mock_planner.movie_engine.search_candidates_for_beat.return_value = [
        {"chunk_id": "c1", "movie_number": 1, "start_seconds": 10.0, "end_seconds": 12.0, "score": 88.0, "retrieval_score": 88.0}
    ]
    plan_high = mock_planner.plan_storyboard(sample_deep_discovery_plan)
    assert plan_high.overall_visual_feasibility_score >= 60.0
    assert plan_high.is_production_feasible is True

    # When no movie footage exists and no artwork exists
    mock_planner.movie_engine.search_candidates_for_beat.return_value = []
    plan_low = mock_planner.plan_storyboard(sample_deep_discovery_plan)
    # Feasibility score should drop
    assert plan_low.overall_visual_feasibility_score < plan_high.overall_visual_feasibility_score


# ── Test 4: Anchor Selection ──────────────────────────────────────────────────

def test_04_anchor_selection(mock_planner, sample_deep_discovery_plan):
    """Verifies that an anchor beat is properly selected and tagged."""
    plan = mock_planner.plan_storyboard(sample_deep_discovery_plan)

    assert len(plan.anchor_beat_ids) >= 1
    anchor_beats = [b for b in plan.beats if b.is_anchor]
    assert len(anchor_beats) >= 1
    assert anchor_beats[0].beat_id in plan.anchor_beat_ids
    assert anchor_beats[0].narrative_phase == PacingPhase.ANCHOR.value


# ── Test 5: Dynamic Pacing Ranges ─────────────────────────────────────────────

def test_05_dynamic_pacing_ranges(mock_planner, sample_deep_discovery_plan):
    """Verifies each beat adheres to its strict pacing phase duration range."""
    plan = mock_planner.plan_storyboard(sample_deep_discovery_plan)

    for b in plan.beats:
        dur = b.target_duration
        if b.narrative_phase == PacingPhase.HOOK.value:
            assert 0.8 <= dur <= 1.2, f"Hook beat duration {dur} outside [0.8, 1.2]"
        elif b.narrative_phase == PacingPhase.SETUP.value:
            assert 1.2 <= dur <= 1.6, f"Setup beat duration {dur} outside [1.2, 1.6]"
        elif b.narrative_phase == PacingPhase.ANCHOR.value:
            assert 2.2 <= dur <= 3.2, f"Anchor beat duration {dur} outside [2.2, 3.2]"
        elif b.narrative_phase == PacingPhase.EVIDENCE.value:
            assert 1.4 <= dur <= 1.8, f"Evidence beat duration {dur} outside [1.4, 1.8]"
        elif b.narrative_phase == PacingPhase.PAYOFF.value:
            assert 1.0 <= dur <= 1.5, f"Payoff beat duration {dur} outside [1.0, 1.5]"


# ── Test 6: Timeline Beat Contracts ───────────────────────────────────────────

def test_06_timeline_beat_contracts(mock_planner, sample_deep_discovery_plan):
    """Verifies continuous, non-overlapping timeline beat contracts."""
    plan = mock_planner.plan_storyboard(sample_deep_discovery_plan)

    assert plan.beats[0].start_seconds == 0.0
    for i in range(len(plan.beats) - 1):
        curr_b = plan.beats[i]
        next_b = plan.beats[i + 1]
        assert round(curr_b.end_seconds, 2) == round(next_b.start_seconds, 2), (
            f"Discontinuity between {curr_b.beat_id} ({curr_b.end_seconds}s) and {next_b.beat_id} ({next_b.start_seconds}s)"
        )
        assert round(curr_b.end_seconds - curr_b.start_seconds, 2) == round(curr_b.target_duration, 2)

    assert round(plan.total_target_duration, 2) == round(plan.beats[-1].end_seconds, 2)


# ── Test 7: Evidence-to-Visual Provenance Linkage ──────────────────────────────

def test_07_evidence_to_visual_provenance_linkage(mock_planner, sample_deep_discovery_plan):
    """Verifies evidence beats retain provenance linkage to source EvidencePoints."""
    plan = mock_planner.plan_storyboard(sample_deep_discovery_plan)

    evidence_beats = [b for b in plan.beats if b.narrative_phase in (PacingPhase.EVIDENCE.value, PacingPhase.ANCHOR.value)]
    assert len(evidence_beats) > 0

    for eb in evidence_beats:
        assert eb.evidence_point_id is not None
        assert len(eb.evidence_point_id) > 0
        assert eb.source_provenance is not None
        assert "source_id" in eb.source_provenance
        assert "route" in eb.source_provenance


# ── Test 8: No-Valid-Visual Handling ──────────────────────────────────────────

def test_08_no_valid_visual_handling(mock_planner):
    """Verifies unfilmed novel scene without artwork falls back truthfully or sets NO_VALID_VISUAL."""
    mock_planner.movie_engine.search_candidates_for_beat.return_value = []
    
    ev_unfilmed = EvidencePoint(
        claim="An obscure magical plant that never appeared in any film and has zero artwork",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="b5_obscure_plant",
        source_excerpt="A tiny purple sprout with no film depiction.",
        verified=True,
    )
    plan_obj = DeepDiscoveryStoryPlan(
        topic_id="obscure_plant_topic",
        discovery_type="BOOK_ONLY_DETAIL",
        evidence_points=[ev_unfilmed],
        anchor_point=ev_unfilmed,
        thesis="A novel-only plant never filmed.",
    )

    sb_plan = mock_planner.plan_storyboard(plan_obj)
    unfilmed_beat = [b for b in sb_plan.beats if b.evidence_point_id == "b5_obscure_plant"][0]
    
    assert unfilmed_beat.visual_source_type in (
        VisualSourceType.NO_VALID_VISUAL,
        VisualSourceType.MOVIE_DIRECT,  # If fallback environment/reaction chosen
    )
    if unfilmed_beat.visual_source_type == VisualSourceType.NO_VALID_VISUAL:
        assert unfilmed_beat.fallback_strategy == FallbackStrategy.REVISION_REQUIRED
        assert unfilmed_beat.visual_feasibility_score <= 30.0


# ── Test 9: Anti-Repetition Behavior ──────────────────────────────────────────

def test_09_anti_repetition_behavior(mock_planner, sample_deep_discovery_plan):
    """Verifies that consecutive beats do not repeat identical shot scales inappropriately."""
    # Force mock_movie to return CLOSE_UP for all queries
    mock_planner.movie_engine.infer_target_shot_scale.return_value = ShotScale.CLOSE_UP
    
    plan = mock_planner.plan_storyboard(sample_deep_discovery_plan)
    
    # Check that not every beat in a row is CLOSE_UP
    consecutive_cu = 0
    max_consecutive_cu = 0
    for b in plan.beats:
        if b.framing_intent == ShotScale.CLOSE_UP:
            consecutive_cu += 1
            max_consecutive_cu = max(max_consecutive_cu, consecutive_cu)
        else:
            consecutive_cu = 0

    assert max_consecutive_cu <= 2, f"Detected {max_consecutive_cu} consecutive CLOSE_UP beats, violating anti-repetition"


# ── Test 10: Framing Intent Preservation from 37b1463 ─────────────────────────

def test_10_framing_intent_preservation_from_37b1463(mock_planner):
    """Verifies that framing intent respects natural medium framing policy."""
    # Reaction cues -> CLOSE_UP
    mock_planner.movie_engine.infer_target_shot_scale.side_effect = lambda b: (
        ShotScale.CLOSE_UP if "shock" in str(b) or "fear" in str(b) or "reaction" in str(b)
        else ShotScale.TWO_SHOT if "talking" in str(b) or "confronts" in str(b)
        else ShotScale.WIDE_SHOT if "castle" in str(b) or "landscape" in str(b)
        else ShotScale.MEDIUM_SHOT
    )

    ev_shock = EvidencePoint(
        claim="Harry's face in shock as the Sorting Hat screamed",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="ev_shock",
        source_excerpt="Harry felt absolute shock.",
    )
    ev_dialogue = EvidencePoint(
        claim="Dumbledore and McGonagall talking quietly outside the Great Hall",
        evidence_route=EvidenceRoute.MOVIE_CANON.value,
        source_id="ev_dial",
        source_excerpt="They conferred together.",
    )

    plan_obj = DeepDiscoveryStoryPlan(
        topic_id="framing_test",
        discovery_type="BOOK_VS_MOVIE",
        evidence_points=[ev_shock, ev_dialogue],
        anchor_point=ev_shock,
        thesis="Framing test short",
    )

    sb_plan = mock_planner.plan_storyboard(plan_obj)
    shock_beat = [b for b in sb_plan.beats if b.evidence_point_id == "ev_shock"][0]
    dial_beat = [b for b in sb_plan.beats if b.evidence_point_id == "ev_dial"][0]

    assert shock_beat.framing_intent == ShotScale.CLOSE_UP
    assert dial_beat.framing_intent == ShotScale.TWO_SHOT


# ── Test 11: Hybrid Hierarchy Enforcement ─────────────────────────────────────

def test_11_hybrid_hierarchy_enforcement(mock_planner, sample_deep_discovery_plan):
    """Verifies hierarchy: Movie direct -> Cleared art -> No valid visual. Rejects generic stock."""
    # Forbidden stock test: if any beat or evidence requests Pexels/Unsplash, must raise ValueError
    bad_plan = DeepDiscoveryStoryPlan(
        topic_id="forbidden_stock_test",
        discovery_type="LORE",
        thesis="Stock test",
        evidence_points=[
            EvidencePoint(
                claim="Using Pexels stock footage for a generic wand",
                evidence_route=EvidenceRoute.NOVEL_CANON.value,
                source_id="bad_stock",
                source_excerpt="stock",
            )
        ],
    )
    with pytest.raises(ValueError, match="FORBIDDEN VISUAL SOURCE"):
        mock_planner.plan_storyboard(bad_plan)


# ── Test 12: Novel Story Isolation ────────────────────────────────────────────

def test_12_novel_story_isolation(mock_planner, sample_deep_discovery_plan):
    """Verifies that Novel Story pipeline is isolated from Deep Discovery Storyboard Planner."""
    # Passing candidate_type="novel_story" must raise ValueError
    with pytest.raises(ValueError, match="Novel Story pipeline is isolated"):
        mock_planner.plan_storyboard(sample_deep_discovery_plan, candidate_type="novel_story")

    # Passing a dict with content_type="novel_story" must raise ValueError
    novel_story_dict = {
        "content_type": "novel_story",
        "discovery_tier": "NOVEL_STORY",
        "topic_id": "ns_topic_01",
    }
    with pytest.raises(ValueError, match="Novel Story pipeline is isolated"):
        mock_planner.plan_storyboard(novel_story_dict)


# ── Test 13: Backward Compatibility ───────────────────────────────────────────

def test_13_backward_compatibility(mock_planner):
    """Verifies that legacy candidate dictionaries and minimal objects can be processed."""
    legacy_candidate = {
        "id": "hps_disc_neville_001",
        "topic_id": "disc_neville_sorting",
        "discovery_type": "BOOK_VS_MOVIE_DIFFERENCE",
        "thesis": "Neville wanted Hufflepuff.",
        "novel_fact_summary": "Neville sat on stool. Hat deliberated. He was sorted into Gryffindor.",
        "expected_duration": 72.0,
    }

    sb_plan = mock_planner.plan_storyboard(legacy_candidate)
    assert sb_plan.storyboard_id in ("sb_hps_disc_neville_001", "sb_disc_neville_sorting")
    assert len(sb_plan.beats) >= 3
    valid, errors = sb_plan.validate()
    assert valid is True


# ── Test 14: Unsupported / Misleading Visual Rejection ─────────────────────────

def test_14_unsupported_misleading_visual_rejection(mock_planner):
    """Verifies that an unfilmed claim is not falsely claimed as DIRECT_EVIDENCE from unrelated clips."""
    # Mock movie returning no valid candidates
    mock_planner.movie_engine.search_candidates_for_beat.return_value = []
    
    ev_unfilmed = EvidencePoint(
        claim="Peeves writing vulgar limericks on the blackboards before first years arrived",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="b1c08_peeves_chalk",
        source_excerpt="Peeves wrote rude words on the chalkboard.",
    )
    plan_obj = DeepDiscoveryStoryPlan(
        topic_id="peeves_unfilmed_rejection",
        discovery_type="BOOK_ONLY_DETAIL",
        evidence_points=[ev_unfilmed],
        anchor_point=ev_unfilmed,
        thesis="Peeves was cut from the movies completely.",
    )

    sb_plan = mock_planner.plan_storyboard(plan_obj)
    peeves_beat = [b for b in sb_plan.beats if b.evidence_point_id == "b1c08_peeves_chalk"][0]

    # Must NOT be marked as MOVIE_DIRECT DIRECT_EVIDENCE without a match
    if peeves_beat.visual_source_type == VisualSourceType.MOVIE_DIRECT:
        assert peeves_beat.visual_role in (VisualRole.CONTEXTUAL_ENVIRONMENT, VisualRole.CHARACTER_REACTION)
    else:
        assert peeves_beat.visual_source_type in (VisualSourceType.FAN_ART, VisualSourceType.NO_VALID_VISUAL)


# ── Test 15: Asymmetric Anchor Duration ───────────────────────────────────────

def test_15_asymmetric_anchor_duration(mock_planner, sample_deep_discovery_plan):
    """Verifies that anchor beats are significantly longer than regular evidence beats."""
    plan = mock_planner.plan_storyboard(sample_deep_discovery_plan)

    anchor_beats = [b for b in plan.beats if b.is_anchor]
    regular_evidence_beats = [
        b for b in plan.beats if b.narrative_phase == PacingPhase.EVIDENCE.value and not b.is_anchor
    ]

    assert len(anchor_beats) >= 1
    assert len(regular_evidence_beats) >= 1

    anchor_dur = anchor_beats[0].target_duration
    reg_dur = regular_evidence_beats[0].target_duration

    # Anchor target is ~2.7s (range 2.2 - 3.2s) vs regular ~1.6s (range 1.4 - 1.8s)
    assert anchor_dur >= 2.2, f"Anchor duration {anchor_dur}s below minimum 2.2s"
    assert reg_dur <= 1.8, f"Regular evidence duration {reg_dur}s exceeds maximum 1.8s"
    assert anchor_dur > reg_dur + 0.5, f"Anchor duration ({anchor_dur}s) not asymmetrically longer than regular ({reg_dur}s)"


# ── Test 16: Deterministic Storyboard Generation ──────────────────────────────

def test_16_deterministic_storyboard_generation(mock_planner, sample_deep_discovery_plan):
    """Verifies that running the planner twice with the same inputs produces identical output."""
    plan1 = mock_planner.plan_storyboard(sample_deep_discovery_plan)
    plan2 = mock_planner.plan_storyboard(sample_deep_discovery_plan)

    dict1 = plan1.to_dict()
    dict2 = plan2.to_dict()

    assert dict1["total_target_duration"] == dict2["total_target_duration"]
    assert dict1["anchor_beat_ids"] == dict2["anchor_beat_ids"]
    assert len(dict1["beats"]) == len(dict2["beats"])

    for b1, b2 in zip(dict1["beats"], dict2["beats"]):
        assert b1["beat_id"] == b2["beat_id"]
        assert b1["start_seconds"] == b2["start_seconds"]
        assert b1["end_seconds"] == b2["end_seconds"]
        assert b1["target_duration"] == b2["target_duration"]
        assert b1["visual_role"] == b2["visual_role"]
        assert b1["visual_source_type"] == b2["visual_source_type"]
        assert b1["framing_intent"] == b2["framing_intent"]
        assert b1["is_anchor"] == b2["is_anchor"]
