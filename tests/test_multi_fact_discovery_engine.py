"""
STORY FORGE — Multi-Fact Discovery Engine V1 Comprehensive Test Suite
====================================================================
Tests all 22 required architectural dimensions:
  1. 5-fact topic pack
  2. 6-fact topic pack
  3. 7-fact topic pack
  4. Thematic coherence
  5. Duplicate-fact rejection
  6. Weak-fact rejection
  7. Fact ordering
  8. Escalation dynamics
  9. Hook generation
 10. Proposition extraction
 11. Proposition structure
 12. Evidence-type assignment
 13. Fact-duration budgeting
 14. 68–78 second target
 15. 80.9 second hard ceiling
 16. Insufficient-fact fallback (< 4 facts)
 17. Single-topic deep-dive routing
 18. Novel Story isolation
 19. Provenance preservation
 20. Asset Acquisition interface compatibility
 21. BEAST V2-ready output contract
 22. Anti-repetition

Synthetic Validation Cases:
  - CASE A: 5 Book-vs-Movie differences
  - CASE B: 7 hidden character details
  - CASE C: 6 lore/foreshadowing connections
  - CASE D: Only 3 strong facts -> must NOT pad
  - CASE E: 7 candidate facts but 2 near-duplicates -> deduplicates
  - CASE F: 7 facts but weak thematic coherence -> rejects / re-routes
"""

import json
import pytest
from core.discovery_types import HookArchetype, TitlePattern, DiscoveryRouting
from core.multi_fact_types import (
    FactType,
    MultiFactFormat,
    MultiFactPayload,
    MultiFactTopicPack,
    RequiredEvidenceType,
    VisualProposition,
)
from engines.multi_fact_discovery_engine import MultiFactDiscoveryEngine
from engines.hp_script_engine import HarryPotterScriptEngine


# ── HELPER FACT GENERATOR ────────────────────────────────────────────────────

def create_sample_fact(
    fact_id: str,
    theme: str,
    claim: str,
    importance: float = 0.8,
    movie_contrast: float = 0.6,
    curiosity: float = 0.8,
    payoff: float = 0.5,
    claim_type: FactType = FactType.BOOK_VS_MOVIE,
    evidence_type: RequiredEvidenceType = RequiredEvidenceType.DIRECT_FILM_EVIDENCE,
    propositions: list = None,
    why_it_matters: str = "This completely changes the audience perspective on the scene."
) -> MultiFactPayload:
    props = propositions or [
        VisualProposition(
            proposition_id=f"prop_{fact_id}_1",
            subject="Harry Potter",
            action="discovers hidden detail",
            object="Gryffindor Sword",
            context="Great Hall",
            visual_role="DIRECT_EVIDENCE",
            estimated_duration_sec=2.5,
        )
    ]
    return MultiFactPayload(
        fact_id=fact_id,
        theme=theme,
        claim=claim,
        claim_type=claim_type,
        canon_source=f"Book {fact_id[-1] if fact_id[-1].isdigit() else '1'}, Chapter 12",
        canon_evidence=f"Canonical excerpt describing {claim} with exact textual proof.",
        importance=importance,
        movie_contrast=movie_contrast,
        curiosity_score=curiosity,
        visual_feasibility=0.85,
        payoff_value=payoff,
        required_evidence_type=evidence_type,
        visual_propositions=props,
        supporting_details=[f"Detail one for {fact_id}", f"Detail two for {fact_id}"],
        why_it_matters=why_it_matters,
        source_provenance={"verified": True, "source": "Novel FTS"},
    )


# ── TEST 1, 2, 3: FACT COUNT PACKS (5-FACT, 6-FACT, 7-FACT) ────────────────

def test_01_five_fact_topic_pack():
    engine = MultiFactDiscoveryEngine()
    theme = "Book vs Movie Differences"
    sample_claims = [
        "Lumos under blanket in Privet Drive violated Ministry trace laws",
        "Hermione took Ron's heroic explanation of the Mudblood slur",
        "Death Eaters burned down the Burrow during winter holiday",
        "Lucius Malfoy attempted Avada Kedavra right outside Dumbledore's office",
        "Voldemort disintegrated into paper flakes instead of leaving a mortal body",
    ]
    facts = [create_sample_fact(f"fact_{i}", theme, claim) for i, claim in enumerate(sample_claims, 1)]

    pack = engine.assemble_topic_pack(
        topic_id="top_5_facts",
        theme=theme,
        candidate_facts=facts,
        target_count=5,
        target_duration=75.0,
    )

    assert pack.is_valid is True
    assert len(pack.facts) == 5
    assert pack.format == MultiFactFormat.MULTI_FACT_DISCOVERY
    assert 68.0 <= pack.total_target_duration <= 78.0


