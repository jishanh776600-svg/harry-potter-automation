"""
STORY FORGE — Narrative Integrity Gate V2 Test Suite
====================================================
Comprehensive regression and adversarial tests validating:
  1. CHARACTER_PRESENT != CLAIM_SUPPORTED
  2. OBJECT_PRESENT != CLAIM_SUPPORTED
  3. LOCATION_PRESENT != CLAIM_SUPPORTED
  4. MOVIE_RELEVANCE != CLAIM_SUPPORTED
  5. HARRY_POTTER_CONTEXT != CLAIM_SUPPORTED

Mandatory Scenarios:
  Scenario A: Sorting Hat + lake scenery -> REJECT
  Scenario B: Sorting Hat + Ollivander wand shop -> REJECT
  Scenario C: Sorting Hat + Quidditch -> REJECT
  Scenario D: Sorting Hat + Buckbeak/lake -> REJECT
  Scenario E: Sorting Hat + correct Sorting Ceremony footage -> ACCEPT
  Scenario F: Internal Hat-thought claim + Harry wearing Sorting Hat -> not classified as direct physical proof
  Scenario G: Quidditch + Ollivander footage -> REJECT
  Scenario H: Correct Quidditch narration + correct Quidditch footage -> ACCEPT
  Scenario I: Same character + wrong movie event -> REJECT
  Scenario J: Correct character + correct location + wrong action -> REJECT

Adversarial Tests:
  - Same character / wrong event
  - Same location / wrong event
  - Character close-up without context / wrong action
  - Correct event / wrong relationship

Contract Hash & Lineage Verification:
  - Cryptographic binding between NarrativeEvidenceContract, CandidateEvidenceEvaluator, and CandidateArbitrator
  - Strict enforcement: RELATED_CLIP_FALLBACK = BLOCKED
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
    EDLEntry,
)
from engines.edl.beat_compiler import VisualBeatCompiler
from engines.edl.candidate_evaluator import CandidateEvidenceEvaluator
from engines.edl.arbitration import CandidateArbitrator
from engines.retrieval.models import RetrievalCandidate


@pytest.fixture
def relevance_evaluator():
    return SemanticRelevanceEvaluator()


# ==============================================================================
# 10 MANDATORY REGRESSION SCENARIOS (A THROUGH J)
# ==============================================================================

# Scenario A: Sorting Hat + lake scenery -> REJECT
def test_scenario_a_sorting_hat_with_lake_scenery(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="scen_a",
        claim_text="The Sorting Hat deliberated intensely over Harry Potter's house placement.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_scene_event="sorting_ceremony",
        required_location="Great Hall",
        forbidden_contexts=["lake", "black lake", "quidditch", "forest"],
        forbidden_locations=["Black Lake", "Lake", "Forbidden Forest"],
        direct_visual_mandatory=True,
    )
    cand_meta = {
        "candidate_id": "cand_lake_wide",
        "title": "Black Lake Scenic Sunset View",
        "visual_description": "Wide panoramic landscape across the Black Lake with distant Hogwarts turrets",
        "action": "camera landscape pan",
        "location": "Black Lake",
        "source_video": "m3_camera_pan_hogwarts.mp4",
        "characters_present": [],
        "verified_entities": [],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.overall_relevance_score == 0.0
    assert result.forbidden_context_passed is False
    assert any("FORBIDDEN" in r for r in result.rejection_reasons)


# Scenario B: Sorting Hat + Ollivander wand shop -> REJECT
def test_scenario_b_sorting_hat_with_ollivander_wand_shop(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="scen_b",
        claim_text="The ancient Sorting Hat evaluated Harry's potential.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_scene_event="sorting_ceremony",
        required_location="Great Hall",
        forbidden_contexts=["diagon alley", "ollivander", "wand shop"],
        forbidden_locations=["Diagon Alley", "Ollivanders Wand Shop"],
        forbidden_events=["ollivander_wand_selection"],
        direct_visual_mandatory=True,
    )
    cand_meta = {
        "candidate_id": "cand_ollivander_boxes",
        "title": "Harry Selects First Wand at Ollivanders",
        "visual_description": "Harry Potter holds a magic wand while wand boxes tumble from dusty shelves",
        "action": "waves wand",
        "location": "Ollivanders Wand Shop",
        "movie_event_id": "ollivander_wand_selection",
        "source_video": "m1_ollivander_wand.mp4",
        "characters_present": ["Harry Potter", "Garrick Ollivander"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["wand"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.overall_relevance_score == 0.0
    assert result.forbidden_context_passed is False
    assert any("FORBIDDEN" in r for r in result.rejection_reasons)


# Scenario C: Sorting Hat + Quidditch -> REJECT
def test_scenario_c_sorting_hat_with_quidditch(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="scen_c",
        claim_text="Placed upon the boy's head, the Sorting Hat weighed Slytherin against Gryffindor.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_scene_event="sorting_ceremony",
        forbidden_contexts=["quidditch", "snitch", "quaffle", "broom", "pitch"],
        forbidden_locations=["Quidditch Pitch"],
        forbidden_events=["quidditch_match"],
        direct_visual_mandatory=True,
    )
    cand_meta = {
        "candidate_id": "cand_quidditch_dive",
        "title": "Harry Dives for Golden Snitch",
        "visual_description": "Harry speeds on his broomstick diving steeply toward the grassy Quidditch pitch",
        "action": "broomstick dive",
        "location": "Quidditch Pitch",
        "movie_event_id": "quidditch_match",
        "source_video": "m1_snitch_catch.mp4",
        "characters_present": ["Harry Potter"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["broomstick", "golden snitch"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.overall_relevance_score == 0.0
    assert result.forbidden_context_passed is False


# Scenario D: Sorting Hat + Buckbeak/lake -> REJECT
def test_scenario_d_sorting_hat_with_buckbeak_lake(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="scen_d",
        claim_text="The Sorting Hat considered Harry Potter for Slytherin.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_scene_event="sorting_ceremony",
        forbidden_contexts=["buckbeak", "hippogriff", "lake"],
        forbidden_subjects=["Buckbeak"],
        forbidden_locations=["Black Lake"],
        direct_visual_mandatory=True,
    )
    cand_meta = {
        "candidate_id": "cand_buckbeak_glide",
        "title": "Buckbeak Gliding Across Lake",
        "visual_description": "Buckbeak the hippogriff glides serenely above the rippling waters of Black Lake",
        "action": "flying",
        "location": "Black Lake",
        "source_video": "m3_buckbeak_flight.mp4",
        "characters_present": ["Buckbeak"],
        "verified_entities": ["Buckbeak"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.overall_relevance_score == 0.0
    assert result.forbidden_context_passed is False
    assert any("FORBIDDEN_SUBJECT" in r or "FORBIDDEN_CONTEXT" in r for r in result.rejection_reasons)


# Scenario E: Sorting Hat + correct Sorting Ceremony footage -> ACCEPT
def test_scenario_e_sorting_hat_correct_ceremony_accepted(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="scen_e",
        claim_text="When placed on his head, the Sorting Hat debated putting Harry in Slytherin.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_action="hat placed on head",
        required_location="Great Hall",
        required_scene_event="sorting_ceremony",
        forbidden_contexts=["quidditch", "lake", "diagon alley", "forest"],
        direct_visual_mandatory=True,
        min_semantic_relevance_threshold=0.65,
    )
    cand_meta = {
        "candidate_id": "cand_sorting_hat_placed",
        "title": "Sorting Hat Placed on Harry Head in Great Hall",
        "visual_description": "Professor McGonagall places the ragged brown Sorting Hat onto young Harry Potter's head before the Great Hall tables",
        "action": "hat placed on head",
        "location": "Great Hall",
        "movie_event_id": "sorting_ceremony",
        "source_video": "m1_sorting_ceremony.mp4",
        "characters_present": ["Harry Potter", "Minerva McGonagall"],
        "verified_entities": ["Harry Potter", "Sorting Hat"],
        "visible_objects": ["Sorting Hat", "stool"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.ACCEPT
    assert result.is_accepted is True
    assert result.overall_relevance_score >= 0.65
    assert result.subject_match is True
    assert result.action_match is True
    assert result.object_target_match is True
    assert result.location_context_match is True
    assert result.temporal_event_match is True
    assert result.forbidden_context_passed is True


# Scenario F: Internal Hat-thought claim + Harry wearing Sorting Hat -> not classified as direct physical proof
def test_scenario_f_internal_thought_not_classified_as_direct_physical_proof(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="scen_f",
        claim_text="The Hat sensed Harry's secret internal ambition and hesitated.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_scene_event="sorting_ceremony",
        direct_visual_mandatory=False,
        is_inherently_non_visual=True,
    )
    # If candidate falsely claims to be DIRECT physical proof of an internal thought:
    cand_claimed_direct = {
        "candidate_id": "cand_sorting_closeup",
        "title": "Harry Wearing Sorting Hat",
        "visual_description": "Close-up of Harry Potter under the Sorting Hat whispering 'not Slytherin'",
        "action": "whispering",
        "location": "Great Hall",
        "movie_event_id": "sorting_ceremony",
        "source_video": "m1_sorting_ceremony.mp4",
        "characters_present": ["Harry Potter"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["Sorting Hat"],
        "is_claimed_direct": True,  # Cannot claim direct proof of invisible mental state
    }
    result_direct = relevance_evaluator.evaluate_relevance(cand_claimed_direct, contract)
    assert result_direct.verdict == RelevanceVerdict.REJECT
    assert result_direct.directness_requirement_satisfied is False
    assert any("INHERENTLY_NON_VISUAL" in r for r in result_direct.rejection_reasons)

    # When evaluated as contextual / optional:
    cand_contextual = dict(cand_claimed_direct)
    cand_contextual["is_claimed_direct"] = False
    result_ctx = relevance_evaluator.evaluate_relevance(cand_contextual, contract)
    assert result_ctx.verdict == RelevanceVerdict.ACCEPT
    assert result_ctx.directness_requirement_satisfied is True


# Scenario G: Quidditch + Ollivander footage -> REJECT
def test_scenario_g_quidditch_with_ollivander_footage(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="scen_g",
        claim_text="Harry caught the golden snitch in his mouth during his debut Quidditch match.",
        required_subjects=["Harry Potter"],
        required_objects=["golden snitch"],
        required_action="catches snitch",
        required_location="Quidditch Pitch",
        required_scene_event="quidditch_match",
        forbidden_contexts=["ollivander", "wand shop", "diagon alley"],
        forbidden_locations=["Ollivanders Wand Shop"],
        forbidden_events=["ollivander_wand_selection"],
        direct_visual_mandatory=True,
    )
    cand_meta = {
        "candidate_id": "cand_ollivander_handing_wand",
        "title": "Ollivander Hands Harry Wand",
        "visual_description": "Garrick Ollivander gently passes an eleven-inch holly wand to Harry inside the Diagon Alley shop",
        "action": "hands wand",
        "location": "Ollivanders Wand Shop",
        "movie_event_id": "ollivander_wand_selection",
        "source_video": "m1_ollivander_wand.mp4",
        "characters_present": ["Harry Potter", "Garrick Ollivander"],
        "verified_entities": ["Harry Potter", "Garrick Ollivander"],
        "visible_objects": ["wand"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.overall_relevance_score == 0.0
    assert result.forbidden_context_passed is False
    assert any("FORBIDDEN" in r for r in result.rejection_reasons)


# Scenario H: Correct Quidditch narration + correct Quidditch footage -> ACCEPT
def test_scenario_h_correct_quidditch_accepted(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="scen_h",
        claim_text="Harry caught the golden snitch during his first Quidditch match.",
        required_subjects=["Harry Potter"],
        required_objects=["golden snitch"],
        required_action="catch",
        required_location="Quidditch Pitch",
        required_scene_event="quidditch_match",
        forbidden_contexts=["ollivander", "wand shop", "great hall sorting"],
        direct_visual_mandatory=True,
    )
    cand_meta = {
        "candidate_id": "cand_snitch_catch_actual",
        "title": "Harry Catches Snitch on Quidditch Pitch",
        "visual_description": "Harry Potter catches the golden snitch in midair while balancing on his Nimbus broomstick above the pitch",
        "action": "catch",
        "location": "Quidditch Pitch",
        "movie_event_id": "quidditch_match",
        "source_video": "m1_snitch_catch.mp4",
        "characters_present": ["Harry Potter"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["golden snitch", "broomstick"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.ACCEPT
    assert result.is_accepted is True
    assert result.overall_relevance_score >= 0.65
    assert result.subject_match is True
    assert result.action_match is True
    assert result.object_target_match is True
    assert result.location_context_match is True
    assert result.temporal_event_match is True


# Scenario I: Same character + wrong movie event -> REJECT
def test_scenario_i_same_character_wrong_movie_event(relevance_evaluator):
    # Narration describes Harry at the Diagon Alley wand shop
    contract = NarrativeEvidenceContract(
        claim_id="scen_i",
        claim_text="Eleven-year-old Harry received his wand from Ollivander in Diagon Alley.",
        required_subjects=["Harry Potter"],
        required_objects=["wand"],
        required_scene_event="ollivander_wand_selection",
        required_location="Ollivanders Wand Shop",
        direct_visual_mandatory=True,
    )
    # Candidate shows Harry in Deathly Hallows Battle of Hogwarts
    cand_meta = {
        "candidate_id": "cand_harry_battle",
        "title": "Harry in Battle of Hogwarts",
        "visual_description": "Battle-weary adult Harry Potter runs through crumbling castle courtyard firing spells",
        "action": "running and firing spell",
        "location": "Courtyard Ruins",
        "movie_event_id": "battle_of_hogwarts",
        "source_video": "m8_courtyard_battle.mp4",
        "characters_present": ["Harry Potter"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["wand"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.overall_relevance_score == 0.0  # Hard veto triggered by event mismatch
    assert result.temporal_event_match is False
    assert result.location_context_match is False
    assert any("EVENT_MISMATCH" in r for r in result.rejection_reasons)


# Scenario J: Correct character + correct location + wrong action -> REJECT
def test_scenario_j_correct_char_and_location_wrong_action(relevance_evaluator):
    # Claim requires placing the Sorting Hat on Harry's head
    contract = NarrativeEvidenceContract(
        claim_id="scen_j",
        claim_text="The Sorting Hat was placed firmly onto Harry's head.",
        required_subjects=["Harry Potter"],
        required_objects=["Sorting Hat"],
        required_action="hat placed on head",
        required_location="Great Hall",
        required_scene_event="sorting_ceremony",
        direct_visual_mandatory=True,
    )
    # Candidate shows Harry in the Great Hall, but eating breakfast / chatting with Ron
    cand_meta = {
        "candidate_id": "cand_harry_eating_greathall",
        "title": "Harry Eating Breakfast in Great Hall",
        "visual_description": "Harry Potter sits at the Gryffindor table eating toast and talking with friends",
        "action": "eating breakfast",
        "location": "Great Hall",
        "movie_event_id": "great_hall_feast",
        "source_video": "m1_breakfast_feast.mp4",
        "characters_present": ["Harry Potter", "Ron Weasley"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["toast", "goblet"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.is_accepted is False
    assert result.overall_relevance_score == 0.0  # Hard veto on action and object mismatch
    assert result.action_match is False
    assert result.object_target_match is False
    assert any("ACTION_MISMATCH" in r for r in result.rejection_reasons)


# ==============================================================================
# ADVERSARIAL TESTS
# ==============================================================================

# Adversarial 1: Same character / wrong event (Harry reading in common room vs. dueling Voldemort)
def test_adversarial_same_character_wrong_event(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="adv_1",
        claim_text="Harry Potter locked wands in Priori Incantatem against Lord Voldemort in the graveyard.",
        required_subjects=["Harry Potter", "Lord Voldemort"],
        required_action="duel",
        required_location="Little Hangleton Graveyard",
        required_scene_event="graveyard_duel",
        forbidden_contexts=["common room", "dormitory", "classroom"],
        direct_visual_mandatory=True,
    )
    cand_meta = {
        "candidate_id": "cand_harry_reading",
        "title": "Harry Studying in Gryffindor Tower",
        "visual_description": "Harry Potter relaxes on a crimson armchair reading an ancient spell book",
        "action": "reading",
        "location": "Gryffindor Common Room",
        "movie_event_id": "common_room_study",
        "source_video": "m4_common_room.mp4",
        "characters_present": ["Harry Potter"],
        "verified_entities": ["Harry Potter"],
        "visible_objects": ["book"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.overall_relevance_score == 0.0
    assert result.subject_match is False
    assert result.action_match is False
    assert result.location_context_match is False


# Adversarial 2: Same location / wrong event (Great Hall feast vs Great Hall duel)
def test_adversarial_same_location_wrong_event(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="adv_2",
        claim_text="Molly Weasley destroyed Bellatrix Lestrange in the Great Hall duel.",
        required_subjects=["Molly Weasley", "Bellatrix Lestrange"],
        required_action="duel",
        required_location="Great Hall",
        required_scene_event="great_hall_final_battle",
        direct_visual_mandatory=True,
    )
    cand_meta = {
        "candidate_id": "cand_welcoming_feast",
        "title": "Start of Term Welcoming Feast in Great Hall",
        "visual_description": "Candles float above four house tables laden with roasted meats and desserts in the Great Hall",
        "action": "camera crane pan over dining tables",
        "location": "Great Hall",
        "movie_event_id": "start_of_term_feast",
        "source_video": "m1_welcoming_feast.mp4",
        "characters_present": ["Albus Dumbledore"],
        "verified_entities": ["Albus Dumbledore"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.overall_relevance_score == 0.0
    assert result.subject_match is False
    assert result.action_match is False
    assert result.temporal_event_match is False


# Adversarial 3: Character close-up without context / wrong action
def test_adversarial_character_closeup_wrong_action(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="adv_3",
        claim_text="Hermione Granger punched Draco Malfoy squarely in the face on the sundial hill.",
        required_subjects=["Hermione Granger", "Draco Malfoy"],
        required_action="punch",
        required_location="Sundial Hill",
        required_scene_event="malfoy_punch",
        direct_visual_mandatory=True,
    )
    # Close-up of Hermione smiling in library
    cand_meta = {
        "candidate_id": "cand_hermione_library_smile",
        "title": "Hermione Smiling in Library",
        "visual_description": "Tight portrait close-up of Hermione Granger smiling warmly over a stack of library books",
        "action": "smiling",
        "location": "Hogwarts Library",
        "movie_event_id": "library_research",
        "source_video": "m2_library_smile.mp4",
        "characters_present": ["Hermione Granger"],
        "verified_entities": ["Hermione Granger"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.overall_relevance_score == 0.0
    assert result.action_match is False
    assert result.subject_match is False  # Missing Draco Malfoy


# Adversarial 4: Correct event / wrong relationship
def test_adversarial_correct_event_wrong_relationship(relevance_evaluator):
    contract = NarrativeEvidenceContract(
        claim_id="adv_4",
        claim_text="Hermione Granger struck Draco Malfoy with a forceful punch.",
        required_subjects=["Hermione Granger", "Draco Malfoy"],
        required_action="punch",
        required_relationship="Hermione Granger attacks Draco Malfoy",
        required_scene_event="malfoy_punch",
        direct_visual_mandatory=True,
    )
    # Candidate where Malfoy points wand at Harry (not Hermione striking Malfoy)
    cand_meta = {
        "candidate_id": "cand_draco_taunting",
        "title": "Draco Malfoy Taunts Trio",
        "visual_description": "Draco Malfoy sneers and taunts Harry Potter with his wand drawn near the sundial",
        "action": "taunt",
        "location": "Sundial Hill",
        "movie_event_id": "malfoy_punch",
        "source_video": "m3_sundial_hill.mp4",
        "characters_present": ["Draco Malfoy", "Harry Potter"],
        "verified_entities": ["Draco Malfoy", "Harry Potter"],
        "is_claimed_direct": True,
    }
    result = relevance_evaluator.evaluate_relevance(cand_meta, contract)
    assert result.verdict == RelevanceVerdict.REJECT
    assert result.overall_relevance_score == 0.0
    assert result.action_match is False
    assert result.relationship_match is False


# ==============================================================================
# PIPELINE INTEGRATION & STRICT ARBITRATION FAIL-CLOSED (NO FALLBACK)
# ==============================================================================

def test_pipeline_arbitrator_blocks_related_clip_fallback():
    """
    Verifies that CandidateArbitrator enforces RELATED_CLIP_FALLBACK = BLOCKED.
    When a candidate fails the narrative integrity gate, the arbitrator must
    fail-closed (UNFULFILLED) rather than picking an irrelevant or related Harry Potter clip.
    """
    arbitrator = CandidateArbitrator()
    b1 = VisualBeat(
        beat_id="b1",
        narration_start=0.0,
        narration_end=3.5,
        text_span="The Sorting Hat deliberated Harry's true potential.",
        visual_assertion="Sorting Hat deliberates on Harry's head",
        required_entities=["Harry Potter", "Sorting Hat"],
        coverage_requirement=CoverageRequirement.DIRECT,
    )

    # Candidate 1: Completely rejected due to forbidden lake context
    cand_lake = EvaluatedCandidate(
        candidate_id="cand_lake_rejected",
        beat_id="b1",
        source_movie_id=3,
        source_video="m3_lake_pan.mp4",
        source_interval=(10.0, 14.0),
        verified_sub_interval=(10.0, 14.0),
        is_rejected=True,
        rejection_reason="SEMANTIC_RELEVANCE_FAILED: FORBIDDEN_CONTEXT_VIOLATION",
    )

    # Candidate 2: Also rejected due to action mismatch
    cand_eating = EvaluatedCandidate(
        candidate_id="cand_eating_rejected",
        beat_id="b1",
        source_movie_id=1,
        source_video="m1_eating_feast.mp4",
        source_interval=(50.0, 54.0),
        verified_sub_interval=(50.0, 54.0),
        is_rejected=True,
        rejection_reason="SEMANTIC_RELEVANCE_FAILED: ACTION_MISMATCH",
    )

    entries, audit = arbitrator.arbitrate_timeline(
        beats=[b1],
        evaluated_candidates_by_beat={"b1": [cand_lake, cand_eating]},
    )

    assert len(entries) == 1
    entry = entries[0]
    # Invariant: NO fallback to an arbitrary clip
    assert entry.coverage_state == CoverageState.UNFULFILLED
    assert entry.source_video == "NONE"
    assert entry.evidence_class == "UNFULFILLED"
    assert entry.confidence == 0.0
    assert audit.passed is True


def test_contract_hash_cryptographic_lineage():
    """
    Verifies that changing any evidentiary constraint alters the contract hash,
    invalidating stale evidence lineage across compiler runs.
    """
    contract_base = NarrativeEvidenceContract(
        claim_id="c_hash_test",
        claim_text="Harry caught the golden snitch.",
        required_subjects=["Harry Potter"],
        required_objects=["golden snitch"],
        required_action="catch",
        required_location="Quidditch Pitch",
        required_scene_event="quidditch_match",
        forbidden_contexts=["wand shop", "lake"],
        direct_visual_mandatory=True,
        contract_version="v2.0",
    )
    hash_base = contract_base.compute_contract_hash()
    assert isinstance(hash_base, str) and len(hash_base) == 16

    # Adding a forbidden location MUST alter the contract hash
    contract_modified = contract_base.model_copy(
        update={"forbidden_locations": ["Ollivanders Wand Shop"]}
    )
    hash_mod = contract_modified.compute_contract_hash()
    assert hash_mod != hash_base

    # Altering the required action MUST alter the contract hash
    contract_act_mod = contract_base.model_copy(
        update={"required_action": "fly"}
    )
    hash_act_mod = contract_act_mod.compute_contract_hash()
    assert hash_act_mod != hash_base
