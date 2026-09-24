"""
STORY FORGE — Temporal Action Validator Test Suite
===================================================
Tests Temporal Action Verification across 15 focused scenarios:
  1. Dynamic action with true transition (drawing sword: emergence -> held) -> DIRECT
  2. Dynamic action with static substitution (already holding sword throughout) -> ACTION_MISMATCH
  3. Dynamic action candidate showing setup phase only -> BEFORE_PHASE_ONLY
  4. Dynamic action candidate showing aftermath phase only -> AFTER_PHASE_ONLY
  5. Rapid physical action with dense sampling (>=8 points) verifying peak impact/motion -> DIRECT
  6. Continuous/static action (looking at mirror) sustained across frames -> DIRECT
  7. Continuous action where gaze/orientation turns away -> rejected
  8. Object state transition verified (door closed -> opening -> open) -> DIRECT
  9. Object state static when transition expected (door already open throughout) -> ACTION_MISMATCH
 10. Subject state transition verified (standing -> lowering -> seated) -> DIRECT
 11. High subject (1.0) + object (1.0) CANNOT compensate for action transition failure -> rejected from DIRECT
 12. Temporal micro-interval tightly bounds action onset/peak/end <= 1.50s starting at action onset
 13. Extensible vocabulary handles multiple verbs (casting spell, throwing, closing door)
 14. Machine-readable evidence trace is populated with frames, transitions, and confidence
 15. End-to-end integration: EvidenceValidationResult output correctly gates Editorial Planner
"""

