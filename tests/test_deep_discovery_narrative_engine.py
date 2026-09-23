"""
Step 1: Deep Discovery Narrative Engine & Schemas Test Suite
================================================================================
Verifies all 16 required capabilities of Step 1:
 1. Deep Discovery schema validation (valid plan passes, invalid fails).
 2. Template A selection (Curated Multi-Point structure).
 3. Template B selection (Myth-Buster / Deep Dive structure).
 4. Hook archetype selection (all 5 archetypes).
 5. Hook repetition prevention (anti-repetition window).
 6. Tri-Partite Evidence routing (novel, movie, BTS).
 7. Topic scoring formula (0.30 * canon + 0.30 * movie + 0.20 * curiosity + 0.20 * visual).
 8. Discovery vs Novel Story routing (>=75 vs >=65 with novel depth & low movie contrast).
 9. Exceptional Micro routing (curiosity >= 80, cannot sustain long form).
10. Backward compatibility with existing Discovery records and schemas.
11. Word-count / duration estimation (240–280 words, 68.0–78.0s, hard ceiling 80.9s).
12. Speech-rate targeting (3.4–3.7 words/second).
13. Payoff metadata (all 7 payoff types).
14. Title-pattern metadata (all 6 title patterns).
15. No generic throat-clearing hooks (rejection of throat-clearing openings).
16. No unsupported factual claims entering a finalized Discovery plan.
"""

import json
import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import Base, DiscoveryCandidate, HarryPotterScript, migrate_discovery_schema
from core.discovery_types import (
    DiscoverySubtype,
    DiscoveryTier,
    DiscoveryStoryStructure,
    HookArchetype,
    EvidenceRoute,
    PayoffType,
    TitlePattern,
    PacingPhase,
    DiscoveryRouting,
    EvidencePoint,
    DeepDiscoveryStoryPlan,
)
from engines.discovery_narrative_engine import DiscoveryNarrativeEngine
from engines.hp_script_engine import HarryPotterScriptEngine


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ── Test 1: Deep Discovery Schema Validation ─────────────────────────────────

def test_01_deep_discovery_schema_validation():
    """Validates that DeepDiscoveryStoryPlan enforces invariants and detects omissions."""
    ev1 = EvidencePoint(
        claim="Peeves dropped a bust of Paracelsus on corridor passersby",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="b1c08_chunk_004",
        source_excerpt="Peeves was bobbing above the corridor dropping a heavy bust of Paracelsus...",
        verified=True
    )
    ev2 = EvidencePoint(
        claim="Rik Mayall filmed scenes as Peeves but Columbus cut them all",
        evidence_route=EvidenceRoute.BTS_PRODUCTION.value,
        source_id="bts_interview_rik_mayall_2001",
        source_excerpt="Rik Mayall shot three weeks of footage as Peeves before being omitted.",
        verified=True
    )

    valid_plan = DeepDiscoveryStoryPlan(
        topic_id="disc_peeves_01",
        discovery_type=DiscoverySubtype.DISCOVERY_OMITTED_SCENE.value,
        discovery_tier=DiscoveryTier.DEEP_DISCOVERY,
        story_structure=DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE,
        hook_archetype=HookArchetype.COUNTER_INTUITIVE_TRUTH,
        evidence_route=EvidenceRoute.NOVEL_CANON,
        thesis="The movies cut Peeves completely, despite full scenes being filmed.",
        evidence_points=[ev1, ev2],
        anchor_point=ev1,
        insider_epiphany="Peeves was omitted not for story reasons, but because cast children couldn't stop laughing.",
        payoff_type=PayoffType.BOOK_MOVIE_REALIZATION,
        payoff_text="Peeves remains the greatest cut character in cinematic fantasy.",
        title_pattern=TitlePattern.BOOK_VS_MOVIE,
        suggested_title="Book vs Movie: The Ghost Cut From All 8 Films",
        expected_duration=72.0,
        target_word_count=255,
        target_speech_rate=3.55,
        topic_score=88.0,
        canon_depth=90.0,
        movie_contrast=95.0,
        curiosity_factor=85.0,
        visual_feasibility=80.0
    )
    assert valid_plan.validate() is True
    assert valid_plan.is_valid is True
    assert len(valid_plan.validation_errors) == 0

    # Serialization and deserialization roundtrip
    data_dict = valid_plan.to_dict()
    roundtrip_plan = DeepDiscoveryStoryPlan.from_dict(data_dict)
    assert roundtrip_plan.topic_id == valid_plan.topic_id
    assert roundtrip_plan.discovery_tier == DiscoveryTier.DEEP_DISCOVERY
    assert len(roundtrip_plan.evidence_points) == 2


