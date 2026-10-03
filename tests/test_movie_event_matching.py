"""
STORY FORGE — V2 Movie Event Matching Engine Focused Test Suite
===============================================================
Tests all components of the Phase 1 visual intelligence layer:
  1. MovieEvent model & purely observable physical claims
  2. VisualBeat & VisualStoryboard model structures
  3. Abstract vs Visualizable claim classification
  4. No-direct-visual-event handling & rewrite recommendations
  5. Event query generation from VisualBeat
  6. Exact subject matching
  7. Exact action matching
  8. Target and object matching
  9. Interaction and location matching
  10. Event-chain context retrieval (Preceding -> Core -> Following)
  11. Wrong-action rejection veto (Action Mismatch)
  12. Generic semantic match rejection
  13. End-to-end benchmark validation across the 4 canonical test queries
"""

import pytest
from engines.movie_event.models import (
    MovieEvent,
    VisualBeat,
    VisualStoryboard,
    MovieEventQuery,
    ClaimClassification,
    ClaimType,
    EventVerificationResult,
    VerificationStatus,
)
from engines.movie_event.index import MovieEventIndex
from engines.movie_event.storyboard_generator import VisualStoryboardGenerator, ClaimTransformer
from engines.movie_event.retrieval_engine import MovieEventRetrievalEngine
from engines.movie_event.verifier import MovieEventVisualVerifier


@pytest.fixture
def index():
    return MovieEventIndex()


@pytest.fixture
def retrieval_engine(index):
    return MovieEventRetrievalEngine(index)


@pytest.fixture
def verifier():
    return MovieEventVisualVerifier()


@pytest.fixture
def storyboard_gen():
    return VisualStoryboardGenerator()


# ------------------------------------------------------------------------------
# 1. MOVIE EVENT MODEL & OBSERVABLE CLAIMS
# ------------------------------------------------------------------------------
def test_movie_event_model_creation_and_observable_claims():
    evt = MovieEvent(
        event_id="evt_test_01",
        movie_id="hp_movie_1",
        movie_number=1,
        scene_id="scene_01",
        start_time=10.0,
        end_time=15.0,
        characters_present=["Harry Potter"],
        primary_subject="Harry Potter",
        action="opens the wooden door",
        target="wooden door",
        interaction_type="physical",
        location="Gryffindor Dormitory",
        visual_description="Harry pushes open the heavy wooden door.",
        observable_claims=["Harry opens door", "Door swings open"],
        unsupported_claims=["Harry wonders what Ron is doing"],
        confidence=1.0,
    )
    assert evt.event_id == "evt_test_01"
    assert evt.duration == 5.0
    assert "Harry opens door" in evt.observable_claims
    assert "Harry wonders what Ron is doing" in evt.unsupported_claims


# ------------------------------------------------------------------------------
# 2. VISUAL BEAT & STORYBOARD MODEL
# ------------------------------------------------------------------------------
def test_visual_beat_and_storyboard_structure():
    beat = VisualBeat(
        beat_id="beat_01",
        start_time=0.0,
        end_time=3.0,
        narrative_text="Snape's first words to Harry were a test.",
        narrative_role="INTRODUCE_CONFRONTATION",
        required_subjects=["Snape", "Harry"],
        required_action="questions and confronts Harry",
        required_target="Harry",
        required_location="Potions classroom",
        forbidden_visuals=["Snape alone", "Harry alone", "generic corridor walking"],
    )
    assert beat.narrative_role == "INTRODUCE_CONFRONTATION"
    assert "Snape alone" in beat.forbidden_visuals

    storyboard = VisualStoryboard(
        storyboard_id="sb_01",
        title="Snape First Words",
        beats=[beat],
        total_duration=3.0,
    )
    assert len(storyboard.beats) == 1
    assert storyboard.total_duration == 3.0


