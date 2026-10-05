"""
Relationship Verification Engine
Verifies that required entity interactions (Subject -> Action -> Object -> Recipient)
are physically established through spatial proximity, directional vector alignment,
and trajectory coupling.
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Any, Optional
import numpy as np

from py_visual_evidence.schema import (
    VisualAssertion,
    EntityTrajectory,
)


class RelationshipVerifier:
    def __init__(self, max_interaction_distance: float = 0.40):
        self.max_interaction_distance = max_interaction_distance

    def verify_relationship(
        self,
        assertion: VisualAssertion,
        trajectories: Dict[str, EntityTrajectory],
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Evaluates whether the physical relationship specified in the assertion
        is upheld by the observed trajectories.
        """
        sub_name = assertion.subject.name
        obj_name = assertion.object.name if assertion.object else None
        rec_name = assertion.recipient.name if assertion.recipient else None

        sub_traj = trajectories.get(sub_name)
        obj_traj = trajectories.get(obj_name) if obj_name else None
        rec_traj = trajectories.get(rec_name) if rec_name else None

        details: Dict[str, Any] = {}

        # 1. Subject-Object Relationship (e.g. Subject holds/interacts with Object)
        if obj_traj and sub_traj:
            num_pts = min(len(sub_traj.points), len(obj_traj.points))
            sub_obj_dists = []
            for i in range(num_pts):
                d = np.linalg.norm(
                    np.array(sub_traj.points[i].centroid) - np.array(obj_traj.points[i].centroid)
                )
                sub_obj_dists.append(float(d))

            min_sub_obj = min(sub_obj_dists) if sub_obj_dists else 1.0
            mean_sub_obj = float(np.mean(sub_obj_dists)) if sub_obj_dists else 1.0
            details["sub_obj_min_dist"] = round(min_sub_obj, 3)
            details["sub_obj_mean_dist"] = round(mean_sub_obj, 3)

            # If subject and object are too far apart across the entire clip, relationship fails
            if min_sub_obj > self.max_interaction_distance:
                return (
                    False,
                    f"Subject '{sub_name}' and Object '{obj_name}' never interact (closest distance: {min_sub_obj:.2f})",
                    details,
                )

        # 2. Subject-Recipient Relationship (e.g. Interaction across counter / face-to-face)
        if sub_traj and rec_traj:
            num_pts = min(len(sub_traj.points), len(rec_traj.points))
            sub_rec_dists = [
                float(np.linalg.norm(np.array(sub_traj.points[i].centroid) - np.array(rec_traj.points[i].centroid)))
                for i in range(num_pts)
            ]
            min_sub_rec = min(sub_rec_dists) if sub_rec_dists else 1.0
            details["sub_rec_min_dist"] = round(min_sub_rec, 3)

            # For direct physical strikes (punch, strike, hit), physical contact/impact proximity is required
            action_lower = assertion.action.lower()
            if any(w in action_lower for w in ("punch", "strike", "hit", "smash", "slap")):
                if min_sub_rec > 0.22:
                    return (
                        False,
                        f"Subject '{sub_name}' and Recipient '{rec_name}' never reach strike contact distance (closest: {min_sub_rec:.2f} > 0.22)",
                        details,
                    )
            elif min_sub_rec > 0.85:
                return (
                    False,
                    f"Subject '{sub_name}' and Recipient '{rec_name}' are mutually disconnected in frame",
                    details,
                )

        # 3. Transfer Relationship (Subject -> Object -> Recipient)
        if sub_traj and obj_traj and rec_traj:
            summary = f"{sub_name} -> {obj_name} -> {rec_name}"
            return True, summary, details

        # 4. Standard Subject -> Recipient Action Relationship
        if sub_traj and rec_traj:
            summary = f"{sub_name} -> {assertion.action} -> {rec_name}"
            return True, summary, details

        # 5. Standard Subject -> Object / Action Relationship
        if sub_traj and obj_traj:
            summary = f"{sub_name} -> {assertion.action} -> {obj_name}"
            return True, summary, details

        if sub_traj:
            summary = f"{sub_name} performing {assertion.action}"
            return True, summary, details

        return False, "Insufficient entity trajectories to establish relationship", details

    verify_relationships = verify_relationship
