"""
STORY FORGE — Narrative Evidence Contract & Semantic Relevance Gate Tests
=========================================================================
Focused test suite verifying:
  1. Negative: Buckbeak cannot satisfy Sorting Hat claim
  2. Negative: Quidditch cannot satisfy Sorting Hat claim
  3. Negative: Generic Dumbledore cannot satisfy Sorting Hat claim
  4. Negative: Generic Harry close-up cannot satisfy "Sorting Hat interaction"
  5. Negative: Unrelated Hogwarts footage cannot satisfy specific event
  6. Positive: Harry + Sorting Hat + sorting interaction satisfies Sorting ceremony claim
  7. Positive: Hermione + Malfoy + actual punch satisfies punch claim
  8. Non-visual: Internal/book-only claim becomes VISUAL_OPTIONAL / non-visual without inventing direct evidence
  9. Non-visual: System rejects direct proof fabrication for invisible thoughts/lore
  10. CandidateEvidenceEvaluator rejects candidates with forbidden contexts
  11. CandidateEvidenceEvaluator rejects candidates failing semantic relevance
  12. CandidateArbitrator fails closed (NO_VALID_VISUAL / UNFULFILLED) when relevance fails
"""

import pytest
from engines.edl.evidence_contract import (
    NarrativeEvidenceContract,
    SemanticRelevanceEvaluator,
    RelevanceVerdict,
    INHERENTLY_NON_VISUAL_PATTERNS,
)
from engines.edl.models import (
    VisualBeat,
    CoverageRequirement,
    CoverageState,
    EvaluatedCandidate,
    CropFeasibility,
)
from engines.edl.beat_compiler import VisualBeatCompiler
from engines.edl.candidate_evaluator import CandidateEvidenceEvaluator
from engines.edl.arbitration import CandidateArbitrator
from engines.retrieval.models import RetrievalCandidate
from engines.perception.models import EntityTimeline, EntityTrack, IdentityMatchStatus, VisualObject


@pytest.fixture
def relevance_evaluator():
    return SemanticRelevanceEvaluator()


# ── 1. NEGATIVE: Buckbeak cannot satisfy Sorting Hat claim ─────────────────────

def test_negative_buckbeak_cannot_satisfy_sorting_hat(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="disc_a1",
        claim_text="Did you know the Sorting Hat considered placing Harry Potter in Slytherin?",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_scene_event="sorting_ceremony",
        forbidden_contexts=["buckbeak", "quidditch", "lake"],
        forbidden_subjects=["buckbeak"],
        direct_visual_mandatory=True,
    )

    # Candidate: Buckbeak dipping talons in lake
    cand_meta = {
        "candidate_id": "cand_buckbeak_lake",
        "title": "Buckbeak Flight Over Lake",
        "visual_description": "Buckbeak flies low over the Black Lake dipping talons in water",
        "action": "flying",
        "location": "Black Lake",
        "source_video": "m3_camera_pan_hogwarts.mp4",
        "characters_present": ["Buckbeak"],
        "verified_entities": ["Buckbeak"],
        "is_claimed_direct": True,
    }

    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.forbidden_context_passed is False
    assert any("FORBIDDEN_CONTEXT_VIOLATION" in r or "FORBIDDEN_SUBJECT_VIOLATION" in r for r in result.rejection_reasons)


# ── 2. NEGATIVE: Quidditch cannot satisfy Sorting Hat claim ───────────────────

def test_negative_quidditch_cannot_satisfy_sorting_hat(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="disc_a4",
        claim_text="The hat honours his choice -- but the ambition it sensed would define his entire journey.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_scene_event="sorting_ceremony",
        forbidden_contexts=["quidditch", "snitch", "broom"],
        direct_visual_mandatory=False,
    )

    # Candidate: Hagrid cheering in Quidditch stands
    cand_meta = {
        "candidate_id": "cand_snitch_catch",
        "title": "Harry Catches Snitch in Quidditch Match",
        "visual_description": "Hagrid cheers excitedly from the spectator towers at the Quidditch pitch",
        "action": "cheering at match",
        "location": "Quidditch Pitch",
        "source_video": "m1_snitch_catch.mp4",
        "characters_present": ["Rubeus Hagrid", "Harry Potter"],
        "is_claimed_direct": False,
    }

    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.forbidden_context_passed is False
    assert any("FORBIDDEN_CONTEXT_VIOLATION" in r for r in result.rejection_reasons)