import pytest
from core.multi_fact_types import VisualProposition
from core.beast_visual_types import BeastCandidateShot
from engines.visual_evidence.evidence_models import (
    EvidenceClass,
    EvidenceRejectionReason,
    TemporalState,
    ActionNature,
    EvidenceValidatorConfig,
)
from engines.visual_evidence.visual_evidence_validator import VisualEvidenceValidator
from engines.visual_evidence.temporal_action_engine import TemporalActionEngine
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
    environment: str = "Courtyard ruins",
    description: str = "",
    metadata: dict = None,
) -> BeastCandidateShot:
    return BeastCandidateShot(
        shot_id=shot_id,
        source_video=f"{shot_id}.mp4",
        movie_number=8,
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
# 1. Dynamic action with true transition (drawing sword: emergence -> held) -> DIRECT
# ------------------------------------------------------------------------------
def test_01_dynamic_action_true_transition_direct(validator):
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
        shot_id="shot_neville_draw_true",
        start=5.0,
        end=6.4,
        characters=["Neville Longbottom"],
        actions=["drawing sword"],
        objects=["Sword of Gryffindor", "Sorting Hat"],
        description="Neville draws the Sword of Gryffindor from the Sorting Hat.",
        metadata={
            "action_start": 5.1,
            "action_peak": 5.7,
            "action_end": 6.3,
        },
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is True
    assert res.evidence_class == EvidenceClass.DIRECT
    assert res.temporal_action_confidence >= 0.85
    assert res.observed_proposition.action_transition_verified is True
    assert len(res.evidence_trace["state_transitions"]) > 0


# ------------------------------------------------------------------------------
# 2. Dynamic action with static substitution (already holding sword) -> ACTION_MISMATCH
# ------------------------------------------------------------------------------
def test_02_dynamic_action_static_substitution_rejected(validator):
    prop = VisualProposition(
        proposition_id="prop_02",
        subject="Neville Longbottom",
        action="drawing_sword",
        object="Sword of Gryffindor",
        context="Courtyard ruins",
        required_temporal_state="DURING",
        evidence_type="DIRECT",
    )
    # Neville is already holding the sword, standing still with no drawing transition
    shot = _make_candidate(
        shot_id="shot_neville_holding_sword",
        start=8.0,
        end=9.5,
        characters=["Neville Longbottom"],
        actions=["holding sword", "standing"],
        objects=["Sword of Gryffindor"],
        description="Neville stands holding the sword already drawn in the courtyard.",
        metadata={
            "object_state": "held",
        },
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.evidence_class in (EvidenceClass.CONTEXT, EvidenceClass.NO_VALID_VISUAL)
    assert res.primary_rejection_reason == EvidenceRejectionReason.ACTION_MISMATCH
    assert "holding_sword" in res.rejection_explanation or "Static Substitution" in res.rejection_explanation


# ------------------------------------------------------------------------------
# 3. Dynamic action candidate showing setup phase only -> BEFORE_PHASE_ONLY
# ------------------------------------------------------------------------------
def test_03_setup_phase_only_rejected(validator):
    prop = VisualProposition(
        proposition_id="prop_03",
        subject="Neville Longbottom",
        action="drawing_sword",
        object="Sword of Gryffindor",
        context="Courtyard ruins",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_neville_setup",
        start=3.0,
        end=4.4,
        characters=["Neville Longbottom"],
        actions=["approaching hat"],
        objects=["Sorting Hat"],
        description="Neville walks up toward the Sorting Hat before touching it.",
        metadata={
            "phase": "BEFORE",
            "action_start": 5.0,
            "action_end": 6.2,
        },
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.primary_rejection_reason == EvidenceRejectionReason.BEFORE_PHASE_ONLY
    assert res.temporal_state == TemporalState.BEFORE


# ------------------------------------------------------------------------------
# 4. Dynamic action candidate showing aftermath phase only -> AFTER_PHASE_ONLY
# ------------------------------------------------------------------------------
def test_04_aftermath_phase_only_rejected(validator):
    prop = VisualProposition(
        proposition_id="prop_04",
        subject="Neville Longbottom",
        action="drawing_sword",
        object="Sword of Gryffindor",
        context="Courtyard ruins",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_neville_aftermath",
        start=7.0,
        end=8.4,
        characters=["Neville Longbottom"],
        actions=["standing victorious"],
        objects=["Sword of Gryffindor"],
        description="Neville after beheading Nagini, holding the sword as Voldemort turns to ash.",
        metadata={
            "phase": "AFTER",
            "action_start": 4.5,
            "action_end": 6.0,
        },
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.primary_rejection_reason == EvidenceRejectionReason.AFTER_PHASE_ONLY
    assert res.temporal_state == TemporalState.AFTER


# ------------------------------------------------------------------------------
# 5. Rapid physical action with dense sampling (>=8 points) -> DIRECT
# ------------------------------------------------------------------------------
def test_05_rapid_physical_action_dense_sampling(validator):
    prop = VisualProposition(
        proposition_id="prop_05",
        subject="Harry Potter",
        action="striking",
        object="Voldemort",
        context="Courtyard",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_harry_strike",
        start=15.0,
        end=16.2,
        characters=["Harry Potter", "Lord Voldemort"],
        actions=["strikes Voldemort"],
        objects=["Elder Wand"],
        environment="Courtyard",
        description="Harry strikes Voldemort across the face as they tumble down the courtyard stairs.",
        metadata={
            "action_start": 15.1,
            "action_peak": 15.6,
            "action_end": 16.1,
        },
    )

    assert TemporalActionEngine.is_rapid_action(prop.action) is True

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is True
    assert res.evidence_class == EvidenceClass.DIRECT
    # Rapid actions must trigger dense sampling (9 points)
    assert len(res.evidence_trace["sampled_frames"]) >= 8
    assert res.temporal_action_confidence >= 0.85
    assert res.temporal_state == TemporalState.PEAK


# ------------------------------------------------------------------------------
# 6. Continuous/static action (looking at mirror) sustained across frames -> DIRECT
# ------------------------------------------------------------------------------
def test_06_continuous_action_sustained_direct(validator):
    prop = VisualProposition(
        proposition_id="prop_06",
        subject="Harry Potter",
        action="looking_at_mirror",
        object="Mirror of Erised",
        context="Abandoned Classroom",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_harry_mirror_sustained",
        start=20.0,
        end=21.4,
        characters=["Harry Potter"],
        actions=["looking at mirror"],
        objects=["Mirror of Erised"],
        environment="Abandoned Classroom",
        description="Harry stares intently into the Mirror of Erised, gazing at his parents' reflection.",
        metadata={
            "action_nature": "CONTINUOUS",
        },
    )

    nature = TemporalActionEngine.classify_action_nature(prop.action)
    assert nature == ActionNature.CONTINUOUS

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is True
    assert res.evidence_class == EvidenceClass.DIRECT
    assert res.temporal_action_confidence >= 0.85
    assert res.observed_proposition.action_nature == "CONTINUOUS"


# ------------------------------------------------------------------------------
# 7. Continuous action where gaze/orientation turns away -> reject
# ------------------------------------------------------------------------------
def test_07_continuous_action_turns_away_rejected(validator):
    prop = VisualProposition(
        proposition_id="prop_07",
        subject="Harry Potter",
        action="looking_at_mirror",
        object="Mirror of Erised",
        context="Abandoned Classroom",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_harry_mirror_turns_away",
        start=22.0,
        end=23.4,
        characters=["Harry Potter"],
        actions=["turns away from mirror"],
        objects=["Mirror of Erised"],
        environment="Abandoned Classroom",
        description="Harry turns away from the Mirror of Erised and walks away toward the exit.",
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.primary_rejection_reason in (EvidenceRejectionReason.ACTION_MISMATCH, EvidenceRejectionReason.DIRECT_EVIDENCE_INSUFFICIENT)
    assert "turns away" in res.rejection_explanation or "broken" in res.rejection_explanation.lower()


# ------------------------------------------------------------------------------
# 8. Object state transition verified (door closed -> opening -> open) -> DIRECT
# ------------------------------------------------------------------------------
def test_08_object_state_transition_verified(validator):
    prop = VisualProposition(
        proposition_id="prop_08",
        subject="Harry Potter",
        action="opening_door",
        object="chamber door",
        context="Dungeons",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_harry_open_door",
        start=30.0,
        end=31.3,
        characters=["Harry Potter"],
        actions=["opens heavy door"],
        objects=["chamber door"],
        environment="Dungeons",
        description="Harry pushes open the heavy chamber door, revealing the dark stairs inside.",
        metadata={
            "action_start": 30.1,
            "action_peak": 30.6,
            "action_end": 31.2,
        },
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is True
    assert res.evidence_class == EvidenceClass.DIRECT
    assert res.temporal_action_confidence >= 0.85
    assert any(t.get("transition_type") == "OPENING" for t in res.evidence_trace["state_transitions"])


# ------------------------------------------------------------------------------
# 9. Object state static when transition expected (door already open) -> reject
# ------------------------------------------------------------------------------
def test_09_object_state_static_when_transition_expected(validator):
    prop = VisualProposition(
        proposition_id="prop_09",
        subject="Harry Potter",
        action="opening_door",
        object="chamber door",
        context="Dungeons",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_harry_door_already_open",
        start=35.0,
        end=36.4,
        characters=["Harry Potter"],
        actions=["walking through doorway"],
        objects=["chamber door"],
        environment="Dungeons",
        description="Harry walks through already open door into the dark room without touching it.",
        metadata={
            "object_state": "open",
        },
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is False
    assert res.primary_rejection_reason == EvidenceRejectionReason.ACTION_MISMATCH
    assert "already open" in res.rejection_explanation


# ------------------------------------------------------------------------------
# 10. Subject state transition verified (standing -> lowering -> seated) -> DIRECT
# ------------------------------------------------------------------------------
def test_10_subject_state_transition_verified(validator):
    prop = VisualProposition(
        proposition_id="prop_10",
        subject="Neville Longbottom",
        action="sitting_down",
        object="stool",
        context="Great Hall",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_neville_sits_down",
        start=40.0,
        end=41.4,
        characters=["Neville Longbottom"],
        actions=["sits down on stool"],
        objects=["stool", "Sorting Hat"],
        environment="Great Hall",
        description="Neville walks up and sits down nervously on the four-legged stool.",
        metadata={
            "action_start": 40.2,
            "action_peak": 40.7,
            "action_end": 41.2,
        },
    )

    res = validator.validate_candidate(prop, shot)
    assert res.is_valid is True
    assert res.evidence_class == EvidenceClass.DIRECT
    assert res.temporal_action_confidence >= 0.85
    assert any(t.get("transition_type") == "POSTURE_CHANGE" for t in res.evidence_trace["state_transitions"])


# ------------------------------------------------------------------------------
# 11. High subject (1.0) + object (1.0) CANNOT compensate for action failure
# ------------------------------------------------------------------------------
def test_11_high_subject_object_cannot_compensate_action_failure(validator):
    prop = VisualProposition(
        proposition_id="prop_11",
        subject="Neville Longbottom",
        action="drawing_sword",
        object="Sword of Gryffindor",
        context="Courtyard ruins",
        evidence_type="DIRECT",
    )
    # Perfect subject (Neville) + perfect object (Sword of Gryffindor) + perfect context (Courtyard)
    # But action transition fails because candidate is static holding
    shot = _make_candidate(
        shot_id="shot_neville_perfect_entities_wrong_action",
        start=50.0,
        end=51.4,
        characters=["Neville Longbottom"],
        actions=["holding sword"],
        objects=["Sword of Gryffindor"],
        environment="Courtyard ruins",
        description="Neville stands holding the sword in the courtyard ruins.",
    )

    res = validator.validate_candidate(prop, shot)
    # Hard gate must trigger: composite cannot qualify as DIRECT
    assert res.is_valid is False
    assert res.evidence_class != EvidenceClass.DIRECT
    assert res.scores.subject_alignment == 1.0
    assert res.scores.object_alignment == 1.0
    assert res.scores.passed_gates is False
    assert res.scores.composite_score <= 0.40


# ------------------------------------------------------------------------------
# 12. Temporal micro-interval tightly bounds action onset/peak/end <= 1.50s
# ------------------------------------------------------------------------------
def test_12_temporal_micro_interval_tightly_bounded():
    # Long source shot (10.0 to 18.0 = 8.0s), with action occurring at 12.3 to 13.5
    interval, state, rejection, explanation = TemporalMicroIntervalExtractor.extract_micro_interval(
        source_start=10.0,
        source_end=18.0,
        action_start=12.3,
        action_peak=12.8,
        action_end=13.5,
        max_duration=1.50,
        min_duration=0.60,
    )
    dur = round(interval[1] - interval[0], 3)
    assert dur <= 1.50
    assert dur >= 0.60
    # Must start at action onset (12.3s) to eliminate visual delay!
    assert interval[0] == 12.3
    assert state == TemporalState.DURING
    assert rejection is None


# ------------------------------------------------------------------------------
# 13. Extensible vocabulary handles multiple verbs (e.g. casting spell, throwing)
# ------------------------------------------------------------------------------
def test_13_extensible_vocabulary_handling(validator):
    verbs = [
        ("casting_spell", "Harry Potter", "Elder Wand", "Casting spell flourish"),
        ("throwing", "Harry Potter", "Snitch", "Harry throwing the golden snitch"),
        ("closing", "Hermione Granger", "grimoire", "Hermione closing the ancient book"),
    ]
    for action, subj, obj, desc in verbs:
        prop = VisualProposition(
            proposition_id=f"prop_{action}",
            subject=subj,
            action=action,
            object=obj,
            context="Great Hall",
            evidence_type="DIRECT",
        )
        shot = _make_candidate(
            shot_id=f"shot_{action}",
            start=60.0,
            end=61.2,
            characters=[subj],
            actions=[action],
            objects=[obj],
            environment="Great Hall",
            description=desc,
            metadata={"action_start": 60.1, "action_peak": 60.5, "action_end": 61.1},
        )
        res = validator.validate_candidate(prop, shot)
        assert res.is_valid is True
        assert res.evidence_class == EvidenceClass.DIRECT
        assert res.temporal_action_confidence >= 0.85


# ------------------------------------------------------------------------------
# 14. Machine-readable evidence trace populated with frames, transitions, confidence
# ------------------------------------------------------------------------------
def test_14_machine_readable_evidence_trace(validator):
    prop = VisualProposition(
        proposition_id="prop_14",
        subject="Neville Longbottom",
        action="drawing_sword",
        object="Sword of Gryffindor",
        context="Courtyard ruins",
        evidence_type="DIRECT",
    )
    shot = _make_candidate(
        shot_id="shot_neville_trace_audit",
        start=70.0,
        end=71.4,
        characters=["Neville Longbottom"],
        actions=["drawing sword"],
        objects=["Sword of Gryffindor"],
        description="Neville draws the Sword of Gryffindor from the Sorting Hat.",
        metadata={"action_start": 70.1, "action_peak": 70.6, "action_end": 71.2},
    )

    res = validator.validate_candidate(prop, shot)
    trace = res.evidence_trace
    assert isinstance(trace, dict)
    assert "action_nature" in trace
    assert "temporal_action_confidence" in trace
    assert "action_transition_verified" in trace
    assert "temporal_state" in trace
    assert "action_window" in trace
    assert "state_transitions" in trace
    assert "sampled_frames" in trace
    assert "gate_status" in trace
    assert trace["action_transition_verified"] is True
    assert len(trace["sampled_frames"]) >= 6


# ------------------------------------------------------------------------------
# 15. End-to-end integration: EvidenceValidationResult output correctly gates Editorial Planner
# ------------------------------------------------------------------------------
def test_15_editorial_planner_gated_by_temporal_action():
    # Construct an editorial proposition with a shot that has action mismatch / static substitution
    prop_dict = {
        "proposition_id": "prop_15",
        "primary_subject": "Neville Longbottom",
        "required_action": "drawing_sword",
        "required_objects": ["Sword of Gryffindor"],
        "required_location": "Courtyard ruins",
        "visual_role": "DIRECT",
        "claim": "Neville draws the sword to defeat Nagini.",
    }
    cand_dict = {
        "candidate_id": "shot_neville_static_for_planner",
        "source_video": "shot_neville_static_for_planner.mp4",
        "start_seconds": 80.0,
        "end_seconds": 81.5,
        "characters_present": ["Neville Longbottom"],
        "actions_depicted": ["holding sword"],
        "objects_present": ["Sword of Gryffindor"],
        "environment": "Courtyard ruins",
        "scene_description": "Neville stands holding the sword already drawn.",
    }

    validator = VisualEvidenceValidator()
    val_res = validator.validate_candidate(prop_dict, cand_dict)
    assert val_res.is_valid is False
    assert val_res.evidence_class == EvidenceClass.CONTEXT

    # Editorial planner evaluates evidence: if a candidate is CONTEXT,
    # the planner assigns CONTEXTUAL_EVIDENCE role and issues validation warning
    from core.multi_fact_types import MultiFactTopicPack, MultiFactPayload, MultiFactFormat, FactType
    from core.beast_v2_types import BeastV2MatchResult, BeastV2Decision, EvidenceType

    planner = EditorialPlanner()
    pack = MultiFactTopicPack(
        topic_id="disc_neville_action_test",
        theme="Neville Sword Lore",
        suggested_title="How Neville Drew The Sword",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=26.0,
        hook="Neville drew Gryffindor's sword to kill Nagini.",
        facts=[
            MultiFactPayload(
                fact_id="fact_1",
                theme="Neville Sword Lore",
                claim="Neville draws the Sword of Gryffindor from the Hat.",
                claim_type=FactType.BOOK_VS_MOVIE,
                canon_source="HP Book 7, Chapter 36",
                canon_evidence="With a single stroke Neville slashed off Nagini's head.",
                fact_number=1,
                visual_propositions=[
                    VisualProposition(
                        proposition_id="prop_15",
                        subject="Neville Longbottom",
                        action="drawing_sword",
                        object="Sword of Gryffindor",
                        context="Courtyard ruins",
                        evidence_type="DIRECT",
                    )
                ]
            )
        ]
    )

    match = BeastV2MatchResult(
        candidate_id="shot_neville_static_for_planner",
        asset_id="shot_neville_static_for_planner.mp4",
        source="MOVIE_ARCHIVE",
        source_start=80.0,
        source_end=81.5,
        evidence_type=EvidenceType.CONTEXTUAL_EVIDENCE,
        evidence_class=val_res.evidence_class.value,
        decision=BeastV2Decision.ACCEPT_CONTEXT,
        verification_metadata={"evidence_class": val_res.evidence_class.value},
    )

    timeline = planner.plan_timeline(
        topic_pack=pack,
        beast_matches=[match],
        candidate_type="deep_discovery",
    )

    unit = next((u for u in timeline.units if u.fact_id == "fact_1"), None)
    assert unit is not None
    assert unit.evidence_type == "CONTEXTUAL_EVIDENCE"
    assert "CONTEXT_NOT_DIRECT" in " ".join(timeline.validation_warnings)
