"""
STORY FORGE — Phase 3 Physical Action & Temporal Evidence Test Suite
=====================================================================
Covers 27 focused validation areas:
  1. action schema
  2. action evidence policy
  3. motion calculation
  4. local optical flow
  5. pose integration
  6. relationship geometry
  7. contact detection
  8. state transition
  9. temporal order
  10. causal graph
  11. punch positive
  12. punch negative
  13. handover positive
  14. handover negative
  15. throw positive
  16. throw negative
  17. break/snap positive
  18. break/snap negative
  19. wrong actor
  20. wrong target
  21. wrong action
  22. wrong temporal order
  23. camera-motion false positive
  24. multi-shot false positive
  25. action-model disagreement
  26. fail-closed behavior
  27. lineage invalidation
"""

import pytest
import numpy as np
import cv2
from py_visual_evidence.schema import BoundingBox

from engines.action.models import (
    PhysicalActionType,
    ActionEvidenceVerdict,
    ActionFailureReason,
    GeometricRelation,
    VisualActionAssertion,
    Keypoint,
    PoseKeypoints,
    TemporalEvent,
    ActionVerificationResult,
)
from engines.action.taxonomy import get_action_policy, ACTION_POLICIES
from engines.action.geometry import SpatialGeometryEngine
from engines.action.motion_analyzer import LocalMotionAnalyzer
from engines.action.pose_kinematics import PoseKinematicsAnalyzer
from engines.action.hoi_engine import HOIEngine
from engines.action.temporal_state import TemporalStateMachine, TemporalStateObservation
from engines.action.causal_graph import TemporalCausalVerifier
from engines.action.shot_boundary import ShotBoundaryAnalyzer
from engines.action.action_model_adapter import ActionModelAdapter
from engines.action.verifier import ActionEvidenceVerifier

from engines.perception.models import (
    EntityTimeline,
    EntityTrack,
    IdentityMatchStatus,
    VisualObject,
    CharacterIdentity,
)
from engines.perception.character_bank import CharacterBank


# Helper fixture for mock character bank
@pytest.fixture
def mock_bank():
    bank = CharacterBank()
    bank.register_character(CharacterIdentity(
        character_id="char_hermione",
        canonical_name="Hermione Granger",
        aliases=["Hermione", "Granger"],
    ))
    bank.register_character(CharacterIdentity(
        character_id="char_draco",
        canonical_name="Draco Malfoy",
        aliases=["Draco", "Malfoy"],
    ))
    bank.register_character(CharacterIdentity(
        character_id="char_harry",
        canonical_name="Harry Potter",
        aliases=["Harry", "Potter"],
    ))
    bank.register_character(CharacterIdentity(
        character_id="char_ollivander",
        canonical_name="Garrick Ollivander",
        aliases=["Ollivander"],
    ))
    return bank


# 1. Action schema test
def test_01_action_schema():
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "test_punch_01",
        "actor": "Hermione Granger",
        "action": "PUNCH",
        "target": "Draco Malfoy",
        "temporal_order": ["approach", "contact", "reaction"],
    })
    assert assertion.action == PhysicalActionType.PUNCH
    assert assertion.actor == "Hermione Granger"
    assert assertion.target == "Draco Malfoy"
    assert "Hermione Granger" in assertion.required_entities
    assert "Draco Malfoy" in assertion.required_entities


# 2. Action evidence policy test
def test_02_action_evidence_policy():
    punch_policy = get_action_policy(PhysicalActionType.PUNCH)
    assert punch_policy.requires_actor is True
    assert punch_policy.requires_target is True
    assert punch_policy.requires_contact is True
    assert punch_policy.requires_motion is True
    assert punch_policy.expected_event_sequence == ["approach", "contact", "reaction"]

    snap_policy = get_action_policy(PhysicalActionType.SNAP)
    assert snap_policy.requires_object is True
    assert snap_policy.requires_state_transition is True