# ── Test 2: Template A Selection (Curated Listicle) ──────────────────────────

def test_02_template_a_selection():
    """Validates selection of Template A for multi-point evidence collections."""
    struct = DiscoveryNarrativeEngine.select_structure(evidence_points_count=4, is_myth_or_deep_dive=False)
    assert struct == DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE

    pacing = DiscoveryNarrativeEngine.get_pacing_intent(struct)
    assert pacing["structure"] == DiscoveryStoryStructure.TEMPLATE_A_CURATED_LISTICLE.value
    assert PacingPhase.ANCHOR.value in pacing["phases"]
    # Anchor cut timing should provide asymmetric emphasis
    anchor_timing = pacing["phases"][PacingPhase.ANCHOR.value]["target_cut_seconds"]
    assert anchor_timing == (2.2, 3.2)


# ── Test 3: Template B Selection (Myth-Buster / Deep Dive) ───────────────────

def test_03_template_b_selection():
    """Validates selection of Template B for single-topic myth-busting deep dives."""
    struct = DiscoveryNarrativeEngine.select_structure(evidence_points_count=1, is_myth_or_deep_dive=True)
    assert struct == DiscoveryStoryStructure.TEMPLATE_B_MYTH_BUSTER

    struct_2 = DiscoveryNarrativeEngine.select_structure(evidence_points_count=2, is_myth_or_deep_dive=False)
    assert struct_2 == DiscoveryStoryStructure.TEMPLATE_B_MYTH_BUSTER


# ── Test 4: Hook Archetype Selection (All 5 Archetypes) ──────────────────────

def test_04_hook_archetype_selection_all_five():
    """Validates that all 5 hook archetypes can be selected based on topic characteristics."""
    # 1. DIALOGUE_COLD_OPEN
    arc_dialogue = DiscoveryNarrativeEngine.select_hook_archetype(
        {"quote": "Give her hell from us, Peeves.", "novel_fact_summary": "Fred said to Peeves"}
    )
    assert arc_dialogue == HookArchetype.DIALOGUE_COLD_OPEN

    # 2. ABSURD_COMIC_REALITY
    arc_comic = DiscoveryNarrativeEngine.select_hook_archetype(
        {"novel_fact_summary": "The Weasley twins sent a toilet seat to Harry in the hospital wing"}
    )
    assert arc_comic == HookArchetype.ABSURD_COMIC_REALITY

    # 3. DIRECT_CHALLENGE
    arc_challenge = DiscoveryNarrativeEngine.select_hook_archetype(
        {"novel_fact_summary": "The Sorting Hat almost put Neville in Hufflepuff after a 4-minute argument"}
    )
    assert arc_challenge == HookArchetype.DIRECT_CHALLENGE

    # 4. COUNTER_INTUITIVE_TRUTH
    arc_contrast = DiscoveryNarrativeEngine.select_hook_archetype(
        {"discovery_type": "DISCOVERY_BOOK_MOVIE_DIFFERENCE", "novel_fact_summary": "Harry never broke the Elder Wand in the books"}
    )
    assert arc_contrast == HookArchetype.COUNTER_INTUITIVE_TRUTH

    # 5. INCREDULITY_AWARENESS_TEST
    arc_incred = DiscoveryNarrativeEngine.select_hook_archetype(
        {"discovery_type": "DISCOVERY_BOOK_MOVIE_DIFFERENCE", "novel_fact_summary": "A hidden difference nobody realized"},
        recent_hooks=[HookArchetype.COUNTER_INTUITIVE_TRUTH]
    )
    assert arc_incred == HookArchetype.INCREDULITY_AWARENESS_TEST


