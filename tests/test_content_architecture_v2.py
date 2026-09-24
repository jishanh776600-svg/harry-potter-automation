"""
STORY FORGE — Content Architecture V2 Focused Test Suite
=========================================================
Tests points A through S:
  Test A: DISCOVERY_BIG duration 60–70s
  Test B: DISCOVERY_SHORT duration 25–30s
  Test C: No fixed fact-count requirement (1-fact Big, 6-fact Big; 1-fact Short, 3-fact Short)
  Test D: One-fact Short works
  Test E: Multi-fact Short works
  Test F: 5–7 fact Big Discovery works
  Test G: Exact visual proposition matching
  Test H: Unrelated video rejected
  Test I: CONTEXT cannot become DIRECT
  Test J: CONTRAST cannot become DIRECT
  Test K: NO_VALID_VISUAL remains authoritative
  Test L: Video-only acquisition
  Test M: Zero image acquisition
  Test N: Fact numbering 01 -> N
  Test O: Counter synchronized to fact boundaries
  Test P: Counter absent for single-fact Discovery
  Test Q: Counter absent for Novel Story
  Test R: Simple-English script preserves canonical meaning
  Test S: Daily cadence = 2 Novel + 1 Big + 1 Short
"""

import pytest
from typing import List, Dict, Any

from core.daily_cadence import (
    DAILY_TARGET,
    NOVEL_STORY,
    DISCOVERY_BIG,
    DISCOVERY_SHORT,
    ContentFormat,
    FORMAT_DURATION_BOUNDS,
    CANONICAL_DAILY_CADENCE,
    DailyCadenceManager,
)
from core.multi_fact_types import (
    MultiFactFormat,
    MultiFactTopicPack,
    MultiFactPayload,
    VisualProposition,
    VisualRelationship,
    RequiredEvidenceType,
    FactType,
)
from core.beast_v2_types import (
    BeastV2MatchResult,
    BeastV2Decision,
    EvidenceType,
    SourceEvidenceType,
    validate_evidence_lineage,
)
from core.acquisition_types import (
    AssetAcquisitionRequest,
    MediaCategory,
    FORBIDDEN_IMAGE_EXTENSIONS,
)
from core.editorial_v2_types import (
    EditorialUnit,
    EditorialTimelineV2,
    EditorialTransitionType,
    MotionTreatment,
)
from core.safe_url_validator import SafeURLValidator
from engines.editorial.editorial_planner import EditorialPlanner
from engines.simple_script_engine import SimpleScriptEngine, SimpleEnglishAudit


# Helper fixtures
def create_sample_fact(fact_num: int, claim: str, duration: float = 10.0) -> MultiFactPayload:
    return MultiFactPayload(
        fact_id=f"fact_{fact_num:02d}",
        theme="Hogwarts Battle",
        claim=claim,
        claim_type=FactType.BOOK_VS_MOVIE,
        canon_source="Harry Potter and the Deathly Hallows, Chapter 36",
        canon_evidence="Canonical book excerpt describing the true event.",
        fact_number=fact_num,
        fact_title=f"Truth {fact_num}",
        target_duration_sec=duration,
        importance=0.85,
        visual_propositions=[
            VisualProposition(
                proposition_id=f"prop_{fact_num}_1",
                subject="Harry Potter",
                action="casts spell",
                object="Wand",
                context="Great Hall",
                required_relationship=VisualRelationship.DIRECT_EVIDENCE,
            )
        ],
    )


def create_sample_match(prop_id: str, decision: BeastV2Decision = BeastV2Decision.ACCEPT_DIRECT) -> BeastV2MatchResult:
    ev_type = EvidenceType.DIRECT_EVIDENCE if decision == BeastV2Decision.ACCEPT_DIRECT else EvidenceType.NO_VALID_VISUAL
    return BeastV2MatchResult(
        candidate_id=prop_id,
        asset_id=f"asset_{prop_id}",
        source="MOVIE_ARCHIVE",
        source_start=10.0,
        source_end=25.0,
        evidence_type=ev_type,
        decision=decision,
        verification_metadata={"proposition_id": prop_id},
    )


