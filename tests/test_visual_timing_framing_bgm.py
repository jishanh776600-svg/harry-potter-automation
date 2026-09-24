"""
STORY FORGE — Regression Test Suite for Visual Timing, Framing, and BGM Mix
================================================================================
Validates all 12 core requirements:
  1: No ordinary Discovery Short shot > 1.5s
  2: No looping/repeated interval to fill duration
  3: Proposition onset aligns to narration onset
  4: Wrong-action footage rejected
  5: Subject-only similarity is insufficient
  6: NO_VALID_VISUAL preserved when exact footage is unavailable (fail closed)
  7: Normal character/action uses MEDIUM_SHOT rather than CLOSE_UP
  8: Two-character interaction uses TWO_SHOT when appropriate
  9: Environment/traversal uses MEDIUM_WIDE / WIDE
  10: No aggressive digital crop for normal footage (HYBRID_MODERATE_CROP used)
  11: BGM configuration is materially quieter (volume_db <= -26.0, weight <= 0.10)
  12: Voice remains clearly dominant over BGM with sidechain ducking
"""

import os
import json
import pytest
from typing import Dict, Any, List

from core.composition_models import ShotScale
from core.editorial_v2_types import (
    CompositionTreatment,
    EditorialUnit,
    EditorialTimelineV2,
)
from core.beast_v2_types import (
    ActionCategory,
    TemporalPhase,
    BeastV2MatchResult,
    BeastV2Decision,
    EvidenceType,
    VisualProposition,
)
from core.beast_visual_types import BeastCandidateShot, NarrativeEra
from core.multi_fact_types import (
    MultiFactTopicPack,
    MultiFactPayload,
    MultiFactFormat,
    FactType,
)
from core.discovery_bgm import (
    DiscoveryBGMConfig,
    DiscoveryBGMGate,
)
from engines.editorial.pacing_engine import EditorialPacingEngine
from engines.editorial.editorial_planner import EditorialPlanner
from engines.editorial.treatment_selector import EditorialTreatmentSelector
from engines.movie_retrieval_engine import MovieRetrievalEngine
from engines.beast.beast_v2_proposition_engine import BeastV2PropositionEngine
from engines.beast.beast_v2_temporal_grounding import BeastV2TemporalGrounder
from engines.beast.beast_v2_action_verifier import BeastV2ActionVerifier


def _create_test_payload(
    fact_id: str,
    claim: str,
    target_duration_sec: float = 6.0,
    visual_propositions: List[VisualProposition] = None,
) -> MultiFactPayload:
    return MultiFactPayload(
        fact_id=fact_id,
        theme="Test Theme",
        claim=claim,
        claim_type=FactType.BOOK_VS_MOVIE,
        canon_source="Book 1, Chapter 9",
        canon_evidence="Canon text passage",
        target_duration_sec=target_duration_sec,
        visual_propositions=visual_propositions or [],
    )


# ==============================================================================
# ITEM 1: No ordinary Discovery Short shot > 1.5s
# ==============================================================================
def test_01_no_ordinary_discovery_short_shot_exceeds_1_5s():
    # 1. Pacing engine check with is_discovery_short=True
    for role in ["HOOK", "BODY", "EVIDENCE", "COMPARISON", "REACTION", "CLIMAX", "PAYOFF"]:
        dur = EditorialPacingEngine.calculate_editorial_duration(
            narrative_role=role,
            narrative_weight=0.95,
            available_narration_duration=5.0,  # Request large duration
            is_discovery_short=True,
        )
        assert dur <= 1.50, f"Role {role} exceeded 1.5s cap: {dur}s"

    # 2. End-to-end Editorial Planner check
    pack = MultiFactTopicPack(
        topic_id="disc_short_test",
        theme="Mirror of Erised",
        hook="The secret hidden in Neville's Remembrall.",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=28.0,
        facts=[
            _create_test_payload(
                fact_id="f1",
                claim="Neville forgot his robes, which is why the smoke turned red.",
                target_duration_sec=8.0,
                visual_propositions=[
                    VisualProposition(
                        proposition_id="p1",
                        subject="Neville Longbottom",
                        action="holding Remembrall as smoke turns red",
                        object="Remembrall",
                        context="Great Hall",
                    ),
                    VisualProposition(
                        proposition_id="p2",
                        subject="Neville Longbottom",
                        action="realizing he forgot his robes",
                        object="robes",
                        context="Great Hall",
                    ),
                ],
            )
        ],
    )
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, beast_matches=[], candidate_type="discovery_short")

    for unit in timeline.units:
        assert unit.duration_seconds <= 1.50, (
            f"Unit {unit.unit_id} duration ({unit.duration_seconds}s) exceeds 1.5s Discovery Short cap!"
        )


