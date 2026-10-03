"""
STORY FORGE — Micro-Beat Visual Alignment Focused Test Suite
============================================================
FOCUSED TESTS ONLY (Part 13: Tests 1 through 7):
  1. Harry + broom required, Harry only visible -> REJECT
  2. Harry + broom both visible -> ACCEPT
  3. Ron hit claim, Ron before impact -> REJECT
  4. Ron hit claim, actual impact -> ACCEPT
  5. Hermione + Malfoy + punch, no punch -> REJECT
  6. Hermione + Malfoy + actual punch -> ACCEPT
  7. Two propositions in one sentence -> split into two independently verified micro-beats
"""

import pytest
from py_visual_evidence.schema import BoundingBox

from engines.retrieval.models import RetrievalCandidate
from engines.perception.models import (
    EntityTimeline,
    EntityTrack,
    IdentityMatchStatus,
    VisualObject,
)
from engines.action.models import (
    PhysicalActionType,
    VisualActionAssertion,
    ActionEvidenceVerdict,
    ActionFailureReason,
)
from engines.edl.models import (
    VisualBeat,
    CoverageRequirement,
    WordTimestamp,
    SentenceBoundary,
    LockedNarrationInput,
)
from engines.edl.candidate_evaluator import CandidateEvidenceEvaluator
from engines.edl.beat_compiler import VisualBeatCompiler


# ------------------------------------------------------------------------------
# TEST 1: Harry + broom required, Harry only visible -> REJECT
# ------------------------------------------------------------------------------
def test_01_harry_broom_harry_only_rejected():
    evaluator = CandidateEvidenceEvaluator()
    beat = VisualBeat(
        beat_id="beat_01",
        narration_start=0.0,
        narration_end=3.0,
        text_span="Harry summoned the broomstick",
        visual_assertion="Harry summoned the broomstick",
        required_entities=["Harry Potter"],
        required_objects=["broomstick"],
        coverage_requirement=CoverageRequirement.DIRECT,
    )
    # Candidate track contains only Harry Potter (no broomstick)
    t_harry = EntityTrack(
        track_id=1,
        character_name="Harry Potter",
        class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[(0, BoundingBox(x=0.45, y=0.2, w=0.08, h=0.6))],
    )
    timeline = EntityTimeline(
        source_video="m1_flying.mp4",
        start_sec=10.0,
        end_sec=13.0,
        tracks=[t_harry],
        object_detections=[],
    )
    cand = RetrievalCandidate(
        candidate_id="cand_harry_only",
        movie_id="hp1",
        start=10.0,
        end=13.0,
        source="L2_MOVIE_EVENT",
        retrieval_score=0.90,
        metadata={
            "source_video": "m1_flying.mp4",
            "location": "quidditch pitch",
            "movie_event_id": "quidditch_match",
        },
    )

    eval_res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert eval_res.is_rejected is True
    assert "NO_REQUIRED_OBJECT" in eval_res.rejection_reason or "OBJECT_MISMATCH" in eval_res.rejection_reason


# ------------------------------------------------------------------------------
# TEST 2: Harry + broom both visible -> ACCEPT
# ------------------------------------------------------------------------------
def test_02_harry_broom_both_visible_accepted():
    evaluator = CandidateEvidenceEvaluator()
    beat = VisualBeat(
        beat_id="beat_02",
        narration_start=0.0,
        narration_end=3.0,
        text_span="Harry summoned the broomstick into his hand",
        visual_assertion="Harry summoned the broomstick into his hand",
        required_entities=["Harry Potter"],
        required_objects=["broomstick"],
        coverage_requirement=CoverageRequirement.DIRECT,
    )
    t_harry = EntityTrack(
        track_id=1,
        character_name="Harry Potter",
        class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[(0, BoundingBox(x=0.45, y=0.2, w=0.08, h=0.6))],
    )
    t_broom = EntityTrack(
        track_id=2,
        character_name="broomstick",
        class_label="object",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[(0, BoundingBox(x=0.52, y=0.3, w=0.05, h=0.3))],
    )
    timeline = EntityTimeline(
        source_video="m1_flying.mp4",
        start_sec=10.0,
        end_sec=13.0,
        tracks=[t_harry, t_broom],
    )
    cand = RetrievalCandidate(
        candidate_id="cand_harry_and_broom",
        movie_id="hp1",
        start=10.0,
        end=13.0,
        source="L2_MOVIE_EVENT",
        retrieval_score=0.92,
        metadata={
            "source_video": "m1_flying.mp4",
            "location": "quidditch pitch",
            "movie_event_id": "quidditch_match",
        },
    )

    eval_res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert eval_res.is_rejected is False
    assert eval_res.is_perception_verified is True
    assert "Harry Potter" in eval_res.verified_entities


