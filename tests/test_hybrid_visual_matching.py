"""
STORY FORGE — Phase 3: Hybrid SRT + Movie Event Visual Matching Test Suite
==========================================================================
Tests the MovieEvent-sole-authority architecture:
  1. SRT -> Time window coarse localization (T0 ± 30s)
  2. MovieEvent search constrained by SRT window (Level 1)
  3. Window expansion to adjacent scene boundaries (Level 2)
  4. MovieEvent chain expansion (Level 3)
  5. Movie-wide and global search (Level 4)
  6. Level 5 fail-closed rejection: NO_VALID_VISUAL (zero SRT fallback)
  7. ARCHITECTURAL ASSERTION: SRT candidate can NEVER become final visual selection
  8. MovieEvent vs MovieEvent comparison & improvement margin
  9. Action mismatch hard veto across movies
  10. Direct visual requirement vs Contextual visual permission
  11. Event-chain continuity preservation
  12. Cryptographic lineage propagation
  13. All 8 movies verified coverage
  14. All 8 movies negative distractor rejection
"""

import pytest
from engines.movie_event.models import (
    MovieEvent,
    VisualBeat,
    MovieEventQuery,
    ClaimType,
    VerificationStatus,
)
from engines.movie_event.index import MovieEventIndex
from engines.movie_event.storyboard_generator import VisualStoryboardGenerator, ClaimTransformer
from engines.movie_event.retrieval_engine import MovieEventRetrievalEngine
from engines.movie_event.verifier import MovieEventVisualVerifier
from engines.movie_event.hybrid_matcher import (
    SRTTimeWindow,
    CandidateComparisonResult,
    HybridVisualSelectionOutput,
    SRTCoarseLocator,
    HybridVisualSelector,
    MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN,
)


@pytest.fixture
def index():
    return MovieEventIndex()


@pytest.fixture
def coarse_locator():
    return SRTCoarseLocator()


@pytest.fixture
def storyboard_gen():
    return VisualStoryboardGenerator()


@pytest.fixture
def hybrid_selector(index):
    return HybridVisualSelector(
        index=index,
        min_improvement_margin=MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN,
    )


# ------------------------------------------------------------------------------
# 1. SRT -> TIME WINDOW CONVERSION
# ------------------------------------------------------------------------------
def test_srt_time_window_conversion(coarse_locator, storyboard_gen):
    beat, _ = storyboard_gen.generate_beat_from_narration(
        beat_id="beat_01",
        narration_text="asphodel wormwood potions",
        start_time=0.0,
        end_time=3.0,
        inferred_movie=1,
    )
    window = coarse_locator.locate_coarse_window(beat, inferred_movie=1, padding_seconds=30.0)
    assert window is not None
    assert window.movie_number == 1
    assert window.scene_window_start <= 3160.0 <= window.scene_window_end
    assert abs(window.preferred_timestamp - 3159.93) < 1.0


# ------------------------------------------------------------------------------
# 2. MOVIE EVENT SEARCH CONSTRAINED BY SRT WINDOW (LEVEL 1)
# ------------------------------------------------------------------------------
def test_movie_event_search_constrained_by_srt_window(hybrid_selector, storyboard_gen):
    beat, _ = storyboard_gen.generate_beat_from_narration(
        beat_id="beat_02",
        narration_text="What would I get if I added root of asphodel to an infusion of wormwood?",
        start_time=0.0,
        end_time=3.0,
        inferred_movie=1,
    )
    output = hybrid_selector.select_visual_for_beat(beat, content_id="test_content_01", inferred_movie=1)
    assert output.status == "VERIFIED"
    assert output.comparison.selected_source == "MOVIE_EVENT"
    assert output.selected_candidate is not None
    assert output.selected_candidate["movie_number"] == 1
    assert output.selected_candidate["candidate_id"] == "evt_m1_potions_snape_questions_harry"


