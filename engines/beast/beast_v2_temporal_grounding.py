"""
STORY FORGE — BEAST V2 Temporal Micro-Interval Grounder
================================================================================
Implements precise sub-second temporal grounding where the proposition occurs:
  - Locates [action_start, action_peak, action_end] rather than blind center-of-shot
  - Produces targeted 1.2–2.0s windows for rapid physical actions
  - Rejects wrong temporal intervals when action occurs elsewhere in the scene,
    refining to the correct action interval
  - Enforces strict <= 2.0s continuous duration limit on ORIENTATION_BRIDGE footage
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

from core.beast_v2_types import (
    ActionCategory,
    TemporalMicroInterval,
    EvidenceType,
)
from core.beast_visual_types import BeastCandidateShot

logger = logging.getLogger("BeastV2TemporalGrounder")

FAST_PHYSICAL_ACTIONS = {
    ActionCategory.STRIKE,
    ActionCategory.DESTROY,
    ActionCategory.CAST,
    ActionCategory.ATTACK,
    ActionCategory.DEFEND,
    ActionCategory.PICK_UP,
    ActionCategory.DROP,
    ActionCategory.TRANSFORM,
}

MAX_ORIENTATION_BRIDGE_DURATION = 2.0


class BeastV2TemporalGrounder:
    """
    Computes precise temporal sub-windows aligned to exact action peaks.
    """

    @classmethod
    def ground_action_interval(
        cls,
        shot: BeastCandidateShot,
        action_category: Optional[ActionCategory] = None,
        target_duration: float = 2.0,
        candidate_interval: Optional[Tuple[float, float]] = None,
    ) -> Tuple[TemporalMicroInterval, bool, Optional[str]]:
        """
        Calculates exact [source_start, source_end] sub-window around action occurrence.
        Returns:
            (interval: TemporalMicroInterval, is_valid: bool, rejection_reason: Optional[str])
        """
        shot_start = shot.start_seconds
        shot_end = shot.end_seconds
        shot_dur = shot.duration

        # Look up explicit action annotations in metadata if present
        meta = shot.metadata or {}
        action_start = meta.get("action_start")
        action_peak = meta.get("action_peak")
        action_end = meta.get("action_end")

        # Determine optimal duration based on action nature
        if action_category in FAST_PHYSICAL_ACTIONS:
            effective_target = min(target_duration, 1.8)
            effective_target = max(1.2, effective_target)
        else:
            effective_target = target_duration

        # Reject candidate shots that only contain BEFORE or AFTER phase
        phase_str = str(meta.get("phase") or meta.get("action_phase") or "").upper()
        if phase_str in ("BEFORE", "AFTER"):
            interval = TemporalMicroInterval(
                source_start=shot_start,
                source_end=shot_end,
                action_start=action_start,
                action_peak=action_peak,
                action_end=action_end,
                target_duration=effective_target,
            )
            return (
                interval,
                False,
                f"Temporal Phase Mismatch: Candidate shot only contains {phase_str} phase, lacking active DURING execution."
            )

        # CASE 7 Check: If candidate_interval is provided, check if it coincides with action interval
        if candidate_interval and action_start is not None and action_end is not None:
            c_start, c_end = candidate_interval
            # Check overlap between candidate interval and actual action
            overlap = max(0.0, min(c_end, action_end) - max(c_start, action_start))
            if overlap <= 0.0 or c_end <= action_start or c_start >= action_end:
                # Candidate interval misses the action or is purely BEFORE/AFTER phase!
                # Create the corrected interval starting directly at action onset (DURING phase)
                sub_start = max(shot_start, action_start)
                sub_end = min(shot_end, sub_start + effective_target)
                if sub_end - sub_start < effective_target:
                    sub_start = max(shot_start, sub_end - effective_target)

                peak = action_peak if action_peak is not None else ((action_start + action_end) / 2.0)
                corrected = TemporalMicroInterval(
                    source_start=round(sub_start, 3),
                    source_end=round(sub_end, 3),
                    action_start=action_start,
                    action_peak=peak,
                    action_end=action_end,
                    target_duration=effective_target,
                )
                phase_reason = "BEFORE" if c_end <= action_start else ("AFTER" if c_start >= action_end else "WRONG")
                reason = (
                    f"Wrong Interval ({phase_reason} phase): Action occurs at [{action_start:.2f}, {action_end:.2f}] "
                    f"but candidate segment was [{c_start:.2f}, {c_end:.2f}]."
                )
                return corrected, False, reason

        # Action-guided onset alignment: cut starts directly at action_start (DURING phase)
        # to eliminate visual delay so footage already shows the action at visual onset.
        if action_start is not None and action_end is not None:
            sub_start = max(shot_start, action_start)
            sub_end = min(shot_end, sub_start + effective_target)
            if (sub_end - sub_start) < effective_target:
                sub_start = max(shot_start, sub_end - effective_target)
            if action_peak is None:
                action_peak = (action_start + action_end) / 2.0
        elif action_peak is not None and shot_start <= action_peak <= shot_end:
            # If only peak is known, use minimal lead-in so action is actively occurring
            lead_in = min(0.2, effective_target * 0.15)
            sub_start = max(shot_start, action_peak - lead_in)
            sub_end = min(shot_end, sub_start + effective_target)
            if (sub_end - sub_start) < effective_target:
                sub_start = max(shot_start, sub_end - effective_target)
        else:
            # Fallback if no sub-action timestamps: natural shot bounded
            if shot_dur <= effective_target:
                sub_start = shot_start
                sub_end = shot_end
            else:
                excess = shot_dur - effective_target
                sub_start = shot_start + (excess / 2.0)
                sub_end = sub_start + effective_target

        interval = TemporalMicroInterval(
            source_start=round(sub_start, 3),
            source_end=round(sub_end, 3),
            action_start=action_start,
            action_peak=action_peak,
            action_end=action_end,
            target_duration=effective_target,
        )
        return interval, True, None

    @classmethod
    def validate_orientation_bridge(cls, duration: float) -> Tuple[bool, Optional[str]]:
        """
        Enforces maximum 2.0-second continuous duration on ORIENTATION_BRIDGE footage.
        """
        if duration > MAX_ORIENTATION_BRIDGE_DURATION:
            return (
                False,
                f"ORIENTATION_BRIDGE duration ({duration:.2f}s) exceeds the strict 2.0s maximum ceiling."
            )
        return True, None