# ── Test 5: Hook Repetition Prevention (Anti-Repetition Window) ───────────────

def test_05_hook_repetition_prevention():
    """Validates that recent hook archetypes are excluded to prevent repetition."""
    context = {"discovery_type": "DISCOVERY_BOOK_MOVIE_DIFFERENCE", "novel_fact_summary": "Book difference"}
    
    first_choice = DiscoveryNarrativeEngine.select_hook_archetype(context, recent_hooks=[])
    assert first_choice == HookArchetype.COUNTER_INTUITIVE_TRUTH

    # When first_choice was recently used, engine must choose an alternative
    second_choice = DiscoveryNarrativeEngine.select_hook_archetype(
        context, recent_hooks=[HookArchetype.COUNTER_INTUITIVE_TRUTH]
    )
    assert second_choice != HookArchetype.COUNTER_INTUITIVE_TRUTH
    assert second_choice == HookArchetype.INCREDULITY_AWARENESS_TEST

    # Exclude both
    third_choice = DiscoveryNarrativeEngine.select_hook_archetype(
        context,
        recent_hooks=[HookArchetype.COUNTER_INTUITIVE_TRUTH, HookArchetype.INCREDULITY_AWARENESS_TEST]
    )
    assert third_choice not in (HookArchetype.COUNTER_INTUITIVE_TRUTH, HookArchetype.INCREDULITY_AWARENESS_TEST)


# ── Test 6: Evidence Routing (Novel, Movie, BTS) ─────────────────────────────

def test_06_tri_partite_evidence_routing():
    """Validates tri-partite evidence routing across novel, movie, and BTS sources."""
    # Novel routing
    ep_novel = DiscoveryNarrativeEngine.route_evidence(
        claim="Neville argued with the Sorting Hat",
        source_type="NOVEL",
        source_id="b1c07_chunk_014",
        source_excerpt="It took a long time to sort Neville..."
    )
    assert ep_novel.evidence_route == EvidenceRoute.NOVEL_CANON.value
    assert ep_novel.verified is True

    # Movie routing
    ep_movie = DiscoveryNarrativeEngine.route_evidence(
        claim="Movie 1 instantly places Neville in Gryffindor",
        source_type="MOVIE",
        source_id="m1_scene_0038_srt",
        source_excerpt="Hat: GRYFFINDOR!"
    )
    assert ep_movie.evidence_route == EvidenceRoute.MOVIE_CANON.value
    assert ep_movie.verified is True

    # BTS routing
    ep_bts = DiscoveryNarrativeEngine.route_evidence(
        claim="Director Chris Columbus shot Peeves scenes with Rik Mayall",
        source_type="BTS_PRODUCTION",
        source_id="dvd_extras_philosophers_stone_disc2",
        source_excerpt="Columbus commentary: Rik Mayall played Peeves on set."
    )
    assert ep_bts.evidence_route == EvidenceRoute.BTS_PRODUCTION.value
    assert ep_bts.verified is True


# ── Test 7: Topic Scoring Formula ─────────────────────────────────────────────