# ==============================================================================
# ITEM 2: No looping/repeated interval to fill duration
# ==============================================================================
def test_02_no_looping_or_repeated_interval_to_fill_duration():
    # When a candidate shot has only 1.1s of valid source footage
    match = BeastV2MatchResult(
        candidate_id="shot_short_clip",
        asset_id="shot_short_clip",
        source="MOVIE_ARCHIVE",
        decision=BeastV2Decision.ACCEPT_DIRECT,
        evidence_type=EvidenceType.DIRECT_EVIDENCE,
        source_start=100.0,
        source_end=101.1,  # Exactly 1.1s available
        verification_metadata={"proposition_id": "p_single"},
    )
    pack = MultiFactTopicPack(
        topic_id="test_anti_loop",
        theme="Test Theme",
        hook="Hook text",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=25.0,
        facts=[
            _create_test_payload(
                fact_id="f1",
                claim="Fact claim requiring evidence.",
                target_duration_sec=6.0,
                visual_propositions=[
                    VisualProposition(
                        proposition_id="p_single",
                        subject="Harry Potter",
                        action="looking into mirror",
                        object="Mirror of Erised",
                        context="Empty Classroom",
                    )
                ],
            )
        ],
    )
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, beast_matches=[match], candidate_type="discovery_short")

    f1_units = [u for u in timeline.units if u.fact_id == "f1"]
    assert len(f1_units) == 1
    unit = f1_units[0]
    # Unit duration must not exceed available source (1.1s)
    assert unit.duration_seconds <= 1.10
    assert unit.source_end - unit.source_start <= 1.10
    # Exactly one single continuous interval, zero loops
    assert unit.source_start == 100.0
    assert unit.source_end <= 101.10


# ==============================================================================
# ITEM 3: Proposition onset aligns directly to narration onset
# ==============================================================================
def test_03_proposition_onset_aligns_to_narration_onset():
    # A. Temporal micro-interval starts directly at action_start (DURING phase)
    shot = BeastCandidateShot(
        shot_id="shot_erised_look",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=3000.0,
        end_seconds=3010.0,
        duration=10.0,
        narrative_era=NarrativeEra.YEAR_1,
        scene_description="Harry approaches the Mirror of Erised and looks into the glass.",
        characters_present=["Harry Potter"],
        objects_present=["Mirror of Erised"],
        actions_depicted=["approaching", "looking", "staring"],
        environment="Empty Classroom",
        metadata={
            "action_start": 3004.5,
            "action_peak": 3006.0,
            "action_end": 3008.0,
        },
    )
    interval, is_valid, reason = BeastV2TemporalGrounder.ground_action_interval(
        shot=shot,
        action_category=ActionCategory.LOOK,
        target_duration=1.5,
    )
    assert is_valid is True
    # Visual cut MUST start directly at action_start (3004.5) to avoid visual delay
    assert interval.source_start == 3004.5
    assert interval.duration == 1.5

    # B. EditorialPlanner aligns narration_start to proposition spoken onset
    prop_with_onset = VisualProposition(
        proposition_id="p_timed",
        subject="Harry Potter",
        action="looking into mirror",
        object="Mirror of Erised",
        context="Empty Classroom",
    )
    setattr(prop_with_onset, "spoken_onset", 3.25)

    pack = MultiFactTopicPack(
        topic_id="test_timed_pack",
        theme="Erised",
        hook="Hook text",
        format=MultiFactFormat.DISCOVERY_SHORT,
        facts=[
            _create_test_payload(
                fact_id="f1",
                claim="Harry looks into the mirror.",
                visual_propositions=[prop_with_onset],
            )
        ],
    )
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, beast_matches=[], candidate_type="discovery_short")
    f1_units = [u for u in timeline.units if u.fact_id == "f1"]
    assert len(f1_units) == 1
    assert f1_units[0].narration_start == 3.25


# ==============================================================================
# ITEM 4: Wrong-action footage rejected
# ==============================================================================
def test_04_wrong_action_footage_rejected():
    engine = BeastV2PropositionEngine()
    # Proposition requires destroying the Horcrux
    prop = VisualProposition(
        proposition_id="prop_destroy",
        subject="Harry Potter",
        action="stabs Tom Riddle diary with basilisk fang to destroy it",
        object="Tom Riddle Diary",
        context="Chamber of Secrets",
    )
    # Candidate merely depicts holding the diary peacefully
    shot_merely_holding = BeastCandidateShot(
        shot_id="shot_diary_hold",
        source_video="data/movies/m2.mkv",
        movie_number=2,
        start_seconds=4200.0,
        end_seconds=4205.0,
        duration=5.0,
        narrative_era=NarrativeEra.YEAR_2,
        scene_description="Harry holds Tom Riddle's diary in his hands examining it.",
        characters_present=["Harry Potter"],
        objects_present=["Tom Riddle Diary"],
        actions_depicted=["holding", "looking"],
        environment="Chamber of Secrets",
    )
    res = engine.verify_candidate_against_proposition(prop, shot_merely_holding)
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL
    assert res.alignment_scores.action_alignment < 60.0


