"""
Multi-Step Event Validation & Causal Sequence Enforcer
Enforces strict chronological sequence (t(A) < t(B) < t(C)) across multiple assertions.
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple
from py_visual_evidence.schema import ObservationEvidence, EvidenceVerdict


class CausalOrderValidator:
    def __init__(self, allow_temporal_overlap_sec: float = 0.10):
        self.allow_temporal_overlap_sec = allow_temporal_overlap_sec

    def validate_causal_sequence(
        self,
        evidences: List[ObservationEvidence],
    ) -> Tuple[bool, List[str]]:
        """
        Validates that a list of observation evidence records, ordered by their
        intended script sequence, satisfies physical temporal causality.
        """
        if len(evidences) <= 1:
            return True, []

        violations = []
        for i in range(1, len(evidences)):
            prev_ev = evidences[i - 1]
            curr_ev = evidences[i]

            prev_end = prev_ev.time_range[1]
            curr_start = curr_ev.time_range[0]

            # In causal narrative logic, Event i cannot occur before Event i-1 starts
            if curr_start < (prev_end - self.allow_temporal_overlap_sec):
                violations.append(
                    f"Causal Sequence Violation: Assertion '{curr_ev.assertion_id}' at {curr_start:.2f}s "
                    f"occurs before preceding Assertion '{prev_ev.assertion_id}' finishes at {prev_end:.2f}s"
                )

        is_valid = len(violations) == 0
        return is_valid, violations