# ------------------------------------------------------------------------------
# 3. WINDOW EXPANSION (LEVEL 1 -> LEVEL 2)
# ------------------------------------------------------------------------------
def test_window_expansion_level_2(hybrid_selector, storyboard_gen):
    beat, _ = storyboard_gen.generate_beat_from_narration(
        beat_id="beat_03",
        narration_text="Harry summons Firebolt broom with Accio spell in the dragon arena.",
        start_time=0.0,
        end_time=3.0,
        inferred_movie=4,
    )
    output = hybrid_selector.select_visual_for_beat(beat, content_id="test_content_02", inferred_movie=4)
    assert output.status == "VERIFIED"
    assert output.search_level_reached in (1, 2)
    assert output.selected_candidate["candidate_id"] == "evt_m4_first_task_harry_summons_firebolt"


# ------------------------------------------------------------------------------
# 4. CANDIDATE COMPARISON LOGIC
# ------------------------------------------------------------------------------
def test_candidate_comparison_logic(hybrid_selector, storyboard_gen):
    beat, _ = storyboard_gen.generate_beat_from_narration(
        beat_id="beat_04",
        narration_text="Hermione punches Malfoy squarely in the face.",
        start_time=0.0,
        end_time=2.5,
        inferred_movie=3,
    )
    output = hybrid_selector.select_visual_for_beat(beat, content_id="test_content_03", inferred_movie=3)
    cmp = output.comparison
    assert cmp.beat_id == "beat_04"
    assert cmp.movie_event_candidate_id == "evt_m3_sundial_hermione_punches_malfoy"
    assert cmp.movie_event_verified is True
    assert cmp.selected_source == "MOVIE_EVENT"
    assert cmp.fallback_used is False


# ------------------------------------------------------------------------------
# 5. HARD ARCHITECTURAL ASSERTION: SRT CAN NEVER BECOME FINAL VISUAL SELECTION
# ------------------------------------------------------------------------------
def test_architectural_assertion_srt_never_selected(hybrid_selector):
    """
    CRITICAL REGRESSION TEST:
    Proves that under NO circumstances can an SRT candidate become the final visual selection.
    This test MUST fail if any future developer reintroduces SRT visual fallback.
    """
    # Scenario 1: SRT finds Snape walking toward Harry; MovieEvent finds Snape questioning Harry.
    # -> Final must be MovieEvent
    beat_q = VisualBeat(
        beat_id="arch_01",
        narrative_text="Snape questions Harry directly.",
        required_action="questions",
        required_subjects=["Snape", "Harry"],
    )
    srt_walk = MovieEvent(
        event_id="srt_dialogue_walk",
        movie_id="hp_movie_1",
        movie_number=1,
        scene_id="s1",
        start_time=3140.0,
        end_time=3145.0,
        primary_subject="Snape",
        secondary_subjects=["Harry"],
        action="walks slowly toward Harry's desk",
        location="Potions",
        visual_description="Snape walks down the aisle.",
    )
    me_question = MovieEvent(
        event_id="evt_m1_potions_snape_questions_harry",
        movie_id="hp_movie_1",
        movie_number=1,
        scene_id="s1",
        start_time=3159.0,
        end_time=3195.0,
        primary_subject="Snape",
        secondary_subjects=["Harry"],
        action="questions and confronts Harry directly",
        location="Potions",
        visual_description="Snape questions Harry directly.",
    )
    ver_srt_walk = hybrid_selector.verifier.verify_event(srt_walk, beat_q)
    ver_me_q = hybrid_selector.verifier.verify_event(me_question, beat_q)

    cmp1 = hybrid_selector._compare_candidates(
        beat=beat_q,
        srt_event=srt_walk,
        srt_score=70.0,
        srt_ver=ver_srt_walk,
        me_event=me_question,
        me_score=90.0,
        me_ver=ver_me_q,
    )
    assert cmp1.selected_source == "MOVIE_EVENT"
    assert cmp1.selected_candidate_id == "evt_m1_potions_snape_questions_harry"
    assert cmp1.fallback_used is False

    # Scenario 2: SRT finds Dumbledore standing; MovieEvent finds NOTHING for drinking.
    # -> Final MUST be NO_VALID_VISUAL. NOT Dumbledore standing!
    beat_drink = VisualBeat(
        beat_id="arch_02",
        narrative_text="Dumbledore drinks water from the crystal goblet.",
        required_action="drinks",
        required_subjects=["Dumbledore"],
        required_objects=["crystal goblet"],
    )
    srt_stand = MovieEvent(
        event_id="srt_dumbledore_stands",
        movie_id="hp_movie_6",
        movie_number=6,
        scene_id="s_cave",
        start_time=7380.0,
        end_time=7390.0,
        primary_subject="Dumbledore",
        action="stands holding crystal goblet",
        location="Horcrux Cave",
        visual_description="Dumbledore stands near the basin.",
    )
    ver_stand = hybrid_selector.verifier.verify_event(srt_stand, beat_drink)

    cmp2 = hybrid_selector._compare_candidates(
        beat=beat_drink,
        srt_event=srt_stand,
        srt_score=85.0,
        srt_ver=ver_stand,
        me_event=None,
        me_score=0.0,
        me_ver=None,
    )
    assert cmp2.selected_source == "NO_VALID_VISUAL"
    assert cmp2.selected_candidate_id is None
    assert cmp2.fallback_used is False

    # Scenario 3: SRT finds Neville talking; MovieEvent finds Neville drawing sword.
    # -> Final must be MovieEvent
    beat_sword = VisualBeat(
        beat_id="arch_03",
        narrative_text="Neville draws the Sword of Gryffindor.",
        required_action="draws",
        required_subjects=["Neville"],
        required_objects=["Sword of Gryffindor"],
    )
    srt_talk = MovieEvent(
        event_id="srt_neville_speech",
        movie_id="hp_movie_8",
        movie_number=8,
        scene_id="s_court",
        start_time=6140.0,
        end_time=6150.0,
        primary_subject="Neville",
        action="speaks defiantly holding Sorting Hat",
        location="Courtyard",
        visual_description="Neville speaks to Voldemort.",
    )
    me_draw = MovieEvent(
        event_id="evt_m8_courtyard_neville_draws_sword",
        movie_id="hp_movie_8",
        movie_number=8,
        scene_id="s_court",
        start_time=6168.0,
        end_time=6215.0,
        primary_subject="Neville",
        action="draws the Sword of Gryffindor from Sorting Hat",
        location="Courtyard",
        visual_description="Neville draws sword from hat.",
    )
    ver_talk = hybrid_selector.verifier.verify_event(srt_talk, beat_sword)
    ver_draw = hybrid_selector.verifier.verify_event(me_draw, beat_sword)

    cmp3 = hybrid_selector._compare_candidates(
        beat=beat_sword,
        srt_event=srt_talk,
        srt_score=50.0,
        srt_ver=ver_talk,
        me_event=me_draw,
        me_score=95.0,
        me_ver=ver_draw,
    )
    assert cmp3.selected_source == "MOVIE_EVENT"
    assert cmp3.selected_candidate_id == "evt_m8_courtyard_neville_draws_sword"
    assert cmp3.fallback_used is False


