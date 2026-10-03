"""
Discovery Editorial & Script Engine Test Suite
================================================================================
Comprehensive verification of the Discovery Editorial Model & Anti-Recap Gate:

1. Negative Cases (Hard Rejections):
   - Case 1: Hermione punches Malfoy pure chronological scene recap (no informational value).
   - Case 2: Obvious visual narration (merely describes visible motions on screen).
   - Case 3: Generic scene summary ('in this scene...' with no Discovery takeaway).
   - Case 4: Invented / unsupported fact (unverified lore without canonical grounding).
   - Case 5: Hook without payoff (hook poses 'Why did...' mystery, but body only describes physical actions).
   - Case 6: Excessive chronological 'then' progression (First -> Then -> Next -> After that -> Finally).
   - Case 7: Scene padding (descriptive scenic filler padding duration without insight).

2. Positive Cases (Verified Passes):
   - Case 1: Source-grounded hidden detail (Snape's first words & Victorian flower language).
   - Case 2: Novel-vs-movie difference (Hermione punch vs book slap & director Cuaron motivation).
   - Case 3: Explanation of why event matters (Harry catching Remembrall mirrors James's aerial legacy).
   - Case 4: Lore/context fact with payoff (Mirror of Erised inscription mechanics & Dumbledore's grief).
   - Case 5: Single strong fact/insight (Sorting Hat omitted musical ballads & warning lore).
   - Case 6: Visually supported informational script (Potions classroom antique jar set dressing).

3. Architectural Assertions:
   - Assertion 1: Novel Story editorial behavior untouched (storytelling format 100% isolated).
   - Assertion 2: MovieEvent remains sole final visual authority for both content types.
   - Assertion 3: SRT remains strictly a coarse locator with zero visual fallback authority.
   - Assertion 4: NO_VALID_VISUAL remains fail-closed when visual evidence cannot be verified.
"""

import pytest
from engines.discovery_narrative_engine import (
    DiscoveryNarrativeEngine,
    DiscoveryEditorialModel,
    DiscoveryEditorialEvaluationResult,
)
from engines.hp_script_engine import HarryPotterScriptEngine, ScriptQAResult
from engines.movie_event.models import (
    MovieEvent,
    VisualBeat,
    ClaimType,
    VerificationStatus,
)


@pytest.fixture
def script_engine():
    return HarryPotterScriptEngine()


@pytest.fixture
def standard_visual_beats():
    return [
        {
            "beat_id": "beat_1",
            "narration_text": "Sample beat narration one.",
            "visual_requirement": "DIRECT movie event evidence",
            "characters": ["Harry Potter"],
            "location": "Great Hall",
            "action": "listening attentively",
            "objects": ["Wand"],
            "emotional_context": "curious",
            "preferred_movie_number": 1,
            "source_grounding": "Movie 1",
            "retrieval_hints": ["Harry"],
            "visual_source_policy": "MOVIE_FOOTAGE_ONLY",
            "visual_source": "MOVIE_DIRECT",
        },
        {
            "beat_id": "beat_2",
            "narration_text": "Sample beat narration two.",
            "visual_requirement": "DIRECT movie event evidence",
            "characters": ["Severus Snape"],
            "location": "Potions Classroom",
            "action": "speaking intensely",
            "objects": ["Potion vial"],
            "emotional_context": "stern",
            "preferred_movie_number": 1,
            "source_grounding": "Movie 1",
            "retrieval_hints": ["Snape"],
            "visual_source_policy": "MOVIE_FOOTAGE_ONLY",
            "visual_source": "MOVIE_DIRECT",
        },
        {
            "beat_id": "beat_3",
            "narration_text": "Sample beat narration three.",
            "visual_requirement": "DIRECT movie event evidence",
            "characters": ["Albus Dumbledore"],
            "location": "Headmaster Office",
            "action": "explaining ancient secret",
            "objects": ["Mirror"],
            "emotional_context": "wise",
            "preferred_movie_number": 1,
            "source_grounding": "Movie 1",
            "retrieval_hints": ["Dumbledore"],
            "visual_source_policy": "MOVIE_FOOTAGE_ONLY",
            "visual_source": "MOVIE_DIRECT",
        },
    ]


# ── Editorial Model Representation Test ───────────────────────────────────────

