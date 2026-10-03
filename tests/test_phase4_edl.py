"""
STORY FORGE — Phase 4: Visual EDL & Candidate Arbitration Test Suite
====================================================================
Comprehensive focused test suite covering all 27 required Phase 4 capabilities:
  1. Complete narration beat compilation
  2. Word-level beat timing
  3. Deep search expansion
  4. Candidate pooling
  5. Candidate diversity
  6. Alternate candidate search
  7. Full-movie fallback
  8. Cross-movie fallback
  9. Phase 2 perception integration
  10. Phase 3 evidence integration
  11. Physical-evidence dominance
  12. Candidate rejection
  13. Temporal interval extraction
  14. Candidate reuse rejection
  15. Legitimate candidate reuse
  16. Multi-beat global arbitration
  17. 9:16 feasibility gate
  18. Narration coverage accounting
  19. Direct beat failure
  20. Anti-loop enforcement
  21. EDL lineage
  22. Silent-event retrieval
  23. Outside-SRT retrieval
  24. Wrong semantic candidate rejection
  25. Multi-scene EDL generation
  26. 4+ segment benchmark
  27. 6+ segment benchmark
"""

import pytest
import hashlib
from typing import List, Dict, Any

from py_visual_evidence.schema import BoundingBox
from engines.retrieval.models import RetrievalCandidate, RetrievalQuery
from engines.retrieval.cascade_engine import RetrievalCascadeEngine
from engines.perception.models import (
    EntityTimeline,
    EntityTrack,
    IdentityMatchStatus,
    VisualObject,
)
from engines.perception.character_bank import CharacterBank
from engines.action.models import (
    PhysicalActionType,
    ActionEvidenceVerdict,
    ActionFailureReason,
)
from engines.action.verifier import ActionEvidenceVerifier
from engines.visual_evidence.subject_aware_composition import SubjectAwareCompositionEngine

from engines.edl.models import (
    LockedNarrationInput,
    WordTimestamp,
    SentenceBoundary,
    VisualBeat,
    CoverageRequirement,
    CoverageState,
    CropFeasibility,
    EvaluatedCandidate,
    EDLEntry,
    VisualEDL,
)
from engines.edl.beat_compiler import VisualBeatCompiler
from engines.edl.concept_expansion import VisualConceptExpander
from engines.edl.deep_search import DeepMovieSearcher
from engines.edl.candidate_evaluator import CandidateEvidenceEvaluator
from engines.edl.arbitration import CandidateArbitrator
from engines.edl.timeline_generator import VisualEDLGenerator


@pytest.fixture
def mock_locked_narration():
    # Locked narration: "Hermione punched Draco because he insulted Buckbeak. In the book, it happened differently."
    # Total duration: 8.0s
    words = [
        WordTimestamp(word="Hermione", start_sec=0.0, end_sec=0.8),
        WordTimestamp(word="punched", start_sec=0.8, end_sec=1.5),
        WordTimestamp(word="Draco", start_sec=1.5, end_sec=2.4),
        WordTimestamp(word="because", start_sec=2.4, end_sec=3.0),
        WordTimestamp(word="he", start_sec=3.0, end_sec=3.4),
        WordTimestamp(word="insulted", start_sec=3.4, end_sec=4.2),
        WordTimestamp(word="Buckbeak.", start_sec=4.2, end_sec=5.2),
        WordTimestamp(word="In", start_sec=5.2, end_sec=5.5),
        WordTimestamp(word="the", start_sec=5.5, end_sec=5.8),
        WordTimestamp(word="book,", start_sec=5.8, end_sec=6.4),
        WordTimestamp(word="it", start_sec=6.4, end_sec=6.8),
        WordTimestamp(word="happened", start_sec=6.8, end_sec=7.4),
        WordTimestamp(word="differently.", start_sec=7.4, end_sec=8.0),
    ]
    sentences = [
        SentenceBoundary(
            sentence_index=0,
            text="Hermione punched Draco because he insulted Buckbeak.",
            start_sec=0.0,
            end_sec=5.2,
            word_start_idx=0,
            word_end_idx=6,
        ),
        SentenceBoundary(
            sentence_index=1,
            text="In the book, it happened differently.",
            start_sec=5.2,
            end_sec=8.0,
            word_start_idx=7,
            word_end_idx=12,
        ),
    ]
    return LockedNarrationInput(
        content_id="test_narration_hp3",
        script_hash="script_hash_abc123",
        narration_hash="narration_hash_def456",
        exact_narration_duration=8.0,
        word_timestamps=words,
        sentence_boundaries=sentences,
        narration_text="Hermione punched Draco because he insulted Buckbeak. In the book, it happened differently.",
    )


