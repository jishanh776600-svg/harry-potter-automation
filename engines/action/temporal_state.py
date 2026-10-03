"""
STORY FORGE — Temporal State Machine
====================================
Tracks and verifies physical object/scene state transitions:
  - Elder Wand: INTACT -> BENDING/SNAP -> BROKEN
  - Handover: WITH_SOURCE -> TRANSFER -> WITH_RECIPIENT
  - Throw: HELD -> RELEASED -> MOVING_AWAY
  - Enforces strict chronological progression and rejects static pre-existing states
"""

from __future__ import annotations
import logging
from typing import List, Dict, Tuple, Optional, Any
from engines.action.models import ActionFailureReason

logger = logging.getLogger("TemporalStateMachine")


class TemporalStateObservation:
    def __init__(self, timestamp_sec: float, frame_index: int, state_name: str, metric_value: float = 0.0):
        self.timestamp_sec = timestamp_sec
        self.frame_index = frame_index
        self.state_name = state_name.upper()
        self.metric_value = metric_value


class TemporalStateMachine:
    """
    Validates that a physical entity transitioned through mandatory discrete states in order.
    """

    @classmethod
    def verify_state_transition(
        cls,
        observations: List[TemporalStateObservation],
        expected_sequence: List[str],
        min_time_delta_sec: float = 0.04,
        max_duration_sec: float = 6.0,
    ) -> Dict[str, Any]:
        """
        Verifies that observations exhibit the expected state sequence forward in time.
        """
        if not expected_sequence:
            return {"verified": True, "reason": "No state sequence required"}

        if not observations or len(observations) < len(expected_sequence):
            return {
                "verified": False,
                "failure_reason": ActionFailureReason.STATE_TRANSITION_NOT_CONFIRMED,
                "explanation": f"Insufficient state observations (got {len(observations)}, needed {len(expected_sequence)})",
            }

        # Sort observations chronologically
        obs_sorted = sorted(observations, key=lambda o: o.timestamp_sec)
        expected_norm = [s.upper() for s in expected_sequence]

        # 1. Anti-Fraud Check: Reject pre-existing final state at onset
        # If the object is already in the final state at the very first observation,
        # no dynamic transition took place.
        final_state = expected_norm[-1]
        initial_obs = obs_sorted[0]
        if initial_obs.state_name == final_state and len(expected_norm) > 1:
            return {
                "verified": False,
                "failure_reason": ActionFailureReason.STATE_TRANSITION_NOT_CONFIRMED,
                "explanation": f"PRE_EXISTING_STATE: Entity was already in final state '{final_state}' at t={initial_obs.timestamp_sec:.2f}s; no transition occurred.",
            }

        # 2. Sequential State Matching
        matched_events: List[TemporalStateObservation] = []
        curr_expected_idx = 0

        for obs in obs_sorted:
            if curr_expected_idx < len(expected_norm):
                target_state = expected_norm[curr_expected_idx]
                if obs.state_name == target_state:
                    # Check temporal order with previous match
                    if matched_events:
                        prev_match = matched_events[-1]
                        if obs.timestamp_sec < prev_match.timestamp_sec + min_time_delta_sec:
                            continue  # Must be strictly later
                    matched_events.append(obs)
                    curr_expected_idx += 1

        if len(matched_events) < len(expected_norm):
            missing_states = expected_norm[len(matched_events):]
            return {
                "verified": False,
                "failure_reason": ActionFailureReason.STATE_TRANSITION_NOT_CONFIRMED,
                "explanation": f"Incomplete state transition sequence. Matched {[m.state_name for m in matched_events]}, missing {missing_states}.",
            }

        # Total duration check
        total_dt = matched_events[-1].timestamp_sec - matched_events[0].timestamp_sec
        if total_dt > max_duration_sec:
            return {
                "verified": False,
                "failure_reason": ActionFailureReason.STATE_TRANSITION_NOT_CONFIRMED,
                "explanation": f"State transition duration {total_dt:.2f}s exceeded maximum allowable {max_duration_sec:.2f}s.",
            }

        return {
            "verified": True,
            "failure_reason": None,
            "matched_sequence": [m.state_name for m in matched_events],
            "timestamps": [round(m.timestamp_sec, 3) for m in matched_events],
            "duration_sec": round(total_dt, 3),
            "explanation": f"Verified complete state sequence: {' -> '.join([m.state_name for m in matched_events])}.",
        }