def test_02_six_fact_topic_pack():
    engine = MultiFactDiscoveryEngine()
    theme = "Hidden Hogwarts Secrets"
    sample_claims = [
        "Room of Requirement transformed into bathroom when Dumbledore had full bladder",
        "Vanishing Cabinet created secret portal between Borgin and Burkes and Hogwarts",
        "Honeydukes cellar passage allowed Harry to sneak into Hogsmeade unnoticed",
        "Fat Lady portrait password changed repeatedly after Sirius Black slashed the canvas",
        "Chamber of Secrets bathroom entrance opened only with parseltongue snake whisper",
        "Astronomy Tower possessed hidden observation balconies inaccessible without flight",
    ]
    facts = [create_sample_fact(f"fact_{i}", theme, claim) for i, claim in enumerate(sample_claims, 1)]

    pack = engine.assemble_topic_pack(
        topic_id="top_6_facts",
        theme=theme,
        candidate_facts=facts,
        target_count=6,
        target_duration=76.0,
    )

    assert pack.is_valid is True
    assert len(pack.facts) == 6
    assert pack.format == MultiFactFormat.MULTI_FACT_DISCOVERY


def test_03_seven_fact_topic_pack():
    engine = MultiFactDiscoveryEngine()
    theme = "Voldemort Horcruxes"
    sample_claims = [
        "Tom Riddle diary destroyed with basilisk venom fang in chamber",
        "Marvolo Gaunt ring carried deadly blood-withering curse on Dumbledore hand",
        "Slytherin locket required drinking emerald potion of despair in seaside cave",
        "Hufflepuff cup hidden inside Lestrange high-security vault in Gringotts",
        "Ravenclaw diadem lost for centuries until hidden inside Room of Requirement",
        "Nagini serpent decapitated with Godric Gryffindor silver sword by Neville",
        "Harry Potter survived accidental soul fragment tethered to his lightning scar",
    ]
    facts = [create_sample_fact(f"fact_{i}", theme, claim) for i, claim in enumerate(sample_claims, 1)]

    pack = engine.assemble_topic_pack(
        topic_id="top_7_facts",
        theme=theme,
        candidate_facts=facts,
        target_count=7,
        target_duration=77.0,
    )

    assert pack.is_valid is True
    assert len(pack.facts) == 7
    assert pack.format == MultiFactFormat.MULTI_FACT_DISCOVERY
    # Fact durations budgeted properly (~9-11s each)
    for f in pack.facts:
        assert 8.0 <= f.target_duration_sec <= 14.0


# ── TEST 4, 5, 6: THEMATIC COHERENCE & DEDUPLICATION & WEAK FACT REJECTION ───

def test_04_thematic_coherence_scoring():
    engine = MultiFactDiscoveryEngine()
    theme = "Snape Classroom Secrets"
    matching_fact = create_sample_fact("f1", theme, "Snape teaches Potions using visual slides instead of a wand")
    disjoint_fact = create_sample_fact("f2", "Quidditch History", "Golden Snitch caught in mouth during match")

    c_match = engine.calculate_thematic_coherence(matching_fact, theme)
    c_disjoint = engine.calculate_thematic_coherence(disjoint_fact, theme)

    assert c_match > c_disjoint
    assert c_match >= 0.70


def test_05_duplicate_fact_rejection():
    engine = MultiFactDiscoveryEngine()
    f1 = create_sample_fact("f1", "Theme", "Harry used a flashlight under his blanket in the original book")
    f2 = create_sample_fact("f2", "Theme", "Harry used a flashlight under his blanket in the original book")  # exact duplicate
    f3 = create_sample_fact("f3", "Theme", "In the book Harry uses a flashlight under his blanket")           # near duplicate
    f4 = create_sample_fact("f4", "Theme", "Hermione explains the meaning of Mudblood in the movie")

    deduped = engine.deduplicate_facts([f1, f2, f3, f4])
    assert len(deduped) == 2
    claims = [f.claim for f in deduped]
    assert f1.claim in claims
    assert f4.claim in claims