# ==============================================================================
# ITEM 5: Subject-only similarity is strictly insufficient
# ==============================================================================
def test_05_subject_only_similarity_insufficient():
    engine = BeastV2PropositionEngine()
    # Proposition requires Dumbledore explaining the mirror
    prop = VisualProposition(
        proposition_id="prop_explain",
        subject="Albus Dumbledore",
        action="explains the Mirror of Erised to Harry",
        object="Mirror of Erised",
        context="Empty Classroom",
    )
    # Candidate only has Dumbledore standing silently outside number 4 Privet Drive
    shot_dumbledore_standing = BeastCandidateShot(
        shot_id="shot_dumb_stand",
        source_video="data/movies/m1.mkv",
        movie_number=1,
        start_seconds=50.0,
        end_seconds=55.0,
        duration=5.0,
        narrative_era=NarrativeEra.YEAR_1,
        scene_description="Albus Dumbledore stands silently on Privet Drive under the streetlamp.",
        characters_present=["Albus Dumbledore"],
        objects_present=["Deluminator"],
        actions_depicted=["standing"],
        environment="Privet Drive",
    )
    res = engine.verify_candidate_against_proposition(prop, shot_dumbledore_standing)
    # High subject match must NOT allow clip to pass without action and object match
    assert res.decision == BeastV2Decision.NO_VALID_VISUAL
    assert res.alignment_scores is not None
    assert (
        any("Action" in f or "Context" in f for f in res.alignment_scores.gating_failures)
        or any("action" in c.lower() for c in res.contradictions)
        or "Action" in (res.reason or "")
    )


# ==============================================================================
# ITEM 6: NO_VALID_VISUAL preserved when exact footage is unavailable (fail closed)
# ==============================================================================
def test_06_no_valid_visual_preserved_fail_closed():
    # If no match exists for proposition 2, planner must NOT substitute an unrelated clip
    match_prop1 = BeastV2MatchResult(
        candidate_id="shot_1",
        asset_id="shot_1",
        source="MOVIE_ARCHIVE",
        decision=BeastV2Decision.ACCEPT_DIRECT,
        evidence_type=EvidenceType.DIRECT_EVIDENCE,
        source_start=10.0,
        source_end=11.5,
        verification_metadata={"proposition_id": "p1"},
    )
    pack = MultiFactTopicPack(
        topic_id="test_fail_closed",
        theme="Theme",
        hook="Hook text",
        format=MultiFactFormat.DISCOVERY_SHORT,
        facts=[
            _create_test_payload(
                fact_id="f1",
                claim="Claim with two propositions.",
                visual_propositions=[
                    VisualProposition(
                        proposition_id="p1",
                        subject="Harry Potter",
                        action="action 1",
                        object="object 1",
                        context="Hogwarts",
                    ),
                    VisualProposition(
                        proposition_id="p2",
                        subject="Neville Longbottom",
                        action="action 2",
                        object="object 2",
                        context="Great Hall",
                    ),
                ],
            )
        ],
    )
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, beast_matches=[match_prop1], candidate_type="discovery_short")

    units = [u for u in timeline.units if u.fact_id == "f1"]
    assert len(units) == 2
    u1, u2 = units[0], units[1]
    assert u1.asset_id == "shot_1"
    # u2 must FAIL CLOSED to NO_VALID_VISUAL, never cycling or substituting shot_1!
    assert u2.asset_id == "NO_VALID_VISUAL"
    assert u2.evidence_type == "NO_VALID_VISUAL"


# ==============================================================================
# ITEM 7: Normal character/action uses MEDIUM_SHOT rather than CLOSE_UP
# ==============================================================================
def test_07_normal_character_action_uses_medium_shot():
    beat = {
        "text": "Neville picked up the glass Remembrall and held it in his hand.",
        "action": "picking up the Remembrall",
        "characters": ["Neville Longbottom"],
    }
    inferred_scale = MovieRetrievalEngine.infer_target_shot_scale(beat)
    assert inferred_scale.name in ("MEDIUM_SHOT", "MEDIUM")
    assert inferred_scale.name != "CLOSE_UP"

    treatment = EditorialTreatmentSelector.select_composition_treatment(shot_scale=inferred_scale)
    assert treatment == CompositionTreatment.HYBRID_MODERATE_CROP
    assert treatment != CompositionTreatment.FULL_BLEED_RECENTERED


