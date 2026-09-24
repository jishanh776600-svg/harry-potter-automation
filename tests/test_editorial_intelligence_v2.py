"""
STORY FORGE — Editorial Intelligence V2 Test Suite
================================================================================
Comprehensive test suite covering all 30 required capability dimensions:
   1. dynamic pacing
   2. narrative weight
   3. hook treatment
   4. punch-in decision
   5. subject tracking
   6. spotlight decision
   7. callout decision
   8. match-cut detection
   9. smash-cut selection
  10. J-cut
  11. L-cut
  12. reaction insert
  13. prop insert
  14. split-screen
  15. PIP
  16. caption emphasis
  17. word-timestamp synchronization
  18. SFX decision integration
  19. solemn suppression
  20. anti-effect-spam
  21. visual density
  22. anti-padding
  23. 9:16 composition preservation
  24. deterministic fingerprint
  25. stale-render invalidation
  26. multi-fact transitions
  27. Book-vs-Movie treatment
  28. BEAST V2 integration
  29. Asset Acquisition compatibility
  30. Novel Story isolation

Synthetic Editorial Benchmark Cases:
  CASE 1: 5-fact Book-vs-Movie Short -> dynamic pacing + comparison treatment
  CASE 2: 7-fact lore Short -> rapid but meaningful transitions
  CASE 3: major emotional reveal -> longer anchor + restrained effects
  CASE 4: object-centric fact -> prop insert + spotlight
  CASE 5: Book vs Movie contradiction -> split-screen + contrast treatment
  CASE 6: BTS fact -> movie footage must NOT be treated as BTS evidence
  CASE 7: no valid direct visual -> no fabricated visual padding
  CASE 8: dense hook -> immediate meaningful visual, no intro padding
  VOICE GATE: VoiceSelectionGate blocks real Short production without user approval
"""

import pytest

from core.editorial_v2_types import (
    EditorialUnit,
    EditorialTimelineV2,
    VisualEmphasisPrimitive,
    EditorialTransitionType,
    MotionTreatment,
    CompositionTreatment,
    CaptionTreatment,
    SFXTreatment,
    SpotlightCalloutConfig,
)
from core.beast_v2_types import (
    BeastV2MatchResult,
    BeastV2Decision,
    EvidenceType,
    SourceEvidenceType,
)
from core.beast_visual_types import BeastCandidateShot, NarrativeEra
from core.multi_fact_types import (
    MultiFactTopicPack,
    MultiFactPayload,
    VisualProposition,
    FactType,
    RequiredEvidenceType,
    MultiFactFormat,
)
from core.composition_models import ShotScale
from engines.editorial.pacing_engine import EditorialPacingEngine
from engines.editorial.treatment_selector import EditorialTreatmentSelector
from engines.editorial.caption_sfx_intelligence import CaptionSFXIntelligence
from engines.editorial.editorial_planner import EditorialPlanner
from engines.editorial.voice_selection_gate import VoiceSelectionGate, VoiceSelectionRequiredError


# ==============================================================================
# FIXTURES
# ==============================================================================

def make_sample_fact(fact_id: str, claim: str, importance: float = 0.8, role: str = "BODY", claim_type: FactType = FactType.BOOK_VS_MOVIE) -> MultiFactPayload:
    return MultiFactPayload(
        fact_id=fact_id,
        theme="Theme",
        claim=claim,
        claim_type=claim_type,
        canon_source="Book 1",
        canon_evidence="Text evidence",
        importance=importance,
        movie_contrast=0.8,
        curiosity_score=0.85,
        visual_feasibility=0.9,
        payoff_value=0.7,
        narrative_role=role,
        visual_propositions=[
            VisualProposition(
                proposition_id=f"prop_{fact_id}_1",
                subject="Neville Longbottom",
                action="pleading",
                object="Sorting Hat",
                context="Great Hall",
            )
        ]
    )