# ------------------------------------------------------------------------------
# 6. MOVIE EVENT VS MOVIE EVENT IMPROVEMENT MARGIN
# ------------------------------------------------------------------------------
def test_competing_movie_events_improvement_margin(hybrid_selector):
    beat = VisualBeat(
        beat_id="beat_compete",
        narrative_text="Snape confronts Harry.",
        required_action="confronts",
        required_subjects=["Snape", "Harry"],
    )
    event_top = MovieEvent(
        event_id="me_primary_95",
        movie_id="hp_movie_1",
        movie_number=1,
        scene_id="s1",
        start_time=100.0,
        end_time=105.0,
        primary_subject="Snape",
        secondary_subjects=["Harry"],
        action="confronts Harry directly",
        location="Potions",
        visual_description="Snape confronts Harry directly.",
    )
    event_runner_up = MovieEvent(
        event_id="me_secondary_75",
        movie_id="hp_movie_1",
        movie_number=1,
        scene_id="s1",
        start_time=100.0,
        end_time=105.0,
        primary_subject="Snape",
        secondary_subjects=["Harry"],
        action="confronts Harry",
        location="Potions",
        visual_description="Snape confronts Harry.",
    )
    ver_top = hybrid_selector.verifier.verify_event(event_top, beat)
    ver_sub = hybrid_selector.verifier.verify_event(event_runner_up, beat)

    cmp = hybrid_selector._compare_candidates(
        beat=beat,
        me_event=event_top,
        me_score=95.0,
        me_ver=ver_top,
        cand_b=event_runner_up,
        score_b=75.0,
        ver_b=ver_sub,
    )
    assert cmp.selected_source == "MOVIE_EVENT"
    assert cmp.selected_candidate_id == "me_primary_95"
    assert cmp.score_delta == 20.0
    assert cmp.margin_satisfied is True
    assert cmp.fallback_used is False