# ------------------------------------------------------------------------------
# TEST 3: Ron hit claim, Ron before impact -> REJECT
# ------------------------------------------------------------------------------
def test_03_ron_hit_claim_before_impact_rejected():
    evaluator = CandidateEvidenceEvaluator()
    beat = VisualBeat(
        beat_id="beat_03",
        narration_start=0.0,
        narration_end=2.5,
        text_span="Ron got hit in the face",
        visual_assertion="broomstick performs HIT on Ron Weasley",
        required_entities=["broomstick", "Ron Weasley"],
        required_action="HIT",
        coverage_requirement=CoverageRequirement.DIRECT,
    )
    # Ron is standing at distance, no contact event or impact occurs
    t_broom = EntityTrack(
        track_id=1,
        character_name="broomstick",
        class_label="object",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[
            (0, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4)),
            (2, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4)),
            (4, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4)),
        ],
    )
    t_ron = EntityTrack(
        track_id=2,
        character_name="Ron Weasley",
        class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[
            (0, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4)),
            (2, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4)),
            (4, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4)),
        ],
    )
    timeline = EntityTimeline(
        source_video="m1_flying.mp4",
        start_sec=15.0,
        end_sec=17.5,
        tracks=[t_broom, t_ron],
    )
    cand = RetrievalCandidate(
        candidate_id="cand_ron_standing_before_impact",
        movie_id="hp1",
        start=15.0,
        end=17.5,
        source="L2_MOVIE_EVENT",
        retrieval_score=0.85,
        metadata={
            "source_video": "m1_flying.mp4",
            "location": "training pitch grounds",
            "movie_event_id": "first_flying_lesson",
        },
    )

    eval_res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert eval_res.is_rejected is True
    assert "PHYSICAL_EVIDENCE_FAILED" in eval_res.rejection_reason or "ACTION_UNVERIFIED" in eval_res.rejection_reason


# ------------------------------------------------------------------------------
# TEST 4: Ron hit claim, actual impact -> ACCEPT
# ------------------------------------------------------------------------------
def test_04_ron_hit_claim_actual_impact_accepted():
    evaluator = CandidateEvidenceEvaluator()
    beat = VisualBeat(
        beat_id="beat_04",
        narration_start=0.0,
        narration_end=2.5,
        text_span="Ron got hit in the face",
        visual_assertion="broomstick performs HIT on Ron Weasley",
        required_entities=["broomstick", "Ron Weasley"],
        required_action="HIT",
        coverage_requirement=CoverageRequirement.DIRECT,
    )
    # Actor/object strikes Ron with physical contact and reaction displacement in 9:16 safe window
    t_striker = EntityTrack(
        track_id=1,
        character_name="broomstick",
        class_label="object",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[
            (0, BoundingBox(x=0.30, y=0.3, w=0.06, h=0.4)),
            (5, BoundingBox(x=0.46, y=0.3, w=0.06, h=0.4)),  # impact contact, v=0.77 >= 0.30
            (10, BoundingBox(x=0.44, y=0.3, w=0.06, h=0.4)),
        ],
    )
    t_ron = EntityTrack(
        track_id=2,
        character_name="Ron Weasley",
        class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[
            (0, BoundingBox(x=0.55, y=0.3, w=0.06, h=0.4)),
            (5, BoundingBox(x=0.52, y=0.3, w=0.06, h=0.4)),  # impact contact
            (10, BoundingBox(x=0.58, y=0.3, w=0.06, h=0.4)),  # reaction displacement
        ],
    )
    timeline = EntityTimeline(
        source_video="m1_flying.mp4",
        start_sec=20.0,
        end_sec=22.5,
        tracks=[t_striker, t_ron],
    )
    cand = RetrievalCandidate(
        candidate_id="cand_ron_actual_impact",
        movie_id="hp1",
        start=20.0,
        end=22.5,
        source="L2_MOVIE_EVENT",
        retrieval_score=0.95,
        metadata={
            "source_video": "m1_flying.mp4",
            "location": "training pitch grounds",
            "movie_event_id": "first_flying_lesson",
        },
    )

    eval_res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert eval_res.is_rejected is False
    assert eval_res.is_physical_verified is True
    # Minimal verified interval is extracted around the event
    assert eval_res.verified_sub_interval is not None
    assert eval_res.verified_sub_interval[0] >= 20.0
    assert eval_res.verified_sub_interval[1] <= 22.5


