"""
STORY FORGE — Tests for THE BEAST Visual Matching Engine
================================================================================
Focused test suite covering all 17 core capabilities:
  1. Visual requirement generation
  2. Shot detection
  3. 5-frame temporal sequence sampling (10%, 30%, 50%, 70%, 90%)
  4. Semantic retrieval and ranking
  5. Character verification
  6. Object verification
  7. Action verification
  8. Location verification
  9. Temporal coherence
  10. Contradiction rejection (Year 1 Sorting vs Year 7 Battle)
  11. Vision-Language verification gate
  12. Multi-stage candidate reranking
  13. NO_VALID_VISUAL fail-closed behavior
  14. Exact timestamp extraction
  15. Deterministic fingerprints
  16. Existing 9:16 composition integration
  17. Existing beat-lock integration
"""

import pytest
import numpy as np
from pathlib import Path

from core.beast_visual_types import (
    BeastVisualRequirement,
    BeastCandidateShot,
    MultiFrameSample,
    NarrativeEra,
    BeastScoringWeights,
)
from core.composition_models import (
    ShotScale,
    NormalizedBBox,
    ShotCompositionAssessment,
)
from core.storyboard_types import VisualRole
from engines.beast_visual_matching_engine import BeastVisualMatchingEngine
from engines.beast.beast_shot_detector import BeastShotDetector
from engines.beast.beast_semantic_retriever import BeastSemanticRetriever
from engines.beast.beast_entity_verifiers import BeastEntityVerifiers
from engines.beast.beast_contradiction_guard import BeastContradictionGuard
from engines.beast.beast_vlm_verifier import BeastVLMVerifier
from engines.beast.beast_scoring_engine import BeastScoringEngine
from engines.remotion_editorial_engine import RemotionEditorialEngine