# ------------------------------------------------------------------------------
# 7. NO_VALID_VISUAL ON ABSTRACT CLAIM
# ------------------------------------------------------------------------------
def test_no_valid_visual_on_abstract_claim(hybrid_selector, storyboard_gen):
    beat, classification = storyboard_gen.generate_beat_from_narration(
        beat_id="beat_08",
        narration_text="Snape secretly suspected Harry was connected to Voldemort.",
        start_time=0.0,
        end_time=3.0,
        inferred_movie=1,
    )
    assert classification.classification == ClaimType.ABSTRACT_NOT_DIRECTLY_VISUALIZABLE
    output = hybrid_selector.select_visual_for_beat(beat, content_id="test_content_06", inferred_movie=1)
    assert output.status == "NO_VALID_VISUAL"
    assert output.comparison.selected_source == "NO_VALID_VISUAL"
    assert output.selected_candidate is None


# ------------------------------------------------------------------------------
# 8. ACTION MISMATCH HARD VETO
# ------------------------------------------------------------------------------
def test_action_mismatch_hard_veto(hybrid_selector, index):
    beat = VisualBeat(
        beat_id="beat_09",
        narrative_text="Hermione punches Malfoy.",
        required_action="punches",
        required_subjects=["Hermione Granger", "Draco Malfoy"],
    )
    # Malfoy fleeing is completely wrong action
    distractor = index.get_event("evt_m3_sundial_malfoy_flees_in_terror")
    ver = hybrid_selector.verifier.verify_event(distractor, beat)
    assert ver.is_verified is False
    assert "ACTION MISMATCH" in ver.explanation


# ------------------------------------------------------------------------------
# 9. DIRECT VISUAL REQUIREMENT VS CONTEXTUAL VISUAL PERMISSION
# ------------------------------------------------------------------------------
def test_direct_visual_requirement_enforcement(hybrid_selector):
    # Direct physical claim must strictly fail if action not present
    beat_direct = VisualBeat(
        beat_id="beat_dir",
        narrative_text="Dumbledore drinks water from the crystal goblet.",
        required_action="drinks",
        required_subjects=["Albus Dumbledore"],
        direct_visual_requirement=True,
        contextual_visual_allowed=False,
    )
    output_direct = hybrid_selector.select_visual_for_beat(beat_direct, content_id="c_dir", inferred_movie=6)
    assert output_direct.status == "NO_VALID_VISUAL"
    assert output_direct.selected_candidate is None


# ------------------------------------------------------------------------------
# 10. EVENT-CHAIN CONTINUITY PRESERVATION
# ------------------------------------------------------------------------------
def test_event_chain_continuity_preservation(hybrid_selector, storyboard_gen):
    beat, _ = storyboard_gen.generate_beat_from_narration(
        beat_id="beat_10",
        narration_text="Harry opens the Chamber of Secrets entrance.",
        start_time=0.0,
        end_time=3.0,
        inferred_movie=2,
    )
    output = hybrid_selector.select_visual_for_beat(beat, content_id="test_content_07", inferred_movie=2)
    assert output.event_chain is not None
    assert output.event_chain["core"] == "evt_m2_bathroom_harry_speaks_parseltongue_opens_chamber"
    assert output.event_chain["preceding"] == "evt_m2_bathroom_harry_inspects_sink"
    assert output.event_chain["following"] == "evt_m2_bathroom_sinks_descend_pipe_revealed"


