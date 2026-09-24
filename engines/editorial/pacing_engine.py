"""
STORY FORGE — Editorial Pacing & Narrative Weight Engine
================================================================================
Implements dynamic, non-metronomic short-form pacing driven by narrative weight:
  - Eliminates rigid fixed-interval cutting
  - Calculates multi-factor narrative weight (importance, curiosity, contrast, emotion, payoff)
  - Maps narrative roles to empirical pacing brackets:
      HOOK:             ~0.8–1.5s (rapid, immediate promise)
      SETUP / ENTRY:    ~1.5–2.5s (accessible grounding)
      EVIDENCE PUNCH:   ~1.2–2.0s (brisk factual delivery)
      MAJOR ANCHOR:     ~2.0–3.2s (cognitive surprise / major reveal)
      FINAL PAYOFF:     ~3.0–4.0s (climax epiphany hold)
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("EditorialPacingEngine")


class EditorialPacingEngine:
    """
    Computes narrative weight and determines adaptive shot durations.
    """

    @classmethod
    def calculate_narrative_weight(
        cls,
        importance: float = 0.5,
        curiosity: float = 0.5,
        movie_contrast: float = 0.5,
        emotional_value: float = 0.5,
        payoff_value: float = 0.5,
        visual_evidence_strength: float = 0.85,
    ) -> float:
        """
        Calculates composite editorial importance weight [0.0 - 1.0].
        High-weight moments receive visual breathing room; low-weight details move briskly.
        """
        weight = (
            (importance * 0.25)
            + (curiosity * 0.20)
            + (movie_contrast * 0.20)
            + (emotional_value * 0.15)
            + (payoff_value * 0.20)
        )
        # Factor visual evidence strength: weak evidence moves faster, strong proof holds longer
        adjusted = weight * (0.85 + (0.15 * min(1.0, max(0.0, visual_evidence_strength))))
        return round(min(1.0, max(0.05, adjusted)), 3)

    @classmethod
    def calculate_editorial_duration(
        cls,
        narrative_role: str,
        narrative_weight: float,
        available_narration_duration: float,
        evidence_type: str = "DIRECT_EVIDENCE",
    ) -> float:
        """
        Determines target cut duration for a visual unit based on role and weight.
        Breaks rigid metronomic boundaries dynamically.
        """
        role_upper = (narrative_role or "BODY").upper()

        # Base target ranges based on empirical forensic findings
        if "HOOK" in role_upper:
            base_min, base_max = 0.8, 1.5
        elif "ENTRY" in role_upper or "SETUP" in role_upper:
            base_min, base_max = 1.5, 2.5
        elif "CLIMAX" in role_upper or "PAYOFF" in role_upper:
            base_min, base_max = 3.0, 4.0
        elif "SURPRISE" in role_upper or narrative_weight >= 0.80:
            base_min, base_max = 2.0, 3.2
        elif "EMOTION" in role_upper:
            base_min, base_max = 2.0, 3.0
        else:  # Normal evidence punch
            base_min, base_max = 1.2, 2.0

        # Scale within range using narrative weight
        target = base_min + ((base_max - base_min) * narrative_weight)

        # Cap at available narration duration if specified and positive
        if available_narration_duration > 0:
            target = min(target, available_narration_duration)

        # Enforce minimum mobile readability threshold (never cut faster than 0.7s)
        return round(max(0.75, target), 2)