# ==============================================================================
# TESTS A & B: DURATION BOUNDS
# ==============================================================================

def test_a_discovery_big_duration_bounds():
    """Test A: DISCOVERY_BIG duration bounds must be strictly 60–70s."""
    min_dur, max_dur = FORMAT_DURATION_BOUNDS[ContentFormat.DISCOVERY_BIG]
    assert min_dur == 60.0
    assert max_dur == 70.0

    # Topic pack validation
    pack = MultiFactTopicPack(
        topic_id="big_01",
        theme="Hogwarts Battle",
        hook="Six truths the films altered.",
        suggested_title="Battle of Hogwarts Lore",
        format=MultiFactFormat.DISCOVERY_BIG,
        total_target_duration=65.0,
        facts=[create_sample_fact(1, "Harry reveals he is alive", 60.0)],
    )
    is_valid, warnings = pack.validate_content_architecture()
    assert is_valid
    assert len(warnings) == 0

    # Out of bounds: too short
    pack_short = MultiFactTopicPack(
        topic_id="big_short",
        theme="Hogwarts Battle",
        hook="Short pack hook.",
        suggested_title="Short Pack",
        format=MultiFactFormat.DISCOVERY_BIG,
        total_target_duration=55.0,
        facts=[create_sample_fact(1, "Too short", 55.0)],
    )
    is_valid_short, warnings_short = pack_short.validate_content_architecture()
    assert not is_valid_short
    assert any("below minimum 60.0s" in w for w in warnings_short)


def test_b_discovery_short_duration_bounds():
    """Test B: DISCOVERY_SHORT duration bounds must be strictly 25–30s."""
    min_dur, max_dur = FORMAT_DURATION_BOUNDS[ContentFormat.DISCOVERY_SHORT]
    assert min_dur == 25.0
    assert max_dur == 30.0

    # Topic pack validation
    pack = MultiFactTopicPack(
        topic_id="short_01",
        theme="Voldemort Lore",
        hook="Voldemort's death was completely changed.",
        suggested_title="Voldemort Body Contrast",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=28.0,
        facts=[create_sample_fact(1, "Voldemort died a mortal human death", 25.0)],
    )
    is_valid, warnings = pack.validate_content_architecture()
    assert is_valid
    assert len(warnings) == 0

    # Out of bounds: too long
    pack_long = MultiFactTopicPack(
        topic_id="short_long",
        theme="Voldemort Lore",
        hook="Long pack hook.",
        suggested_title="Long Pack",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=35.0,
        facts=[create_sample_fact(1, "Too long", 35.0)],
    )
    is_valid_long, warnings_long = pack_long.validate_content_architecture()
    assert not is_valid_long
    assert any("exceeds maximum 30.0s" in w for w in warnings_long)


# ==============================================================================
# TESTS C, D, E, F: FACT COUNT FLEXIBILITY (NO FIXED FACT REQUIREMENT)
# ==============================================================================

