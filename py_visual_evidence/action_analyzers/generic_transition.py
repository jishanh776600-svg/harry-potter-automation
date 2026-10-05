"""
Generic State-Transition Analyzer
Reusable engine for arbitrary STATE_A -> EVENT -> STATE_B transitions
(e.g., standing -> falling, closed -> open, holding -> released).
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
import numpy as np

from py_visual_evidence.schema import (
    VisualAssertion,
    EntityTrajectory,
    StateTransitionResult,
    ActionResult,
)
from py_visual_evidence.action_analyzers.base import BaseActionAnalyzer


class GenericStateTransitionAnalyzer(BaseActionAnalyzer):
    """
    Evaluates whether an entity undergoes a transition from initial_state to final_state
    by observing trajectory bounding box geometry, aspect ratios, and spatial displacement.
    """

    def analyze_action(
        self,
        frames: List[np.ndarray],
        trajectories: Dict[str, EntityTrajectory],
        assertion: VisualAssertion,
        fps: float = 24.0,
    ) -> ActionResult:
        target_name = assertion.object.name if assertion.object and assertion.object.name in trajectories else assertion.subject.name
        traj = trajectories.get(target_name)

        if not traj or len(traj.points) < 4:
            return ActionResult(
                action_name=assertion.action,
                detected=False,
                confidence=0.0,
                peak_metric_value=0.0,
                threshold_used=1.0,
                details={"error": f"Insufficient trajectory points for '{target_name}' to analyze generic transition."},
            )

        spec = assertion.expected_state_transition
        initial_state = spec.initial_state.lower() if spec else "initial"
        final_state = spec.final_state.lower() if spec else "final"

        # Extract temporal feature series
        pts = traj.points
        heights = [p.bbox.h for p in pts]
        aspect_ratios = [p.bbox.w / (p.bbox.h + 1e-5) for p in pts]
        y_centroids = [p.centroid[1] for p in pts]

        n = len(pts)
        start_h = float(np.mean(heights[:max(1, int(n * 0.25))]))
        end_h = float(np.mean(heights[int(n * 0.75):]))

        start_y = float(np.mean(y_centroids[:max(1, int(n * 0.25))]))
        end_y = float(np.mean(y_centroids[int(n * 0.75):]))

        start_aspect = float(np.mean(aspect_ratios[:max(1, int(n * 0.25))]))
        end_aspect = float(np.mean(aspect_ratios[int(n * 0.75):]))

        detected = False
        ratio = 1.0

        if "fall" in final_state or "lying" in final_state:
            # Standing -> Falling: Vertical height collapses, y centroid drops downward
            height_drop = (start_h - end_h) / (start_h + 1e-5)
            y_drop = end_y - start_y
            detected = height_drop > 0.25 or y_drop > 0.15
            ratio = 1.0 + max(height_drop, y_drop)
        elif "open" in final_state or "spread" in final_state:
            # Closed -> Open: Bounding box width / aspect ratio expands
            aspect_growth = (end_aspect - start_aspect) / (start_aspect + 1e-5)
            detected = aspect_growth > 0.30
            ratio = 1.0 + aspect_growth
        elif "stand" in final_state or "rise" in final_state:
            # Seated -> Standing: Height expands, y centroid rises upward
            height_growth = (end_h - start_h) / (start_h + 1e-5)
            detected = height_growth > 0.20
            ratio = 1.0 + height_growth
        else:
            # General geometric displacement
            displacement = np.linalg.norm(np.array(pts[-1].centroid) - np.array(pts[0].centroid))
            detected = displacement > 0.10
            ratio = 1.0 + float(displacement)

        conf = min(0.95, 0.70 + (ratio - 1.0) * 0.4) if detected else 0.20

        return ActionResult(
            action_name=assertion.action,
            detected=detected,
            confidence=round(conf, 3),
            peak_metric_value=round(ratio, 3),
            threshold_used=1.20,
            details={
                "transition": f"{initial_state} -> {final_state}",
                "start_metric": round(start_h, 3),
                "end_metric": round(end_h, 3),
                "transition_ratio": round(ratio, 3),
            },
        )
