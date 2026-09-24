"""
STORY FORGE — Visual Evidence Validator Test Suite
===================================================
Tests proposition-level video evidence validation:
  1. Exact action -> DIRECT (Case A)
  2. Wrong action -> reject (Case B)
  3. Subject + Object match but action is wrong -> reject (Case C)
  4. Missing object -> reject (OBJECT_MISSING)
  5. Correct character but wrong scene -> reject (Case D / CONTEXT_MISMATCH)
  6. Action happens BEFORE the selected interval -> reject (Case E / BEFORE_PHASE_ONLY)
  7. Action happens AFTER the selected interval -> reject (Case F / AFTER_PHASE_ONLY)
  8. Subject-only match -> reject (character presence is never sufficient)
  9. Contextual footage -> CONTEXT (Case G)
 10. No reliable evidence / uncertain -> NO_VALID_VISUAL (Case H)
 11. Exact action for 0.8–1.4s -> accept exact micro-interval (Case I)
 12. Candidate is >1.5s -> trim to actual evidence interval <= 1.5s (Case J)
 13. Image / non-video media strictly rejected (VIDEO-ONLY policy)
 14. Human-readable rejection reasons (ACTION_MISMATCH, OBJECT_MISSING, etc.)
 15. Evidence classification reaches Editorial Planner correctly
"""

import pytest
from core.multi_fact_types import (
    VisualProposition,
    VisualRelationship,
    MultiFactTopicPack,
    MultiFactPayload,
    MultiFactFormat,
    FactType,
)
from core.beast_visual_types import BeastCandidateShot
from core.beast_v2_types import BeastV2MatchResult, BeastV2Decision, EvidenceType
from engines.visual_evidence.evidence_models import (
    EvidenceClass,
    EvidenceRejectionReason,
    TemporalState,
    EvidenceValidatorConfig,
)
from engines.visual_evidence.visual_evidence_validator import VisualEvidenceValidator
from engines.visual_evidence.temporal_extractor import TemporalMicroIntervalExtractor
from engines.editorial.editorial_planner import EditorialPlanner


@pytest.fixture
def validator():
    return VisualEvidenceValidator()


def _make_candidate(
    shot_id: str,
    start: float,
    end: float,
    characters: list,
    actions: list,
    objects: list,
    environment: str = "Great Hall",
    description: str = "",
    metadata: dict = None,
) -> BeastCandidateShot:
    return BeastCandidateShot(
        shot_id=shot_id,
        source_video=f"{shot_id}.mp4",
        movie_number=1,
        start_seconds=start,
        end_seconds=end,
        duration=round(end - start, 3),
        characters_present=characters,
        actions_depicted=actions,
        objects_present=objects,
        environment=environment,
        scene_description=description,
        metadata=metadata or {},
    )