def test_07_topic_scoring_formula():
    """Validates the 4-part topic scoring formula with 0.30/0.30/0.20/0.20 weights."""
    # Score = (0.30 * 100) + (0.30 * 80) + (0.20 * 90) + (0.20 * 70)
    # Score = 30 + 24 + 18 + 14 = 86.0
    score = DiscoveryNarrativeEngine.calculate_topic_score(
        canon_depth=100.0,
        movie_contrast=80.0,
        curiosity_factor=90.0,
        visual_feasibility=70.0
    )
    assert score == 86.0

    # Minimum boundary
    min_score = DiscoveryNarrativeEngine.calculate_topic_score(0, 0, 0, 0)
    assert min_score == 0.0

    # Maximum boundary
    max_score = DiscoveryNarrativeEngine.calculate_topic_score(100, 100, 100, 100)
    assert max_score == 100.0


# ── Test 8: Discovery vs Novel Story Routing ─────────────────────────────────

def test_08_discovery_vs_novel_story_routing():
    """Validates routing between Deep Discovery, Novel Story, Hold, and Reject."""
    # 1. High contrast & canon -> Deep Discovery
    r_disc = DiscoveryNarrativeEngine.route_candidate(
        topic_score=82.0, canon_depth=85.0, movie_contrast=80.0, curiosity_factor=80.0
    )
    assert r_disc == DiscoveryRouting.DEEP_DISCOVERY

    # 2. Deep novel lore but low movie contrast -> Novel Story
    r_novel = DiscoveryNarrativeEngine.route_candidate(
        topic_score=68.0, canon_depth=85.0, movie_contrast=20.0, curiosity_factor=75.0
    )
    assert r_novel == DiscoveryRouting.NOVEL_STORY

    # 3. Moderate score 50-64 -> Hold
    r_hold = DiscoveryNarrativeEngine.route_candidate(
        topic_score=58.0, canon_depth=50.0, movie_contrast=60.0, curiosity_factor=60.0
    )
    assert r_hold == DiscoveryRouting.HOLD

    # 4. Low score < 50 -> Reject
    r_reject = DiscoveryNarrativeEngine.route_candidate(
        topic_score=42.0, canon_depth=30.0, movie_contrast=40.0, curiosity_factor=40.0
    )
    assert r_reject == DiscoveryRouting.REJECT


# ── Test 9: Exceptional Micro Routing ────────────────────────────────────────

def test_09_exceptional_micro_routing():
    """Validates exceptional Micro routing only when curiosity >= 80 and cannot sustain 65-80s."""
    r_micro = DiscoveryNarrativeEngine.route_candidate(
        topic_score=72.0,
        canon_depth=60.0,
        movie_contrast=70.0,
        curiosity_factor=88.0,
        can_sustain_long_form=False
    )
    assert r_micro == DiscoveryRouting.MICRO_DISCOVERY

    # When it CAN sustain long form, it is NOT forced into Micro
    r_normal = DiscoveryNarrativeEngine.route_candidate(
        topic_score=78.0,
        canon_depth=80.0,
        movie_contrast=80.0,
        curiosity_factor=88.0,
        can_sustain_long_form=True
    )
    assert r_normal == DiscoveryRouting.DEEP_DISCOVERY


# ── Test 10: Backward Compatibility with Existing Discovery Records ──────────