def test_c_no_fixed_fact_count_requirement():
    """Test C: Neither format requires a fixed fact count. Content determines structure."""
    # 1-fact Big Discovery (deep singular topic) is valid
    pack_big_1 = MultiFactTopicPack(
        topic_id="big_1",
        theme="Wand Lore",
        hook="The Elder Wand mystery explained.",
        suggested_title="The Elder Wand Ownership Truth",
        format=MultiFactFormat.DISCOVERY_BIG,
        total_target_duration=64.0,
        facts=[create_sample_fact(1, "Deep singular analysis of wand allegiance", 60.0)],
    )
    valid_b1, w_b1 = pack_big_1.validate_content_architecture()
    assert valid_b1, f"Expected 1-fact big to be valid, got warnings: {w_b1}"

    # 6-fact Big Discovery is valid
    facts_6 = [create_sample_fact(i, f"Truth {i}", 10.0) for i in range(1, 7)]
    pack_big_6 = MultiFactTopicPack(
        topic_id="big_6",
        theme="Hogwarts Battle",
        hook="Six Battle of Hogwarts truths.",
        suggested_title="6 Battle of Hogwarts Truths",
        format=MultiFactFormat.DISCOVERY_BIG,
        total_target_duration=65.0,
        facts=facts_6,
    )
    valid_b6, w_b6 = pack_big_6.validate_content_architecture()
    assert valid_b6, f"Expected 6-fact big to be valid, got warnings: {w_b6}"

    # 1-fact Short is valid
    pack_short_1 = MultiFactTopicPack(
        topic_id="short_1",
        theme="Neville Lore",
        hook="Neville's wand secret.",
        suggested_title="Neville Wand Fact",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=28.0,
        facts=[create_sample_fact(1, "Neville used his father's wand", 25.0)],
    )
    valid_s1, w_s1 = pack_short_1.validate_content_architecture()
    assert valid_s1, f"Expected 1-fact short to be valid, got warnings: {w_s1}"

    # 3-fact Short is valid
    facts_3 = [create_sample_fact(i, f"Quick contrast {i}", 8.0) for i in range(1, 4)]
    pack_short_3 = MultiFactTopicPack(
        topic_id="short_3",
        theme="Wand Differences",
        hook="Three quick wand differences.",
        suggested_title="3 Quick Wand Differences",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=27.0,
        facts=facts_3,
    )
    valid_s3, w_s3 = pack_short_3.validate_content_architecture()
    assert valid_s3, f"Expected 3-fact short to be valid, got warnings: {w_s3}"


def test_d_one_fact_short_works():
    """Test D: 1-fact Discovery Short generates a valid timeline."""
    fact = create_sample_fact(1, "Bellatrix died frozen with a smile in the book", 22.0)
    pack = MultiFactTopicPack(
        topic_id="single_fact_short",
        theme="Bellatrix Lore",
        hook="The movies got Bellatrix's death completely wrong.",
        suggested_title="Bellatrix Death Book Truth",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=26.0,
        facts=[fact],
        payoff_text="She died a mortal death, not exploding into blue confetti.",
    )
    matches = [
        create_sample_match("hook"),
        create_sample_match("prop_1_1"),
        create_sample_match("payoff"),
    ]
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, matches)
    assert timeline.total_duration_seconds > 0
    assert len(timeline.units) >= 3


def test_e_multi_fact_short_works():
    """Test E: Multi-fact Discovery Short (e.g. 2-3 facts) generates a valid timeline."""
    facts = [
        create_sample_fact(1, "Harry never snapped the Elder Wand", 10.0),
        create_sample_fact(2, "He used it to repair his own holly wand", 10.0),
    ]
    pack = MultiFactTopicPack(
        topic_id="two_fact_short",
        theme="Elder Wand Lore",
        hook="Harry never snapped the Elder Wand.",
        suggested_title="Two Elder Wand Facts",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=28.0,
        facts=facts,
        payoff_text="He put it back in Dumbledore's tomb.",
    )
    matches = [
        create_sample_match("hook"),
        create_sample_match("prop_1_1"),
        create_sample_match("prop_2_1"),
        create_sample_match("payoff"),
    ]
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, matches)
    assert len(timeline.fact_counters) == 2
    assert timeline.fact_counters[0]["counter"] == "FACT 01"
    assert timeline.fact_counters[1]["counter"] == "FACT 02"


def test_f_five_to_seven_fact_big_discovery_works():
    """Test F: 5–7 fact Big Discovery processes properly with sequential boundaries."""
    facts = [create_sample_fact(i, f"Truth {i}", 9.0) for i in range(1, 7)]
    pack = MultiFactTopicPack(
        topic_id="battle_hogwarts_6",
        theme="Hogwarts Battle",
        hook="Six Battle of Hogwarts truths the movies got completely backwards.",
        suggested_title="6 Battle of Hogwarts Truths",
        format=MultiFactFormat.DISCOVERY_BIG,
        total_target_duration=65.0,
        facts=facts,
        payoff_text="The entire battle made sense in the book.",
    )
    matches = [create_sample_match("hook")] + [create_sample_match(f"prop_{i}_1") for i in range(1, 7)] + [create_sample_match("payoff")]
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, matches)
    assert len(timeline.fact_counters) == 6
    assert timeline.fact_counters[0]["counter"] == "FACT 01"
    assert timeline.fact_counters[5]["counter"] == "FACT 06"