# ------------------------------------------------------------------------------
# TEST 5: Hermione + Malfoy + punch, no punch -> REJECT
# ------------------------------------------------------------------------------
def test_05_hermione_malfoy_punch_no_punch_rejected():
    evaluator = CandidateEvidenceEvaluator()
    beat = VisualBeat(
        beat_id="beat_05",
        narration_start=0.0,
        narration_end=3.0,
        text_span="Hermione punches Malfoy",
        visual_assertion="Hermione Granger performs PUNCH on Draco Malfoy",
        required_entities=["Hermione Granger", "Draco Malfoy"],
        required_action="PUNCH",
        coverage_requirement=CoverageRequirement.DIRECT,
    )
    # Hermione and Malfoy standing apart talking, no punch contact
    t_hermione = EntityTrack(
        track_id=1,
        character_name="Hermione Granger",
        class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[
            (0, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4)),
            (2, BoundingBox(x=0.15, y=0.3, w=0.15, h=0.4)),
            (4, BoundingBox(x=0.15, y=0.3, w=0.15, h=0.4)),
        ],
    )
    t_draco = EntityTrack(
        track_id=2,
        character_name="Draco Malfoy",
        class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[
            (0, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4)),
            (2, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4)),
            (4, BoundingBox(x=0.7, y=0.3, w=0.15, h=0.4)),
        ],
    )
    timeline = EntityTimeline(
        source_video="m3_punch.mp4",
        start_sec=40.0,
        end_sec=43.0,
        tracks=[t_hermione, t_draco],
    )
    cand = RetrievalCandidate(
        candidate_id="cand_malfoy_standoff_no_punch",
        movie_id="hp3",
        start=40.0,
        end=43.0,
        source="L2_MOVIE_EVENT",
        retrieval_score=0.88,
        metadata={
            "source_video": "m3_punch.mp4",
            "location": "sundial hillside",
            "movie_event_id": "malfoy_confrontation",
        },
    )

    eval_res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert eval_res.is_rejected is True
    assert "PHYSICAL_EVIDENCE_FAILED" in eval_res.rejection_reason or "CONTACT_NOT_CONFIRMED" in eval_res.rejection_reason