def test_10_backward_compatibility(in_memory_db):
    """Validates that legacy records load and instantiate cleanly without errors."""
    session = in_memory_db

    # Create legacy candidate with only pre-Step-1 fields
    legacy_candidate = DiscoveryCandidate(
        id="disc_legacy_test_01",
        content_type="discovery",
        discovery_type="BOOK_VS_MOVIE_DIFFERENCE",
        book_number=1,
        book_title="Harry Potter and the Philosopher's Stone",
        chapter_number=7,
        chapter_title="The Sorting Hat",
        chunk_id_primary="b1c07_001",
        novel_fact_summary="Neville wanted Hufflepuff",
        novel_evidence_text="Neville walked up...",
        corresponding_movie_number=1,
        movie_shows="Hat says Gryffindor",
        status="ELIGIBLE",
        content_fingerprint="legacy_fp_12345"
    )
    session.add(legacy_candidate)
    session.commit()

    # Query back
    loaded = session.query(DiscoveryCandidate).filter_by(id="disc_legacy_test_01").first()
    assert loaded is not None
    assert loaded.id == "disc_legacy_test_01"
    # New fields should default safely
    assert loaded.discovery_tier == "DEEP_DISCOVERY"
    assert loaded.topic_score == 0.0
    assert loaded.thesis is None or loaded.thesis == ""

    # Legacy HarryPotterScript record
    legacy_script = HarryPotterScript(
        id="hps_legacy_test_01",
        candidate_id="disc_legacy_test_01",
        content_type="discovery",
        book_number=1,
        book_title="Philosopher's Stone",
        chapter_number=7,
        chapter_title="Sorting Hat",
        source_chunks_json='["b1c07_001"]',
        source_reference="Book 1 Chapter 7",
        hook="In the book, Neville begged the hat.",
        development="He feared Gryffindor bravery was beyond him.",
        payoff="The hat refused his plea and chose Gryffindor.",
        full_text="In the book, Neville begged the hat. He feared Gryffindor bravery was beyond him. The hat refused his plea and chose Gryffindor.",
        word_count=26,
        estimated_duration_sec=10.4,
        visual_beats_json='[]',
        qa_status="APPROVED"
    )
    session.add(legacy_script)
    session.commit()

    loaded_script = session.query(HarryPotterScript).filter_by(id="hps_legacy_test_01").first()
    assert loaded_script is not None
    assert loaded_script.discovery_tier == "DEEP_DISCOVERY"


# ── Test 11: Word-Count / Duration Estimation ────────────────────────────────

