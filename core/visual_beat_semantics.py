"""
STORY FORGE Visual Beat Semantics & Requirement Contracts (PART G)
================================================================================
Translates narration beat text and story structure into explicit visual contracts:
- Determines character identity, actions, context, and environment.
- Enforces hard framing preferences:
  * Normal character narration -> PREFER MEDIUM, MEDIUM_WIDE, TWO_SHOT
  * Movement/traversal -> PREFER MEDIUM_WIDE, WIDE
  * Environment/context -> PREFER WIDE, MEDIUM_WIDE
  * Interaction between characters -> PREFER TWO_SHOT, MEDIUM
  * Facial-emotion narration -> CLOSE_UP allowed
  * EXTREME_CLOSE_UP allowed ONLY when explicitly justified
- Rejects candidate shots that fail composition or crop safety.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set

from core.composition_models import ShotScale


# Canonical emotion cues that justify a CLOSE_UP
EMOTION_KEYWORDS: Set[str] = {
    "terrified", "terror", "afraid", "crying", "wept", "weeping", "shocked",
    "shock", "furious", "rage", "despair", "epiphany", "realized", "horrified",
    "horror", "grief", "smiled", "whispered", "pleaded", "pleading", "begged",
    "staring", "gasped", "trembling", "pale", "eyes widened"
}

# Movement / traversal cues
MOVEMENT_KEYWORDS: Set[str] = {
    "walked", "walking", "ran", "running", "entered", "entering", "stepped",
    "fled", "fleeing", "approached", "marched", "crossed", "traveled", "flew",
    "flying", "chased", "escaped", "rushed", "hurried"
}

# Interaction cues
INTERACTION_KEYWORDS: Set[str] = {
    "argued", "arguing", "talked", "talking", "confronted", "confronting",
    "battled", "dueling", "stood before", "bowed", "spoke to", "faced",
    "together", "between", "listened", "exchanged"
}

# Environment / setting cues
ENVIRONMENT_KEYWORDS: Set[str] = {
    "great hall", "hogwarts", "chamber of secrets", "forbidden forest",
    "courtyard", "gryffindor common room", "dungeons", "potions classroom",
    "ministry of magic", "diagon alley", "astronomy tower", "grounds",
    "graveyard", "lake", "platform 9 3/4"
}

# Canonical Harry Potter character names
CANONICAL_CHARACTERS = [
    "Neville Longbottom", "Neville", "Harry Potter", "Harry", "Ron Weasley", "Ron",
    "Hermione Granger", "Hermione", "Albus Dumbledore", "Dumbledore",
    "Severus Snape", "Snape", "Lord Voldemort", "Voldemort", "Draco Malfoy", "Malfoy",
    "Minerva McGonagall", "McGonagall", "Rubeus Hagrid", "Hagrid",
    "Sorting Hat", "Bellatrix Lestrange", "Bellatrix", "Sirius Black", "Sirius",
    "Remus Lupin", "Lupin", "Peter Pettigrew", "Wormtail", "Peeves",
    "Argus Filch", "Filch", "Ginny Weasley", "Ginny", "Luna Lovegood", "Luna",
    "Fred Weasley", "George Weasley", "Vernon Dursley", "Petunia Dursley", "Dudley Dursley"
]


@dataclass
class VisualBeatRequirement:
    """
    Structured visual requirement contract generated from a narration beat.
    """
    beat_id: str
    narration_text: str
    narrative_phase: str = "EVIDENCE"             # HOOK, SETUP, EVIDENCE, CONTRAST, ANCHOR, PAYOFF
    required_characters: List[str] = field(default_factory=list)
    forbidden_characters: List[str] = field(default_factory=list)
    required_actions: List[str] = field(default_factory=list)
    required_context_or_environment: Optional[str] = None
    is_emotional_beat: bool = False
    is_movement_beat: bool = False
    is_interaction_beat: bool = False
    is_environment_beat: bool = False
    preferred_shot_scales: List[ShotScale] = field(default_factory=list)
    disallowed_shot_scales: List[ShotScale] = field(default_factory=list)
    allow_close_up: bool = False
    allow_extreme_close_up: bool = False
    require_face_visible: bool = False
    require_context_visible: bool = False
    no_face_cutoff: bool = True
    no_body_cutoff: bool = True

    def __post_init__(self):
        # Infer properties if not explicitly populated
        text_lower = self.narration_text.lower()

        if not self.required_characters:
            for char in CANONICAL_CHARACTERS:
                pattern = r"\b" + re.escape(char.lower()) + r"\b"
                if re.search(pattern, text_lower):
                    # Store standardized short name
                    short_name = char.split()[-1] if " " in char and char not in ("Sorting Hat", "Peter Pettigrew") else char
                    if short_name not in self.required_characters:
                        self.required_characters.append(short_name)

        # Check emotion
        if any(w in text_lower for w in EMOTION_KEYWORDS):
            self.is_emotional_beat = True
            self.allow_close_up = True
            self.require_face_visible = True

        # Check movement
        if any(w in text_lower for w in MOVEMENT_KEYWORDS):
            self.is_movement_beat = True

        # Check interaction
        if any(w in text_lower for w in INTERACTION_KEYWORDS) or len(self.required_characters) >= 2:
            self.is_interaction_beat = True

        # Check environment (sorted by longest phrase first so specific places match before general)
        for env in sorted(ENVIRONMENT_KEYWORDS, key=len, reverse=True):
            if env in text_lower:
                self.is_environment_beat = True
                self.required_context_or_environment = env
                break

        # Setup preferred and disallowed shot scales if not already set
        if not self.preferred_shot_scales:
            if self.is_interaction_beat:
                self.preferred_shot_scales = [ShotScale.TWO_SHOT, ShotScale.MEDIUM, ShotScale.MEDIUM_WIDE]
                self.disallowed_shot_scales = [ShotScale.EXTREME_CLOSE_UP]
                if not self.is_emotional_beat:
                    self.disallowed_shot_scales.append(ShotScale.CLOSE_UP)

            elif self.is_movement_beat:
                self.preferred_shot_scales = [ShotScale.MEDIUM_WIDE, ShotScale.WIDE, ShotScale.MEDIUM]
                self.disallowed_shot_scales = [ShotScale.CLOSE_UP, ShotScale.EXTREME_CLOSE_UP]

            elif self.is_environment_beat:
                self.preferred_shot_scales = [ShotScale.WIDE, ShotScale.MEDIUM_WIDE, ShotScale.EXTREME_WIDE]
                self.disallowed_shot_scales = [ShotScale.CLOSE_UP, ShotScale.EXTREME_CLOSE_UP, ShotScale.MEDIUM_CLOSE]

            elif self.is_emotional_beat:
                self.preferred_shot_scales = [ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE, ShotScale.MEDIUM]
                self.disallowed_shot_scales = [ShotScale.EXTREME_WIDE]

            else:
                # Normal character narration: PREFER MEDIUM, MEDIUM_WIDE, TWO_SHOT
                self.preferred_shot_scales = [ShotScale.MEDIUM, ShotScale.MEDIUM_WIDE, ShotScale.TWO_SHOT]
                self.disallowed_shot_scales = [ShotScale.CLOSE_UP, ShotScale.EXTREME_CLOSE_UP]
                self.allow_close_up = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "narration_text": self.narration_text,
            "narrative_phase": self.narrative_phase,
            "required_characters": self.required_characters,
            "forbidden_characters": self.forbidden_characters,
            "required_actions": self.required_actions,
            "required_context_or_environment": self.required_context_or_environment,
            "is_emotional_beat": self.is_emotional_beat,
            "is_movement_beat": self.is_movement_beat,
            "is_interaction_beat": self.is_interaction_beat,
            "is_environment_beat": self.is_environment_beat,
            "preferred_shot_scales": [s.value for s in self.preferred_shot_scales],
            "disallowed_shot_scales": [s.value for s in self.disallowed_shot_scales],
            "allow_close_up": self.allow_close_up,
            "allow_extreme_close_up": self.allow_extreme_close_up,
            "require_face_visible": self.require_face_visible,
            "require_context_visible": self.require_context_visible,
            "no_face_cutoff": self.no_face_cutoff,
            "no_body_cutoff": self.no_body_cutoff,
        }
