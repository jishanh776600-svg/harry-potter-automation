"""
STORY FORGE — Editorial Caption & SFX Intelligence Layer
================================================================================
Implements synchronized kinetic typography and directorial SFX decision logic:
  - Synchronizes captions with word timestamps without jittery over-animation
  - Applies selective gold highlight on canon lore keywords
  - Selects kinetic reveal-word bursts exclusively on punchlines and discoveries
  - Generates synchronized SFX cues following the 4-tier editorial hierarchy:
      NORMAL:     Visual only (no SFX)
      IMPORTANT:  Visual + Caption emphasis
      MAJOR:      Visual + Caption + SFX (CLICK, SHORT_TRANSITION, WHOOSH)
      CLIMAX:     Visual + Caption + SFX (REVELATION) + Deliberate Hold
  - Implements Intentional Silence / Solemn Suppression for death, sacrifice, and grief
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Set

from core.editorial_v2_types import CaptionTreatment, SFXTreatment

logger = logging.getLogger("CaptionSFXIntelligence")

# Canon lore terms receiving gold keyword emphasis
CANON_LORE_KEYWORDS = {
    "sorting hat", "hatstall", "gryffindor", "hufflepuff", "slytherin", "ravenclaw",
    "neville", "harry", "dumbledore", "snape", "voldemort", "horcrux", "paracelsus",
    "peeves", "erised", "remembrall", "diagon alley", "godric", "salazar", "helga",
    "rowena", "hallows", "deathly hallows", "elder wand", "resurrection stone",
    "invisibility cloak", "chamber of secrets", "sword of gryffindor", "basilisk",
    "nagini", "azkaban", "ministry of magic", "avada kedavra", "lumos"
}

# Solemn words triggering intentional silence
SOLEMN_WORDS = {
    "death", "died", "dies", "dead", "killed", "sacrifice", "sacrificed", "funeral",
    "mourning", "tragic", "tragedy", "murder", "murdered", "corpse", "slain", "grief",
    "weeping", "blood", "lifeless", "grave"
}


class CaptionSFXIntelligence:
    """
    Directorial controller for kinetic captions and synchronized sound effects.
    """

    @classmethod
    def select_caption_treatment(
        cls,
        text: str,
        narrative_weight: float = 0.5,
        is_revelation: bool = False,
    ) -> CaptionTreatment:
        """
        Chooses caption kinetic behavior.
        Keeps baseline typography stable; emphasizes only canon nouns and revelations.
        """
        text_lower = text.lower()

        if is_revelation or narrative_weight >= 0.90:
            return CaptionTreatment.REVEAL_WORD_BURST

        if any(kw in text_lower for kw in CANON_LORE_KEYWORDS):
            return CaptionTreatment.CANON_KEYWORD_HIGHLIGHT

        if narrative_weight >= 0.75:
            return CaptionTreatment.CONTROLLED_SCALE_PULSE

        return CaptionTreatment.STANDARD_STATIC

    @classmethod
    def select_sfx_treatment(
        cls,
        text: str,
        narrative_role: str = "BODY",
        narrative_weight: float = 0.5,
        last_sfx_timestamp: float = -10.0,
        current_timestamp: float = 0.0,
        sfx_cooldown: float = 2.5,
    ) -> Tuple[SFXTreatment, str]:
        """
        Assigns sound effects following the 4-tier hierarchy.
        Enforces intentional silence on solemn content and respects acoustic cooldowns.
        """
        text_lower = text.lower()
        role_upper = narrative_role.upper()

        # 1. SOLEMN SUPPRESSION: Intentional Silence
        words = set(re.findall(r"\w+", text_lower))
        if words.intersection(SOLEMN_WORDS):
            return SFXTreatment.INTENTIONAL_SILENCE, "Intentional silence: solemn / tragic canon content"

        # 2. Cooldown check: prevent acoustic clutter
        time_since_last = current_timestamp - last_sfx_timestamp
        if time_since_last < sfx_cooldown:
            return SFXTreatment.NONE, "SFX suppressed: cooldown active"

        # 3. Editorial hierarchy
        if "CLIMAX" in role_upper or "PAYOFF" in role_upper or narrative_weight >= 0.95:
            return SFXTreatment.REVELATION, "Climax revelation: peak canon epiphany"

        if "SURPRISE" in role_upper or narrative_weight >= 0.82:
            return SFXTreatment.WHOOSH, "Major structural transition / cognitive surprise"

        if "HOOK" in role_upper:
            return SFXTreatment.CLICK, "Hook attention grabber"

        if narrative_weight >= 0.70:
            return SFXTreatment.SHORT_TRANSITION, "Evidence shift accent"

        # Default normal tier: visual cut only
        return SFXTreatment.NONE, "Normal tier: visual cut only (no SFX)"