# 3. Motion calculation test
def test_03_motion_calculation():
    analyzer = LocalMotionAnalyzer()
    track = EntityTrack(track_id=1, character_name="Harry Potter", class_label="person")
    # Entity moving horizontally at 0.5 units/sec
    track.history = [
        (0, BoundingBox(x=0.1, y=0.4, w=0.2, h=0.4)),
        (5, BoundingBox(x=0.2, y=0.4, w=0.2, h=0.4)),
        (10, BoundingBox(x=0.3, y=0.4, w=0.2, h=0.4)),
    ]
    timestamps = [0.0, 0.2, 0.4]
    profile = analyzer.analyze_track_motion(track, timestamps=timestamps, fps=25.0)
    assert profile.peak_speed > 0.40
    assert profile.net_displacement >= 0.19


# 4. Local optical flow test
def test_04_local_optical_flow():
    analyzer = LocalMotionAnalyzer()
    # Create synthetic moving frames
    f1 = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(f1, (20, 20), (40, 40), (255, 255, 255), -1)
    f2 = np.zeros((100, 100, 3), dtype=np.uint8)
    cv2.rectangle(f2, (30, 20), (50, 40), (255, 255, 255), -1)

    bboxes = [
        BoundingBox(x=0.1, y=0.1, w=0.5, h=0.5),
        BoundingBox(x=0.2, y=0.1, w=0.5, h=0.5),
    ]
    energies = analyzer.compute_roi_optical_flow([f1, f2], [0, 1], bboxes)
    assert len(energies) == 2
    assert energies[1] > 0.0


# 5. Pose integration test
def test_05_pose_integration():
    analyzer = PoseKinematicsAnalyzer()
    # Create arm extending outward
    pose1 = PoseKeypoints(
        frame_index=0, timestamp_sec=0.0, track_id=1, character_name="Hermione",
        right_shoulder=Keypoint(x=0.3, y=0.4, confidence=0.9),
        right_elbow=Keypoint(x=0.35, y=0.45, confidence=0.9),
        right_wrist=Keypoint(x=0.36, y=0.42, confidence=0.9),
    )
    pose2 = PoseKeypoints(
        frame_index=5, timestamp_sec=0.2, track_id=1, character_name="Hermione",
        right_shoulder=Keypoint(x=0.3, y=0.4, confidence=0.9),
        right_elbow=Keypoint(x=0.45, y=0.42, confidence=0.9),
        right_wrist=Keypoint(x=0.60, y=0.40, confidence=0.9),
    )
    target_centroids = [(0.65, 0.40), (0.65, 0.40)]
    kinematics = analyzer.derive_arm_kinematics([pose1, pose2], target_centroids=target_centroids, side="right")
    assert len(kinematics) == 2
    assert kinematics[1].velocity_toward_target > 0.50
    assert kinematics[1].extension_angle_deg > 140.0


# 6. Relationship geometry test
def test_06_relationship_geometry():
    geom = SpatialGeometryEngine()
    box_a = BoundingBox(x=0.2, y=0.3, w=0.15, h=0.3)
    box_b = BoundingBox(x=0.5, y=0.3, w=0.15, h=0.3)
    # Distance between boxes
    d = geom.bounding_box_distance(box_a, box_b)
    assert round(d, 2) == 0.15

    rels = geom.evaluate_static_relations(box_a, box_b, "Hermione", "Draco", 0.0, 0)
    rel_types = [r.relation for r in rels]
    assert GeometricRelation.LEFT_OF in rel_types
    assert GeometricRelation.NEAR in rel_types


# 7. Contact detection test
def test_07_contact_detection():
    geom = SpatialGeometryEngine()
    # Overlapping boxes
    box_a = BoundingBox(x=0.3, y=0.3, w=0.2, h=0.3)
    box_b = BoundingBox(x=0.4, y=0.3, w=0.2, h=0.3)
    rels = geom.evaluate_static_relations(box_a, box_b, "Actor", "Target", 0.5, 12)
    assert any(r.relation == GeometricRelation.TOUCHING for r in rels)
    assert any(r.relation == GeometricRelation.OVERLAPPING for r in rels)