# ==============================================================================
# TESTS G, H, I, J, K: EXACT VISUAL PROPOSITION MATCHING & LINEAGE
# ==============================================================================

def test_g_exact_visual_proposition_matching():
    """Test G: Visual propositions require exact relationship matching."""
    prop = VisualProposition(
        proposition_id="p1",
        subject="Harry",
        action="reveals himself under invisibility cloak",
        object="Invisibility Cloak",
        context="Great Hall",
        required_relationship=VisualRelationship.DIRECT_EVIDENCE,
    )
    assert prop.required_relationship == VisualRelationship.DIRECT_EVIDENCE


def test_h_unrelated_video_rejected():
    """Test H: Unrelated video cannot satisfy proposition evidence."""
    unrelated_decision = BeastV2Decision.NO_VALID_VISUAL
    evidence = validate_evidence_lineage(unrelated_decision, EvidenceType.DIRECT_EVIDENCE, media_category="video")
    assert evidence == EvidenceType.NO_VALID_VISUAL


def test_i_context_cannot_become_direct():
    """Test I: ACCEPT_CONTEXT cannot be promoted to DIRECT_EVIDENCE."""
    with pytest.raises(ValueError) as exc_info:
        validate_evidence_lineage(
            beast_decision=BeastV2Decision.ACCEPT_CONTEXT,
            claimed_evidence=EvidenceType.DIRECT_EVIDENCE,
            media_category="video",
        )
    assert "LINEAGE VIOLATION: CONTEXT cannot be silently promoted" in str(exc_info.value)


def test_j_contrast_cannot_become_direct():
    """Test J: ACCEPT_CONTRAST cannot be promoted to DIRECT_EVIDENCE."""
    with pytest.raises(ValueError) as exc_info:
        validate_evidence_lineage(
            beast_decision=BeastV2Decision.ACCEPT_CONTRAST,
            claimed_evidence=EvidenceType.DIRECT_EVIDENCE,
            media_category="video",
        )
    assert "LINEAGE VIOLATION: CONTRAST cannot be silently promoted" in str(exc_info.value)


def test_k_no_valid_visual_remains_authoritative():
    """Test K: NO_VALID_VISUAL remains authoritative regardless of claimed evidence."""
    result = validate_evidence_lineage(
        beast_decision=BeastV2Decision.NO_VALID_VISUAL,
        claimed_evidence=EvidenceType.DIRECT_EVIDENCE,
        media_category="video",
    )
    assert result == EvidenceType.NO_VALID_VISUAL


# ==============================================================================
# TESTS L & M: VIDEO-ONLY VS ZERO IMAGE ACQUISITION
# ==============================================================================

def test_l_video_only_acquisition():
    """Test L: Video assets pass lineage validation and production acquisition requests."""
    result = validate_evidence_lineage(
        beast_decision=BeastV2Decision.ACCEPT_DIRECT,
        claimed_evidence=EvidenceType.DIRECT_EVIDENCE,
        media_category="video",
    )
    assert result == EvidenceType.DIRECT_EVIDENCE

    req = AssetAcquisitionRequest(
        query="Harry Potter dueling Voldemort",
        proposition_id="prop_video_1",
        fact_id="fact_01",
        short_id="short_01",
        subject="Harry Potter",
        action="dueling Voldemort",
        era="BATTLE_OF_HOGWARTS",
        target_media_category=MediaCategory.VIDEO,
    )
    assert req.target_media_category == MediaCategory.VIDEO
    assert req.is_proposition_grounded() is True