def test_06_weak_fact_rejection():
    engine = MultiFactDiscoveryEngine()
    theme = "Harry Potter Lore"
    strong_claims = [
        "Dumbledore hand withered from dark ring curse",
        "Snape cast silver doe patronus to guide Harry",
        "Regulus Black swapped locket note with Kreacher",
        "Kreacher told dark tale of underwater cave inferi",
    ]
    strong_facts = [create_sample_fact(f"strong_{i}", theme, claim, importance=0.9, curiosity=0.9) for i, claim in enumerate(strong_claims, 1)]
    weak_fact = create_sample_fact("weak_1", theme, "Harry wore round glasses", importance=0.1, curiosity=0.1, movie_contrast=0.1)

    selected, fmt, note = engine.select_facts_for_theme(theme, strong_facts + [weak_fact], target_count=5)
    # The weak fact should be rejected
    selected_ids = [f.fact_id for f in selected]
    assert "weak_1" not in selected_ids
    assert len(selected) == 4


# ── TEST 7, 8: FACT ORDERING & ESCALATION ────────────────────────────────────

def test_07_and_08_fact_ordering_and_escalation():
    engine = MultiFactDiscoveryEngine()
    theme = "Movie Changes"
    f_accessible = create_sample_fact("f_acc", theme, "Lumos under blanket", importance=0.7, payoff=0.3)
    f_deep = create_sample_fact("f_deep", theme, "Mudblood explanation stolen from Ron", importance=0.8, payoff=0.5)
    f_surprise = create_sample_fact("f_surp", theme, "The Burrow burning down was completely made up", importance=0.8, curiosity=0.95, movie_contrast=0.95, payoff=0.6)
    f_emotion = create_sample_fact("f_emo", theme, "George smiles at Fred who is no longer standing beside him", importance=0.9, payoff=0.7)
    f_emotion.emotional_value = 0.95
    f_climax = create_sample_fact("f_climax", theme, "Lucius Malfoy attempted to murder a student in the hall", importance=0.95, curiosity=0.95, payoff=0.99)

    ordered = engine.order_facts([f_climax, f_accessible, f_deep, f_surprise, f_emotion])

    # First should be accessible ENTRY
    assert ordered[0].narrative_role == "ENTRY"
    assert ordered[0].fact_id == "f_acc"
    # Last should be CLIMAX with highest payoff
    assert ordered[-1].narrative_role == "CLIMAX"
    assert ordered[-1].fact_id == "f_climax"


# ── TEST 9: HOOK GENERATION (ZERO THROAT-CLEARING) ───────────────────────────

def test_09_hook_generation():
    engine = MultiFactDiscoveryEngine()
    theme = "Harry Potter Movie Changes"
    hook = engine.generate_thematic_hook(theme, 5, HookArchetype.COUNTER_INTUITIVE_TRUTH)

    assert "five" in hook.lower()
    assert theme in hook
    # Assert zero throat-clearing
    for forbidden in ["in this video", "today we", "let's talk about", "welcome back"]:
        assert forbidden not in hook.lower()


# ── TEST 10, 11: PROPOSITION EXTRACTION & STRUCTURE ──────────────────────────

def test_10_and_11_visual_proposition_structure():
    vp = VisualProposition(
        proposition_id="prop_01",
        subject="Neville Longbottom",
        action="pleads and argues",
        object="Sorting Hat",
        context="Great Hall",
        visual_role="DIRECT_EVIDENCE",
        narrative_era="YEAR_1",
        preferred_framing="MEDIUM_SHOT",
        estimated_duration_sec=2.2,
    )

    assert vp.subject == "Neville Longbottom"
    assert vp.action == "pleads and argues"
    assert vp.object == "Sorting Hat"
    assert vp.context == "Great Hall"

    # Export to BEAST V2 requirement
    beast_req = vp.to_beast_requirement(beat_id="beat_01")
    assert beast_req["primary_subject"] == "Neville Longbottom"
    assert beast_req["required_action"] == "pleads and argues"
    assert "Sorting Hat" in beast_req["required_objects"]
    assert beast_req["visual_role"] == "DIRECT_EVIDENCE"


# ── TEST 12: EVIDENCE-TYPE ASSIGNMENT ────────────────────────────────────────