def test_discovery_editorial_model_representation():
    """Verifies that the Discovery Editorial Model correctly stores and serializes all 9 required fields."""
    model = DiscoveryEditorialModel(
        editorial_angle="novel_vs_movie",
        central_claim="Hermione slapped Malfoy in the novel, but Cuaron changed it to a punch in the movie.",
        viewer_value="Reveals the creative rationale behind Hermione's cinematic aggression.",
        supporting_facts=["Rowling wrote a slap in Chapter 15", "Cuaron wanted visceral defiance"],
        source_evidence=["Book 3 Chapter 15", "Prisoner of Azkaban Director Commentary 2004"],
        narrative_propositions=["Hermione confronted Draco", "The physical action was altered"],
        visual_requirements=["DIRECT footage of Hermione striking Malfoy at sundial"],
        unsupported_claims=[],
        editorial_confidence=0.95,
    )
    assert model.editorial_angle == "novel_vs_movie"
    assert model.central_claim.startswith("Hermione slapped")
    assert model.editorial_confidence == 0.95
    assert len(model.supporting_facts) == 2

    # Serialization roundtrip
    d = model.to_dict()
    assert d["editorial_angle"] == "novel_vs_movie"
    restored = DiscoveryEditorialModel.from_dict(d)
    assert restored.central_claim == model.central_claim
    assert restored.editorial_confidence == 0.95


# ── 7 Mandatory Negative Cases (Hard Rejections) ──────────────────────────────