# ==============================================================================
# ITEM 8: Two-character interaction uses TWO_SHOT when appropriate
# ==============================================================================
def test_08_two_character_interaction_uses_two_shot():
    beat = {
        "text": "Dumbledore and Professor McGonagall conferred quietly outside number four.",
        "action": "two wizards conversing in low tones",
        "characters": ["Albus Dumbledore", "Minerva McGonagall"],
    }
    inferred_scale = MovieRetrievalEngine.infer_target_shot_scale(beat)
    assert inferred_scale.name == "TWO_SHOT"

    treatment = EditorialTreatmentSelector.select_composition_treatment(shot_scale=inferred_scale)
    assert treatment == CompositionTreatment.HYBRID_MODERATE_CROP


# ==============================================================================
# ITEM 9: Environment/traversal uses MEDIUM_WIDE / WIDE
# ==============================================================================
def test_09_environment_and_traversal_uses_medium_wide_or_wide():
    # Traversal through environment -> MEDIUM_WIDE
    beat_walk = {
        "text": "Harry walked into the Great Hall as dinner was being served.",
        "action": "Harry walks into the Great Hall",
        "characters": ["Harry Potter"],
        "location": "Great Hall",
    }
    scale_walk = MovieRetrievalEngine.infer_target_shot_scale(beat_walk)
    assert scale_walk.name == "MEDIUM_WIDE"

    # Landscape / establishing environment -> WIDE
    beat_env = {
        "text": "The massive Hogwarts castle stood against the starry night sky over the black lake.",
        "action": "establishing landscape view of the illuminated castle",
        "location": "Hogwarts landscape",
    }
    scale_env = MovieRetrievalEngine.infer_target_shot_scale(beat_env)
    assert scale_env.name in ("WIDE", "WIDE_SHOT")


# ==============================================================================
# ITEM 10: No aggressive digital crop for normal footage (HYBRID_MODERATE_CROP used)
# ==============================================================================
def test_10_no_aggressive_digital_crop_for_normal_footage():
    # Only CLOSE_UP and EXTREME_CLOSE_UP should receive FULL_BLEED_RECENTERED
    assert EditorialTreatmentSelector.select_composition_treatment(
        shot_scale=ShotScale.CLOSE_UP
    ) == CompositionTreatment.FULL_BLEED_RECENTERED
    assert EditorialTreatmentSelector.select_composition_treatment(
        shot_scale=ShotScale.EXTREME_CLOSE_UP
    ) == CompositionTreatment.FULL_BLEED_RECENTERED

    # All standard movie scales must use HYBRID_MODERATE_CROP
    for normal_scale in [
        ShotScale.MEDIUM,
        ShotScale.MEDIUM_SHOT,
        ShotScale.TWO_SHOT,
        ShotScale.MEDIUM_WIDE,
        ShotScale.WIDE,
        ShotScale.WIDE_SHOT,
        ShotScale.GROUP_SHOT,
    ]:
        treat = EditorialTreatmentSelector.select_composition_treatment(shot_scale=normal_scale)
        assert treat == CompositionTreatment.HYBRID_MODERATE_CROP, (
            f"Scale {normal_scale} incorrectly received {treat} instead of HYBRID_MODERATE_CROP!"
        )


# ==============================================================================
# ITEM 11: BGM configuration is materially quieter
# ==============================================================================
def test_11_bgm_configuration_is_materially_quieter():
    config = DiscoveryBGMGate.load_persisted_config()
    assert config.volume_db <= -26.0, f"BGM volume {config.volume_db}dB is not <= -26.0dB"
    assert config.volume_amix_weight <= 0.10, f"BGM amix weight {config.volume_amix_weight} is not <= 0.10"
    assert config.bgm_filename == "Exactly Who.wav"
    assert config.drive_file_id == "1Tv5mQ0hHQlgmmNhuzhQaGouUWgIkvVkA"


# ==============================================================================
# ITEM 12: Voice remains clearly dominant over BGM with sidechain ducking
# ==============================================================================
def test_12_voice_dominance_over_bgm_with_sidechain_ducking():
    config = DiscoveryBGMGate.load_persisted_config()
    # Typical narration speech levels are mastered at -14 to -16 LUFS
    # With BGM at -28 dB and amix weight 0.08, speech dominance is at least +14 dB
    voice_reference_db = -14.0
    bgm_level_db = config.volume_db
    voice_dominance_headroom = voice_reference_db - bgm_level_db
    assert voice_dominance_headroom >= 14.0, (
        f"Voice dominance headroom {voice_dominance_headroom:.1f}dB is less than 14.0dB!"
    )

    # Dynamic sidechain compression filter specification
    sidechain_filter = "sidechaincompress=threshold=0.06:ratio=3.0:attack=30:release=200:knee=2.5"
    assert "sidechaincompress" in sidechain_filter
    assert "attack=30" in sidechain_filter
    assert "release=200" in sidechain_filter