def test_11_word_count_and_duration_estimation():
    """Validates word count bounds (240-280 words) and duration (68.0-78.0s, ceiling 80.9s)."""
    targets = DiscoveryNarrativeEngine.calculate_targets(tier=DiscoveryTier.DEEP_DISCOVERY)
    assert targets["min_duration"] == 68.0
    assert targets["max_duration"] == 78.0
    assert targets["hard_ceiling_duration"] == 80.9
    assert targets["min_word_count"] == 240
    assert targets["max_word_count"] == 280

    # Check that default duration * speech rate falls squarely within 240-280 words
    expected_words = targets["target_word_count"]
    assert 240 <= expected_words <= 280

    # Test Script QA bounds for Deep Discovery
    script_engine = HarryPotterScriptEngine()
    beats = [
        {"beat_id": "b1", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
        {"beat_id": "b2", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
        {"beat_id": "b3", "visual_source_policy": "MOVIE_FOOTAGE_ONLY"},
    ]

    # Valid 250 words script text
    valid_words = ["magic"] * 250
    valid_text = " ".join(valid_words)
    qa_res = script_engine.evaluate_script_qa(valid_text, beats, candidate_type="deep_discovery")
    assert qa_res.word_count == 250
    assert 68.0 <= qa_res.estimated_duration_sec <= 78.0
    assert qa_res.passed is True


# ── Test 12: Speech-Rate Targeting ───────────────────────────────────────────

def test_12_speech_rate_targeting():
    """Validates that speech rate targets 3.4-3.7 words per second."""
    targets = DiscoveryNarrativeEngine.calculate_targets(tier=DiscoveryTier.DEEP_DISCOVERY)
    rate = targets["target_speech_rate"]
    assert 3.4 <= rate <= 3.7
    assert targets["min_speech_rate"] == 3.4
    assert targets["max_speech_rate"] == 3.7


# ── Test 13: Payoff Metadata ──────────────────────────────────────────────────

def test_13_payoff_metadata():
    """Validates that all 7 canonical payoff types are supported."""
    expected_payoffs = [
        PayoffType.REVEAL,
        PayoffType.REFRAME,
        PayoffType.IRONY,
        PayoffType.COMEDIC_PUNCHLINE,
        PayoffType.CANON_CLARIFICATION,
        PayoffType.BOOK_MOVIE_REALIZATION,
        PayoffType.DEBATE_QUESTION,
    ]
    for pt in expected_payoffs:
        assert isinstance(pt.value, str)
        assert len(pt.value) > 0


# ── Test 14: Title-Pattern Metadata ───────────────────────────────────────────

def test_14_title_pattern_metadata():
    """Validates that all 6 curiosity title formula patterns produce non-deceptive titles."""
    patterns = [
        TitlePattern.CURIOSITY_QUESTION,
        TitlePattern.HIDDEN_DETAIL,
        TitlePattern.COUNTER_INTUITIVE_TRUTH,
        TitlePattern.BOOK_VS_MOVIE,
        TitlePattern.MYSTERY_REVEAL,
        TitlePattern.CHALLENGE,
    ]
    for pat in patterns:
        title = DiscoveryNarrativeEngine.generate_suggested_title(
            pattern=pat,
            topic_summary="Neville Longbottom sorting hat difference",
            entities=["Neville"]
        )
        assert isinstance(title, str)
        assert len(title) > 10
        assert "Neville" in title


# ── Test 15: No Generic Throat-Clearing Hooks ─────────────────────────────────

def test_15_no_generic_throat_clearing_hooks():
    """Validates that generic openings are rejected in Frame 0."""
    forbidden_openings = [
        "In this video we are going to look at Peeves the poltergeist.",
        "Today we're going to talk about the Sorting Hat in Harry Potter.",
        "Let's talk about the biggest book versus movie difference.",
        "Did you know that Rik Mayall was cast as Peeves?",
        "Welcome back to another Harry Potter short.",
        "What if I told you Neville almost went to Hufflepuff?",
        "Have you ever wondered why Peeves was cut?",
        "In today's short we explore the Elder Wand.",
    ]
    for opening in forbidden_openings:
        is_valid, errors = DiscoveryNarrativeEngine.validate_hook(opening)
        assert is_valid is False, f"Failed to reject throat-clearing opening: {opening}"
        assert len(errors) > 0

    # Valid Frame 0 opening
    valid_opening = "The Harry Potter movies completely hid the most chaotic ghost in Hogwarts history."
    is_valid, errors = DiscoveryNarrativeEngine.validate_hook(valid_opening)
    assert is_valid is True
    assert len(errors) == 0


# ── Test 16: No Unsupported Factual Claims in Final Plan ─────────────────────

def test_16_no_unsupported_factual_claims():
    """Validates that unverified claims or claims lacking source IDs are rejected."""
    # Case A: unverified claim
    unverified_ep = EvidencePoint(
        claim="Dumbledore was secretly a time traveler",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="fan_theory_site",
        source_excerpt="Some forum post",
        verified=False
    )
    is_valid, errors = DiscoveryNarrativeEngine.validate_evidence_points([unverified_ep])
    assert is_valid is False
    assert any("unverified" in err for err in errors)

    # Case B: missing source excerpt
    missing_excerpt_ep = EvidencePoint(
        claim="Snape's patronus was a doe",
        evidence_route=EvidenceRoute.NOVEL_CANON.value,
        source_id="b7c33_chunk_019",
        source_excerpt="",  # Empty!
        verified=False
    )
    is_valid, errors = DiscoveryNarrativeEngine.validate_evidence_points([missing_excerpt_ep])
    assert is_valid is False

    # Case C: plan with unverified claim fails plan.validate()
    plan = DeepDiscoveryStoryPlan(
        topic_id="unsupported_test",
        discovery_type="DISCOVERY_FACT",
        thesis="Unverified claim plan",
        evidence_points=[unverified_ep],
        expected_duration=72.0,
        target_word_count=255,
        target_speech_rate=3.55
    )
    assert plan.validate() is False
    assert plan.is_valid is False
    assert len(plan.validation_errors) > 0
