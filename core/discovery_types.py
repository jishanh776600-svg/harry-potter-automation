"""
Discovery Content Types and Information Architecture
===================================================
Defines canonical Discovery subtypes, visual classifications, and 
the 11-point Discovery Quality Gate for Harry Potter Shorts.
"""
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


class DiscoverySubtype(str, Enum):
    """Explicit Discovery subtypes governing script format and structure."""
    DISCOVERY_FACT = "DISCOVERY_FACT"
    DISCOVERY_BOOK_MOVIE_DIFFERENCE = "DISCOVERY_BOOK_MOVIE_DIFFERENCE"
    DISCOVERY_OMITTED_SCENE = "DISCOVERY_OMITTED_SCENE"
    DISCOVERY_NOVEL_ONLY_DETAIL = "DISCOVERY_NOVEL_ONLY_DETAIL"
    DISCOVERY_CHARACTER_DETAIL = "DISCOVERY_CHARACTER_DETAIL"
    DISCOVERY_BEHIND_THE_SCENES = "DISCOVERY_BEHIND_THE_SCENES"
    DISCOVERY_MOVIE_DETAIL = "DISCOVERY_MOVIE_DETAIL"
    DISCOVERY_TRIVIA = "DISCOVERY_TRIVIA"


class VisualClassification(str, Enum):
    """
    Visual-to-Script relationship classification.
    DIRECT: Footage directly depicts the fact/object/action.
    CONTEXTUAL: Footage provides authentic scene/character context for external factual voiceover.
    UNSUPPORTED: Visuals have no meaningful relation to the topic (rejected).
    """
    DIRECT = "DIRECT"
    CONTEXTUAL = "CONTEXTUAL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass
class DiscoveryQAResult:
    """Detailed evaluation from the 11-Point Discovery Quality Gate."""
    passed: bool
    subtype: str
    fact_identifiable: bool            # Check A
    fact_explicitly_stated: bool       # Check B
    subject_in_first_5s: bool          # Check C
    feels_like_information: bool       # Check D
    subtype_structure_valid: bool      # Check E
    book_movie_both_stated: bool       # Check F (if BOOK_MOVIE_DIFFERENCE)
    omission_explicitly_stated: bool   # Check G (if OMITTED_SCENE)
    production_fact_stated: bool       # Check H (if BEHIND_THE_SCENES)
    avoids_chronological_story: bool   # Check I
    is_standalone: bool                # Check J
    no_part_markers: bool              # Check K
    failure_reasons: List[str] = field(default_factory=list)