# 8. State transition test
def test_08_state_transition():
    obs = [
        TemporalStateObservation(timestamp_sec=0.1, frame_index=2, state_name="INTACT"),
        TemporalStateObservation(timestamp_sec=0.5, frame_index=12, state_name="BROKEN"),
    ]
    res = TemporalStateMachine.verify_state_transition(obs, ["INTACT", "BROKEN"])
    assert res["verified"] is True
    assert res["matched_sequence"] == ["INTACT", "BROKEN"]


# 9. Temporal order test
def test_09_temporal_order():
    obs = [
        TemporalStateObservation(timestamp_sec=0.5, frame_index=12, state_name="INTACT"),
        TemporalStateObservation(timestamp_sec=0.1, frame_index=2, state_name="BROKEN"),
    ]
    # Inverted order: was broken first!
    res = TemporalStateMachine.verify_state_transition(obs, ["INTACT", "BROKEN"])
    assert res["verified"] is False
    assert res["failure_reason"] == ActionFailureReason.STATE_TRANSITION_NOT_CONFIRMED


# 10. Causal graph test
def test_10_causal_graph():
    events = [
        TemporalEvent(event_id="e1", name="approach", timestamp_sec=1.0, frame_index=24, confidence=0.9),
        TemporalEvent(event_id="e2", name="contact", timestamp_sec=1.2, frame_index=28, confidence=0.95),
        TemporalEvent(event_id="e3", name="reaction", timestamp_sec=1.5, frame_index=36, confidence=0.85),
    ]
    graph = TemporalCausalVerifier.build_and_verify_graph(events, ["approach", "contact", "reaction"])
    assert graph.is_valid is True
    assert len(graph.edges) == 2


# 11. Punch positive test
def test_11_punch_positive(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_hermione = EntityTrack(
        track_id=1, character_name="Hermione Granger", class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
    )
    t_hermione.history = [
        (0, BoundingBox(x=0.2, y=0.3, w=0.15, h=0.4)),  # approaching
        (5, BoundingBox(x=0.35, y=0.3, w=0.15, h=0.4)), # contact
        (10, BoundingBox(x=0.30, y=0.3, w=0.15, h=0.4)),# recover
    ]
    t_draco = EntityTrack(
        track_id=2, character_name="Draco Malfoy", class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
    )
    t_draco.history = [
        (0, BoundingBox(x=0.55, y=0.3, w=0.15, h=0.4)),
        (5, BoundingBox(x=0.48, y=0.3, w=0.15, h=0.4)), # contact
        (10, BoundingBox(x=0.65, y=0.3, w=0.15, h=0.4)),# displacement/reaction
    ]
    timestamps = [0.0, 0.2, 0.4]

    timeline = EntityTimeline(
        source_video="test.mp4", start_sec=0.0, end_sec=0.4,
        tracks=[t_hermione, t_draco],
    )
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "punch_pos_01",
        "actor": "Hermione Granger",
        "action": "PUNCH",
        "target": "Draco Malfoy",
        "temporal_order": ["approach", "contact", "reaction"],
    })

    res = verifier.verify_action(assertion, timeline, timestamps=timestamps, fps=25.0)
    assert res.is_verified is True
    assert res.verdict == ActionEvidenceVerdict.VERIFIED


# 12. Punch negative test (no contact / near miss)
def test_12_punch_negative_no_contact(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_hermione = EntityTrack(
        track_id=1, character_name="Hermione Granger", class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
    )
    t_hermione.history = [
        (0, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4)),
        (5, BoundingBox(x=0.15, y=0.3, w=0.15, h=0.4)),
    ]
    t_draco = EntityTrack(
        track_id=2, character_name="Draco Malfoy", class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
    )
    t_draco.history = [
        (0, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4)),
        (5, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4)),
    ]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.2, tracks=[t_hermione, t_draco])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "punch_neg_01",
        "actor": "Hermione Granger",
        "action": "PUNCH",
        "target": "Draco Malfoy",
    })
    res = verifier.verify_action(assertion, timeline, timestamps=[0.0, 0.2], fps=25.0)
    assert res.is_verified is False
    assert ActionFailureReason.CONTACT_NOT_CONFIRMED in res.failure_reasons