# ── 3. NEGATIVE: Generic Dumbledore cannot satisfy Sorting Hat claim ──────────

def test_negative_dumbledore_cannot_satisfy_sorting_hat(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="disc_a2",
        claim_text="When placed on his head, the Sorting Hat debated his placement.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_scene_event="sorting_ceremony",
        required_action="hat placed on head",
        forbidden_contexts=["office", "tower", "viaduct"],
        direct_visual_mandatory=True,
    )

    # Candidate: Dumbledore in his office looking at parchment
    cand_meta = {
        "candidate_id": "cand_dumbledore_office",
        "title": "Dumbledore at Desk",
        "visual_description": "Albus Dumbledore sits at his circular desk examining a manuscript",
        "action": "examining parchment",
        "location": "Headmaster Office",
        "source_video": "m2_dumbledore_office.mp4",
        "characters_present": ["Albus Dumbledore"],
        "verified_entities": ["Albus Dumbledore"],
        "is_claimed_direct": True,
    }

    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.subject_match is False
    assert result.action_match is False


# ── 4. NEGATIVE: Generic Harry close-up cannot satisfy Sorting Hat interaction ─

def test_negative_generic_harry_cannot_satisfy_hat_interaction(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="disc_a2",
        claim_text="The Sorting Hat was placed onto Harry's head.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_action="hat placed on head",
        required_scene_event="sorting_ceremony",
        direct_visual_mandatory=True,
    )

    # Candidate: Harry sitting in Gryffindor common room reading
    cand_meta = {
        "candidate_id": "cand_harry_common_room",
        "title": "Harry Reading by Fireplace",
        "visual_description": "Close-up of Harry Potter reading a textbook beside the fire",
        "action": "reading",
        "location": "Gryffindor Common Room",
        "source_video": "m1_common_room.mp4",
        "characters_present": ["Harry Potter"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["book"],
        "is_claimed_direct": True,
    }

    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.action_match is False
    assert result.object_target_match is False


# ── 5. NEGATIVE: Unrelated Hogwarts footage cannot satisfy specific event ─────

def test_negative_generic_hogwarts_pan_cannot_satisfy_wand_shop(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="disc_a3",
        claim_text="Garrick Ollivander handed Harry his wand at Diagon Alley.",
        required_subjects=["Garrick Ollivander", "Harry Potter"],
        required_objects=["wand"],
        required_location="Ollivanders Wand Shop",
        required_scene_event="ollivander_wand_shop",
        forbidden_contexts=["lake", "castle exterior", "sorting", "quidditch"],
        direct_visual_mandatory=True,
    )

    # Candidate: Castle exterior camera pan
    cand_meta = {
        "candidate_id": "cand_castle_pan",
        "title": "Hogwarts Castle Establishing Pan",
        "visual_description": "Exterior landscape camera pan across Hogwarts towers and bridge",
        "action": "pan",
        "location": "Castle Exterior",
        "source_video": "m3_camera_pan_hogwarts.mp4",
        "characters_present": [],
        "is_claimed_direct": True,
    }

    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.subject_match is False
    assert result.location_context_match is False


# ── 6. POSITIVE: Harry + Sorting Hat + interaction satisfies claim ─────────────

def test_positive_sorting_hat_placed_satisfies_claim(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="disc_a2",
        claim_text="Professor McGonagall placed the Sorting Hat on Harry's head.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_action="hat placed on head",
        required_location="Great Hall",
        required_scene_event="sorting_ceremony",
        forbidden_contexts=["quidditch", "buckbeak", "lake", "snitch"],
        direct_visual_mandatory=True,
    )

    cand_meta = {
        "candidate_id": "cand_sorting_hat_placed",
        "title": "Sorting Hat Placed on Harry",
        "visual_description": "In the Great Hall, Professor McGonagall places the patched Sorting Hat onto Harry Potter's head during the sorting ceremony",
        "action": "hat placed on head",
        "location": "Great Hall",
        "movie_event_id": "sorting_ceremony_harry",
        "source_video": "m1_sorting_hat_placed.mp4",
        "characters_present": ["Harry Potter", "Minerva McGonagall"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["Sorting Hat", "stool"],
        "is_claimed_direct": True,
    }

    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.ACCEPT
    assert result.is_accepted is True
    assert result.overall_relevance_score >= 0.85
    assert result.subject_match is True
    assert result.action_match is True
    assert result.object_target_match is True
    assert result.forbidden_context_passed is True


# ── 7. POSITIVE: Hermione + Malfoy + punch satisfies punch claim ──────────────

def test_positive_hermione_punches_malfoy_satisfies_punch(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="novel_b2",
        claim_text="Hermione Granger delivered a fierce punch right to Draco Malfoy's face.",
        required_subjects=["Hermione Granger", "Draco Malfoy"],
        required_action="punch",
        required_location="Sundial Hillside",
        required_scene_event="malfoy_confrontation",
        forbidden_contexts=["great hall", "sorting", "quidditch", "classroom"],
        direct_visual_mandatory=True,
    )

    cand_meta = {
        "candidate_id": "cand_hermione_punch",
        "title": "Hermione Punches Draco Malfoy",
        "visual_description": "At the sundial stone circle hillside, Hermione Granger draws back her fist and punches Draco Malfoy in the face",
        "action": "punch",
        "location": "Sundial Hillside",
        "movie_event_id": "malfoy_confrontation_punch",
        "source_video": "m3_hermione_punches_malfoy.mp4",
        "characters_present": ["Hermione Granger", "Draco Malfoy"],
        "verified_entities": ["Hermione Granger", "Draco Malfoy"],
        "is_claimed_direct": True,
    }

    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.ACCEPT
    assert result.is_accepted is True
    assert result.overall_relevance_score >= 0.90
    assert result.subject_match is True
    assert result.action_match is True
    assert result.forbidden_context_passed is True


# ── 8. NON-VISUAL: Internal/book-only claim classified as VISUAL_OPTIONAL ──────

def test_non_visual_claim_classified_as_visual_optional():
    compiler = VisualBeatCompiler()
    
    # Internal cognitive claim
    claim1 = "The hat detected great talent, resourcefulness, and hidden ambition."
    req1 = compiler._determine_coverage_requirement(claim1)
    assert req1 == CoverageRequirement.VISUAL_OPTIONAL

    # Book-only comparative claim
    claim2 = "In the book, the hat debates out loud, explicitly naming Slytherin."
    req2 = compiler._determine_coverage_requirement(claim2)
    assert req2 == CoverageRequirement.VISUAL_OPTIONAL


# ── 9. NON-VISUAL: Rejects fabricating direct proof for invisible thoughts ────

def test_non_visual_rejects_direct_proof_fabrication(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="disc_a2_mental",
        claim_text="The hat detected great talent, resourcefulness, and hidden ambition.",
        is_inherently_non_visual=True,
        direct_visual_mandatory=False,
    )
    assert contract.is_inherently_non_visual is True

    # Candidate falsely asserting it proves invisible thoughts as DIRECT
    cand_meta = {
        "candidate_id": "cand_face_closeup",
        "title": "Harry Face Close-Up",
        "visual_description": "Harry Potter looking straight ahead",
        "action": "looking",
        "location": "Great Hall",
        "characters_present": ["Harry Potter"],
        "is_claimed_direct": True,  # Falsely claims to be direct proof of mental state
    }

    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.directness_requirement_satisfied is False
    assert any("INHERENTLY_NON_VISUAL" in r for r in result.rejection_reasons)


# ── 10. CandidateEvidenceEvaluator rejects candidate with forbidden context ───

def test_evaluator_rejects_candidate_with_forbidden_context():
    evaluator = CandidateEvidenceEvaluator()
    cand = RetrievalCandidate(
        candidate_id="c_quidditch",
        movie_id="1",
        start=10.0,
        end=15.0,
        source="TEST",
        retrieval_score=0.85,
        metadata={"title": "Quidditch match", "visual_description": "Quidditch pitch broom action"},
    )
    beat = VisualBeat(
        beat_id="b_sorting",
        narration_start=0.0,
        narration_end=4.0,
        text_span="The Sorting Hat considered placing Harry in Slytherin",
        visual_assertion="Sorting Hat considers Slytherin",
        required_entities=["Harry Potter"],
        required_objects=["sorting_hat"],
    )

    t_h = EntityTrack(track_id=1, character_name="Harry Potter", identity_status=IdentityMatchStatus.FACE_CONFIRMED)
    timeline = EntityTimeline(tracks=[t_h])

    res = evaluator.evaluate_candidate(cand, beat, timeline=timeline)
    assert res.is_rejected is True
    assert "SEMANTIC_RELEVANCE_FAILED" in res.rejection_reason
    assert any("FORBIDDEN_CONTEXT_VIOLATION" in r for r in res.relevance_rejection_reasons)


# ── 11. CandidateEvidenceEvaluator rejects candidate failing semantic relevance

def test_evaluator_rejects_unrelated_candidate():
    evaluator = CandidateEvidenceEvaluator()
    cand = RetrievalCandidate(
        candidate_id="c_graveyard",
        movie_id="4",
        start=10.0,
        end=15.0,
        source="TEST",
        retrieval_score=0.20,
        metadata={"title": "Graveyard standoff", "visual_description": "Dark cemetery tombstone duel", "location": "Little Hangleton"},
    )
    beat = VisualBeat(
        beat_id="b_sorting",
        narration_start=0.0,
        narration_end=4.0,
        text_span="Professor McGonagall placed the Sorting Hat upon Harry's head",
        visual_assertion="Sorting ceremony in Great Hall",
        required_entities=["Harry Potter"],
        required_objects=["sorting_hat"],
    )

    res = evaluator.evaluate_candidate(cand, beat)
    assert res.is_rejected is True
    assert "SEMANTIC_RELEVANCE_FAILED" in res.rejection_reason


# ── 12. CandidateArbitrator fails closed when relevance fails ──────────────────

def test_arbitrator_fails_closed_on_relevance_failure():
    arbitrator = CandidateArbitrator()
    b1 = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=3.0,
        text_span="The Sorting Hat spoke to Harry",
        visual_assertion="Sorting Hat speaks",
        required_entities=["Harry Potter"],
        coverage_requirement=CoverageRequirement.DIRECT,
    )

    # Candidate was rejected during semantic evaluation
    cand_rejected = EvaluatedCandidate(
        candidate_id="c_bad",
        beat_id="b1",
        source_movie_id=3,
        source_video="m3_camera_pan_hogwarts.mp4",
        source_interval=(0.0, 5.0),
        verified_sub_interval=(0.0, 5.0),
        is_rejected=True,
        rejection_reason="SEMANTIC_RELEVANCE_FAILED: FORBIDDEN_CONTEXT_VIOLATION",
    )

    entries, audit = arbitrator.arbitrate_timeline(
        beats=[b1],
        evaluated_candidates_by_beat={"b1": [cand_rejected]},
    )

    # Fail closed: must produce UNFULFILLED entry rather than accepting bad footage
    assert len(entries) == 1
    assert entries[0].coverage_state == CoverageState.UNFULFILLED
    assert entries[0].source_video == "NONE"