# ------------------------------------------------------------------------------
# 3. ABSTRACT VS VISUALIZABLE CLASSIFICATION
# ------------------------------------------------------------------------------
def test_abstract_vs_visualizable_classification():
    # Direct physical claim
    res_direct = ClaimTransformer.classify_claim("Harry opens the Chamber of Secrets entrance.")
    assert res_direct.classification == ClaimType.DIRECTLY_VISUALIZABLE
    assert res_direct.is_directly_visualizable is True
    assert res_direct.demonstrable_action == "opens"

    # Abstract internal claim
    res_abstract = ClaimTransformer.classify_claim("Snape secretly suspected Harry was connected to the Dark Lord.")
    assert res_abstract.classification == ClaimType.ABSTRACT_NOT_DIRECTLY_VISUALIZABLE
    assert res_abstract.is_directly_visualizable is False
    assert "secret" in res_abstract.abstract_elements or "suspected" in res_abstract.abstract_elements


# ------------------------------------------------------------------------------
# 4. NO DIRECT VISUAL EVENT & REWRITE RECOMMENDATION
# ------------------------------------------------------------------------------
def test_no_direct_visual_event_and_rewrite_recommendation():
    claim = "Snape secretly suspected Harry."
    classification = ClaimTransformer.classify_claim(claim)
    assert classification.is_directly_visualizable is False
    assert "NO_DIRECT_VISUAL_EVENT" in (classification.rejection_notice or "")
    assert classification.recommended_rewrite is not None
    assert "watched Harry closely" in classification.recommended_rewrite


# ------------------------------------------------------------------------------
# 5. EVENT QUERY GENERATION
# ------------------------------------------------------------------------------
def test_event_query_generation(storyboard_gen):
    beat, _ = storyboard_gen.generate_beat_from_narration(
        beat_id="beat_test",
        narration_text="Hermione punches Malfoy on the hill.",
        start_time=0.0,
        end_time=2.5,
    )
    query = storyboard_gen.create_event_query(beat)
    assert query.subject == "Hermione Granger"
    assert "punch" in query.action.lower()
    assert query.target == "Draco Malfoy"
    assert "Hermione Granger alone" in query.forbidden_elements


# ------------------------------------------------------------------------------
# 6. EXACT SUBJECT MATCHING
# ------------------------------------------------------------------------------
def test_exact_subject_matching(retrieval_engine):
    # Query specifying Neville Longbottom
    query = MovieEventQuery(subject="Neville Longbottom", action="draws")
    results = retrieval_engine.retrieve_events(query, top_k=5)
    assert len(results) > 0
    top_event = results[0][0]
    assert top_event.primary_subject == "Neville Longbottom"


# ------------------------------------------------------------------------------
# 7. EXACT ACTION MATCHING
# ------------------------------------------------------------------------------
def test_exact_action_matching(retrieval_engine):
    # Query for punching
    query = MovieEventQuery(subject="Hermione Granger", action="punches", target="Draco Malfoy")
    results = retrieval_engine.retrieve_events(query, top_k=3)
    top_event, score, breakdown = results[0]
    assert top_event.event_id == "evt_m3_sundial_hermione_punches_malfoy"
    assert breakdown["action"] > 30.0


# ------------------------------------------------------------------------------
# 8. TARGET AND OBJECT MATCHING
# ------------------------------------------------------------------------------
def test_target_and_object_matching(retrieval_engine):
    query = MovieEventQuery(
        subject="Neville Longbottom",
        action="draws",
        target="Sword of Gryffindor",
        objects=["Sorting Hat", "Sword of Gryffindor"],
    )
    results = retrieval_engine.retrieve_events(query, top_k=3)
    top_event, score, breakdown = results[0]
    assert top_event.event_id == "evt_m8_courtyard_neville_draws_sword"
    assert breakdown["target"] == 15.0