# 13. Handover positive test
def test_13_handover_positive(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_src = EntityTrack(track_id=1, character_name="Garrick Ollivander", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_rec = EntityTrack(track_id=2, character_name="Harry Potter", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_obj = EntityTrack(track_id=3, character_name="wand", class_label="prop")

    # Wand starts near Ollivander (0.1), moves across (0.3), settles near Harry (0.5)
    t_src.history = [(f, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4)) for f in range(9)]
    t_rec.history = [(f, BoundingBox(x=0.55, y=0.3, w=0.15, h=0.4)) for f in range(9)]
    t_obj.history = [
        (0, BoundingBox(x=0.15, y=0.4, w=0.05, h=0.05)),
        (1, BoundingBox(x=0.15, y=0.4, w=0.05, h=0.05)),
        (2, BoundingBox(x=0.16, y=0.4, w=0.05, h=0.05)),
        (3, BoundingBox(x=0.25, y=0.4, w=0.05, h=0.05)), # transit
        (4, BoundingBox(x=0.35, y=0.4, w=0.05, h=0.05)), # transit
        (5, BoundingBox(x=0.45, y=0.4, w=0.05, h=0.05)), # transit
        (6, BoundingBox(x=0.52, y=0.4, w=0.05, h=0.05)),
        (7, BoundingBox(x=0.53, y=0.4, w=0.05, h=0.05)),
        (8, BoundingBox(x=0.53, y=0.4, w=0.05, h=0.05)),
    ]
    timestamps = [f * 0.1 for f in range(9)]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.8, tracks=[t_src, t_rec, t_obj])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "handover_pos_01",
        "actor": "Garrick Ollivander",
        "action": "HANDOVER",
        "target": "Harry Potter",
        "object": "wand",
    })
    res = verifier.verify_action(assertion, timeline, timestamps=timestamps, fps=10.0)
    assert res.is_verified is True
    assert res.verdict == ActionEvidenceVerdict.VERIFIED


# 14. Handover negative test (two people standing near object on a table)
def test_14_handover_negative_static_proximity(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_src = EntityTrack(track_id=1, character_name="Garrick Ollivander", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_rec = EntityTrack(track_id=2, character_name="Harry Potter", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_obj = EntityTrack(track_id=3, character_name="wand", class_label="prop")

    # Static wand resting on table in middle
    t_src.history = [(f, BoundingBox(x=0.2, y=0.3, w=0.15, h=0.4)) for f in range(9)]
    t_rec.history = [(f, BoundingBox(x=0.5, y=0.3, w=0.15, h=0.4)) for f in range(9)]
    t_obj.history = [(f, BoundingBox(x=0.35, y=0.5, w=0.05, h=0.05)) for f in range(9)]

    timestamps = [f * 0.1 for f in range(9)]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.8, tracks=[t_src, t_rec, t_obj])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "handover_neg_01",
        "actor": "Garrick Ollivander",
        "action": "HANDOVER",
        "target": "Harry Potter",
        "object": "wand",
    })
    res = verifier.verify_action(assertion, timeline, timestamps=timestamps, fps=10.0)
    assert res.is_verified is False
    assert ActionFailureReason.INTERACTION_NOT_CONFIRMED in res.failure_reasons


# 15. Throw positive test
def test_15_throw_positive(mock_bank):
    hoi = HOIEngine()
    t_actor = EntityTrack(track_id=1, character_name="Harry Potter", class_label="person")
    t_actor.history = [(f, BoundingBox(x=0.2, y=0.3, w=0.15, h=0.4)) for f in range(6)]
    # Object starts at actor, separates rapidly
    t_obj = EntityTrack(track_id=2, character_name="ball", class_label="prop")
    t_obj.history = [
        (0, BoundingBox(x=0.25, y=0.35, w=0.05, h=0.05)),
        (1, BoundingBox(x=0.26, y=0.35, w=0.05, h=0.05)),
        (2, BoundingBox(x=0.40, y=0.30, w=0.05, h=0.05)),
        (3, BoundingBox(x=0.55, y=0.25, w=0.05, h=0.05)),
        (4, BoundingBox(x=0.70, y=0.20, w=0.05, h=0.05)),
        (5, BoundingBox(x=0.85, y=0.18, w=0.05, h=0.05)),
    ]
    # Check initial possession vs separation
    geom = SpatialGeometryEngine()
    d_start = geom.bounding_box_distance(t_actor.history[0][1], t_obj.history[0][1])
    d_end = geom.bounding_box_distance(t_actor.history[-1][1], t_obj.history[-1][1])
    assert d_start < 0.05
    assert d_end > 0.50