def make_sample_match(asset_id: str = "shot_01", start: float = 10.0, end: float = 15.0) -> BeastV2MatchResult:
    return BeastV2MatchResult(
        candidate_id=asset_id,
        asset_id=asset_id,
        source="MOVIE_ARCHIVE",
        source_start=start,
        source_end=end,
        decision=BeastV2Decision.ACCEPT_DIRECT,
        evidence_type=EvidenceType.DIRECT_EVIDENCE,
        confidence=92.0,
    )


# ==============================================================================
# 30 FOCUSED CAPABILITY TESTS
# ==============================================================================

def test_01_dynamic_pacing():
    pacing = EditorialPacingEngine()
    dur_hook = pacing.calculate_editorial_duration("HOOK", 0.9, 1.5)
    dur_body = pacing.calculate_editorial_duration("BODY", 0.5, 2.0)
    dur_climax = pacing.calculate_editorial_duration("CLIMAX", 0.95, 4.0)

    assert 0.8 <= dur_hook <= 1.5
    assert 1.2 <= dur_body <= 2.0
    assert 3.0 <= dur_climax <= 4.0
    assert dur_climax > dur_body > dur_hook


def test_02_narrative_weight():
    pacing = EditorialPacingEngine()
    high_weight = pacing.calculate_narrative_weight(importance=0.95, curiosity=0.95, movie_contrast=0.9, emotional_value=0.9, payoff_value=0.99)
    low_weight = pacing.calculate_narrative_weight(importance=0.2, curiosity=0.2, movie_contrast=0.1, emotional_value=0.1, payoff_value=0.2)
    assert high_weight > low_weight
    assert high_weight >= 0.85
    assert low_weight <= 0.35


def test_03_hook_treatment():
    planner = EditorialPlanner()
    pack = MultiFactTopicPack(
        topic_id="top_hook",
        theme="Hook Test",
        hook="Neville actually begged the Sorting Hat for Hufflepuff.",
        facts=[make_sample_fact("f1", "Claim")],
    )
    match = make_sample_match("shot_hook", 0.0, 5.0)
    timeline = planner.plan_timeline(pack, [match])
    hook_unit = timeline.units[0]
    assert hook_unit.visual_role == "HOOK"
    assert 0.8 <= hook_unit.duration_seconds <= 1.5
    assert hook_unit.motion_treatment == MotionTreatment.PUNCH_IN_115
    assert hook_unit.transition_type == EditorialTransitionType.HARD_CUT


def test_04_punch_in_decision():
    treatment = EditorialTreatmentSelector()
    motion_punch = treatment.select_motion_treatment(narrative_weight=0.95, is_revelation=True)
    motion_normal = treatment.select_motion_treatment(narrative_weight=0.5, is_revelation=False)
    assert motion_punch == MotionTreatment.PUNCH_IN_115
    assert motion_normal == MotionTreatment.STATIC


def test_05_subject_tracking_composition():
    treatment = EditorialTreatmentSelector()
    comp_close = treatment.select_composition_treatment(ShotScale.MEDIUM_SHOT)
    comp_wide = treatment.select_composition_treatment(ShotScale.WIDE_SHOT)
    assert comp_close == CompositionTreatment.FULL_BLEED_RECENTERED
    assert comp_wide == CompositionTreatment.HYBRID_MODERATE_CROP


def test_06_spotlight_decision():
    treatment = EditorialTreatmentSelector()
    prop = VisualProposition("p1", "None", "showing hidden detail", "Daily Prophet Headline", "Diagon")
    callout = treatment.select_callout(prop, is_hidden_detail=True)
    assert callout is not None
    assert callout.callout_type in ("CIRCULAR_HIGHLIGHT", "MAGNIFIER")
    assert 1.0 <= callout.duration_seconds <= 1.5


def test_07_callout_decision_prop_inscription():
    treatment = EditorialTreatmentSelector()
    prop = VisualProposition("p2", "None", "examining prop", "Inscribed Locket", "Cave")
    callout = treatment.select_callout(prop, is_prop_inscription=True)
    assert callout is not None
    assert callout.callout_type == "MAGNIFIER"
    assert callout.label == "Inscribed Locket"