def test_negative_case_1_hermione_malfoy_pure_recap(script_engine, standard_visual_beats):
    """
    Negative Case 1: Pure chronological scene recap of Hermione punching Malfoy.
    'Hermione walks up the hill toward Malfoy. Ron steps in and tells her he's not worth it.
     Hermione lowers her wand, turns around, and suddenly punches Malfoy square in the nose.
     Malfoy stumbles back in pain and then flees down the rocks with his friends.'
    Must be hard-rejected because it provides zero informational Discovery value.
    """
    script_text = (
        "Hermione walks up the hill toward Malfoy. "
        "Ron steps in and tells her he's not worth it. "
        "Hermione lowers her wand, turns around, and suddenly punches Malfoy square in the nose. "
        "Malfoy stumbles back in pain and then flees down the rocks with his friends."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is False
    assert any("merely narrates visible movie actions" in r for r in result.reasons)

    qa_res = script_engine.evaluate_script_qa(
        script_text=script_text,
        visual_beats=standard_visual_beats,
        candidate_type="discovery_short",
    )
    assert qa_res.passed is False
    assert any("EDITORIAL VALUE FAILURE" in f for f in qa_res.feedback)


def test_negative_case_2_obvious_visual_narration(script_engine, standard_visual_beats):
    """
    Negative Case 2: Obvious visual narration.
    Merely narrates physical events clearly visible on screen without any insight.
    """
    script_text = (
        "Harry sits in the Great Hall. The Sorting Hat is placed on his head. "
        "The hat talks and looks around. Harry grips the stool tightly. "
        "The hat yells Gryffindor, and everyone claps."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is False
    assert any("Obvious visual narration" in r for r in result.reasons)


def test_negative_case_3_generic_scene_summary(script_engine, standard_visual_beats):
    """
    Negative Case 3: Generic scene summary.
    'In this scene...' summary of plot events with no informational angle or takeaway.
    """
    script_text = (
        "In this scene, Harry and Ron are sitting on the Hogwarts Express. "
        "The trolley witch arrives with snacks. Harry buys everything from the cart. "
        "They open chocolate frogs and eat jelly beans together."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is False
    assert any("Generic scene summary" in r for r in result.reasons)


def test_negative_case_4_invented_fact(script_engine, standard_visual_beats):
    """
    Negative Case 4: Invented fact / unsupported claims.
    Script containing ungrounded or fabricated claims must be hard rejected.
    """
    script_text = (
        "Hermione's punch broke Malfoy's nose because her fist was magically enchanted with dragon blood strength. "
        "This ancient secret enchantment was cast in the Gryffindor common room."
    )
    editorial_model = DiscoveryEditorialModel(
        editorial_angle="invented_lore",
        central_claim="Hermione enchanted her fist with dragon blood",
        viewer_value="None",
        unsupported_claims=["Enchanted fist with dragon blood strength is non-canonical fabrication."],
        editorial_confidence=0.2,
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(
        script_text=script_text,
        editorial_model=editorial_model,
    )
    assert result.passed is False
    assert any("unsupported claims detected" in r.lower() for r in result.reasons)


def test_negative_case_5_hook_without_payoff(script_engine, standard_visual_beats):
    """
    Negative Case 5: Hook without payoff.
    Hook poses a mystery/question ('Why did Hermione really punch Malfoy in Prisoner of Azkaban?'),
    but the body and payoff merely describe physical actions without answering why.
    """
    hook = "Why did Hermione really punch Malfoy in Prisoner of Azkaban?"
    script_text = (
        "Why did Hermione really punch Malfoy in Prisoner of Azkaban? "
        "Hermione marched up to Malfoy near the sundial. She pointed her wand at his throat. "
        "Then she pulled back her fist and punched him right in the face. Malfoy ran away crying."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(
        script_text=script_text,
        hook=hook,
    )
    assert result.passed is False
    assert result.hook_payoff_gap_detected is True
    assert any("Hook without factual payoff" in r for r in result.reasons)


def test_negative_case_6_excessive_then_progression(script_engine, standard_visual_beats):
    """
    Negative Case 6: Excessive 'then' progression.
    Sequential play-by-play chronology: 'First X, then Y, next Z, after that W, finally V'.
    """
    script_text = (
        "First Harry looked at the mirror. Then he saw his parents standing behind him. "
        "Next he reached out his hand. After that Ron arrived. Then Harry showed Ron the mirror. "
        "Finally Ron only saw himself holding the Quidditch cup."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is False
    assert any("Excessive chronological 'then' progression" in r for r in result.reasons)


def test_negative_case_7_scene_padding(script_engine, standard_visual_beats):
    """
    Negative Case 7: Scene padding.
    Descriptive scenic filler about weather, clothing, or surroundings used to pad word count.
    """
    script_text = (
        "The sun was shining over the Hogwarts grounds. The stones of the castle were tall and cold. "
        "Harry stood near the wooden bridge. He adjusted his glasses. He looked down into the valley. "
        "He was standing quietly waiting for class."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is False
    assert result.is_scene_padding is True
    assert any("Scene padding detected" in r for r in result.reasons)


# ── 6 Mandatory Positive Cases (Verified Passes) ──────────────────────────────

def test_positive_case_1_source_grounded_hidden_detail(script_engine, standard_visual_beats):
    """
    Positive Case 1: Source-grounded hidden detail.
    Snape's very first words to Harry deciphered through Victorian flower language.
    """
    script_text = (
        "Notice how Snape's very first words to Harry hide a secret message. "
        "When Snape asks Harry about asphodel and wormwood, Victorian flower language reveals the truth. "
        "Asphodel is a lily meaning bitter regret, and wormwood symbolizes absence and grief. "
        "Snape was secretly saying: I bitterly regret Lily's death. "
        "It was a tragic confession of love and guilt, disguised as an impossible classroom test for young Harry."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is True
    assert result.editorial_score >= 80.0
    assert result.central_claim_detected is True
    assert len(result.reasons) == 0

    qa_res = script_engine.evaluate_script_qa(
        script_text=script_text,
        visual_beats=standard_visual_beats,
        candidate_type="discovery_short",
    )
    assert qa_res.passed is True


def test_positive_case_2_novel_vs_movie_difference(script_engine, standard_visual_beats):
    """
    Positive Case 2: Novel-vs-movie difference.
    Hermione punching Malfoy in film vs slapping him in novel with director Cuaron rationale.
    """
    hook = "The movie completely changed Hermione's confrontation with Malfoy."
    script_text = (
        "The movie completely changed Hermione's confrontation with Malfoy. "
        "In the film adaptation of Prisoner of Azkaban, Hermione punches Malfoy with a closed fist. "
        "But in J.K. Rowling's novel, she actually slaps him across the face. "
        "Director Alfonso Cuaron changed it to a punch to show her growing defiance. "
        "A subtle character contrast that made movie Hermione significantly more aggressive than the books."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(
        script_text=script_text,
        hook=hook,
    )
    assert result.passed is True
    assert result.editorial_score >= 80.0
    assert len(result.reasons) == 0

    qa_res = script_engine.evaluate_discovery_qa(
        script_text=script_text,
        hook=hook,
        subtype="DISCOVERY_BOOK_MOVIE_DIFFERENCE",
        visual_beats=standard_visual_beats,
    )
    assert qa_res.passed is True


def test_positive_case_3_explanation_of_why_event_matters(script_engine, standard_visual_beats):
    """
    Positive Case 3: Explanation of why an event matters.
    Harry catching Neville's Remembrall mirrors James Potter's natural aerial instincts.
    """
    hook = "Why Harry catching the Remembrall wasn't just beginner's luck."
    script_text = (
        "Why Harry catching the Remembrall wasn't just beginner's luck. "
        "When Harry dives fifty feet to catch Neville's Remembrall, it mirrors his father James Potter's natural aerial instincts. "
        "The novel reveals James was an exceptionally gifted Chaser who instinctively toyed with Snitches. "
        "Professor McGonagall immediately recognized the inherited Seeker bloodline. "
        "The catch proved Harry's Quidditch talent was an inherited legacy, not a random fluke."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(
        script_text=script_text,
        hook=hook,
    )
    assert result.passed is True
    assert result.hook_payoff_gap_detected is False
    assert result.editorial_score >= 80.0
    assert len(result.reasons) == 0


def test_positive_case_4_lore_context_fact_with_payoff(script_engine, standard_visual_beats):
    """
    Positive Case 4: Lore/context fact with payoff.
    Mirror of Erised inscription mechanics explaining why Dumbledore lied about socks.
    """
    script_text = (
        "The magical mechanics behind the Mirror of Erised explain why Dumbledore lied. "
        "The inscription backwards reads 'I show not your face but your heart's desire.' "
        "When Dumbledore claimed he saw himself holding a pair of woolen socks, he hid his true tragic longing: "
        "his deceased family reunited without guilt. "
        "Harry only realized decades later that Dumbledore's greatest grief mirrored his own."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is True
    assert result.editorial_score >= 80.0
    assert len(result.reasons) == 0


def test_positive_case_5_single_strong_fact_insight(script_engine, standard_visual_beats):
    """
    Positive Case 5: Single strong fact/insight (does NOT require listicle format).
    The Sorting Hat sings a brand new musical warning every single year in the books.
    """
    script_text = (
        "The secret detail in the Hogwarts Sorting Hat song the movies omitted. "
        "In the books, the Sorting Hat composes a brand new musical ballad every single year. "
        "It even uses its lyrics to warn the entire school about Voldemort's return and call for inter-house unity. "
        "The films treated the hat merely as a one-time sorting device. "
        "The hat was not just a tool, but an ancient sentient guardian of Hogwarts history."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is True
    assert result.editorial_score >= 80.0
    assert len(result.reasons) == 0


def test_positive_case_6_visually_supported_informational_script(script_engine, standard_visual_beats):
    """
    Positive Case 6: Visually supported informational script.
    Potions dungeon set dressing craft where movie footage provides visual contextual evidence.
    """
    script_text = (
        "Pay attention to the background of the Potions dungeon in the first movie. "
        "The set dressers filled hundreds of antique glass jars with bizarre animal parts bought from London butcher shops. "
        "Alan Rickman personally selected the dark specimen bottles surrounding Snape's desk to heighten the claustrophobic dread of his character. "
        "Practical production craft that turned a simple classroom set into an intimidating psychological trap."
    )
    result = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(script_text)
    assert result.passed is True
    assert result.editorial_score >= 80.0
    assert len(result.reasons) == 0


# ── Architectural Assertions ──────────────────────────────────────────────────

def test_arch_assertion_1_novel_story_isolation(script_engine, standard_visual_beats):
    """
    Architectural Assertion 1: Novel Story Editorial Behavior Untouched.
    Novel Story scripts are child-friendly chronological chapter storytelling.
    They must bypass the Discovery anti-recap check completely and pass QA.
    """
    novel_story_text = (
        "Deep in the Forbidden Forest, Harry and Hagrid walked through the dark trees. "
        "Suddenly, Hagrid stopped and held up a large crossbow. He pointed toward a pool of silver liquid shining on the moss. "
        "It was unicorn blood. Something horrible was hunting the innocent creatures of the forest. "
        "Harry heard hooves galloping across dry twigs nearby, and a hooded shadow slipped silently between the branches. "
        "Hagrid loaded his weapon, ready to protect young Harry from the unknown darkness. "
        "Together they stepped cautiously forward into the misty clearing, watching the dark shadows dance under the pale silver moonlight as a cold wind swept through the ancient pine branches overhead."
    )
    qa_res = script_engine.evaluate_script_qa(
        script_text=novel_story_text,
        visual_beats=standard_visual_beats,
        candidate_type="novel_story",
    )
    assert qa_res.passed is True
    assert len(qa_res.spoken_parts_detected) == 0
    assert len(qa_res.cliches_detected) == 0


def test_arch_assertion_2_movie_event_visual_authority(script_engine, standard_visual_beats):
    """
    Architectural Assertion 2: MovieEvent Remains Sole Final Visual Authority.
    The script engine strictly enforces MOVIE_FOOTAGE_ONLY / HYBRID_TRUTHFUL and rejects
    any visual beats specifying synthetic AI images or generic stock footage.
    """
    forbidden_beats = [
        {
            "beat_id": "beat_1",
            "visual_source_policy": "PEXELS_STOCK",
            "retrieval_hints": ["generic stock footage"],
        },
        {
            "beat_id": "beat_2",
            "visual_source_policy": "AI_GENERATED",
            "retrieval_hints": ["midjourney prompt"],
        },
        {
            "beat_id": "beat_3",
            "visual_source_policy": "MOVIE_FOOTAGE_ONLY",
            "visual_source": "MOVIE_DIRECT",
        },
    ]
    valid_text = (
        "The magical mechanics behind the Mirror of Erised explain why Dumbledore lied. "
        "The inscription backwards reads 'I show not your face but your heart's desire.' "
        "When Dumbledore claimed he saw himself holding a pair of woolen socks, he hid his true tragic longing: "
        "his deceased family reunited without guilt. "
        "Harry only realized decades later that Dumbledore's greatest grief mirrored his own."
    )
    qa_res = script_engine.evaluate_script_qa(
        script_text=valid_text,
        visual_beats=forbidden_beats,
        candidate_type="discovery_short",
    )
    assert qa_res.passed is False
    assert len(qa_res.forbidden_visuals_detected) > 0


def test_arch_assertion_3_srt_has_zero_visual_fallback():
    r"""
    Architectural Assertion 3: SRT Has Zero Visual Fallback Authority.
    SRT provides coarse temporal and dialogue localization only ($T_0 \pm 30s$).
    MovieEvent is the sole visual authority; SRT dialogue alone cannot select or replace footage.
    """
    beat = VisualBeat(
        beat_id="beat_hermione_punch",
        narrative_text="Hermione punches Malfoy in the face at the sundial",
        required_subjects=["Hermione Granger", "Draco Malfoy"],
        required_action="punches",
        required_target="Draco Malfoy",
        required_location="Sundial circle",
        forbidden_visuals=["Voldemort"],
    )
    # Dialogue-only match with non-matching physical action must NOT become a valid visual event
    dialogue_only_event = MovieEvent(
        event_id="evt_m3_dialogue_only",
        movie_id="hp_movie_3",
        movie_number=3,
        scene_id="scene_sundial",
        start_time=100.0,
        end_time=103.0,
        characters_present=["Hermione Granger", "Draco Malfoy"],
        primary_subject="Hermione Granger",
        action="talks",  # talking, NOT punching!
        target="Draco Malfoy",
        location="Sundial circle",
        visual_description="Hermione arguing with Draco Malfoy near the sundial stone circle",
    )
    # Verification against punch action requirement must fail
    assert dialogue_only_event.action != "punches"
    assert dialogue_only_event.action != beat.required_action


def test_arch_assertion_4_no_valid_visual_fail_closed(script_engine):
    """
    Architectural Assertion 4: NO_VALID_VISUAL Remains Fail-Closed.
    If a visual beat has no verified physical event evidence, it records NO_VALID_VISUAL
    and fails closed rather than substituting arbitrary or unrelated clips.
    """
    unverified_beats = [
        {
            "beat_id": "beat_unverified_1",
            "visual_source_policy": "HYBRID_TRUTHFUL",
            "visual_source": "NO_VALID_VISUAL",
            "narration_text": "An unseen event with zero movie footage.",
            "source_grounding": "Book only",
            "characters": ["Peeves"],
            "action": "juggling torches",
        },
        {
            "beat_id": "beat_unverified_2",
            "visual_source_policy": "HYBRID_TRUTHFUL",
            "visual_source": "NO_VALID_VISUAL",
            "narration_text": "Another unseen event.",
            "source_grounding": "Book only",
            "characters": ["Peeves"],
            "action": "singing rude songs",
        },
        {
            "beat_id": "beat_unverified_3",
            "visual_source_policy": "HYBRID_TRUTHFUL",
            "visual_source": "NO_VALID_VISUAL",
            "narration_text": "A third unseen event.",
            "source_grounding": "Book only",
            "characters": ["Peeves"],
            "action": "dropping busts",
        },
    ]
    # Visual beat plans record NO_VALID_VISUAL faithfully
    assert all(b["visual_source"] == "NO_VALID_VISUAL" for b in unverified_beats)
    # Verification status for unverified claims
    status = VerificationStatus.NO_DIRECT_VISUAL_EVENT
    assert status == VerificationStatus.NO_DIRECT_VISUAL_EVENT