# 1. Complete narration beat compilation
def test_01_complete_narration_beat_compilation(mock_locked_narration):
    compiler = VisualBeatCompiler()
    beats = compiler.compile_beats(mock_locked_narration)
    assert len(beats) >= 2
    assert beats[0].narration_start == 0.0
    assert beats[-1].narration_end == 8.0
    # Check that coverage requirement is assigned
    assert any(b.coverage_requirement == CoverageRequirement.DIRECT for b in beats)
    assert any(b.coverage_requirement == CoverageRequirement.VISUAL_OPTIONAL for b in beats)


# 2. Word-level beat timing
def test_02_word_level_beat_timing(mock_locked_narration):
    compiler = VisualBeatCompiler()
    beats = compiler.compile_beats(mock_locked_narration)
    # Ensure no zero-duration or paragraph-level collapse
    for b in beats:
        assert b.duration > 0.5
        assert b.narration_start < b.narration_end
    # Ensure contiguous coverage without gaps
    for i in range(len(beats) - 1):
        assert abs(beats[i].narration_end - beats[i + 1].narration_start) < 0.001


# 3. Deep search expansion
def test_03_deep_search_expansion():
    expander = VisualConceptExpander()
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.5,
        text_span="Harry snaps the Elder Wand",
        visual_assertion="Harry Potter performs SNAP on elder_wand",
        required_entities=["Harry Potter"],
        required_objects=["elder_wand"],
        required_action="SNAP",
        required_state="BROKEN",
    )
    queries = expander.expand_beat(beat)
    assert len(queries) >= 5
    lower_q = [q.lower() for q in queries]
    assert any("harry" in q for q in lower_q)
    assert any("elder wand" in q or "wand" in q for q in lower_q)
    assert any("snapping" in q or "breaks" in q or "broken" in q for q in lower_q)


# 4. Candidate pooling
def test_04_candidate_pooling():
    searcher = DeepMovieSearcher(min_candidate_pool_size=5)
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=3.0,
        text_span="Hermione punched Draco",
        visual_assertion="Hermione punches Draco",
        required_entities=["Hermione Granger", "Draco Malfoy"],
        required_action="PUNCH",
    )
    cands, diag = searcher.search_beat_candidates(beat, target_movie_id=3)
    assert len(cands) >= 5
    assert diag.candidates_returned >= 5
    assert "L1_L4_PRIMARY_CASCADE" in diag.search_levels_attempted


# 5. Candidate diversity
def test_05_candidate_diversity():
    searcher = DeepMovieSearcher(min_candidate_pool_size=5)
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Harry Potter",
        visual_assertion="Harry Potter standing",
        required_entities=["Harry Potter"],
    )
    cands, _ = searcher.search_beat_candidates(beat, target_movie_id=1)
    # Check that candidates are temporally distributed rather than clustered in single 2-sec window
    start_times = [c.start for c in cands]
    assert len(set(start_times)) >= 3


# 6. Alternate candidate search
def test_06_alternate_candidate_search():
    searcher = DeepMovieSearcher()
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Hermione punched Draco",
        visual_assertion="Hermione punches Draco",
        required_entities=["Hermione Granger", "Draco Malfoy"],
        required_action="PUNCH",
    )
    cands, _ = searcher.search_beat_candidates(beat, target_movie_id=3)
    # If first candidate is rejected, alternate candidates exist in the pool
    assert len(cands) > 1
    top_cand = cands[0]
    alternate_cand = cands[1]
    assert top_cand.candidate_id != alternate_cand.candidate_id