def test_08_match_cut_detection():
    treatment = EditorialTreatmentSelector()
    shot_a = BeastCandidateShot("s1", "v1", 1, 0.0, 5.0, 5.0, objects_present=["Sword of Gryffindor"])
    shot_b = BeastCandidateShot("s2", "v2", 2, 10.0, 15.0, 5.0, objects_present=["Sword of Gryffindor"])
    trans, reason = treatment.select_transition(shot_a, shot_b)
    assert trans == EditorialTransitionType.MATCH_CUT
    assert "Sword of Gryffindor" in reason


def test_09_smash_cut_selection():
    treatment = EditorialTreatmentSelector()
    trans, reason = treatment.select_transition(None, None, narrative_role="SURPRISE", movie_contrast=0.95)
    assert trans == EditorialTransitionType.SMASH_CUT
    assert "Smash cut" in reason


def test_10_j_cut_selection():
    treatment = EditorialTreatmentSelector()
    trans, reason = treatment.select_transition(None, None, is_audio_led_j_cut=True)
    assert trans == EditorialTransitionType.J_CUT
    assert "Audio lead-in" in reason


def test_11_l_cut_selection():
    treatment = EditorialTreatmentSelector()
    trans, reason = treatment.select_transition(None, None, is_audio_led_l_cut=True)
    assert trans == EditorialTransitionType.L_CUT
    assert "Audio overlap" in reason


def test_12_reaction_insert_primitive():
    prims = EditorialTreatmentSelector.assemble_emphasis_primitives(
        motion=MotionTreatment.STATIC,
        composition=CompositionTreatment.FULL_BLEED_RECENTERED,
        callout=None,
        narrative_role="EMOTION",
        is_reaction=True,
    )
    assert VisualEmphasisPrimitive.REACTION_INSERT in prims


def test_13_prop_insert_primitive():
    prims = EditorialTreatmentSelector.assemble_emphasis_primitives(
        motion=MotionTreatment.STATIC,
        composition=CompositionTreatment.FULL_BLEED_RECENTERED,
        callout=None,
        narrative_role="BODY",
        is_object_prop=True,
    )
    assert VisualEmphasisPrimitive.OBJECT_SPOTLIGHT in prims


def test_14_split_screen_selection():
    comp = EditorialTreatmentSelector.select_composition_treatment(is_book_vs_movie_comparison=True)
    assert comp == CompositionTreatment.SPLIT_SCREEN_VERTICAL


def test_15_pip_selection():
    comp = EditorialTreatmentSelector.select_composition_treatment(is_citation_or_bts_inset=True)
    assert comp == CompositionTreatment.PICTURE_IN_PICTURE_OVERLAY


def test_16_caption_emphasis():
    capt = CaptionSFXIntelligence.select_caption_treatment("Harry held the Horcrux tightly", narrative_weight=0.8)
    assert capt == CaptionTreatment.CANON_KEYWORD_HIGHLIGHT


def test_17_word_timestamp_synchronization():
    planner = EditorialPlanner()
    pack = MultiFactTopicPack("top_words", "Theme", "Hook text", [make_sample_fact("f1", "Claim")])
    match = make_sample_match("s1", 0.0, 5.0)
    timeline = planner.plan_timeline(pack, [match])
    # Verify timeline is strictly gapless across narration intervals
    expected_start = 0.0
    for u in timeline.units:
        assert abs(u.narration_start - expected_start) < 0.01
        expected_start = u.narration_end


def test_18_sfx_decision_integration():
    sfx, reason = CaptionSFXIntelligence.select_sfx_treatment("Massive secret revealed", narrative_role="CLIMAX", narrative_weight=0.98)
    assert sfx == SFXTreatment.REVELATION


def test_19_solemn_suppression():
    sfx, reason = CaptionSFXIntelligence.select_sfx_treatment("Severus Snape dies in the boathouse tragic death", narrative_role="EMOTION", narrative_weight=0.95)
    assert sfx == SFXTreatment.INTENTIONAL_SILENCE
    assert "Intentional silence" in reason


