"""
STORY FORGE — Temporal Causal Evidence Graph
============================================
Enforces physical and chronological causality across detected action events:
  - Directed Acyclic Graph (DAG) validation: Cause must precede effect
  - Strictly rejects inverted timelines (e.g. reaction -> contact -> approach)
  - Computes deterministic graph hashes for cryptographic lineage verification
"""

from __future__ import annotations
import hashlib
import json
import logging
from typing import List, Dict, Tuple, Optional, Any

from engines.action.models import (
    TemporalEvent,
    CausalEdge,
    CausalEvidenceGraph,
    ActionFailureReason,
)

logger = logging.getLogger("CausalGraph")


class TemporalCausalVerifier:
    """
    Validates physical causal consistency in event sequences.
    """

    @classmethod
    def build_and_verify_graph(
        cls,
        events: List[TemporalEvent],
        expected_sequence: List[str],
        min_delta_sec: float = 0.0,
        max_delta_sec: float = 3.0,
    ) -> CausalEvidenceGraph:
        """
        Constructs a causal DAG from events and verifies that the events
        satisfy the expected causal sequence.
        """
        graph = CausalEvidenceGraph(events=events, edges=[])

        if not expected_sequence:
            graph.is_valid = True
            return graph

        # Map event names to earliest matching event
        events_by_name: Dict[str, List[TemporalEvent]] = {}
        for ev in events:
            key = ev.name.lower()
            if key not in events_by_name:
                events_by_name[key] = []
            events_by_name[key].append(ev)

        # 1. Check all required events exist
        for req_name in expected_sequence:
            norm_req = req_name.lower()
            if norm_req not in events_by_name or not events_by_name[norm_req]:
                graph.is_valid = False
                graph.violation_reason = f"MISSING_CAUSAL_NODE: Required event '{req_name}' was not detected in timeline."
                return graph

        # 2. Check pairwise chronological and causal order
        edges: List[CausalEdge] = []
        for i in range(len(expected_sequence) - 1):
            cause_name = expected_sequence[i].lower()
            effect_name = expected_sequence[i + 1].lower()

            cause_evs = events_by_name[cause_name]
            effect_evs = events_by_name[effect_name]

            # Find valid cause -> effect pair
            found_valid_pair = False
            best_cause: Optional[TemporalEvent] = None
            best_effect: Optional[TemporalEvent] = None
            inverted_detected = False

            for c_ev in cause_evs:
                for e_ev in effect_evs:
                    delta = e_ev.timestamp_sec - c_ev.timestamp_sec
                    if delta < -0.01:
                        # Effect happened before cause!
                        inverted_detected = True
                    elif min_delta_sec <= delta <= max_delta_sec:
                        found_valid_pair = True
                        best_cause = c_ev
                        best_effect = e_ev
                        break
                if found_valid_pair:
                    break

            if not found_valid_pair:
                graph.is_valid = False
                if inverted_detected:
                    graph.violation_reason = (
                        f"CAUSAL_INVERSION_DETECTED: '{effect_name}' preceded '{cause_name}'. "
                        f"Physical actions require cause to precede effect."
                    )
                else:
                    graph.violation_reason = (
                        f"CAUSAL_TIMING_DISCONNECTED: Time gap between '{cause_name}' and '{effect_name}' "
                        f"does not satisfy physical latency bounds [{min_delta_sec}s, {max_delta_sec}s]."
                    )
                return graph

            edges.append(CausalEdge(
                cause_event_id=best_cause.event_id,
                effect_event_id=best_effect.event_id,
                min_time_delta_sec=min_delta_sec,
                max_time_delta_sec=max_delta_sec,
                verified=True,
            ))

        graph.edges = edges
        graph.is_valid = True
        return graph

    @classmethod
    def compute_graph_hash(cls, graph: CausalEvidenceGraph) -> str:
        """Computes deterministic SHA-256 hash for causal evidence graph."""
        data = {
            "is_valid": graph.is_valid,
            "violation_reason": graph.violation_reason,
            "events": [
                {
                    "id": ev.event_id,
                    "name": ev.name,
                    "ts": round(ev.timestamp_sec, 3),
                    "conf": round(ev.confidence, 4),
                }
                for ev in sorted(graph.events, key=lambda e: e.timestamp_sec)
            ],
            "edges": [
                {
                    "cause": ed.cause_event_id,
                    "effect": ed.effect_event_id,
                    "verified": ed.verified,
                }
                for ed in graph.edges
            ]
        }
        serialized = json.dumps(data, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