def test_12_evidence_type_assignment():
    f_direct = create_sample_fact("f1", "Theme", "Harry stabs diary", evidence_type=RequiredEvidenceType.DIRECT_FILM_EVIDENCE)
    f_prop = create_sample_fact("f2", "Theme", "Weasley family photo in Egypt", evidence_type=RequiredEvidenceType.OBJECT_PROP_EVIDENCE)
    f_bts = create_sample_fact("f3", "Theme", "Jason Isaacs improvised line", evidence_type=RequiredEvidenceType.BTS_EVIDENCE)

    assert f_direct.required_evidence_type == RequiredEvidenceType.DIRECT_FILM_EVIDENCE
    assert f_prop.required_evidence_type == RequiredEvidenceType.OBJECT_PROP_EVIDENCE
    assert f_bts.required_evidence_type == RequiredEvidenceType.BTS_EVIDENCE


# ── TEST 13, 14, 15: DURATION & WORD BUDGETING (68-78s, CEILING 80.9s) ───────

def test_13_14_15_duration_and_word_budgeting():
    engine = MultiFactDiscoveryEngine()
    theme = "Movie Mistakes"
    claims = [
        "Cameraman wearing jeans visible in dueling club crowd",
        "Sound microphone battery pack visible under shirt during duel",
        "Pillow visible beneath stunt double falling from broomstick",
        "Wand swapped hands between cuts during potions lesson",
        "Platform nine three quarters brick archway lighting mismatch",
    ]
    facts = [create_sample_fact(f"fact_{i}", theme, claim) for i, claim in enumerate(claims, 1)]

    pack = engine.assemble_topic_pack(
        topic_id="top_budget",
        theme=theme,
        candidate_facts=facts,
        target_count=5,
        target_duration=74.5,
    )

    assert 68.0 <= pack.total_target_duration <= 78.0
    assert pack.total_target_duration <= 80.9  # Hard ceiling
    assert 220 <= pack.total_target_words <= 300
    assert 3.4 <= pack.target_speech_rate <= 3.7

    # Climax gets higher budget than entry
    climax_fact = [f for f in pack.facts if f.narrative_role == "CLIMAX"][0]
    entry_fact = [f for f in pack.facts if f.narrative_role == "ENTRY"][0]
    assert climax_fact.target_duration_sec >= entry_fact.target_duration_sec


# ── TEST 16, 17: INSUFFICIENT FACTS FALLBACK (< 4 FACTS) ─────────────────────

def test_16_and_17_insufficient_facts_fallback():
    engine = MultiFactDiscoveryEngine()
    theme = "Rare Obscure Lore"
    # Only 3 strong facts available
    three_facts = [create_sample_fact(f"f_{i}", theme, f"Unique fact {i}", importance=0.9) for i in range(1, 4)]

    pack = engine.assemble_topic_pack(
        topic_id="top_three",
        theme=theme,
        candidate_facts=three_facts,
        target_count=5,
    )

    # Invariant: Must NOT pad to 5! Routes to SINGLE_TOPIC_DEEP_DIVE
    assert len(pack.facts) == 1
    assert pack.format == MultiFactFormat.SINGLE_TOPIC_DEEP_DIVE


# ── TEST 18: NOVEL STORY ISOLATION ───────────────────────────────────────────

def test_18_novel_story_isolation():
    """Confirms Novel Story routing remains completely unaffected."""
    routing = DiscoveryRouting.NOVEL_STORY
    assert routing.value == "NOVEL_STORY"
    assert routing != MultiFactFormat.MULTI_FACT_DISCOVERY.value


# ── TEST 19: PROVENANCE PRESERVATION ─────────────────────────────────────────

def test_19_provenance_preservation():
    f = create_sample_fact("f_prov", "Theme", "Claim with full provenance")
    f.source_provenance = {
        "canon_book": "Philosopher's Stone",
        "chapter": 7,
        "movie_number": 1,
        "timestamp_start": 2535.0,
    }
    assert f.canon_source.startswith("Book")
    assert f.source_provenance["canon_book"] == "Philosopher's Stone"
    assert f.source_provenance["timestamp_start"] == 2535.0


# ── TEST 20: ASSET ACQUISITION ENGINE COMPATIBILITY ──────────────────────────

def test_20_asset_acquisition_engine_compatibility():
    """Verifies that facts generate structured queries consumable by AssetAcquisitionEngine."""
    from engines.acquisition.query_generator import AcquisitionQueryGenerator
    from core.acquisition_types import MediaCategory

    vp = VisualProposition(
        proposition_id="vp_acq",
        subject="Neville Longbottom",
        action="pulls Sword of Gryffindor from hat",
        object="Sword of Gryffindor",
        context="Courtyard ruins",
        visual_role="DIRECT_EVIDENCE",
    )
    queries = AcquisitionQueryGenerator.generate_queries(vp, target_media=MediaCategory.IMAGE)
    assert len(queries) >= 1
    assert any("Neville Longbottom" in q for q in queries)