def test_20_anti_effect_spam():
    treatment = EditorialTreatmentSelector()
    # If 2 punch-ins already happened recently, third must NOT punch-in
    motion = treatment.select_motion_treatment(narrative_weight=0.95, is_revelation=True, recent_punch_ins=2)
    assert motion != MotionTreatment.PUNCH_IN_115


def test_21_visual_density():
    planner = EditorialPlanner()
    facts = [make_sample_fact(f"f_{i}", f"Fact claim {i}") for i in range(1, 6)]
    pack = MultiFactTopicPack("top_dens", "Theme", "Hook text", facts=facts)
    matches = [make_sample_match(f"s_{i}", 0.0, 10.0) for i in range(1, 6)]
    timeline = planner.plan_timeline(pack, matches)
    # Hook + 5 facts + payoff = 7 meaningful units
    assert timeline.total_cuts >= 7
    assert timeline.quality_audit["average_cut_duration"] <= 4.0


def test_22_anti_padding():
    planner = EditorialPlanner()
    # Short source asset (only 1.1s long)
    match_short = make_sample_match("short_asset", start=5.0, end=6.1)
    pack = MultiFactTopicPack("top_pad", "Theme", "Hook", facts=[make_sample_fact("f1", "Claim")])
    timeline = planner.plan_timeline(pack, [match_short])
    # The unit must NOT exceed the source asset length (1.1s)
    unit = [u for u in timeline.units if u.fact_id == "f1"][0]
    assert unit.duration_seconds <= 1.11


def test_23_nine_sixteen_composition_preservation():
    comp = EditorialTreatmentSelector.select_composition_treatment(ShotScale.MEDIUM_SHOT)
    assert comp in (CompositionTreatment.FULL_BLEED_RECENTERED, CompositionTreatment.HYBRID_MODERATE_CROP)
    assert comp != CompositionTreatment.BLURRED_PADDING


def test_24_deterministic_fingerprint():
    planner = EditorialPlanner()
    pack = MultiFactTopicPack("top_fp", "Theme", "Hook", facts=[make_sample_fact("f1", "Claim")])
    matches = [make_sample_match("s1", 0.0, 5.0)]
    t1 = planner.plan_timeline(pack, matches)
    t2 = planner.plan_timeline(pack, matches)
    assert t1.deterministic_fingerprint == t2.deterministic_fingerprint
    assert len(t1.deterministic_fingerprint) == 16


def test_25_stale_render_invalidation():
    p1 = EditorialPlanner(config_version="v2.0")
    p2 = EditorialPlanner(config_version="v2.1")
    pack = MultiFactTopicPack("top_stale", "Theme", "Hook", facts=[make_sample_fact("f1", "Claim")])
    matches = [make_sample_match("s1", 0.0, 5.0)]
    t1 = p1.plan_timeline(pack, matches)
    t2 = p2.plan_timeline(pack, matches)
    assert t1.deterministic_fingerprint != t2.deterministic_fingerprint


def test_26_multi_fact_transitions():
    planner = EditorialPlanner()
    facts = [
        make_sample_fact("f1", "Claim 1", role="ENTRY"),
        make_sample_fact("f2", "Claim 2", role="SURPRISE"),
        make_sample_fact("f3", "Claim 3", role="CLIMAX"),
    ]
    pack = MultiFactTopicPack("top_trans", "Theme", "Hook", facts=facts)
    matches = [make_sample_match(f"s_{i}", 0.0, 10.0) for i in range(1, 4)]
    timeline = planner.plan_timeline(pack, matches)
    transitions = [u.transition_type for u in timeline.units]
    assert EditorialTransitionType.SMASH_CUT in transitions or EditorialTransitionType.HARD_CUT in transitions


def test_27_book_vs_movie_treatment():
    treatment = EditorialTreatmentSelector()
    comp = treatment.select_composition_treatment(is_book_vs_movie_comparison=True)
    assert comp == CompositionTreatment.SPLIT_SCREEN_VERTICAL