# 16. Throw negative test (held entire time)
def test_16_throw_negative_held_entire_time(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_actor = EntityTrack(track_id=1, character_name="Harry Potter", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_obj = EntityTrack(track_id=2, character_name="wand", class_label="prop")
    # Wand stays held inside Harry's bounding box
    t_actor.history = [(f, BoundingBox(x=0.2, y=0.3, w=0.15, h=0.4)) for f in range(6)]
    t_obj.history = [(f, BoundingBox(x=0.25, y=0.35, w=0.05, h=0.05)) for f in range(6)]

    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.5, tracks=[t_actor, t_obj])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "throw_neg_01",
        "actor": "Harry Potter",
        "action": "THROW",
        "object": "wand",
        "temporal_order": ["held", "release", "moving_away"],
    })
    res = verifier.verify_action(assertion, timeline, timestamps=[f * 0.1 for f in range(6)], fps=10.0)
    assert res.is_verified is False


# 17. Break/snap positive test
def test_17_break_snap_positive(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_actor = EntityTrack(track_id=1, character_name="Harry Potter", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_actor.history = [
        (0, BoundingBox(x=0.3, y=0.3, w=0.2, h=0.4)),
        (10, BoundingBox(x=0.38, y=0.3, w=0.2, h=0.4)),
    ]
    t_obj = EntityTrack(track_id=2, character_name="Elder Wand", class_label="prop")
    t_obj.history = [
        (0, BoundingBox(x=0.35, y=0.4, w=0.1, h=0.05)),
        (10, BoundingBox(x=0.35, y=0.4, w=0.1, h=0.05)),
    ]
    obj_dets = [
        VisualObject(object_id="obj_1", label="Elder Wand", confidence=0.9, state="INTACT", timestamp=0.1, bbox=BoundingBox(x=0.35, y=0.4, w=0.1, h=0.05)),
        VisualObject(object_id="obj_1", label="Elder Wand", confidence=0.9, state="BROKEN", timestamp=0.8, bbox=BoundingBox(x=0.35, y=0.4, w=0.1, h=0.05)),
    ]
    timeline = EntityTimeline(
        source_video="test.mp4", start_sec=0.0, end_sec=1.0,
        tracks=[t_actor, t_obj], object_detections=obj_dets,
    )
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "snap_pos_01",
        "actor": "Harry Potter",
        "action": "SNAP",
        "object": "Elder Wand",
        "expected_state_transition": ("INTACT", "BROKEN"),
    })
    res = verifier.verify_action(assertion, timeline, timestamps=[0.0, 0.4], fps=10.0)
    assert res.is_verified is True
    assert res.verdict == ActionEvidenceVerdict.VERIFIED


# 18. Break/snap negative test (already broken at start)
def test_18_break_snap_negative_already_broken(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_actor = EntityTrack(track_id=1, character_name="Harry Potter", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_actor.history = [(0, BoundingBox(x=0.3, y=0.3, w=0.2, h=0.4))]
    t_obj = EntityTrack(track_id=2, character_name="Elder Wand", class_label="prop")
    t_obj.history = [(0, BoundingBox(x=0.35, y=0.4, w=0.1, h=0.05))]
    # Already broken at t=0.1!
    obj_dets = [
        VisualObject(object_id="obj_1", label="Elder Wand", confidence=0.9, state="BROKEN", timestamp=0.1, bbox=BoundingBox(x=0.35, y=0.4, w=0.1, h=0.05)),
        VisualObject(object_id="obj_1", label="Elder Wand", confidence=0.9, state="BROKEN", timestamp=0.8, bbox=BoundingBox(x=0.35, y=0.4, w=0.1, h=0.05)),
    ]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=1.0, tracks=[t_actor, t_obj], object_detections=obj_dets)
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "snap_neg_01",
        "actor": "Harry Potter",
        "action": "SNAP",
        "object": "Elder Wand",
        "expected_state_transition": ("INTACT", "BROKEN"),
    })
    res = verifier.verify_action(assertion, timeline, timestamps=[0.1, 0.8], fps=10.0)
    assert res.is_verified is False
    assert ActionFailureReason.STATE_TRANSITION_NOT_CONFIRMED in res.failure_reasons