# ==============================================================================
# FIXTURES
# ==============================================================================
@pytest.fixture
def sample_candidate_shots():
    """Provides representative candidate shots for testing."""
    return [
        # Candidate A: Neville on stool arguing with Sorting Hat (Movie 1, Year 1)
        BeastCandidateShot(
            shot_id="shot_m1_neville_sorting_01",
            source_video="data/movies/m1.mkv",
            movie_number=1,
            start_seconds=2568.5,
            end_seconds=2574.0,
            duration=5.5,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Neville Longbottom sits terrified on the wooden stool in the Great Hall, begging the Sorting Hat placed on his head.",
            characters_present=["Neville Longbottom", "Sorting Hat"],
            detected_faces=1,
            primary_character_prominence=0.35,
            objects_present=["Sorting Hat", "Stool"],
            actions_depicted=["pleading", "sitting on stool", "arguing"],
            environment="Great Hall",
            shot_scale=ShotScale.MEDIUM_SHOT,
            composition=ShotCompositionAssessment(
                shot_scale=ShotScale.MEDIUM_SHOT,
                subject_bbox=NormalizedBBox(0.35, 0.20, 0.40, 0.70),
                is_9x16_crop_safe=True,
            ),
        ),
        # Candidate B: Neville fighting in Battle of Hogwarts with sword (Movie 8, Year 7)
        BeastCandidateShot(
            shot_id="shot_m8_neville_battle_01",
            source_video="data/movies/m8.mkv",
            movie_number=8,
            start_seconds=6168.0,
            end_seconds=6172.5,
            duration=4.5,
            narrative_era=NarrativeEra.YEAR_7,
            scene_description="Neville Longbottom with battle wounds and blood draws the Sword of Gryffindor from the tattered Sorting Hat in the ruined courtyard during the final battle.",
            characters_present=["Neville Longbottom", "Sorting Hat"],
            detected_faces=1,
            primary_character_prominence=0.45,
            objects_present=["Sword of Gryffindor", "Sorting Hat"],
            actions_depicted=["drawing sword", "fighting", "battle"],
            environment="Hogwarts Courtyard",
            shot_scale=ShotScale.MEDIUM_SHOT,
            composition=ShotCompositionAssessment(
                shot_scale=ShotScale.MEDIUM_SHOT,
                subject_bbox=NormalizedBBox(0.30, 0.15, 0.45, 0.75),
                is_9x16_crop_safe=True,
            ),
        ),
        # Candidate C: Harry staring into Mirror of Erised (Movie 1, Year 1)
        BeastCandidateShot(
            shot_id="shot_m1_harry_erised_01",
            source_video="data/movies/m1.mkv",
            movie_number=1,
            start_seconds=4200.0,
            end_seconds=4206.0,
            duration=6.0,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Harry Potter stands transfixed staring into the Mirror of Erised in an abandoned classroom, gazing at his parents reflected inside.",
            characters_present=["Harry Potter"],
            detected_faces=1,
            primary_character_prominence=0.30,
            objects_present=["Mirror of Erised"],
            actions_depicted=["staring", "looking into mirror"],
            environment="Abandoned Classroom",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
        # Candidate D: Harry running through a corridor (Movie 1, Year 1)
        BeastCandidateShot(
            shot_id="shot_m1_harry_corridor_run_01",
            source_video="data/movies/m1.mkv",
            movie_number=1,
            start_seconds=3100.0,
            end_seconds=3103.5,
            duration=3.5,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Harry Potter sprints through a stone corridor at night escaping Mrs Norris.",
            characters_present=["Harry Potter"],
            detected_faces=1,
            primary_character_prominence=0.25,
            objects_present=[],
            actions_depicted=["running", "fleeing"],
            environment="Hogwarts Corridor",
            shot_scale=ShotScale.MEDIUM_WIDE,
        ),
        # Candidate E: Snape standing in potion classroom (Movie 1, Year 1)
        BeastCandidateShot(
            shot_id="shot_m1_snape_potions_01",
            source_video="data/movies/m1.mkv",
            movie_number=1,
            start_seconds=1800.0,
            end_seconds=1804.0,
            duration=4.0,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Severus Snape turns his black cloak standing menacingly in the dark potions dungeon surrounded by cauldrons and vials.",
            characters_present=["Severus Snape"],
            detected_faces=1,
            primary_character_prominence=0.50,
            objects_present=["Potion", "Cauldron"],
            actions_depicted=["standing", "glaring"],
            environment="Dungeons",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
    ]


# ==============================================================================
# TEST 1: VISUAL REQUIREMENT GENERATION (PHASE 1)
# ==============================================================================
def test_01_visual_requirement_generation():
    engine = BeastVisualMatchingEngine()
    narration = "Terrified by family expectations, Neville begged the Sorting Hat to place him in Hufflepuff."
    req = engine.parse_narration_beat(
        beat_id="beat_01",
        narration_text=narration,
        narrative_phase="EVIDENCE",
        visual_role=VisualRole.DIRECT_EVIDENCE,
    )

    assert req.beat_id == "beat_01"
    assert req.primary_subject == "Neville Longbottom"
    assert req.secondary_subject == "Sorting Hat"
    assert "Sorting Hat" in req.required_objects
    assert "pleading" in req.required_action or "begging" in req.required_action
    assert req.expected_era == NarrativeEra.YEAR_1
    assert any("reject battle of hogwarts" in n for n in req.negative_constraints)
    assert req.visual_role == VisualRole.DIRECT_EVIDENCE


# ==============================================================================
# TEST 2 & 3: MULTI-FRAME SAMPLING (PHASE 3)
# ==============================================================================
def test_02_multi_frame_sampling(sample_candidate_shots):
    detector = BeastShotDetector()
    shot = sample_candidate_shots[0]

    # Extract multi-frame sample (simulate without writing files)
    sample = detector.extract_multi_frame_sample(shot, extract_images=False)
    assert sample.shot_id == shot.shot_id
    assert len(sample.percentiles) == 5
    assert sample.percentiles == [0.10, 0.30, 0.50, 0.70, 0.90]
    assert len(sample.timestamps) == 5

    # Check timestamps: equidistant interpolation
    expected_t = [round(shot.start_seconds + p * shot.duration, 3) for p in [0.10, 0.30, 0.50, 0.70, 0.90]]
    assert sample.timestamps == expected_t


# ==============================================================================
# TEST 4: SEMANTIC RETRIEVAL (PHASE 4)
# ==============================================================================
def test_03_semantic_retrieval(sample_candidate_shots):
    retriever = BeastSemanticRetriever()
    req = BeastVisualRequirement(
        beat_id="beat_test",
        narration_text="Neville begged the Sorting Hat for Hufflepuff.",
        primary_subject="Neville Longbottom",
        secondary_subject="Sorting Hat",
        required_action="pleading and begging",
        required_objects=["Sorting Hat", "Stool"],
    )

    results = retriever.retrieve_candidates(req, sample_candidate_shots, top_k=5)
    assert len(results) == len(sample_candidate_shots)

    # Top result should be Neville with Sorting Hat
    top_shot, top_score = results[0]
    assert "neville" in top_shot.shot_id.lower()
    assert top_score > 60.0


# ==============================================================================
# TEST 5: CHARACTER VERIFICATION (PHASE 5)
# ==============================================================================
def test_04_character_verification(sample_candidate_shots):
    verifiers = BeastEntityVerifiers()
    req = BeastVisualRequirement(
        beat_id="beat_test",
        narration_text="Neville sat before the Sorting Hat.",
        primary_subject="Neville Longbottom",
        secondary_subject="Sorting Hat",
    )

    # Candidate A: Neville + Sorting Hat
    p_score_a, s_score_a, _ = verifiers.verify_character(req, sample_candidate_shots[0])
    assert p_score_a == 100.0
    assert s_score_a == 100.0

    # Candidate C: Harry Potter
    p_score_c, s_score_c, _ = verifiers.verify_character(req, sample_candidate_shots[2])
    assert p_score_c == 0.0


# ==============================================================================
# TEST 6: OBJECT VERIFICATION (PHASE 6)
# ==============================================================================
def test_05_object_verification(sample_candidate_shots):
    verifiers = BeastEntityVerifiers()
    req = BeastVisualRequirement(
        beat_id="beat_test",
        narration_text="Looking into the Mirror of Erised.",
        required_objects=["Mirror of Erised"],
    )

    # Candidate C: Harry with Mirror of Erised
    score_c, _ = verifiers.verify_object(req, sample_candidate_shots[2])
    assert score_c == 100.0

    # Candidate D: Harry running in corridor (No mirror)
    score_d, _ = verifiers.verify_object(req, sample_candidate_shots[3])
    assert score_d == 0.0


# ==============================================================================
# TEST 7: ACTION VERIFICATION (PHASE 7)
# ==============================================================================
def test_06_action_verification(sample_candidate_shots):
    verifiers = BeastEntityVerifiers()
    req = BeastVisualRequirement(
        beat_id="beat_test",
        narration_text="Neville pleaded with the Hat.",
        required_action="pleading and begging",
    )

    # Candidate A has 'pleading' action
    score_a, _ = verifiers.verify_action(req, sample_candidate_shots[0])
    assert score_a == 100.0

    # Candidate B has 'drawing sword' and 'fighting' action
    score_b, _ = verifiers.verify_action(req, sample_candidate_shots[1])
    assert score_b < 50.0


# ==============================================================================
# TEST 8: LOCATION VERIFICATION (PHASE 8)
# ==============================================================================
def test_07_location_verification(sample_candidate_shots):
    verifiers = BeastEntityVerifiers()
    req = BeastVisualRequirement(
        beat_id="beat_test",
        narration_text="Inside the Great Hall.",
        required_location="Great Hall",
    )

    # Candidate A is in Great Hall
    score_a, _ = verifiers.verify_location(req, sample_candidate_shots[0])
    assert score_a == 100.0

    # Candidate E is in Dungeons
    score_e, _ = verifiers.verify_location(req, sample_candidate_shots[4])
    assert score_e < 50.0


# ==============================================================================
# TEST 9: CONTRADICTION REJECTION (PHASE 12)
# ==============================================================================
def test_08_contradiction_rejection(sample_candidate_shots):
    """
    CRITICAL INVARIANT:
    Narration describes Year 1 Neville begging the Sorting Hat.
    Candidate B contains Neville, but in Year 7 Battle of Hogwarts.
    Contradiction Guard must HARD-REJECT Candidate B.
    """
    guard = BeastContradictionGuard()
    req = BeastVisualRequirement(
        beat_id="beat_sorting",
        narration_text="Neville sat on that stool begging the Sorting Hat to send him to Hufflepuff.",
        primary_subject="Neville Longbottom",
        secondary_subject="Sorting Hat",
        required_action="pleading on stool with sorting hat",
        expected_era=NarrativeEra.YEAR_1,
        negative_constraints=["reject battle of hogwarts", "reject year 7", "reject sword"],
    )

    # Test Candidate A (Year 1 Sorting) -> NO contradiction
    has_contra_a, pen_a, _ = guard.evaluate_contradiction(req, sample_candidate_shots[0])
    assert has_contra_a is False
    assert pen_a == 0.0

    # Test Candidate B (Year 7 Battle) -> HARD CONTRADICTION
    has_contra_b, pen_b, reasons_b = guard.evaluate_contradiction(req, sample_candidate_shots[1])
    assert has_contra_b is True
    assert pen_b == 100.0
    assert any("Era Mismatch" in r or "Negative Constraint" in r or "Action" in r for r in reasons_b)


# ==============================================================================
# TEST 10: VLM VERIFICATION GATE (PHASE 9)
# ==============================================================================
def test_09_vlm_verification_gate(sample_candidate_shots):
    vlm = BeastVLMVerifier(mock_mode=True)
    req = BeastVisualRequirement(
        beat_id="beat_test",
        narration_text="Neville begging the Sorting Hat.",
        primary_subject="Neville Longbottom",
        secondary_subject="Sorting Hat",
        required_action="pleading and begging",
        expected_era=NarrativeEra.YEAR_1,
    )

    # Valid candidate
    verdict_valid = vlm.verify_candidate(req, sample_candidate_shots[0])
    assert verdict_valid.match is True
    assert verdict_valid.confidence >= 70.0
    assert verdict_valid.action_present is True

    # Year 7 battle candidate evaluated for Year 1 sorting
    verdict_mismatch = vlm.verify_candidate(req, sample_candidate_shots[1])
    assert verdict_mismatch.match is False or verdict_mismatch.contradiction_detected is True


# ==============================================================================
# TEST 11: MULTI-STAGE RERANKING (PHASE 11)
# ==============================================================================
def test_10_multi_stage_reranking(sample_candidate_shots):
    engine = BeastVisualMatchingEngine()
    req = engine.parse_narration_beat(
        beat_id="beat_neville_sorting",
        narration_text="Terrified by his family, eleven-year-old Neville begged the Sorting Hat to place him in Hufflepuff.",
        narrative_phase="EVIDENCE",
    )

    match_result = engine.find_best_visual_match(req, sample_candidate_shots, target_duration=2.5)
    assert match_result is not None
    best_shot, breakdown = match_result

    # Best shot MUST be the Sorting Hat shot (Candidate A), NOT the battle shot (Candidate B)
    assert best_shot.shot_id == "shot_m1_neville_sorting_01"
    assert breakdown.is_acceptable is True
    assert breakdown.final_score >= 65.0
    assert breakdown.character_score == 100.0
    assert breakdown.object_score == 100.0


# ==============================================================================
# TEST 12: NO_VALID_VISUAL ON LOW CONFIDENCE (PHASE 16)
# ==============================================================================
def test_11_no_valid_visual_on_low_confidence(sample_candidate_shots):
    """
    When no candidate in the pool matches the required visual, engine must fail closed
    and return None (NO_VALID_VISUAL) rather than hallucinating or forcing unrelated footage.
    """
    engine = BeastVisualMatchingEngine(min_confidence_threshold=65.0)
    req = BeastVisualRequirement(
        beat_id="beat_unmatchable",
        narration_text="Dobby the house elf snapped his fingers and vanished from Malfoy Manor.",
        primary_subject="Dobby",
        required_action="snapping fingers and vanishing",
        required_location="Malfoy Manor",
        confidence_threshold=65.0,
    )

    # Candidate pool only has Neville, Harry, and Snape
    match = engine.find_best_visual_match(req, sample_candidate_shots)
    assert match is None


# ==============================================================================
# TEST 13: EXACT TIMESTAMP EXTRACTION (PHASE 14)
# ==============================================================================
def test_12_exact_timestamp_extraction(sample_candidate_shots):
    scorer = BeastScoringEngine()
    shot = sample_candidate_shots[0]  # start=2568.5, end=2574.0, dur=5.5s
    target_dur = 2.0

    interval = scorer.refine_sub_interval(shot, target_duration=target_dur)
    start_sub, end_sub = interval

    assert start_sub >= shot.start_seconds
    assert end_sub <= shot.end_seconds
    assert round(end_sub - start_sub, 2) == target_dur


# ==============================================================================
# TEST 14: TEMPORAL COHERENCE (PHASE 10)
# ==============================================================================
def test_13_temporal_coherence():
    scorer = BeastScoringEngine()
    req = BeastVisualRequirement(beat_id="b1", narration_text="Test narration")
    tiny_shot = BeastCandidateShot(
        shot_id="shot_tiny",
        source_video="test.mp4",
        movie_number=1,
        start_seconds=10.0,
        end_seconds=10.4,
        duration=0.4,  # Sub-second flash
    )

    breakdown = scorer.score_candidate(
        requirement=req,
        shot=tiny_shot,
        semantic_sim=80.0,
        primary_char_score=100.0,
        secondary_char_score=100.0,
        action_score=80.0,
        object_score=80.0,
        location_score=80.0,
        has_contradiction=False,
        contradiction_reasons=[],
    )

    # Sub-second shots receive heavy temporal coherence penalty
    assert breakdown.temporal_coherence < 50.0
    assert any("too brief" in r.lower() for r in breakdown.rejection_reasons)


# ==============================================================================
# TEST 15: DETERMINISTIC FINGERPRINTS (PHASE 17)
# ==============================================================================
def test_14_deterministic_fingerprints(sample_candidate_shots):
    retriever = BeastSemanticRetriever()
    shot = sample_candidate_shots[0]

    emb1 = retriever.shot_to_embedding(shot)
    emb2 = retriever.shot_to_embedding(shot)

    assert np.allclose(emb1, emb2)
    assert np.isclose(np.linalg.norm(emb1), 1.0)


# ==============================================================================
# TEST 16: INTEGRATION WITH 9:16 COMPOSITION GATE
# ==============================================================================
def test_15_composition_assessment_integration():
    scorer = BeastScoringEngine()
    req = BeastVisualRequirement(beat_id="b1", narration_text="Neville speaking")
    # Shot with severe crop hazard
    hazard_shot = BeastCandidateShot(
        shot_id="shot_hazard",
        source_video="test.mp4",
        movie_number=1,
        start_seconds=10.0,
        end_seconds=15.0,
        duration=5.0,
        composition=ShotCompositionAssessment(
            shot_scale=ShotScale.CLOSE_UP,
            subject_bbox=NormalizedBBox(0.20, 0.0, 0.60, 0.90),
            is_9x16_crop_safe=False,
            crop_rejection_reasons=["Head cutoff detected"],
        ),
    )

    breakdown = scorer.score_candidate(
        requirement=req,
        shot=hazard_shot,
        semantic_sim=85.0,
        primary_char_score=100.0,
        secondary_char_score=100.0,
        action_score=80.0,
        object_score=80.0,
        location_score=80.0,
        has_contradiction=False,
        contradiction_reasons=[],
    )

    assert breakdown.crop_risk_penalty > 0.0
    assert any("head cutoff" in r.lower() for r in breakdown.rejection_reasons)


# ==============================================================================
# TEST 17: INTEGRATION WITH BEAT-LOCK WORD TIMESTAMPS (PHASE 15)
# ==============================================================================
def test_16_beat_lock_integration():
    """Confirms extracted cut points can snap to Whisper word boundaries."""
    mock_words = [
        {"word": "The", "start": 0.00, "end": 0.20},
        {"word": "movies", "start": 0.22, "end": 0.55},
        {"word": "skipped", "start": 0.58, "end": 0.95},
        {"word": "Neville", "start": 1.02, "end": 1.45},
        {"word": "Longbottom", "start": 1.48, "end": 2.10},
    ]
    raw_cut_points = [0.0, 1.15, 2.05]
    snapped = RemotionEditorialEngine.snap_cut_points_to_words(
        cut_points=raw_cut_points,
        words=mock_words,
        total_duration=2.10,
    )
    # The cut near 1.15 should snap cleanly to word onset 1.02
    assert snapped[0] == 0.0
    assert snapped[1] == 1.02
    assert snapped[2] == 2.10