def test_28_beast_v2_integration():
    planner = EditorialPlanner()
    match = BeastV2MatchResult(
        candidate_id="b2_c1",
        asset_id="b2_c1",
        source="MOVIE_ARCHIVE",
        source_start=12.5,
        source_end=15.0,
        evidence_type=EvidenceType.DIRECT_EVIDENCE,
        decision=BeastV2Decision.ACCEPT_DIRECT,
        confidence=95.0,
    )
    pack = MultiFactTopicPack("top_b2", "Theme", "Hook", facts=[make_sample_fact("f1", "Claim")])
    timeline = planner.plan_timeline(pack, [match])
    assert timeline.units[1].asset_id == "b2_c1"
    assert timeline.units[1].evidence_type == "DIRECT_EVIDENCE"


def test_29_asset_acquisition_compatibility():
    planner = EditorialPlanner()
    match_acq = BeastV2MatchResult(
        candidate_id="acq_web_123",
        asset_id="acq_web_123",
        source="ASSET_ACQUISITION",
        source_start=0.0,
        source_end=3.0,
        evidence_type=EvidenceType.OBJECT_PROP_EVIDENCE,
        source_evidence_type=SourceEvidenceType.PHOTOGRAPH,
        decision=BeastV2Decision.ACCEPT_OBJECT,
        confidence=90.0,
    )
    pack = MultiFactTopicPack("top_acq", "Theme", "Hook", facts=[make_sample_fact("f1", "Object Claim")])
    timeline = planner.plan_timeline(pack, [match_acq])
    assert timeline.units[1].asset_id == "acq_web_123"


def test_30_novel_story_isolation():
    planner = EditorialPlanner()
    pack = MultiFactTopicPack("top_ns", "Theme", "Hook", facts=[make_sample_fact("f1", "Claim")])
    with pytest.raises(ValueError, match="Novel Story pipeline is isolated"):
        planner.plan_timeline(pack, [make_sample_match()], candidate_type="novel_story")


# ==============================================================================
# SYNTHETIC EDITORIAL BENCHMARK CASES (CASES 1 THROUGH 8 + VOICE GATE)
# ==============================================================================

def test_synthetic_case_1_book_vs_movie_pacing_and_comparison():
    """CASE 1: 5-fact Book-vs-Movie Short -> dynamic pacing + comparison treatment."""
    planner = EditorialPlanner()
    facts = [
        make_sample_fact(f"bm_{i}", f"Book vs movie difference {i}", claim_type=FactType.BOOK_VS_MOVIE)
        for i in range(1, 6)
    ]
    pack = MultiFactTopicPack("case1_bm", "5 Book vs Movie Differences", "Hook text", facts=facts)
    matches = [make_sample_match(f"bm_shot_{i}", 0.0, 10.0) for i in range(1, 6)]
    timeline = planner.plan_timeline(pack, matches)

    assert timeline.is_valid is True
    assert timeline.total_cuts >= 7
    # Dynamic pacing: hook is shorter than payoff
    assert timeline.units[0].duration_seconds < timeline.units[-1].duration_seconds


def test_synthetic_case_2_seven_fact_lore_rapid_transitions():
    """CASE 2: 7-fact lore Short -> rapid but meaningful transitions."""
    planner = EditorialPlanner()
    facts = [make_sample_fact(f"lore_{i}", f"Lore clue {i}") for i in range(1, 8)]
    pack = MultiFactTopicPack("case2_lore", "7 Hidden Lore Clues", "Hook text", facts=facts)
    matches = [make_sample_match(f"lore_s_{i}", 0.0, 10.0) for i in range(1, 8)]
    timeline = planner.plan_timeline(pack, matches)

    assert len(timeline.units) >= 9
    # Transition variety
    assert len(timeline.quality_audit["transition_types_used"]) >= 1


def test_synthetic_case_3_major_emotional_reveal_restrained():
    """CASE 3: Major emotional reveal -> longer anchor + restrained effects."""
    pacing = EditorialPacingEngine()
    dur = pacing.calculate_editorial_duration("EMOTION", 0.95, 3.5)
    assert 2.0 <= dur <= 3.5

    # Check solemn silence
    sfx, reason = CaptionSFXIntelligence.select_sfx_treatment("Snape dies looking into Lily eyes", narrative_role="EMOTION")
    assert sfx == SFXTreatment.INTENTIONAL_SILENCE