# ------------------------------------------------------------------------------
# 11. CRYPTOGRAPHIC LINEAGE PROPAGATION
# ------------------------------------------------------------------------------
def test_cryptographic_lineage_propagation(hybrid_selector, storyboard_gen):
    beat, _ = storyboard_gen.generate_beat_from_narration(
        beat_id="beat_11",
        narration_text="Snape questions Harry in Potions classroom.",
        start_time=0.0,
        end_time=3.0,
        inferred_movie=1,
    )
    content_id = "lineage_test_01"
    output = hybrid_selector.select_visual_for_beat(beat, content_id=content_id, inferred_movie=1)
    lineage = output.lineage_metadata

    assert lineage["content_id"] == content_id
    assert "narration_hash" in lineage
    assert "proposition_hash" in lineage
    assert "source_evidence_hash" in lineage
    assert "timeline_hash" in lineage
    assert lineage["visual_plan_id"].startswith("vp_")


# ------------------------------------------------------------------------------
# 12. ALL 8 MOVIES VERIFIED COVERAGE
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("movie_num, narration, expected_event", [
    (1, "Snape questions Harry in Potions classroom.", "evt_m1_potions_snape_questions_harry"),
    (2, "Harry opens the Chamber of Secrets entrance.", "evt_m2_bathroom_harry_speaks_parseltongue_opens_chamber"),
    (3, "Hermione punches Malfoy squarely in the face.", "evt_m3_sundial_hermione_punches_malfoy"),
    (4, "Harry summons Firebolt broom with Accio spell.", "evt_m4_first_task_harry_summons_firebolt"),
    (5, "Harry casts Expecto Patronum in Room of Requirement.", "evt_m5_ror_harry_casts_patronum"),
    (6, "Harry drinks Felix Felicis potion from small vial.", "evt_m6_common_room_harry_drinks_felix_felicis"),
    (7, "Ron destroys Slytherin Locket with Sword of Gryffindor.", "evt_m7_forest_ron_destroys_locket_with_sword"),
    (8, "Neville draws the Sword of Gryffindor from Sorting Hat.", "evt_m8_courtyard_neville_draws_sword"),
])
def test_all_8_movies_verified_coverage(hybrid_selector, storyboard_gen, movie_num, narration, expected_event):
    beat, _ = storyboard_gen.generate_beat_from_narration(
        beat_id=f"cov_m{movie_num}",
        narration_text=narration,
        start_time=0.0,
        end_time=3.0,
        inferred_movie=movie_num,
    )
    output = hybrid_selector.select_visual_for_beat(beat, content_id=f"test_cov_m{movie_num}", inferred_movie=movie_num)
    assert output.status == "VERIFIED"
    assert output.comparison.selected_source == "MOVIE_EVENT"
    assert output.selected_candidate is not None
    assert output.selected_candidate["candidate_id"] == expected_event
    assert output.selected_candidate["movie_number"] == movie_num


# ------------------------------------------------------------------------------
# 13. ALL 8 MOVIES NEGATIVE TESTS (FAIL CLOSED)
# ------------------------------------------------------------------------------
@pytest.mark.parametrize("movie_num, distractor_id, req_action", [
    (1, "evt_m1_potions_snape_walks_alone_distractor", "questions"),
    (2, "evt_m2_bathroom_harry_stares_flooded_distractor", "opens"),
    (3, "evt_m3_sundial_malfoy_mocks_friends_distractor", "punches"),
    (4, "evt_m4_defense_moody_holds_flask_standing_distractor", "drinks"),
    (5, "evt_m5_atrium_dumbledore_stands_fountain_distractor", "conjures"),
    (6, "evt_m6_cave_dumbledore_holds_crystal_goblet_distractor", "drinks"),
    (7, "evt_m7_forest_ron_stands_holding_sword_distractor", "destroys"),
    (8, "evt_m8_courtyard_neville_stands_speechless_distractor", "draws"),
])
def test_all_8_movies_negative_veto(hybrid_selector, index, movie_num, distractor_id, req_action):
    beat = VisualBeat(
        beat_id=f"neg_m{movie_num}",
        narrative_text=f"Action required: {req_action}",
        required_action=req_action,
    )
    distractor = index.get_event(distractor_id)
    assert distractor is not None, f"Distractor {distractor_id} not found!"
    ver = hybrid_selector.verifier.verify_event(distractor, beat)
    assert ver.is_verified is False
    assert ver.status == VerificationStatus.REJECT_ACTION_MISMATCH
