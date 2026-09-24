"""
STORY FORGE — Daily Content Cadence & Architecture V2
=====================================================
Defines the explicit daily production cadence:
  STORY FORGE publishes 4 Shorts/day:
    Slot 1: NOVEL STORY     (45–60 seconds)
    Slot 2: DISCOVERY BIG   (60–70 seconds)
    Slot 3: NOVEL STORY     (45–60 seconds)
    Slot 4: DISCOVERY SHORT (25–30 seconds)

Target breakdown:
  2 × Novel Story
  1 × Discovery Big
  1 × Discovery Short
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any


# ── Explicit Cadence Constants ──────────────────────────────────────────────────
DAILY_TARGET: int = 4
NOVEL_STORY: int = 2
DISCOVERY_BIG: int = 1
DISCOVERY_SHORT: int = 1


class ContentFormat(str, Enum):
    """Canonical daily publishing formats."""
    NOVEL_STORY = "NOVEL_STORY"
    DISCOVERY_BIG = "DISCOVERY_BIG"
    DISCOVERY_SHORT = "DISCOVERY_SHORT"


FORMAT_DURATION_BOUNDS: Dict[ContentFormat, Tuple[float, float]] = {
    ContentFormat.NOVEL_STORY: (45.0, 60.0),
    ContentFormat.DISCOVERY_BIG: (60.0, 70.0),
    ContentFormat.DISCOVERY_SHORT: (25.0, 30.0),
}


@dataclass
class DailySlotPlan:
    """A single scheduled slot within the daily publishing cadence."""
    slot_index: int                            # 1, 2, 3, 4
    format: ContentFormat
    min_duration_sec: float
    max_duration_sec: float
    description: str

    def is_duration_compliant(self, duration_sec: float) -> bool:
        return self.min_duration_sec <= duration_sec <= self.max_duration_sec


# Canonical 4-slot sequence per day
CANONICAL_DAILY_CADENCE: List[DailySlotPlan] = [
    DailySlotPlan(
        slot_index=1,
        format=ContentFormat.NOVEL_STORY,
        min_duration_sec=45.0,
        max_duration_sec=60.0,
        description="Slot 1: Novel Story (Deep novel lore, emotional narrative)"
    ),
    DailySlotPlan(
        slot_index=2,
        format=ContentFormat.DISCOVERY_BIG,
        min_duration_sec=60.0,
        max_duration_sec=70.0,
        description="Slot 2: Discovery Big (Multi-fact or deep topic reveal)"
    ),
    DailySlotPlan(
        slot_index=3,
        format=ContentFormat.NOVEL_STORY,
        min_duration_sec=45.0,
        max_duration_sec=60.0,
        description="Slot 3: Novel Story (Deep novel lore, emotional narrative)"
    ),
    DailySlotPlan(
        slot_index=4,
        format=ContentFormat.DISCOVERY_SHORT,
        min_duration_sec=25.0,
        max_duration_sec=30.0,
        description="Slot 4: Discovery Short (Compact single/multi-fact contrast)"
    ),
]


class DailyCadenceManager:
    """
    Manages and enforces the 4 Shorts/day cadence in production planning & reserves:
      - 2 Novel Stories
      - 1 Discovery Big
      - 1 Discovery Short
    """

    @classmethod
    def get_canonical_plan(cls) -> List[DailySlotPlan]:
        return list(CANONICAL_DAILY_CADENCE)

    @classmethod
    def get_slot_plan(cls, slot_index: int) -> DailySlotPlan:
        if slot_index < 1 or slot_index > DAILY_TARGET:
            raise ValueError(f"Invalid slot index {slot_index}. Daily slots are 1 to {DAILY_TARGET}.")
        return CANONICAL_DAILY_CADENCE[slot_index - 1]

    @classmethod
    def validate_daily_batch(cls, items: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Validates that a planned daily set of items complies with the cadence contract:
        Exactly 4 items: 2 Novel Story, 1 Discovery Big, 1 Discovery Short.
        """
        errors = []
        if len(items) != DAILY_TARGET:
            errors.append(f"Daily batch must contain exactly {DAILY_TARGET} items, got {len(items)}.")

        format_counts: Dict[ContentFormat, int] = {
            ContentFormat.NOVEL_STORY: 0,
            ContentFormat.DISCOVERY_BIG: 0,
            ContentFormat.DISCOVERY_SHORT: 0,
        }

        for idx, item in enumerate(items, 1):
            raw_fmt = item.get("format")
            try:
                fmt = ContentFormat(raw_fmt)
                format_counts[fmt] += 1
            except (ValueError, TypeError):
                errors.append(f"Item {idx} has unrecognized format '{raw_fmt}'.")
                continue

            dur = float(item.get("duration_sec", item.get("duration", 0.0)))
            min_d, max_d = FORMAT_DURATION_BOUNDS[fmt]
            if not (min_d <= dur <= max_d):
                errors.append(
                    f"Item {idx} ({fmt.value}) duration {dur:.1f}s out of canonical range [{min_d}s, {max_d}s]."
                )

        if format_counts[ContentFormat.NOVEL_STORY] != NOVEL_STORY:
            errors.append(f"Expected exactly {NOVEL_STORY} Novel Stories, got {format_counts[ContentFormat.NOVEL_STORY]}.")
        if format_counts[ContentFormat.DISCOVERY_BIG] != DISCOVERY_BIG:
            errors.append(f"Expected exactly {DISCOVERY_BIG} Discovery Big, got {format_counts[ContentFormat.DISCOVERY_BIG]}.")
        if format_counts[ContentFormat.DISCOVERY_SHORT] != DISCOVERY_SHORT:
            errors.append(f"Expected exactly {DISCOVERY_SHORT} Discovery Short, got {format_counts[ContentFormat.DISCOVERY_SHORT]}.")

        return len(errors) == 0, errors

    @classmethod
    def route_candidate_to_format(
        cls,
        natural_duration_sec: float,
        is_novel_lore_only: bool = False,
        has_film_contrast: bool = True,
        fact_count: int = 1,
    ) -> ContentFormat:
        """
        Routes a candidate topic to its natural format based on content strength
        and natural storytelling length, NOT arbitrary fact count.
        """
        # Lore-heavy topics without film contrast belong to Novel Story
        if is_novel_lore_only and not has_film_contrast:
            return ContentFormat.NOVEL_STORY

        # If natural length fits compact format (25-30s), route to DISCOVERY_SHORT
        if natural_duration_sec <= 35.0:
            return ContentFormat.DISCOVERY_SHORT

        # Otherwise route to DISCOVERY_BIG (60-70s)
        return ContentFormat.DISCOVERY_BIG