# ------------------------------------------------------------------------------
# TEST 6: Hermione + Malfoy + actual punch -> ACCEPT
# ------------------------------------------------------------------------------
def test_06_hermione_malfoy_actual_punch_accepted():
    evaluator = CandidateEvidenceEvaluator()
    beat = VisualBeat(
        beat_id="beat_06",
        narration_start=0.0,
        narration_end=3.0,
        text_span="Hermione punches Malfoy",
        visual_assertion="Hermione Granger performs PUNCH on Draco Malfoy",
        required_entities=["Hermione Granger", "Draco Malfoy"],
        required_action="PUNCH",
        coverage_requirement=CoverageRequirement.DIRECT,
    )
    # Hermione approaches at high velocity (v=0.42 >= 0.35), contacts Draco, and Draco displaces backward (dx=0.06 >= 0.05)
    t_hermione = EntityTrack(
        track_id=1,
        character_name="Hermione Granger",
        class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[
            (0, BoundingBox(x=0.25, y=0.3, w=0.06, h=0.4)),
            (5, BoundingBox(x=0.46, y=0.3, w=0.06, h=0.4)),  # punch contact, dx=0.21, dt=0.5s -> v=0.42 >= 0.35
            (10, BoundingBox(x=0.44, y=0.3, w=0.06, h=0.4)),
        ],
    )
    t_draco = EntityTrack(
        track_id=2,
        character_name="Draco Malfoy",
        class_label="person",
        identity_status=IdentityMatchStatus.FACE_CONFIRMED,
        history=[
            (0, BoundingBox(x=0.55, y=0.3, w=0.06, h=0.4)),
            (5, BoundingBox(x=0.52, y=0.3, w=0.06, h=0.4)),  # punch contact
            (10, BoundingBox(x=0.58, y=0.3, w=0.06, h=0.4)),  # knockback reaction displacement
        ],
    )
    timeline = EntityTimeline(
        source_video="m3_punch.mp4",
        start_sec=45.0,
        end_sec=48.0,
        tracks=[t_hermione, t_draco],
    )
    cand = RetrievalCandidate(
        candidate_id="cand_hermione_actual_punch",
        movie_id="hp3",
        start=45.0,
        end=48.0,
        source="L2_MOVIE_EVENT",
        retrieval_score=0.96,
        metadata={
            "source_video": "m3_punch.mp4",
            "location": "sundial hillside",
            "movie_event_id": "malfoy_confrontation",
        },
    )

    eval_res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert eval_res.is_rejected is False
    assert eval_res.is_physical_verified is True
    assert eval_res.verified_action == "PUNCH"


# ------------------------------------------------------------------------------
# TEST 7: Two propositions in one sentence -> split into two micro-beats
# ------------------------------------------------------------------------------
def test_07_two_propositions_split_into_two_microbeats():
    compiler = VisualBeatCompiler()
    # Sentence: "Harry grabs the broom and Ron gets knocked away."
    words = [
        WordTimestamp(word="Harry", start_sec=0.0, end_sec=0.4),
        WordTimestamp(word="grabs", start_sec=0.4, end_sec=0.8),
        WordTimestamp(word="the", start_sec=0.8, end_sec=1.0),
        WordTimestamp(word="broom", start_sec=1.0, end_sec=1.5),
        WordTimestamp(word="and", start_sec=1.5, end_sec=1.8),
        WordTimestamp(word="Ron", start_sec=1.8, end_sec=2.2),
        WordTimestamp(word="gets", start_sec=2.2, end_sec=2.5),
        WordTimestamp(word="knocked", start_sec=2.5, end_sec=3.0),
        WordTimestamp(word="away.", start_sec=3.0, end_sec=3.5),
    ]
    sentence_boundary = SentenceBoundary(
        sentence_index=0,
        text="Harry grabs the broom and Ron gets knocked away.",
        start_sec=0.0,
        end_sec=3.5,
        word_start_idx=0,
        word_end_idx=len(words) - 1,
    )
    narration_input = LockedNarrationInput(
        content_id="test_split_microbeat_01",
        script_hash="dummy_script_hash_01",
        narration_hash="dummy_narration_hash_01",
        narration_text="Harry grabs the broom and Ron gets knocked away.",
        word_timestamps=words,
        sentence_boundaries=[sentence_boundary],
        exact_narration_duration=3.5,
    )

    beats = compiler.compile_beats(narration_input)

    # Must be split into at least 2 distinct micro-beats
    assert len(beats) >= 2, f"Expected at least 2 micro-beats, got {len(beats)}"

    beat_1 = beats[0]
    beat_2 = beats[1]

    # Beat 1 verifies Harry + broom + grab
    assert "Harry Potter" in beat_1.required_entities
    assert "broomstick" in beat_1.required_objects
    assert beat_1.required_action == "GRAB"

    # Beat 2 verifies Ron + knock/hit
    assert "Ron Weasley" in beat_2.required_entities
    assert beat_2.required_action in ("KNOCK", "HIT")

    # Time intervals must be independent and contiguous
    assert beat_1.narration_start == 0.0
    assert beat_1.narration_end == beat_2.narration_start
    assert beat_2.narration_end == 3.5