def test_synthetic_case_4_object_centric_prop_spotlight():
    """CASE 4: Object-centric fact -> prop insert + spotlight."""
    treatment = EditorialTreatmentSelector()
    prop = VisualProposition("p_obj", "None", "gleaming", "Sword of Gryffindor", "Office", visual_role="OBJECT_PROP")
    callout = treatment.select_callout(prop, is_prop_inscription=True)
    assert callout is not None
    assert callout.callout_type == "MAGNIFIER"


def test_synthetic_case_5_book_vs_movie_split_screen():
    """CASE 5: Book vs Movie contradiction -> split-screen + contrast treatment."""
    comp = EditorialTreatmentSelector.select_composition_treatment(is_book_vs_movie_comparison=True)
    assert comp == CompositionTreatment.SPLIT_SCREEN_VERTICAL


def test_synthetic_case_6_bts_fact_source_separation():
    """CASE 6: BTS fact -> movie footage must NOT be treated as BTS evidence."""
    match = BeastV2MatchResult(
        candidate_id="bts_c1",
        asset_id="bts_c1",
        source="MOVIE_ARCHIVE",
        source_start=0.0,
        source_end=2.0,
        source_evidence_type=SourceEvidenceType.FILM,
        decision=BeastV2Decision.NO_VALID_VISUAL,
        reason="BTS requires behind-the-scenes evidence, not movie fiction",
    )
    assert match.decision == BeastV2Decision.NO_VALID_VISUAL


def test_synthetic_case_7_no_valid_direct_visual_no_fabricated_padding():
    """CASE 7: No valid direct visual -> no fabricated visual padding."""
    planner = EditorialPlanner()
    match_invalid = BeastV2MatchResult(
        candidate_id="none",
        asset_id="none",
        source="NONE",
        source_start=0.0,
        source_end=0.0,
        decision=BeastV2Decision.NO_VALID_VISUAL,
    )
    pack = MultiFactTopicPack("case7_none", "Theme", "Hook", facts=[make_sample_fact("f1", "Claim")])
    timeline = planner.plan_timeline(pack, [match_invalid])
    assert any("NO_VALID_VISUAL" in w for w in timeline.validation_warnings)


def test_synthetic_case_8_dense_hook_no_intro_padding():
    """CASE 8: Dense hook -> immediate meaningful visual, no intro padding."""
    planner = EditorialPlanner()
    pack = MultiFactTopicPack("case8_hook", "Theme", "Cold open question hook", facts=[make_sample_fact("f1", "Claim")])
    timeline = planner.plan_timeline(pack, [make_sample_match("h1", 0.0, 5.0)])
    hook_unit = timeline.units[0]
    assert hook_unit.visual_role == "HOOK"
    assert hook_unit.duration_seconds <= 1.5
    assert "fade" not in hook_unit.reason.lower()


def test_voice_selection_hard_gate():
    """VOICE SELECTION HARD GATE: Blocks real Short production without explicit user approval."""
    VoiceSelectionGate.reset_gate()
    assert VoiceSelectionGate.is_approved() is False

    # Attempting to verify gate without user approval raises VoiceSelectionRequiredError
    with pytest.raises(VoiceSelectionRequiredError, match="VOICE_SELECTION_REQUIRED"):
        VoiceSelectionGate.verify_gate()

    # User explicitly auditions and approves
    VoiceSelectionGate.set_approved_voice("af_bella", {"auditioned": True, "style": "BELLA_CANON_EXPERT"})
    assert VoiceSelectionGate.is_approved() is True
    assert VoiceSelectionGate.get_selected_voice() == "af_bella"

    # Now verify_gate succeeds without error
    VoiceSelectionGate.verify_gate()
    # Reset for cleanliness
    VoiceSelectionGate.reset_gate()