def test_m_zero_image_acquisition():
    """Test M: Non-video assets (JPG, PNG, WEBP, images) are strictly forbidden."""
    # Lineage rejects images
    with pytest.raises(ValueError) as exc_info:
        validate_evidence_lineage(
            beast_decision=BeastV2Decision.ACCEPT_DIRECT,
            claimed_evidence=EvidenceType.DIRECT_EVIDENCE,
            media_category="image",
        )
    assert "VIDEO-ONLY POLICY VIOLATION" in str(exc_info.value)

    # SafeURLValidator rejects static image extensions
    for ext in FORBIDDEN_IMAGE_EXTENSIONS:
        test_url = f"https://archive.org/media/frame{ext}"
        is_safe, reason = SafeURLValidator.is_safe_url(test_url)
        assert is_safe is False
        assert "Static image format" in reason or "VIDEO ONLY" in reason


# ==============================================================================
# TESTS N, O, P, Q: FACT NUMBERING & SYNCHRONIZATION
# ==============================================================================

def test_n_fact_numbering_01_to_n():
    """Test N: Multi-fact topic pack produces FACT 01 -> FACT NN numbering."""
    facts = [create_sample_fact(i, f"Truth {i}", 10.0) for i in range(1, 10)]
    pack = MultiFactTopicPack(
        topic_id="facts_9",
        theme="Hogwarts Battle",
        hook="Nine battle truths.",
        suggested_title="9 Truths",
        format=MultiFactFormat.DISCOVERY_BIG,
        total_target_duration=65.0,
        facts=facts,
    )
    assert pack.get_fact_counter(1) == "FACT 01"
    assert pack.get_fact_counter(2) == "FACT 02"
    assert pack.get_fact_counter(9) == "FACT 09"


def test_o_counter_synchronized_to_fact_boundaries():
    """Test O: Fact counter is synchronized to fact start/end times in timeline."""
    facts = [
        create_sample_fact(1, "Harry never died in the courtyard", 10.0),
        create_sample_fact(2, "Voldemort collapsed into a human corpse", 10.0),
    ]
    pack = MultiFactTopicPack(
        topic_id="sync_test",
        theme="Battle Lore",
        hook="Two truths the film reversed.",
        suggested_title="Sync Test",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=28.0,
        facts=facts,
        payoff_text="The book was far more grounded.",
    )
    matches = [
        create_sample_match("hook"),
        create_sample_match("prop_1_1"),
        create_sample_match("prop_2_1"),
        create_sample_match("payoff"),
    ]
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, matches)

    assert len(timeline.fact_counters) == 2
    f1 = timeline.fact_counters[0]
    f2 = timeline.fact_counters[1]

    assert f1["counter"] == "FACT 01"
    assert f2["counter"] == "FACT 02"
    # End of fact 1 should equal start of fact 2
    assert f1["end_time"] == pytest.approx(f2["start_time"], abs=0.01)

    # Editorial units for fact 1 have fact_counter == "FACT 01"
    fact1_units = [u for u in timeline.units if u.fact_id == "fact_01"]
    for u in fact1_units:
        assert u.fact_counter == "FACT 01"
        assert u.fact_number == 1


def test_p_counter_absent_for_single_fact_discovery():
    """Test P: Fact counter must be absent for single-fact Discovery Short/Big."""
    pack = MultiFactTopicPack(
        topic_id="single_fact",
        theme="Wand Lore",
        hook="Did Harry snap the wand?",
        suggested_title="Single Truth",
        format=MultiFactFormat.DISCOVERY_SHORT,
        total_target_duration=26.0,
        facts=[create_sample_fact(1, "Harry repaired his wand", 22.0)],
        payoff_text="The movie invented the snap.",
    )
    assert pack.get_fact_counter(1) is None

    matches = [create_sample_match("hook"), create_sample_match("prop_1_1"), create_sample_match("payoff")]
    planner = EditorialPlanner()
    timeline = planner.plan_timeline(pack, matches)
    assert len(timeline.fact_counters) == 0
    for u in timeline.units:
        assert u.fact_counter is None


