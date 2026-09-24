"""
STORY FORGE — Temporal Micro-Interval Extractor
===============================================
Extracts the smallest useful temporal micro-interval where the required
visual action occurs:
  - Inspects BEFORE, ONSET, DURING, AFTER phases.
  - Aligns start time strictly to action onset to eliminate visual delay.
  - Rejects intervals that only show BEFORE (setup) or AFTER (aftermath).
  - Enforces strict <= 1.50s ceiling for Discovery Shorts (no stretching, no looping).
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

from engines.visual_evidence.evidence_models import (
    TemporalState,
    EvidenceRejectionReason,
)

logger = logging.getLogger("TemporalMicroIntervalExtractor")


class TemporalMicroIntervalExtractor:
    """
    Sub-second temporal micro-interval extraction engine.
    """

    MAX_DISCOVERY_DURATION = 1.50
    MIN_DISCOVERY_DURATION = 0.60

    @classmethod
    def extract_micro_interval(
        cls,
        source_start: float,
        source_end: float,
        action_start: Optional[float] = None,
        action_peak: Optional[float] = None,
        action_end: Optional[float] = None,
        candidate_phase: Optional[str] = None,
        max_duration: float = 1.50,
        min_duration: float = 0.60,
    ) -> Tuple[Tuple[float, float], TemporalState, Optional[EvidenceRejectionReason], str]:
        """
        Calculates the exact [start, end] micro-interval where the action happens.

        Returns:
            (interval: (start, end),
             state: TemporalState,
             rejection_reason: Optional[EvidenceRejectionReason],
             explanation: str)
        """
        source_start = round(float(source_start), 3)
        source_end = round(float(source_end), 3)
        total_dur = max(0.0, source_end - source_start)

        # 1. Check explicit phase flags if provided
        phase_str = (candidate_phase or "").strip().upper()
        if phase_str == "BEFORE":
            return (
                (source_start, min(source_end, source_start + max_duration)),
                TemporalState.BEFORE,
                EvidenceRejectionReason.BEFORE_PHASE_ONLY,
                "Candidate only depicts setup/approach BEFORE action onset."
            )
        if phase_str == "AFTER":
            return (
                (source_start, min(source_end, source_start + max_duration)),
                TemporalState.AFTER,
                EvidenceRejectionReason.AFTER_PHASE_ONLY,
                "Candidate only depicts aftermath/reaction AFTER action finished."
            )

        # 2. Check relationship between source candidate interval and action interval
        if action_start is not None and action_end is not None:
            act_s = round(float(action_start), 3)
            act_e = round(float(action_end), 3)

            # Candidate interval completely finishes before action begins
            if source_end <= act_s:
                return (
                    (source_start, source_end),
                    TemporalState.BEFORE,
                    EvidenceRejectionReason.BEFORE_PHASE_ONLY,
                    f"Candidate interval [{source_start:.2f}, {source_end:.2f}] ends before action onset ({act_s:.2f}s)."
                )

            # Candidate interval starts after action already concluded
            if source_start >= act_e:
                return (
                    (source_start, source_end),
                    TemporalState.AFTER,
                    EvidenceRejectionReason.AFTER_PHASE_ONLY,
                    f"Candidate interval [{source_start:.2f}, {source_end:.2f}] begins after action ended ({act_e:.2f}s)."
                )

            # Action occurs within or overlaps candidate interval:
            # Action onset alignment: production interval begins at action onset!
            micro_start = max(source_start, act_s)
            raw_action_dur = act_e - micro_start

            # Calculate target duration: between min_duration and max_duration
            if raw_action_dur <= max_duration:
                # Action fits cleanly within 1.50s limit (e.g. 0.8s - 1.4s)
                micro_dur = max(min_duration, raw_action_dur)
                micro_end = min(source_end, micro_start + micro_dur)
                if (micro_end - micro_start) < min_duration:
                    micro_start = max(source_start, micro_end - min_duration)
            else:
                # Action is longer than 1.50s: trim strictly to max_duration around peak/onset
                micro_dur = max_duration
                if action_peak is not None and micro_start <= action_peak <= (micro_start + raw_action_dur):
                    # Center slightly on peak while respecting onset
                    lead = min(0.25, max_duration * 0.2)
                    micro_start = max(source_start, max(act_s, action_peak - lead))
                    micro_end = min(source_end, micro_start + max_duration)
                    if (micro_end - micro_start) < max_duration:
                        micro_start = max(source_start, micro_end - max_duration)
                else:
                    micro_end = min(source_end, micro_start + max_duration)

            micro_dur = round(micro_end - micro_start, 3)
            assert micro_dur <= max_duration + 0.01, f"Extracted interval {micro_dur}s exceeded {max_duration}s cap"

            return (
                (round(micro_start, 3), round(micro_end, 3)),
                TemporalState.DURING,
                None,
                f"Action onset aligned at {micro_start:.2f}s (duration {micro_dur:.2f}s <= {max_duration:.2f}s)."
            )

        # 3. If action_peak is known but not full start/end
        if action_peak is not None:
            pk = round(float(action_peak), 3)
            if source_end <= pk - 0.5:
                return (
                    (source_start, source_end),
                    TemporalState.BEFORE,
                    EvidenceRejectionReason.BEFORE_PHASE_ONLY,
                    f"Candidate finishes before action peak ({pk:.2f}s)."
                )
            if source_start >= pk + 0.5:
                return (
                    (source_start, source_end),
                    TemporalState.AFTER,
                    EvidenceRejectionReason.AFTER_PHASE_ONLY,
                    f"Candidate starts after action peak ({pk:.2f}s)."
                )

            lead = min(0.20, max_duration * 0.15)
            micro_start = max(source_start, pk - lead)
            micro_end = min(source_end, micro_start + max_duration)
            if (micro_end - micro_start) < min_duration and total_dur >= min_duration:
                micro_start = max(source_start, micro_end - min_duration)

            micro_dur = round(micro_end - micro_start, 3)
            return (
                (round(micro_start, 3), round(micro_end, 3)),
                TemporalState.DURING,
                None,
                f"Action peak aligned at {pk:.2f}s (duration {micro_dur:.2f}s <= {max_duration:.2f}s)."
            )

        # 4. Fallback if no sub-action timestamps are present:
        # Bounded by max_duration without stretching
        if total_dur <= max_duration:
            micro_start = source_start
            micro_end = source_end
        else:
            # Take the initial onset window up to max_duration
            micro_start = source_start
            micro_end = round(source_start + max_duration, 3)

        micro_dur = round(micro_end - micro_start, 3)
        return (
            (round(micro_start, 3), round(micro_end, 3)),
            TemporalState.DURING,
            None,
            f"Bounded to {micro_dur:.2f}s (<= {max_duration:.2f}s ceiling)."
        )