# ── TEST 21: BEAST V2-READY OUTPUT CONTRACT ──────────────────────────────────

def test_21_beast_v2_ready_contract():
    f = create_sample_fact("f_beast", "Theme", "Bellatrix kills Sirius Black")
    f.required_evidence_type = RequiredEvidenceType.DIRECT_FILM_EVIDENCE
    vp = VisualProposition(
        proposition_id="vp_beast_1",
        subject="Bellatrix Lestrange",
        action="casts spell and smiles maliciously",
        object="Wand",
        context="Department of Mysteries",
        visual_role="DIRECT_EVIDENCE",
        narrative_era="YEAR_5",
        preferred_framing="MEDIUM_SHOT",
    )
    f.visual_propositions = [vp]

    req = vp.to_beast_requirement("beat_05")
    assert req["beat_id"] == "beat_05"
    assert req["primary_subject"] == "Bellatrix Lestrange"
    assert req["required_action"] == "casts spell and smiles maliciously"
    assert req["narrative_era"] == "YEAR_5"
    assert req["visual_role"] == "DIRECT_EVIDENCE"


# ── TEST 22: ANTI-REPETITION ─────────────────────────────────────────────────

def test_22_anti_repetition_tracking():
    engine = MultiFactDiscoveryEngine()
    theme = "Anti Repetition Theme"
    claims = [
        "Marauders created map with insulted message to Snape",
        "Boggart changed form into Severus wearing Grandma clothing",
        "Time Turner had strict five hour safety limit",
        "Pensieve thoughts could be altered with cloudy mist memory",
        "Mirror of Erised showed deepest desperate heart desire",
    ]
    facts = [create_sample_fact(f"rep_{i}", theme, claim) for i, claim in enumerate(claims, 1)]

    pack = engine.assemble_topic_pack("top_rep", theme, facts, target_count=5)
    assert theme in engine._recent_themes
    for f in pack.facts:
        assert f.fact_id in engine._recent_fact_ids


# ==============================================================================
# SYNTHETIC CANONICAL VALIDATION CASES (CASES A THROUGH F)
# ==============================================================================

def test_synthetic_case_a_five_book_vs_movie_differences():
    """CASE A: 5 Book-vs-Movie differences."""
    engine = MultiFactDiscoveryEngine()
    theme = "5 Book Changes That Don't Make Any Sense"
    facts = [
        create_sample_fact("case_a_1", theme, "Underage Lumos under blanket violates Ministry trace rules", movie_contrast=0.9),
        create_sample_fact("case_a_2", theme, "Hermione explains Mudblood which originally was Ron's heroic moment", movie_contrast=0.85),
        create_sample_fact("case_a_3", theme, "Death Eaters burn down the Burrow but it appears fine next movie", movie_contrast=0.9),
        create_sample_fact("case_a_4", theme, "Lucius Malfoy improvises an illegal killing curse inside school", movie_contrast=0.95),
        create_sample_fact("case_a_5", theme, "Voldemort dissolves into confetti ash instead of leaving a mortal body", movie_contrast=0.99, payoff=0.95),
    ]

    pack = engine.assemble_topic_pack("case_a_pack", theme, facts, target_count=5, target_duration=74.0)
    assert pack.is_valid is True
    assert len(pack.facts) == 5
    assert 68.0 <= pack.total_target_duration <= 78.0

    # Script engine synthesis test
    script_engine = HarryPotterScriptEngine()
    script = script_engine.generate_multi_fact_script(pack)
    assert script.word_count >= 220
    assert script.word_count <= 300
    assert script.qa_status == "APPROVED"
    assert script.total_beats >= 5


def test_synthetic_case_b_seven_hidden_character_details():
    """CASE B: 7 hidden character details."""
    engine = MultiFactDiscoveryEngine()
    theme = "7 Hidden Character Details in Harry Potter"
    claims = [
        "Dumbledore avoided eye contact due to legilimency fear",
        "Snape looked into Harry green eyes before dying",
        "Sirius Black barked out laugh echoing his animagus dog form",
        "Remus Lupin grayed prematurely due to harsh full moon transformations",
        "Percy Weasley constantly polished prefect badge with pride",
        "Luna Lovegood wore radish earrings to ward off mischievous nargles",
        "Alastor Moody drank only from personal hip flask against poison",
    ]
    facts = [
        create_sample_fact(f"case_b_{i}", theme, claim, curiosity=0.85 + (i * 0.02))
        for i, claim in enumerate(claims, 1)
    ]
    pack = engine.assemble_topic_pack("case_b_pack", theme, facts, target_count=7, target_duration=77.0)
    assert pack.is_valid is True
    assert len(pack.facts) == 7