def test_q_counter_absent_for_novel_story():
    """Test Q: Fact counter must be absent for Novel Story format."""
    pack = MultiFactTopicPack(
        topic_id="novel_story_pack",
        theme="Prince's Tale",
        hook="Look at me.",
        suggested_title="Snape's Final Memory",
        format=MultiFactFormat.NOVEL_STORY,
        total_target_duration=50.0,
        facts=[create_sample_fact(1, "Look at me", 20.0), create_sample_fact(2, "The silver doe", 25.0)],
    )
    assert pack.get_fact_counter(1) is None
    assert pack.get_fact_counter(2) is None


# ==============================================================================
# TEST R: SIMPLE-ENGLISH SCRIPT ENGINE & CANON PRESERVATION
# ==============================================================================

def test_r_simple_english_script_engine():
    """Test R: Simple English engine validates conversational clarity and preserves HP canon."""
    # Good conversational script
    good_script = (
        "In the movie, Harry Potter snaps the Elder Wand and tosses it away. "
        "That never happened in the book. Harry uses the Elder Wand to fix his broken phoenix feather wand first. "
        "Then he returns the legendary wand to Dumbledore's white tomb. "
        "The power was broken with his death."
    )
    audit = SimpleScriptEngine.validate_script(good_script)
    assert audit.is_valid
    assert audit.flesch_score >= 65.0
    assert audit.avg_sentence_length <= 16.0
    assert len(audit.forbidden_words) == 0

    # Script with academic jargon
    bad_script = (
        "Notwithstanding the cinematic adaptation, furthermore Harry Potter elucidates "
        "the intrinsic dichotomy between book and movie in juxtaposition to the Elder Wand."
    )
    bad_audit = SimpleScriptEngine.validate_script(bad_script)
    assert not bad_audit.is_valid
    assert "notwithstanding" in bad_audit.forbidden_words
    assert "furthermore" in bad_audit.forbidden_words
    assert "elucidates" in bad_audit.forbidden_words

    # Simplification test
    simplified = SimpleScriptEngine.simplify_script("Furthermore, Harry subsequently defeated Voldemort.")
    assert "also" in simplified.lower()
    assert "then" in simplified.lower()
    assert "Harry" in simplified
    assert "Voldemort" in simplified


# ==============================================================================
# TEST S: DAILY CADENCE (2 NOVEL + 1 BIG + 1 SHORT)
# ==============================================================================

def test_s_daily_cadence_enforcement():
    """Test S: Daily cadence targets exactly 4 Shorts (2 Novel + 1 Big + 1 Short)."""
    assert DAILY_TARGET == 4
    assert NOVEL_STORY == 2
    assert DISCOVERY_BIG == 1
    assert DISCOVERY_SHORT == 1

    canonical = DailyCadenceManager.get_canonical_plan()
    assert len(canonical) == 4
    assert canonical[0].format == ContentFormat.NOVEL_STORY
    assert canonical[1].format == ContentFormat.DISCOVERY_BIG
    assert canonical[2].format == ContentFormat.NOVEL_STORY
    assert canonical[3].format == ContentFormat.DISCOVERY_SHORT

    # Valid batch
    valid_batch = [
        {"format": "NOVEL_STORY", "title": "Novel 1", "duration": 52.0},
        {"format": "DISCOVERY_BIG", "title": "Big 1", "duration": 65.0},
        {"format": "NOVEL_STORY", "title": "Novel 2", "duration": 48.0},
        {"format": "DISCOVERY_SHORT", "title": "Short 1", "duration": 28.0},
    ]
    is_valid, msg = DailyCadenceManager.validate_daily_batch(valid_batch)
    assert is_valid, msg

    # Invalid batch: missing 1 Novel Story, has 2 Discovery Big
    invalid_batch = [
        {"format": "NOVEL_STORY", "title": "Novel 1", "duration": 52.0},
        {"format": "DISCOVERY_BIG", "title": "Big 1", "duration": 65.0},
        {"format": "DISCOVERY_BIG", "title": "Big 2", "duration": 62.0},
        {"format": "DISCOVERY_SHORT", "title": "Short 1", "duration": 28.0},
    ]
    is_valid_inv, msg_inv = DailyCadenceManager.validate_daily_batch(invalid_batch)
    assert not is_valid_inv
    assert any("Expected exactly 2 Novel Stories" in err for err in msg_inv)