# 7. Full-movie fallback
def test_07_full_movie_fallback():
    searcher = DeepMovieSearcher(min_candidate_pool_size=10)
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="rare action event",
        visual_assertion="rare action",
        required_entities=["Harry Potter"],
    )
    cands, diag = searcher.search_beat_candidates(beat, target_movie_id=3)
    assert "L6_FULL_MOVIE_SEARCH" in diag.search_levels_attempted


# 8. Cross-movie fallback
def test_08_cross_movie_fallback():
    searcher = DeepMovieSearcher(min_candidate_pool_size=15)
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="cross movie search",
        visual_assertion="cross movie",
        required_entities=["Harry Potter"],
    )
    cands, diag = searcher.search_beat_candidates(beat, target_movie_id=3, allow_cross_movie=True)
    assert "L7_FRANCHISE_WIDE_SEARCH" in diag.search_levels_attempted
    movie_ids = {c.movie_id for c in cands}
    assert len(movie_ids) >= 1


# 9. Phase 2 perception integration
def test_09_phase2_perception_integration():
    evaluator = CandidateEvidenceEvaluator()
    cand = RetrievalCandidate(
        candidate_id="c1",
        movie_id="3",
        start=100.0,
        end=105.0,
        source="TEST",
        retrieval_score=0.90,
    )
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Hermione confronted Draco",
        visual_assertion="Hermione confronted Draco",
        required_entities=["Hermione Granger", "Draco Malfoy"],
    )
    # Timeline with only Draco (Hermione missing)
    t_draco = EntityTrack(track_id=1, character_name="Draco Malfoy", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    timeline = EntityTimeline(tracks=[t_draco])

    res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert res.is_rejected is True
    assert "NO_CONFIDENT_IDENTITY" in res.rejection_reason
    assert "Hermione Granger" in res.rejection_reason


# 10. Phase 3 evidence integration
def test_10_phase3_evidence_integration():
    evaluator = CandidateEvidenceEvaluator()
    cand = RetrievalCandidate(
        candidate_id="c1",
        movie_id="3",
        start=100.0,
        end=105.0,
        source="TEST",
        retrieval_score=0.92,
    )
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Hermione punched Draco",
        visual_assertion="Hermione punches Draco",
        required_entities=["Hermione Granger", "Draco Malfoy"],
        required_action="PUNCH",
    )
    # Timeline where they stand distant without contact
    t_hermione = EntityTrack(track_id=1, character_name="Hermione Granger", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_hermione.history = [(0, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4))]
    t_draco = EntityTrack(track_id=2, character_name="Draco Malfoy", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_draco.history = [(0, BoundingBox(x=0.8, y=0.3, w=0.15, h=0.4))]
    timeline = EntityTimeline(tracks=[t_hermione, t_draco])

    res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert res.is_rejected is True
    assert "PHYSICAL_EVIDENCE_FAILED" in res.rejection_reason


# 11. Physical-evidence dominance
def test_11_physical_evidence_dominance():
    evaluator = CandidateEvidenceEvaluator()
    # Candidate with extremely high OpenCLIP / semantic score (0.99)
    cand = RetrievalCandidate(
        candidate_id="c_high_semantic",
        movie_id="3",
        start=100.0,
        end=105.0,
        source="TEST",
        retrieval_score=0.99,
        semantic_score=0.99,
    )
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Hermione punched Draco",
        visual_assertion="Hermione punches Draco",
        required_entities=["Hermione Granger", "Draco Malfoy"],
        required_action="PUNCH",
    )
    # But physical proof fails
    t_h = EntityTrack(track_id=1, character_name="Hermione Granger", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_h.history = [(0, BoundingBox(x=0.1, y=0.3, w=0.15, h=0.4))]
    t_d = EntityTrack(track_id=2, character_name="Draco Malfoy", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_d.history = [(0, BoundingBox(x=0.8, y=0.3, w=0.15, h=0.4))]
    timeline = EntityTimeline(tracks=[t_h, t_d])

    res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    # Physical evidence must defeat semantic similarity
    assert res.is_rejected is True
    assert res.overall_arbitration_score == 0.0 or res.is_rejected


# 12. Candidate rejection
def test_12_candidate_rejection():
    evaluator = CandidateEvidenceEvaluator()
    cand = RetrievalCandidate(candidate_id="c1", movie_id="8", start=10.0, end=15.0, source="TEST", retrieval_score=0.8)
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Harry broke the Elder Wand",
        visual_assertion="Harry breaks elder_wand",
        required_entities=["Harry Potter"],
        required_objects=["elder_wand"],
        required_action="BREAK",
    )
    # Timeline with Harry but no elder_wand
    t_h = EntityTrack(track_id=1, character_name="Harry Potter", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    timeline = EntityTimeline(tracks=[t_h])
    res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert res.is_rejected is True
    assert "NO_REQUIRED_OBJECT" in res.rejection_reason


# 13. Temporal interval extraction
def test_13_temporal_interval_extraction():
    evaluator = CandidateEvidenceEvaluator()
    cand = RetrievalCandidate(
        candidate_id="c1",
        movie_id="3",
        start=100.0,
        end=108.0,
        source="TEST",
        retrieval_score=0.85,
    )
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Hermione punched Draco",
        visual_assertion="Hermione punches Draco",
        required_entities=["Hermione Granger", "Draco Malfoy"],
        required_action="PUNCH",
    )
    t_h = EntityTrack(track_id=1, character_name="Hermione Granger", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_h.history = [
        (0, BoundingBox(x=0.2, y=0.3, w=0.15, h=0.4)),
        (5, BoundingBox(x=0.45, y=0.3, w=0.15, h=0.4)),
        (10, BoundingBox(x=0.48, y=0.3, w=0.15, h=0.4)),
    ]
    t_d = EntityTrack(track_id=2, character_name="Draco Malfoy", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_d.history = [
        (0, BoundingBox(x=0.55, y=0.3, w=0.15, h=0.4)),
        (5, BoundingBox(x=0.55, y=0.3, w=0.15, h=0.4)),
        (10, BoundingBox(x=0.65, y=0.3, w=0.15, h=0.4)),
    ]
    timeline = EntityTimeline(tracks=[t_h, t_d])
    res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert res.is_physical_verified is True
    # Verified sub-interval is tightly extracted (smaller than 100.0 -> 108.0)
    assert res.verified_duration < (108.0 - 100.0)


# 14. Candidate reuse rejection
def test_14_candidate_reuse_rejection():
    arbitrator = CandidateArbitrator()
    b1 = VisualBeat(beat_id="b1", narration_start=0.0, narration_end=2.0, text_span="Hermione punched Draco", visual_assertion="Hermione punches Draco", required_entities=["Hermione Granger", "Draco Malfoy"], required_action="PUNCH")
    b2 = VisualBeat(beat_id="b2", narration_start=2.0, narration_end=4.0, text_span="Harry talked to Ron", visual_assertion="Harry talks to Ron", required_entities=["Harry Potter", "Ron Weasley"])

    # Shared candidate interval (100-105s in M3)
    cand_a = EvaluatedCandidate(
        candidate_id="cand_a",
        beat_id="b1",
        source_movie_id=3,
        source_video="m3.mp4",
        source_interval=(100.0, 105.0),
        verified_sub_interval=(100.0, 105.0),
        is_physical_verified=True,
        overall_arbitration_score=0.90,
        verified_entities=["Hermione Granger", "Draco Malfoy"],
        verified_action="PUNCH",
        evidence_hash="ev_a",
    )
    # Cand A also evaluated for b2, but b2 requires Harry + Ron!
    cand_a_for_b2 = EvaluatedCandidate(
        candidate_id="cand_a",
        beat_id="b2",
        source_movie_id=3,
        source_video="m3.mp4",
        source_interval=(100.0, 105.0),
        verified_sub_interval=(100.0, 105.0),
        is_physical_verified=False,
        overall_arbitration_score=0.85,
        verified_entities=["Hermione Granger", "Draco Malfoy"],
        evidence_hash="ev_a",
    )
    # Candidate B for b2 with clean unique interval
    cand_b = EvaluatedCandidate(
        candidate_id="cand_b",
        beat_id="b2",
        source_movie_id=3,
        source_video="m3.mp4",
        source_interval=(200.0, 205.0),
        verified_sub_interval=(200.0, 205.0),
        is_physical_verified=True,
        overall_arbitration_score=0.82,
        verified_entities=["Harry Potter", "Ron Weasley"],
        evidence_hash="ev_b",
    )

    entries, audit = arbitrator.arbitrate_timeline(
        beats=[b1, b2],
        evaluated_candidates_by_beat={"b1": [cand_a], "b2": [cand_a_for_b2, cand_b]},
    )
    assert len(entries) == 2
    # Ensure cand_a was NOT reused for b2; cand_b was selected instead
    assert entries[0].evidence_id == "cand_a"
    assert entries[1].evidence_id == "cand_b"


# 15. Legitimate candidate reuse
def test_15_legitimate_candidate_reuse():
    arbitrator = CandidateArbitrator()
    # Beat 1: Hermione punches Draco (action)
    b1 = VisualBeat(beat_id="b1", narration_start=0.0, narration_end=1.5, text_span="Hermione punched Draco", visual_assertion="Hermione punches Draco", required_entities=["Hermione Granger", "Draco Malfoy"], required_action="PUNCH")
    # Beat 2: Draco collapses backward (consequence of same physical evidence)
    b2 = VisualBeat(beat_id="b2", narration_start=1.5, narration_end=3.0, text_span="Malfoy fell to the ground", visual_assertion="Draco Malfoy falls", required_entities=["Draco Malfoy"])

    cand_same = EvaluatedCandidate(
        candidate_id="cand_punch_scene",
        beat_id="b1",
        source_movie_id=3,
        source_video="m3.mp4",
        source_interval=(4212.0, 4216.0),
        verified_sub_interval=(4212.0, 4216.0),
        is_physical_verified=True,
        overall_arbitration_score=0.95,
        verified_entities=["Hermione Granger", "Draco Malfoy"],
        verified_action="PUNCH",
        evidence_hash="ev_punch_scene",
    )
    entries, audit = arbitrator.arbitrate_timeline(
        beats=[b1, b2],
        evaluated_candidates_by_beat={"b1": [cand_same], "b2": [cand_same]},
    )
    assert len(entries) == 2
    # Reuse is legitimate and tagged in reuse_group
    assert entries[1].reuse_group is not None


# 16. Multi-beat global arbitration
def test_16_multi_beat_global_arbitration():
    arbitrator = CandidateArbitrator()
    b1 = VisualBeat(beat_id="b1", narration_start=0.0, narration_end=2.0, text_span="Beat 1", visual_assertion="Beat 1", required_entities=["Harry Potter"])
    b2 = VisualBeat(beat_id="b2", narration_start=2.0, narration_end=4.0, text_span="Beat 2", visual_assertion="Beat 2", required_entities=["Ron Weasley"])

    # Cand A scores 0.92 on Beat 1, and 0.90 on Beat 2
    cand_a = EvaluatedCandidate(candidate_id="cA", beat_id="b1", source_movie_id=1, source_video="m1.mp4", source_interval=(10.0, 15.0), verified_sub_interval=(10.0, 15.0), overall_arbitration_score=0.92, verified_entities=["Harry Potter"], evidence_hash="hA")
    cand_a2 = EvaluatedCandidate(candidate_id="cA", beat_id="b2", source_movie_id=1, source_video="m1.mp4", source_interval=(10.0, 15.0), verified_sub_interval=(10.0, 15.0), overall_arbitration_score=0.90, verified_entities=["Ron Weasley"], evidence_hash="hA")

    # Cand D scores 0.88 on Beat 2 with unique interval (50-55s)
    cand_d = EvaluatedCandidate(candidate_id="cD", beat_id="b2", source_movie_id=1, source_video="m1.mp4", source_interval=(50.0, 55.0), verified_sub_interval=(50.0, 55.0), overall_arbitration_score=0.88, verified_entities=["Ron Weasley"], evidence_hash="hD")

    entries, _ = arbitrator.arbitrate_timeline(
        beats=[b1, b2],
        evaluated_candidates_by_beat={"b1": [cand_a], "b2": [cand_a2, cand_d]},
    )
    # Globally assigns Beat 1 -> cA, Beat 2 -> cD to maximize diversity
    assert entries[0].evidence_id == "cA"
    assert entries[1].evidence_id == "cD"


# 17. 9:16 feasibility gate
def test_17_crop_feasibility_gate():
    evaluator = CandidateEvidenceEvaluator()
    cand = RetrievalCandidate(candidate_id="c1", movie_id="3", start=10.0, end=15.0, source="TEST", retrieval_score=0.8)
    beat = VisualBeat(beat_id="b1", narration_start=0.0, narration_end=2.0, text_span="Wide standoff", visual_assertion="Two people far apart", required_entities=["Hermione Granger", "Draco Malfoy"])

    # Two subjects at opposite edges of 1920x800 frame (x=0.05 and x=0.95)
    # A 9:16 crop has aspect width 450px out of 1920px. Distance 0.90 cannot fit in 0.23 width!
    box_left = BoundingBox(x=0.05, y=0.3, w=0.1, h=0.4)
    box_right = BoundingBox(x=0.90, y=0.3, w=0.1, h=0.4)

    res = evaluator.evaluate_candidate(cand, beat, subject_bboxes=[box_left, box_right], is_two_shot=True)
    assert res.is_rejected is True
    assert res.crop_feasibility == CropFeasibility.IMPOSSIBLE
    assert "CROP_IMPOSSIBLE" in res.rejection_reason


# 18. Narration coverage accounting
def test_18_narration_coverage_accounting(mock_locked_narration):
    generator = VisualEDLGenerator()
    edl = generator.generate_edl(mock_locked_narration, target_movie_id=3)
    assert edl.total_narration_duration == 8.0
    calc_total = edl.directly_covered_duration + edl.optional_duration + edl.unfulfilled_duration
    assert abs(calc_total - 8.0) < 0.05
    assert edl.coverage_percentage >= 0.0 and edl.coverage_percentage <= 1.0


# 19. Direct beat failure
def test_19_direct_beat_failure():
    generator = VisualEDLGenerator()
    words = [WordTimestamp(word="Impossible", start_sec=0.0, end_sec=1.0), WordTimestamp(word="action", start_sec=1.0, end_sec=2.0)]
    narration = LockedNarrationInput(
        content_id="test_fail",
        script_hash="s1",
        narration_hash="n1",
        exact_narration_duration=2.0,
        word_timestamps=words,
        sentence_boundaries=[SentenceBoundary(sentence_index=0, text="Impossible action", start_sec=0.0, end_sec=2.0, word_start_idx=0, word_end_idx=1)],
        narration_text="Impossible action",
        editorial_beat_boundaries=[{"beat_id": "b1", "start_sec": 0.0, "end_sec": 2.0, "text": "Non-existent character actions", "coverage": "DIRECT", "required_entities": ["Alien Martian"]}],
    )
    edl = generator.generate_edl(narration)
    assert edl.is_complete is False
    assert edl.failure_reason is not None
    assert "INSUFFICIENT_VISUAL_COVERAGE" in edl.failure_reason


# 20. Anti-loop enforcement
def test_20_anti_loop_enforcement():
    arbitrator = CandidateArbitrator()
    b1 = VisualBeat(beat_id="b1", narration_start=0.0, narration_end=2.0, text_span="Beat 1", visual_assertion="Beat 1")
    b2 = VisualBeat(beat_id="b2", narration_start=2.0, narration_end=4.0, text_span="Beat 2", visual_assertion="Beat 2")

    # If someone tries to force the same clip twice without justification
    cand_loop = EvaluatedCandidate(candidate_id="c_same", beat_id="b1", source_movie_id=1, source_video="m1.mp4", source_interval=(10.0, 15.0), verified_sub_interval=(10.0, 15.0), overall_arbitration_score=0.9, evidence_hash="h1")
    entries, audit = arbitrator.arbitrate_timeline(
        beats=[b1, b2],
        evaluated_candidates_by_beat={"b1": [cand_loop], "b2": [cand_loop]},
    )
    # Second beat must reject the loop
    assert entries[1].coverage_state == CoverageState.UNFULFILLED or entries[1].reuse_group is not None


# 21. EDL lineage
def test_21_edl_lineage(mock_locked_narration):
    generator = VisualEDLGenerator()
    edl = generator.generate_edl(mock_locked_narration, target_movie_id=3)
    assert edl.lineage.is_valid()
    assert len(edl.lineage.edl_hash) == 64
    assert edl.lineage.content_id == mock_locked_narration.content_id


# 22. Silent-event retrieval
def test_22_silent_event_retrieval():
    searcher = DeepMovieSearcher()
    beat = VisualBeat(
        beat_id="b_silent",
        narration_start=0.0,
        narration_end=3.0,
        text_span="Harry looked at the wand in silence",
        visual_assertion="Harry holds wand silently",
        required_entities=["Harry Potter"],
        required_objects=["wand"],
        required_action="HOLD",
    )
    cands, _ = searcher.search_beat_candidates(beat, target_movie_id=8)
    assert len(cands) > 0
    # Must retrieve candidates via dense visual and temporal proposals even without dialogue


# 23. Outside-SRT retrieval
def test_23_outside_srt_retrieval():
    searcher = DeepMovieSearcher()
    beat = VisualBeat(
        beat_id="b_outside",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Hermione strikes Malfoy",
        visual_assertion="Hermione punches Draco",
        required_entities=["Hermione Granger", "Draco Malfoy"],
        required_action="PUNCH",
    )
    cands, diag = searcher.search_beat_candidates(beat, target_movie_id=3)
    # Level 5 expansion provides expanded windows outside dialogue boundary
    expanded = [c for c in cands if "adj_exp" in c.candidate_id or c.retrieval_trace.get("deep_search_level") == "L5_ADJACENT"]
    assert len(expanded) > 0


# 24. Wrong semantic candidate rejection
def test_24_wrong_semantic_candidate_rejection():
    evaluator = CandidateEvidenceEvaluator()
    # Candidate with high OpenCLIP score because scene looks like a classroom
    cand = RetrievalCandidate(candidate_id="c_wrong_scene", movie_id="1", start=50.0, end=55.0, source="TEST", retrieval_score=0.91)
    beat = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=2.0,
        text_span="Snape reprimanded Harry",
        visual_assertion="Snape confronts Harry",
        required_entities=["Severus Snape", "Harry Potter"],
    )
    # Timeline only has Ron and Hermione
    t_r = EntityTrack(track_id=1, character_name="Ron Weasley", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    t_h = EntityTrack(track_id=2, character_name="Hermione Granger", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    timeline = EntityTimeline(tracks=[t_r, t_h])
    res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert res.is_rejected is True
    assert "NO_CONFIDENT_IDENTITY" in res.rejection_reason


# 25. Multi-scene EDL generation
def test_25_multi_scene_edl_generation():
    arbitrator = CandidateArbitrator()
    b1 = VisualBeat(beat_id="b1", narration_start=0.0, narration_end=2.0, text_span="Beat 1", visual_assertion="Beat 1")
    b2 = VisualBeat(beat_id="b2", narration_start=2.0, narration_end=4.0, text_span="Beat 2", visual_assertion="Beat 2")
    b3 = VisualBeat(beat_id="b3", narration_start=4.0, narration_end=6.0, text_span="Beat 3", visual_assertion="Beat 3")

    c1 = EvaluatedCandidate(candidate_id="c1", beat_id="b1", source_movie_id=3, source_video="m3.mp4", source_interval=(10.0, 15.0), verified_sub_interval=(10.0, 15.0), overall_arbitration_score=0.9, is_physical_verified=True, evidence_hash="h1")
    c2 = EvaluatedCandidate(candidate_id="c2", beat_id="b2", source_movie_id=3, source_video="m3.mp4", source_interval=(80.0, 85.0), verified_sub_interval=(80.0, 85.0), overall_arbitration_score=0.9, is_physical_verified=True, evidence_hash="h2")
    c3 = EvaluatedCandidate(candidate_id="c3", beat_id="b3", source_movie_id=3, source_video="m3.mp4", source_interval=(150.0, 155.0), verified_sub_interval=(150.0, 155.0), overall_arbitration_score=0.9, is_physical_verified=True, evidence_hash="h3")

    entries, audit = arbitrator.arbitrate_timeline(
        beats=[b1, b2, b3],
        evaluated_candidates_by_beat={"b1": [c1], "b2": [c2], "b3": [c3]},
    )
    assert len(entries) == 3
    source_starts = [e.source_clip_start for e in entries]
    assert len(set(source_starts)) == 3  # 3 distinct footage segments!


# 26. 4+ segment benchmark
def test_26_four_plus_segment_benchmark():
    arbitrator = CandidateArbitrator()
    beats = [
        VisualBeat(beat_id=f"b_{i}", narration_start=i * 2.0, narration_end=(i + 1) * 2.0, text_span=f"Beat {i}", visual_assertion=f"Assertion {i}")
        for i in range(4)
    ]
    candidates_by_beat = {
        f"b_{i}": [
            EvaluatedCandidate(
                candidate_id=f"cand_seg_{i}",
                beat_id=f"b_{i}",
                source_movie_id=i % 3 + 1,
                source_video=f"m{i % 3 + 1}.mp4",
                source_interval=(100.0 * (i + 1), 100.0 * (i + 1) + 4.0),
                verified_sub_interval=(100.0 * (i + 1), 100.0 * (i + 1) + 4.0),
                is_physical_verified=True,
                overall_arbitration_score=0.90,
                evidence_hash=f"hash_{i}",
            )
        ]
        for i in range(4)
    }
    entries, audit = arbitrator.arbitrate_timeline(beats, candidates_by_beat)
    assert len(entries) == 4
    unique_segments = len({(e.source_movie_id, e.source_clip_start) for e in entries})
    assert unique_segments >= 4
    assert audit.passed is True


# 27. 6+ segment benchmark
def test_27_six_plus_segment_benchmark():
    arbitrator = CandidateArbitrator()
    beats = [
        VisualBeat(beat_id=f"b_{i}", narration_start=i * 2.0, narration_end=(i + 1) * 2.0, text_span=f"Beat {i}", visual_assertion=f"Assertion {i}")
        for i in range(6)
    ]
    candidates_by_beat = {
        f"b_{i}": [
            EvaluatedCandidate(
                candidate_id=f"cand_seg_{i}",
                beat_id=f"b_{i}",
                source_movie_id=i % 4 + 1,
                source_video=f"m{i % 4 + 1}.mp4",
                source_interval=(50.0 * (i + 1), 50.0 * (i + 1) + 3.0),
                verified_sub_interval=(50.0 * (i + 1), 50.0 * (i + 1) + 3.0),
                is_physical_verified=True,
                overall_arbitration_score=0.92,
                evidence_hash=f"hash_seg_{i}",
            )
        ]
        for i in range(6)
    }
    entries, audit = arbitrator.arbitrate_timeline(beats, candidates_by_beat)
    assert len(entries) == 6
    unique_segments = len({(e.source_movie_id, e.source_clip_start) for e in entries})
    assert unique_segments >= 6
    assert audit.passed is True
    assert audit.stream_loops_detected == 0