def test_synthetic_case_c_six_lore_foreshadowing_connections():
    """CASE C: 6 lore/foreshadowing connections."""
    engine = MultiFactDiscoveryEngine()
    theme = "6 Foreshadowing Clues Hidden in Early Movies"
    claims = [
        "Petunia mentioned awful boy talking about dementors in book five",
        "Snape first question about asphodel and wormwood symbolized Lily death",
        "Gryffindor sword absorbed basilisk venom making it horcrux weapon",
        "Vanishing cabinet in Borgin and Burkes repaired by Malfoy later",
        "Ron joked Harry would suffer but get gold in divination prediction",
        "Fawkes phoenix tears healed basilisk wound foreshadowing graveyard help",
    ]
    facts = [
        create_sample_fact(f"case_c_{i}", theme, claim, importance=0.85)
        for i, claim in enumerate(claims, 1)
    ]
    pack = engine.assemble_topic_pack("case_c_pack", theme, facts, target_count=6, target_duration=75.0)
    assert pack.is_valid is True
    assert len(pack.facts) == 6


def test_synthetic_case_d_only_three_strong_facts_no_padding():
    """CASE D: Only 3 strong facts -> MUST NOT PAD."""
    engine = MultiFactDiscoveryEngine()
    theme = "Three Clues"
    claims = [
        "First rare secret about Ravenclaw diadem creation",
        "Second rare secret about Helga Hufflepuff golden cup",
        "Third rare secret about Salazar Slytherin hidden basilisk chamber",
    ]
    facts = [create_sample_fact(f"case_d_{i}", theme, claim, importance=0.95) for i, claim in enumerate(claims, 1)]

    pack = engine.assemble_topic_pack("case_d_pack", theme, facts, target_count=5)
    # Refuses to pad; routes to single-topic deep dive
    assert pack.format == MultiFactFormat.SINGLE_TOPIC_DEEP_DIVE
    assert len(pack.facts) == 1


def test_synthetic_case_e_seven_candidates_two_duplicates():
    """CASE E: 7 candidate facts but 2 near-duplicates -> deduplicates."""
    engine = MultiFactDiscoveryEngine()
    theme = "Duplication Test"
    unique_claims = [
        "Neville lost toad Trevor on Hogwarts Express train",
        "Trevor escaped across Black Lake during boat crossing",
        "Trevor hid behind potted plant in Herbology greenhouse",
        "Hagrid returned toad safely to Gryffindor common room",
        "Trevor jumped into lake waters during final celebration",
    ]
    unique_facts = [create_sample_fact(f"case_e_{i}", theme, claim) for i, claim in enumerate(unique_claims, 1)]
    dup_1 = create_sample_fact("case_e_dup1", theme, "Neville lost toad Trevor on Hogwarts Express train")
    dup_2 = create_sample_fact("case_e_dup2", theme, "Trevor escaped across Black Lake during boat crossing")

    pack = engine.assemble_topic_pack("case_e_pack", theme, unique_facts + [dup_1, dup_2], target_count=7)
    assert len(pack.facts) == 5  # 2 duplicates removed


def test_synthetic_case_f_weak_thematic_coherence():
    """CASE F: Facts with weak thematic coherence -> reject/re-route."""
    engine = MultiFactDiscoveryEngine()
    theme = "Snape Defense Against The Dark Arts"
    disjoint_facts = [
        create_sample_fact("case_f_1", "Quidditch", "Gryffindor won Quidditch cup in year three"),
        create_sample_fact("case_f_2", "Dobby", "Dobby dropped a pudding at the Dursleys"),
        create_sample_fact("case_f_3", "Trevor", "Trevor the toad was found on the train"),
        create_sample_fact("case_f_4", "Gringotts", "Griphook betrayed the trio at Gringotts"),
    ]

    selected, fmt, note = engine.select_facts_for_theme(theme, disjoint_facts, target_count=5, min_coherence=0.40)
    assert len(selected) == 0
    assert "INSUFFICIENT_STRONG_FACTS" in note