# 19. Wrong actor test
def test_19_wrong_actor(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    # Neville is in the track, but assertion claims Hermione
    t_actor = EntityTrack(track_id=1, character_name="Neville Longbottom", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_actor.history = [(0, BoundingBox(x=0.2, y=0.3, w=0.2, h=0.4))]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.5, tracks=[t_actor])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "wrong_actor_01",
        "actor": "Hermione Granger",
        "action": "PUNCH",
        "target": "Draco Malfoy",
    })
    res = verifier.verify_action(assertion, timeline)
    assert res.is_verified is False
    assert ActionFailureReason.ACTOR_NOT_CONFIRMED in res.failure_reasons


# 20. Wrong target test
def test_20_wrong_target(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_hermione = EntityTrack(track_id=1, character_name="Hermione Granger", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_ron = EntityTrack(track_id=2, character_name="Ron Weasley", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_hermione.history = [(0, BoundingBox(x=0.2, y=0.3, w=0.2, h=0.4))]
    t_ron.history = [(0, BoundingBox(x=0.5, y=0.3, w=0.2, h=0.4))]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.5, tracks=[t_hermione, t_ron])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "wrong_target_01",
        "actor": "Hermione Granger",
        "action": "PUNCH",
        "target": "Draco Malfoy",  # Draco is not in the scene
    })
    res = verifier.verify_action(assertion, timeline)
    assert res.is_verified is False
    assert ActionFailureReason.TARGET_NOT_CONFIRMED in res.failure_reasons


# 21. Wrong action test
def test_21_wrong_action(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_actor = EntityTrack(track_id=1, character_name="Harry Potter", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    # Slow walking motion (peak speed 0.15)
    t_actor.history = [
        (0, BoundingBox(x=0.1, y=0.4, w=0.2, h=0.4)),
        (10, BoundingBox(x=0.15, y=0.4, w=0.2, h=0.4)),
    ]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=1.0, tracks=[t_actor])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "wrong_act_01",
        "actor": "Harry Potter",
        "action": "RUN",  # Policy requires min_peak_velocity 0.40
    })
    res = verifier.verify_action(assertion, timeline, timestamps=[0.0, 1.0], fps=10.0)
    assert res.is_verified is False
    assert ActionFailureReason.INSUFFICIENT_MOTION in res.failure_reasons


# 22. Wrong temporal order test
def test_22_wrong_temporal_order():
    # Reaction before contact
    events = [
        TemporalEvent(event_id="e1", name="reaction", timestamp_sec=0.2, frame_index=4, confidence=0.9),
        TemporalEvent(event_id="e2", name="contact", timestamp_sec=0.8, frame_index=16, confidence=0.9),
    ]
    graph = TemporalCausalVerifier.build_and_verify_graph(events, ["contact", "reaction"])
    assert graph.is_valid is False
    assert "CAUSAL_INVERSION_DETECTED" in graph.violation_reason


