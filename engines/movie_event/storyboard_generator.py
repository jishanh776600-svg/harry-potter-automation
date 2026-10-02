"""
STORY FORGE — Visual Storyboard Generator & Claim Transformation (V2)
=====================================================================
Transforms narration text / propositions into structured VisualBeats and evaluates
claim visual demonstrability:
  1. DIRECTLY_VISUALIZABLE: Physical actions observable on camera.
  2. VISUALLY_REPRESENTABLE_WITH_CONTEXT: Physical actions requiring contextual grounding.
  3. ABSTRACT_NOT_DIRECTLY_VISUALIZABLE: Mental states, hidden intentions, or unfilmed lore.
     Returns NO_DIRECT_VISUAL_EVENT and recommends observable rewrites.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from engines.movie_event.models import (
    VisualBeat,
    VisualStoryboard,
    ClaimClassification,
    ClaimType,
    MovieEventQuery,
    VISUAL_OPTIONAL,
    DIRECT_VISUAL,
)

logger = logging.getLogger("StoryboardGenerator")

# Book canon / factual comparison patterns (unfilmed lore or canonical differences)
BOOK_CANON_PATTERNS = [
    r"\bin the books?\b",
    r"\bbook canon\b",
    r"\bnever breaks?\b",
    r"\bnever broke\b",
    r"\bnever happened\b",
    r"\browling\b",
    r"\boriginal novels?\b",
    r"\bbook version\b",
    r"\bwritten canon\b",
    r"\bpage\b",
    r"\bcut from the film\b",
    r"\bnever shown on screen\b",
    r"\bbook lore\b",
]

# Mental, emotional, or unverifiable abstract predicates
ABSTRACT_PREDICATES = [
    "suspect", "suspected", "suspecting", "suspects",
    "secretly", "secret", "believed", "felt", "knew",
    "feared", "wondered", "intended", "schemed", "hated",
    "realized", "remembered", "wished", "regretted", "envied",
    "doubted", "planned in secret", "harbored", "pondered",
    "symbolized", "symbolize", "foreshadowed", "meant"
]

# Directly observable physical action verbs
DIRECT_ACTION_VERBS = [
    "question", "questions", "questioned", "address", "addresses", "addressed",
    "punch", "punches", "punched", "strike", "strikes", "struck",
    "draw", "draws", "drew", "pull", "pulls", "pulled",
    "open", "opens", "opened", "unlock", "unlocks", "unlocked",
    "walk", "walks", "walked", "run", "runs", "ran",
    "point", "points", "pointed", "speak", "speaks", "spoke",
    "drop", "drops", "dropped", "take", "takes", "took",
    "hold", "holds", "held", "shout", "shouts", "shouted",
    "confront", "confronts", "confronted", "brandish", "brandishes", "brandished",
    "respond", "responds", "responded", "challenge", "challenges", "challenged",
    "inspect", "inspects", "inspected", "enter", "enters", "entered",
    "summon", "summons", "summoned", "accio", "drink", "drinks", "drank",
    "destroy", "destroys", "destroyed", "cast", "casts", "conjure", "conjures",
    "touch", "touches", "touched", "catch", "catches", "caught",
    "flee", "flees", "fled", "reveal", "reveals", "revealed",
    "stab", "stabs", "stabbed", "behead", "beheads", "beheaded",
    "snap", "snaps", "snapped", "break", "breaks", "broke",
]


class ClaimTransformer:
    """
    Analyzes narrative propositions and classifies them into:
      - DIRECTLY_VISUALIZABLE
      - VISUALLY_REPRESENTABLE_WITH_CONTEXT
      - ABSTRACT_NOT_DIRECTLY_VISUALIZABLE
    For abstract claims, formulates concrete visual rewrite recommendations.
    """

    @classmethod
    def classify_claim(cls, narration_claim: str) -> ClaimClassification:
        """Classifies a narration claim and extracts physical action or recommends rewrite."""
        text_lower = narration_claim.lower()

        # Check for book canon / factual comparison signals (unfilmed lore or differences)
        is_book_lore = any(re.search(pat, text_lower) for pat in BOOK_CANON_PATTERNS)
        if is_book_lore:
            return ClaimClassification(
                raw_claim=narration_claim,
                classification=ClaimType.ABSTRACT_NOT_DIRECTLY_VISUALIZABLE,
                is_directly_visualizable=False,
                demonstrable_action=None,
                abstract_elements=["book_canonical_comparison"],
                recommended_rewrite=None,
                rejection_notice="VISUAL_OPTIONAL: Narrative describes unfilmed book canon or factual contrast without filmed physical action.",
            )

        # Check for abstract verbs/adverbs
        detected_abstract = [p for p in ABSTRACT_PREDICATES if re.search(rf"\b{re.escape(p)}\b", text_lower)]

        # Check for direct physical action verbs
        detected_actions = [a for a in DIRECT_ACTION_VERBS if re.search(rf"\b{re.escape(a)}\b", text_lower)]
        if "?" in narration_claim or text_lower.startswith(("what ", "where ", "why ", "how ", "who ")):
            if "question" not in detected_actions and "questions" not in detected_actions:
                detected_actions.append("questions")

        # 1. Pure Abstract claim (has abstract predicates, no direct physical action)
        if detected_abstract and not detected_actions:
            rewrite = cls._recommend_rewrite(narration_claim, detected_abstract)
            return ClaimClassification(
                raw_claim=narration_claim,
                classification=ClaimType.ABSTRACT_NOT_DIRECTLY_VISUALIZABLE,
                is_directly_visualizable=False,
                demonstrable_action=None,
                abstract_elements=detected_abstract,
                recommended_rewrite=rewrite,
                rejection_notice="NO_DIRECT_VISUAL_EVENT: Narrative describes invisible internal state or abstract interpretation.",
            )

        # 2. Hybrid claim (has abstract concept but also a physical action, e.g. "Snape questioned Harry because he suspected him")
        if detected_abstract and detected_actions:
            return ClaimClassification(
                raw_claim=narration_claim,
                classification=ClaimType.VISUALLY_REPRESENTABLE_WITH_CONTEXT,
                is_directly_visualizable=True,
                demonstrable_action=detected_actions[0],
                abstract_elements=detected_abstract,
                recommended_rewrite=None,
                rejection_notice=None,
            )

        # 3. Direct physical claim
        action_identified = detected_actions[0] if detected_actions else "observable interaction"
        return ClaimClassification(
            raw_claim=narration_claim,
            classification=ClaimType.DIRECTLY_VISUALIZABLE,
            is_directly_visualizable=True,
            demonstrable_action=action_identified,
            abstract_elements=[],
            recommended_rewrite=None,
            rejection_notice=None,
        )

    @classmethod
    def _recommend_rewrite(cls, claim: str, abstract_words: List[str]) -> str:
        """Generates a concrete, observable physical rewrite for an abstract claim."""
        claim_lower = claim.lower()
        if "suspect" in claim_lower or "secret" in claim_lower:
            return "Snape watched Harry closely from across the classroom during the lesson."
        if "felt" in claim_lower or "fear" in claim_lower:
            return "Harry gripped his wand and stepped back, staring up at the shadowed doorway."
        if "believed" in claim_lower or "thought" in claim_lower:
            return "Dumbledore paused and leaned over his desk, studying the parchment in silence."
        return f"{claim} -> [Rewrite to specify observable character body language, gestures, or physical action]"


class VisualStoryboardGenerator:
    """
    Transforms narration beats into structured VisualBeats defining
    EXACT observable visual events, locations, targets, and forbidden elements.
    """

    def __init__(self):
        self.transformer = ClaimTransformer()

    def generate_beat_from_narration(
        self,
        beat_id: str,
        narration_text: str,
        start_time: float,
        end_time: float,
        narrative_role: str = "DEVELOPMENT",
        inferred_movie: Optional[int] = None,
        direct_visual_requirement: Optional[bool] = None,
        coverage_requirement: Optional[str] = None,
        visual_state: Optional[str] = None,
        visual_assertion: Optional[Any] = None,
    ) -> Tuple[VisualBeat, ClaimClassification]:
        """
        Creates a concrete VisualBeat from a narration beat.
        Guarantees that forbidden visuals prevent false-positive visual reuse.
        """
        classification = self.transformer.classify_claim(narration_text)

        # Extract characters from narration
        subjects = self._extract_characters(narration_text)
        action = classification.demonstrable_action or "address or interact"
        target = self._extract_target(narration_text, subjects)
        location = self._extract_location(narration_text)
        objects = self._extract_objects(narration_text)

        # Formulate strict forbidden elements based on required event
        forbidden: List[str] = []
        if len(subjects) >= 2:
            # If multi-character interaction required, forbid showing characters isolated or walking alone
            forbidden.append(f"{subjects[0]} alone")
            forbidden.append("generic corridor walking")
            forbidden.append("unrelated students")

        if "potions" in narration_text.lower() or "snape" in narration_text.lower():
            forbidden.extend(["quidditch pitch", "great hall feast", "daylight courtyard", "forest"])

        if "sword" in narration_text.lower() or "neville" in narration_text.lower():
            forbidden.extend(["sorting ceremony year 1", "greenhouse herbiology", "train compartment"])

        if "chamber" in narration_text.lower():
            forbidden.extend(["daylight common room", "quidditch pitch", "hagrid hut"])

        if "punch" in narration_text.lower() or "malfoy" in narration_text.lower():
            forbidden.extend(["potions dungeon", "train station", "great hall"])

        if direct_visual_requirement is not None:
            is_direct = direct_visual_requirement
        else:
            is_direct = classification.is_directly_visualizable
        cov_req = coverage_requirement or (DIRECT_VISUAL if is_direct else VISUAL_OPTIONAL)

        beat = VisualBeat(
            beat_id=beat_id,
            start_time=start_time,
            end_time=end_time,
            narration_start=start_time,
            narration_end=end_time,
            narrative_text=narration_text,
            narrative_role=narrative_role,
            required_subjects=subjects,
            required_action=action,
            required_target=target,
            required_location=location,
            required_objects=objects,
            required_entities=list(dict.fromkeys(subjects + objects + ([target] if target else []))),
            required_interaction="confrontation" if "confront" in narration_text.lower() or "punch" in narration_text.lower() else "direct_interaction",
            visual_state=visual_state,
            visual_assertion=visual_assertion,
            preferred_shot_scale="TWO_SHOT" if len(subjects) >= 2 else "MEDIUM_CLOSE_UP",
            preferred_visual_role="CORE_ACTION",
            forbidden_visuals=forbidden,
            direct_visual_requirement=is_direct,
            coverage_requirement=cov_req,
            contextual_visual_allowed=not is_direct,
            fallback_strategy="STRICT_FAIL",
        )

        return beat, classification

    def create_event_query(self, beat: VisualBeat) -> MovieEventQuery:
        """Translates a VisualBeat into an executable MovieEventQuery."""
        primary_sub = beat.required_subjects[0] if beat.required_subjects else None
        return MovieEventQuery(
            subject=primary_sub,
            action=beat.required_action,
            target=beat.required_target,
            interaction=beat.required_interaction,
            location=beat.required_location,
            objects=beat.required_objects,
            forbidden_elements=beat.forbidden_visuals,
            visual_role=beat.preferred_visual_role,
        )

    def _extract_characters(self, text: str) -> List[str]:
        known = [
            ("Snape", ["snape", "severus"]),
            ("Harry Potter", ["harry", "potter"]),
            ("Neville Longbottom", ["neville", "longbottom"]),
            ("Hermione Granger", ["hermione", "granger"]),
            ("Draco Malfoy", ["malfoy", "draco"]),
            ("Ron Weasley", ["ron", "weasley"]),
            ("Lord Voldemort", ["voldemort", "dark lord", "tom riddle"]),
            ("Albus Dumbledore", ["dumbledore", "albus"]),
            ("Sirius Black", ["sirius", "black"]),
            ("Lucius Malfoy", ["lucius"]),
            ("Mad-Eye Moody", ["moody", "barty", "crouch"]),
            ("Horace Slughorn", ["slughorn"]),
            ("Bathilda Bagshot", ["bathilda"]),
            ("Nagini", ["nagini"]),
            ("Cedric Diggory", ["cedric"]),
        ]
        found = []
        text_lower = text.lower()
        for canonical, aliases in known:
            if any(re.search(rf"\b{re.escape(a)}\b", text_lower) for a in aliases):
                found.append(canonical)
        return found

    def _extract_target(self, text: str, subjects: List[str]) -> Optional[str]:
        text_lower = text.lower()
        if "harry" in text_lower and "Snape" in subjects:
            return "Harry Potter"
        if "malfoy" in text_lower and "Hermione Granger" in subjects:
            return "Draco Malfoy"
        if "sword" in text_lower:
            return "Sword of Gryffindor"
        if "chamber" in text_lower or "entrance" in text_lower or "sink" in text_lower:
            return "Chamber of Secrets entrance"
        if "firebolt" in text_lower:
            return "Firebolt broom"
        if "cup" in text_lower:
            return "Triwizard Cup"
        if "felix" in text_lower or "vial" in text_lower:
            return "Felix Felicis vial"
        if "locket" in text_lower:
            return "Slytherin Locket"
        if "nagini" in text_lower:
            return "Nagini"
        if len(subjects) >= 2:
            return subjects[1]
        return None

    def _extract_location(self, text: str) -> Optional[str]:
        text_lower = text.lower()
        if "potions" in text_lower or "classroom" in text_lower:
            return "Potions classroom"
        if "courtyard" in text_lower or "ruin" in text_lower:
            return "Hogwarts Ruined Courtyard"
        if "bathroom" in text_lower or "myrtle" in text_lower:
            return "Moaning Myrtle's Bathroom"
        if "sundial" in text_lower or "stone circle" in text_lower:
            return "Sundial Hill / Stone Circle"
        if "arena" in text_lower or "dragon" in text_lower:
            return "Triwizard Arena"
        if "maze" in text_lower:
            return "Triwizard Maze"
        if "graveyard" in text_lower:
            return "Little Hangleton Graveyard"
        if "room of requirement" in text_lower or "requirement" in text_lower:
            return "Room of Requirement"
        if "atrium" in text_lower or "ministry" in text_lower:
            return "Ministry of Magic Atrium"
        if "cave" in text_lower:
            return "Horcrux Cave"
        if "tower" in text_lower or "astronomy" in text_lower:
            return "Astronomy Tower"
        if "forest" in text_lower:
            return "Forest of Dean"
        if "godric" in text_lower:
            return "Godric's Hollow"
        if "common room" in text_lower:
            return "Gryffindor Common Room"
        return None

    def _extract_objects(self, text: str) -> List[str]:
        objects = []
        text_lower = text.lower()
        if re.search(r"\bsword\b", text_lower):
            objects.append("Sword of Gryffindor")
        if re.search(r"\b(sorting hat|hat)\b", text_lower):
            objects.append("Sorting Hat")
        if re.search(r"\b(tap|snake tap)\b", text_lower):
            objects.append("snake tap")
        if re.search(r"\bwand\b", text_lower):
            objects.append("wand")
        if re.search(r"\b(quill|parchment)\b", text_lower):
            objects.append("quill")
        if re.search(r"\b(firebolt|broom)\b", text_lower):
            objects.append("Firebolt")
        if re.search(r"\b(cup|triwizard cup)\b", text_lower):
            objects.append("Triwizard Cup")
        if re.search(r"\b(felix|felix felicis|vial)\b", text_lower):
            objects.append("Felix Felicis vial")
        if re.search(r"\b(locket|horcrux)\b", text_lower):
            objects.append("Slytherin Locket")
        if re.search(r"\b(goblet|water)\b", text_lower):
            objects.append("crystal goblet")
        if re.search(r"\bflask\b", text_lower):
            objects.append("Polyjuice hip flask")
        if re.search(r"\bsnitch\b", text_lower):
            objects.append("Golden Snitch")
        return objects