# ------------------------------------------------------------------------------
# 9. INTERACTION AND LOCATION MATCHING
# ------------------------------------------------------------------------------
def test_interaction_and_location_matching(retrieval_engine):
    query = MovieEventQuery(
        subject="Severus Snape",
        action="questions",
        target="Harry Potter",
        location="Potions classroom",
        interaction="teacher_student_confrontation",
    )
    results = retrieval_engine.retrieve_events(query, top_k=3)
    top_event, score, breakdown = results[0]
    assert top_event.event_id == "evt_m1_potions_snape_questions_harry"
    assert breakdown["location"] == 10.0
    assert breakdown["interaction"] == 10.0


# ------------------------------------------------------------------------------
# 10. EVENT-CHAIN RETRIEVAL TRIPLET
# ------------------------------------------------------------------------------
def test_event_chain_retrieval_triplet(retrieval_engine):
    core_id = "evt_m1_potions_snape_questions_harry"
    chain = retrieval_engine.retrieve_event_chain(core_id)
    assert chain["core"] is not None
    assert chain["core"].event_id == core_id
    assert chain["preceding"] is not None
    assert chain["preceding"].event_id == "evt_m1_potions_snape_walks_toward_harry"
    assert chain["following"] is not None
    assert chain["following"].event_id == "evt_m1_potions_harry_defends_self"


# ------------------------------------------------------------------------------
# 11. WRONG-ACTION REJECTION VETO
# ------------------------------------------------------------------------------
def test_wrong_action_rejection_veto(index, verifier):
    # Required: Snape questions Harry
    # Candidate: Snape walking alone in corridor
    candidate = index.get_event("evt_m1_potions_snape_walks_alone_distractor")
    assert candidate is not None

    query = MovieEventQuery(
        subject="Severus Snape",
        action="questions",
        target="Harry Potter",
    )
    verification = verifier.verify_event(candidate, query)
    assert verification.is_verified is False
    assert verification.status == VerificationStatus.REJECT_ACTION_MISMATCH
    assert "ACTION MISMATCH" in verification.explanation


# ------------------------------------------------------------------------------
# 12. GENERIC SEMANTIC MATCH REJECTION
# ------------------------------------------------------------------------------
def test_generic_semantic_match_rejection(index, verifier):
    # Required: Harry opens Chamber of Secrets entrance
    # Candidate: Harry wading through flooded bathroom (semantically related to Myrtle's bathroom, but wrong action)
    candidate = index.get_event("evt_m2_bathroom_harry_stares_flooded_distractor")
    assert candidate is not None

    query = MovieEventQuery(
        subject="Harry Potter",
        action="opens",
        target="Chamber of Secrets entrance",
    )
    verification = verifier.verify_event(candidate, query)
    assert verification.is_verified is False
    assert verification.status == VerificationStatus.REJECT_ACTION_MISMATCH


# ------------------------------------------------------------------------------
# 13. BENCHMARK RETRIEVAL FOR ALL 4 CANONICAL TEST QUERIES
# ------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "query_text,expected_event_id,expected_movie",
    [
        ("Snape questions Harry in Potions classroom.", "evt_m1_potions_snape_questions_harry", 1),
        ("Neville draws the Sword of Gryffindor.", "evt_m8_courtyard_neville_draws_sword", 8),
        ("Harry opens the Chamber of Secrets entrance.", "evt_m2_bathroom_harry_speaks_parseltongue_opens_chamber", 2),
        ("Hermione punches Malfoy.", "evt_m3_sundial_hermione_punches_malfoy", 3),
    ]
)
def test_canonical_benchmark_queries(query_text, expected_event_id, expected_movie, storyboard_gen, retrieval_engine, verifier):
    beat, _ = storyboard_gen.generate_beat_from_narration("test_beat", query_text, 0.0, 3.0)
    query = storyboard_gen.create_event_query(beat)
    ranked = retrieval_engine.retrieve_events(query, top_k=5)
    assert len(ranked) > 0

    top_event = ranked[0][0]
    assert top_event.event_id == expected_event_id
    assert top_event.movie_number == expected_movie

    verification = verifier.verify_event(top_event, beat)
    assert verification.is_verified is True
    assert verification.status == VerificationStatus.VERIFIED