# 23. Camera-motion false positive test
def test_23_camera_motion_false_positive():
    analyzer = LocalMotionAnalyzer()
    track = EntityTrack(track_id=1, character_name="Harry Potter", class_label="person")
    track.history = [
        (0, BoundingBox(x=0.2, y=0.4, w=0.2, h=0.4)),
        (1, BoundingBox(x=0.3, y=0.4, w=0.2, h=0.4)),
    ]
    # Synthetic frames simulating camera pan right by 192 pixels (0.1 normalized)
    f1 = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cv2.circle(f1, (500, 500), 20, (255, 255, 255), -1)
    cv2.circle(f1, (1000, 500), 20, (255, 255, 255), -1)
    f2 = np.zeros((1080, 1920, 3), dtype=np.uint8)
    cv2.circle(f2, (692, 500), 20, (255, 255, 255), -1)
    cv2.circle(f2, (1192, 500), 20, (255, 255, 255), -1)

    profile = analyzer.analyze_track_motion(track, frames=[f1, f2], timestamps=[0.0, 0.1], fps=10.0)
    # True compensated motion should be near 0 because the camera shifted by the exact same amount
    assert profile.compensated_centroids[1][0] < 0.25


# 24. Multi-shot false positive test (contact coincides with hard cut)
def test_24_multi_shot_cut_false_positive():
    shot_analyzer = ShotBoundaryAnalyzer()
    cuts = [type("MockCut", (), {"timestamp_sec": 1.5, "frame_index": 36})()]
    res = shot_analyzer.verify_action_across_cuts(
        cuts=cuts,
        action_interval=(1.0, 2.0),
        has_direct_requirement=True,
        contact_timestamp=1.52,  # Contact happened inside the cut!
    )
    assert res["continuous"] is False
    assert res["failure_reason"] == ActionFailureReason.ACTION_NOT_VERIFIED_ACROSS_CUT


# 25. Action-model disagreement test (high model score does NOT override missing contact)
def test_25_action_model_disagreement(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_hermione = EntityTrack(track_id=1, character_name="Hermione Granger", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_draco = EntityTrack(track_id=2, character_name="Draco Malfoy", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    # Characters are far apart: distance 0.6
    t_hermione.history = [(0, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4))]
    t_draco.history = [(0, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4))]

    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.5, tracks=[t_hermione, t_draco])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "disagreement_01",
        "actor": "Hermione Granger",
        "action": "PUNCH",
        "target": "Draco Malfoy",
    })
    # Action classifier falsely gives 0.99 confidence to "PUNCH"
    precomputed = {"punch": 0.99}
    res = verifier.verify_action(assertion, timeline, precomputed_action_scores=precomputed)
    assert res.is_verified is False
    assert ActionFailureReason.CONTACT_NOT_CONFIRMED in res.failure_reasons


# 26. Fail-closed behavior test (unknown identity fails closed)
def test_26_fail_closed_unknown_identity(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    # Person is UNKNOWN
    t_unknown = EntityTrack(track_id=1, character_name="Hermione Granger", class_label="person", identity_status=IdentityMatchStatus.UNKNOWN)
    t_unknown.history = [(0, BoundingBox(x=0.2, y=0.3, w=0.2, h=0.4))]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.5, tracks=[t_unknown])
    assertion = VisualActionAssertion.from_dict({
        "assertion_id": "fail_closed_01",
        "actor": "Hermione Granger",
        "action": "RAISE",
    })
    res = verifier.verify_action(assertion, timeline)
    assert res.is_verified is False
    assert ActionFailureReason.ACTOR_NOT_CONFIRMED in res.failure_reasons


# 27. Lineage invalidation test (tampering with assertion changes lineage hash)
def test_27_lineage_invalidation(mock_bank):
    verifier = ActionEvidenceVerifier(character_bank=mock_bank)
    t_hermione = EntityTrack(track_id=1, character_name="Hermione Granger", class_label="person", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_hermione.history = [(0, BoundingBox(x=0.2, y=0.3, w=0.2, h=0.4))]
    timeline = EntityTimeline(source_video="test.mp4", start_sec=0.0, end_sec=0.5, tracks=[t_hermione])

    ass1 = VisualActionAssertion.from_dict({"assertion_id": "a1", "actor": "Hermione Granger", "action": "RAISE"})
    ass2 = VisualActionAssertion.from_dict({"assertion_id": "a1", "actor": "Hermione Granger", "action": "LOWER"})

    res1 = verifier.verify_action(ass1, timeline)
    res2 = verifier.verify_action(ass2, timeline)

    assert res1.lineage_hash != res2.lineage_hash
    assert len(res1.lineage_hash) == 64