# ------------------------------------------------------------------------------
# 1. CASE A: Exact action + subject + object + context -> DIRECT
# ------------------------------------------------------------------------------
def test_01_exact_subject_action_object_context_direct(validator):
    prop = VisualProposition(
        proposition_id="prop_01",
        subject="Neville Longbottom",
        action="drawing_sword",
        object="Sword of Gryffindor",
        context="Courtyard ruins",
        required_temporal_state="DURING",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_neville_sword_01",
        start=10.0,
        end=11.4,
        characters=["Neville Longbottom"],
        actions=["drawing sword", "pulling silver sword"],
        objects=["Sword of Gryffindor", "Sorting Hat"],
        environment="Courtyard ruins",
        description="Neville draws the Sword of Gryffindor from the Sorting Hat in the courtyard.",
        metadata={"action_start": 10.1, "action_peak": 10.7, "action_end": 11.3},
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is True
    assert res.evidence_class == EvidenceClass.DIRECT
    assert res.validated_duration <= 1.50
    assert res.scores.passed_gates is True
    assert res.scores.action_alignment >= 0.75
    assert res.scores.subject_alignment >= 0.70
    assert res.scores.object_alignment >= 0.70


# ------------------------------------------------------------------------------
# 2. CASE B: Subject matches but action is wrong -> REJECT (Action is Primary Veto)
# ------------------------------------------------------------------------------
def test_02_subject_matches_action_wrong_reject(validator):
    # Prompt example: Expected Neville begs Sorting Hat, Observed Neville sits on stool
    prop = VisualProposition(
        proposition_id="prop_02",
        subject="Neville",
        action="begging",
        object="Sorting Hat",
        context="Great Hall",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_neville_sitting_01",
        start=20.0,
        end=21.4,
        characters=["Neville"],
        actions=["sitting on stool"],
        objects=["Sorting Hat", "stool"],
        environment="Great Hall",
        description="Neville sitting silently on the three-legged stool under the Sorting Hat.",
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class in (EvidenceClass.CONTEXT, EvidenceClass.NO_VALID_VISUAL)
    assert EvidenceRejectionReason.ACTION_MISMATCH in res.rejection_reasons
    assert "Action Mismatch" in res.rejection_explanation


# ------------------------------------------------------------------------------
# 3. CASE C: Subject + Object match but action is wrong -> REJECT
# ------------------------------------------------------------------------------
def test_03_subject_object_match_action_wrong_reject(validator):
    # Expected: Harry looks at Mirror of Erised
    # Candidate: Harry walks toward Mirror (walking != looking)
    prop = VisualProposition(
        proposition_id="prop_03",
        subject="Harry Potter",
        action="looking",
        object="Mirror of Erised",
        context="Abandoned Classroom",
    )
    shot = _make_candidate(
        shot_id="shot_harry_walking_01",
        start=50.0,
        end=51.4,
        characters=["Harry Potter"],
        actions=["walking toward mirror"],
        objects=["Mirror of Erised"],
        environment="Abandoned Classroom",
        description="Harry walking quickly across the room toward the Mirror of Erised.",
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class != EvidenceClass.DIRECT
    assert EvidenceRejectionReason.ACTION_MISMATCH in res.rejection_reasons


# ------------------------------------------------------------------------------
# 4. Missing Object -> REJECT (Object absent from candidate footage)
# ------------------------------------------------------------------------------
def test_04_missing_object_reject(validator):
    # Expected: Harry looks at Mirror of Erised
    # Candidate: Harry close-up, but mirror is not in the frame
    prop = VisualProposition(
        proposition_id="prop_04",
        subject="Harry Potter",
        action="looking",
        object="Mirror of Erised",
        context="Abandoned Classroom",
    )
    shot = _make_candidate(
        shot_id="shot_harry_face_only",
        start=60.0,
        end=61.2,
        characters=["Harry Potter"],
        actions=["looking"],
        objects=[],  # Mirror absent!
        environment="Abandoned Classroom",
        description="Tight close-up of Harry's face looking in awe.",
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class != EvidenceClass.DIRECT
    assert EvidenceRejectionReason.OBJECT_MISSING in res.rejection_reasons
    assert "Object Missing" in res.rejection_explanation


# ------------------------------------------------------------------------------
# 5. CASE D: Correct character but wrong scene -> REJECT (CONTEXT_MISMATCH)
# ------------------------------------------------------------------------------
def test_05_correct_character_wrong_scene_reject(validator):
    # Expected: Neville in Great Hall sorting ceremony
    # Candidate: Neville in Gryffindor common room
    prop = VisualProposition(
        proposition_id="prop_05",
        subject="Neville Longbottom",
        action="sitting",
        object="Sorting Hat",
        context="Great Hall",
    )
    shot = _make_candidate(
        shot_id="shot_neville_common_room",
        start=100.0,
        end=101.4,
        characters=["Neville Longbottom"],
        actions=["sitting"],
        objects=["Sorting Hat"],
        environment="Common Room",  # Wrong context!
        description="Neville sitting in an armchair in the Gryffindor common room.",
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class == EvidenceClass.NO_VALID_VISUAL
    assert EvidenceRejectionReason.CONTEXT_MISMATCH in res.rejection_reasons


# ------------------------------------------------------------------------------
# 6. CASE E: Action happens BEFORE selected interval -> REJECT (BEFORE_PHASE_ONLY)
# ------------------------------------------------------------------------------
def test_06_action_happens_before_selected_interval_reject(validator):
    prop = VisualProposition(
        proposition_id="prop_06",
        subject="Harry",
        action="opening",
        object="door",
        context="Corridor",
    )
    # Action opened at 40.0–40.4s, candidate interval is 40.8–42.0s (aftermath)
    shot = _make_candidate(
        shot_id="shot_door_after",
        start=40.8,
        end=42.0,
        characters=["Harry"],
        actions=["walking through"],
        objects=["door"],
        environment="Corridor",
        description="Harry walks through the already open doorway.",
        metadata={"action_start": 40.0, "action_end": 40.4, "action_phase": "AFTER"},
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class != EvidenceClass.DIRECT
    assert EvidenceRejectionReason.AFTER_PHASE_ONLY in res.rejection_reasons


# ------------------------------------------------------------------------------
# 7. CASE F: Action happens AFTER selected interval -> REJECT (BEFORE_PHASE_ONLY)
# ------------------------------------------------------------------------------
def test_07_action_happens_after_selected_interval_reject(validator):
    prop = VisualProposition(
        proposition_id="prop_07",
        subject="Harry",
        action="opening",
        object="door",
        context="Corridor",
    )
    # Action opens at 41.5–42.0s, candidate interval is 40.0–40.8s (approach/setup only)
    shot = _make_candidate(
        shot_id="shot_door_before",
        start=40.0,
        end=40.8,
        characters=["Harry"],
        actions=["approaching door"],
        objects=["door"],
        environment="Corridor",
        description="Harry approaches the closed door with hesitation.",
        metadata={"action_start": 41.5, "action_end": 42.0, "action_phase": "BEFORE"},
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class != EvidenceClass.DIRECT
    assert EvidenceRejectionReason.BEFORE_PHASE_ONLY in res.rejection_reasons


# ------------------------------------------------------------------------------
# 8. Subject-only match -> REJECT (Character presence is never sufficient)
# ------------------------------------------------------------------------------
def test_08_subject_only_match_is_insufficient(validator):
    # Expected: Dumbledore explains the Mirror of Erised
    # Candidate: Dumbledore standing silently
    prop = VisualProposition(
        proposition_id="prop_08",
        subject="Albus Dumbledore",
        action="explaining",
        object="Mirror of Erised",
        context="Classroom",
    )
    shot = _make_candidate(
        shot_id="shot_dumbledore_silent",
        start=120.0,
        end=121.4,
        characters=["Albus Dumbledore"],
        actions=["standing silently"],
        objects=["Mirror of Erised"],
        environment="Classroom",
        description="Dumbledore standing motionless in shadows.",
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class != EvidenceClass.DIRECT
    assert EvidenceRejectionReason.ACTION_MISMATCH in res.rejection_reasons


# ------------------------------------------------------------------------------
# 9. CASE G: Contextual footage -> Classified strictly as CONTEXT, never DIRECT
# ------------------------------------------------------------------------------
def test_09_contextual_footage_classified_as_context(validator):
    # Narration: "In the book, Neville begged the Hat for Hufflepuff."
    # Movie candidate: Neville at Sorting ceremony in Great Hall under Hat, but only sitting
    prop = VisualProposition(
        proposition_id="prop_09",
        subject="Neville Longbottom",
        action="begging",
        object="Sorting Hat",
        context="Great Hall",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_neville_ceremony_context",
        start=25.0,
        end=26.4,
        characters=["Neville Longbottom"],
        actions=["sitting on stool"],
        objects=["Sorting Hat", "stool"],
        environment="Great Hall",
        description="Neville seated on the stool during the Sorting ceremony in the Great Hall.",
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False  # Cannot serve as direct proof
    assert res.evidence_class == EvidenceClass.CONTEXT
    assert "CONTEXTUAL ONLY" in res.rejection_explanation
    assert res.primary_rejection_reason == EvidenceRejectionReason.ACTION_MISMATCH


# ------------------------------------------------------------------------------
# 10. CASE H: No reliable evidence -> NO_VALID_VISUAL
# ------------------------------------------------------------------------------
def test_10_no_reliable_evidence_no_valid_visual(validator):
    prop = VisualProposition(
        proposition_id="prop_10",
        subject="Voldemort",
        action="drinking potion",
        object="cauldron",
        context="Graveyard",
    )
    # Candidate from wrong movie and wrong characters
    shot = _make_candidate(
        shot_id="shot_unrelated",
        start=10.0,
        end=11.0,
        characters=["Ron Weasley"],
        actions=["eating chicken"],
        objects=["plate"],
        environment="Great Hall",
        description="Ron eating chicken drumstick at the feast.",
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class == EvidenceClass.NO_VALID_VISUAL


# ------------------------------------------------------------------------------
# 11. CASE I: Exact action for only 0.8–1.4s -> Accept exact micro-interval
# ------------------------------------------------------------------------------
def test_11_exact_action_micro_interval_extraction():
    # Candidate is 10.0–14.0s (4 seconds)
    # Actual action occurs at 11.2s–12.4s (1.2s duration)
    micro, state, rej, expl = TemporalMicroIntervalExtractor.extract_micro_interval(
        source_start=10.0,
        source_end=14.0,
        action_start=11.2,
        action_peak=11.8,
        action_end=12.4,
        max_duration=1.50,
    )
    assert rej is None
    assert state == TemporalState.DURING
    assert micro[0] == 11.2  # Action onset alignment
    dur = round(micro[1] - micro[0], 2)
    assert 1.15 <= dur <= 1.50
    assert dur <= 1.50


# ------------------------------------------------------------------------------
# 12. CASE J: Candidate is > 1.5s -> Trim to actual evidence interval <= 1.50s
# ------------------------------------------------------------------------------
def test_12_candidate_longer_than_1_5s_trimmed_strictly():
    # Long 5-second candidate shot
    micro, state, rej, expl = TemporalMicroIntervalExtractor.extract_micro_interval(
        source_start=100.0,
        source_end=105.0,
        action_start=101.0,
        action_peak=102.0,
        action_end=104.0,
        max_duration=1.50,
    )
    dur = round(micro[1] - micro[0], 2)
    assert dur <= 1.50
    assert micro[0] >= 100.0
    assert micro[1] <= 105.0


# ------------------------------------------------------------------------------
# 13. Image / non-video media strictly rejected (VIDEO-ONLY policy)
# ------------------------------------------------------------------------------
def test_13_images_strictly_rejected_as_no_valid_visual(validator):
    prop = VisualProposition(
        proposition_id="prop_13",
        subject="Harry",
        action="looking",
        object="None",
        context="Hogwarts",
    )
    image_cand = {
        "candidate_id": "image_promo_01",
        "asset_id": "promo_poster.jpg",
        "media_type": "image",
        "characters_present": ["Harry"],
        "scene_description": "Promotional poster still of Harry.",
    }
    res = validator.validate_candidate(prop, image_cand)
    assert res.is_valid is False
    assert res.evidence_class == EvidenceClass.NO_VALID_VISUAL
    assert EvidenceRejectionReason.IMAGE_NOT_PERMITTED in res.rejection_reasons


# ------------------------------------------------------------------------------
# 14. Human-readable rejection reasons are always recorded
# ------------------------------------------------------------------------------
def test_14_human_readable_rejection_reasons_present(validator):
    prop = VisualProposition(
        proposition_id="prop_14",
        subject="Neville",
        action="slaying",
        object="Nagini",
        context="Courtyard",
    )
    shot = _make_candidate(
        shot_id="shot_mismatch",
        start=10.0,
        end=11.0,
        characters=["Neville"],
        actions=["holding toad"],
        objects=["toad"],
        environment="Courtyard",
        description="Neville holding Trevor the toad.",
    )

    res = validator.validate_candidate(prop, shot)
    assert len(res.rejection_reasons) > 0
    assert res.primary_rejection_reason is not None
    assert len(res.rejection_explanation) > 10
    assert any(r in [
        EvidenceRejectionReason.ACTION_MISMATCH,
        EvidenceRejectionReason.OBJECT_MISSING
    ] for r in res.rejection_reasons)


# ------------------------------------------------------------------------------
# 15. Evidence classification reaches Editorial Planner correctly
# ------------------------------------------------------------------------------
def test_15_evidence_classification_reaches_editorial_planner():
    planner = EditorialPlanner()
    pack = MultiFactTopicPack(
        topic_id="disc_neville_test",
        theme="Hogwarts Sorting Lore",
        suggested_title="Why Neville Begged The Hat",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=26.0,
        hook="Neville's greatest secret was cut from the film.",
        facts=[
            MultiFactPayload(
                fact_id="fact_1",
                theme="Hogwarts Sorting Lore",
                claim="Neville pleaded with the Hat for Hufflepuff.",
                claim_type=FactType.BOOK_VS_MOVIE,
                canon_source="HP Book 1, Chapter 7",
                canon_evidence="Neville begged the Hat for Hufflepuff.",
                fact_number=1,
                visual_propositions=[
                    VisualProposition(
                        proposition_id="prop_test_1",
                        subject="Neville Longbottom",
                        action="begging",
                        object="Sorting Hat",
                        context="Great Hall",
                        evidence_type="DIRECT",
                    )
                ]
            )
        ]
    )

    # Simulate match with CONTEXT classification
    match = BeastV2MatchResult(
        candidate_id="shot_context_01",
        asset_id="shot_context_01.mp4",
        source="MOVIE_ARCHIVE",
        source_start=10.0,
        source_end=11.4,
        evidence_type=EvidenceType.CONTEXTUAL_EVIDENCE,
        evidence_class="CONTEXT",
        decision=BeastV2Decision.ACCEPT_CONTEXT,
        verification_metadata={"evidence_class": "CONTEXT"},
    )

    timeline = planner.plan_timeline(
        topic_pack=pack,
        beast_matches=[match],
        candidate_type="deep_discovery",
    )

    # Unit must reflect CONTEXTUAL_EVIDENCE and not be falsely treated as DIRECT
    unit = next((u for u in timeline.units if u.fact_id == "fact_1"), None)
    assert unit is not None
    assert unit.evidence_type == "CONTEXTUAL_EVIDENCE"
    assert "CONTEXT_NOT_DIRECT" in " ".join(timeline.validation_warnings)
