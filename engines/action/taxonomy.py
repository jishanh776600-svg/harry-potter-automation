"""
STORY FORGE — Physical Action Taxonomy & Declarative Evidence Policies
======================================================================
Defines the expected physical evidence requirements, geometric criteria,
temporal state sequences, and rejection rules for each canonical action.
"""

from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from engines.action.models import PhysicalActionType


class ActionEvidencePolicy(BaseModel):
    """
    Declarative policy defining the exact physical evidence requirements
    for a given physical action type.
    """
    action_type: PhysicalActionType
    requires_actor: bool = True
    requires_target: bool = False
    requires_object: bool = False
    requires_motion: bool = True
    requires_contact: bool = False
    requires_hoi: bool = False
    requires_state_transition: bool = False
    supporting_reaction: bool = False
    
    # Expected chronological event sequence
    expected_event_sequence: List[str] = Field(default_factory=list)
    
    # Quantitative physical thresholds (normalized screen units)
    min_peak_velocity: float = 0.20
    max_contact_distance: float = 0.15  # Max centroid-to-boundary distance for contact
    min_contact_iou: float = 0.0        # Overlap or edge contact required
    min_displacement: float = 0.05
    max_duration_sec: float = 5.0
    min_duration_sec: float = 0.2


# ---------------------------------------------------------------------------
# Declarative Policy Registry for Supported Physical Actions
# ---------------------------------------------------------------------------

ACTION_POLICIES: Dict[PhysicalActionType, ActionEvidencePolicy] = {
    # 1. PUNCH / HIT: Actor strikes target entity
    PhysicalActionType.PUNCH: ActionEvidencePolicy(
        action_type=PhysicalActionType.PUNCH,
        requires_actor=True,
        requires_target=True,
        requires_object=False,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=False,
        requires_state_transition=False,
        supporting_reaction=True,
        expected_event_sequence=["approach", "contact", "reaction"],
        min_peak_velocity=0.35,
        max_contact_distance=0.12,
    ),
    PhysicalActionType.HIT: ActionEvidencePolicy(
        action_type=PhysicalActionType.HIT,
        requires_actor=True,
        requires_target=True,
        requires_object=False,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=False,
        requires_state_transition=False,
        supporting_reaction=True,
        expected_event_sequence=["approach", "contact", "reaction"],
        min_peak_velocity=0.30,
        max_contact_distance=0.14,
    ),

    # 2. KICK: Actor leg/foot strikes target entity
    PhysicalActionType.KICK: ActionEvidencePolicy(
        action_type=PhysicalActionType.KICK,
        requires_actor=True,
        requires_target=True,
        requires_object=False,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=False,
        requires_state_transition=False,
        supporting_reaction=True,
        expected_event_sequence=["approach", "contact", "reaction"],
        min_peak_velocity=0.35,
        max_contact_distance=0.15,
    ),

    # 3. PUSH: Sustained contact leading to target displacement
    PhysicalActionType.PUSH: ActionEvidencePolicy(
        action_type=PhysicalActionType.PUSH,
        requires_actor=True,
        requires_target=True,
        requires_object=False,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=False,
        requires_state_transition=False,
        supporting_reaction=True,
        expected_event_sequence=["approach", "contact", "displacement"],
        min_peak_velocity=0.20,
        max_contact_distance=0.10,
    ),

    # 4. PULL: Contact or grasp leading to target moving toward actor
    PhysicalActionType.PULL: ActionEvidencePolicy(
        action_type=PhysicalActionType.PULL,
        requires_actor=True,
        requires_target=True,
        requires_object=False,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=False,
        requires_state_transition=False,
        supporting_reaction=True,
        expected_event_sequence=["contact", "motion_toward_actor"],
        min_peak_velocity=0.18,
        max_contact_distance=0.12,
    ),

    # 5. GRAB / PICK_UP: Approach to object, contact, followed by persistent retention
    PhysicalActionType.GRAB: ActionEvidencePolicy(
        action_type=PhysicalActionType.GRAB,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["approach", "contact", "held"],
        min_peak_velocity=0.18,
        max_contact_distance=0.10,
    ),
    PhysicalActionType.PICK_UP: ActionEvidencePolicy(
        action_type=PhysicalActionType.PICK_UP,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["reach", "contact", "lift", "held"],
        min_peak_velocity=0.15,
        max_contact_distance=0.10,
    ),

    # 6. PUT_DOWN: Held object lowered to resting surface, released
    PhysicalActionType.PUT_DOWN: ActionEvidencePolicy(
        action_type=PhysicalActionType.PUT_DOWN,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["held", "lower", "release"],
        min_peak_velocity=0.12,
        max_contact_distance=0.15,
    ),

    # 7. HANDOVER: Source possesses object -> moves toward recipient -> recipient possesses
    PhysicalActionType.HANDOVER: ActionEvidencePolicy(
        action_type=PhysicalActionType.HANDOVER,
        requires_actor=True,
        requires_target=True,   # Recipient
        requires_object=True,
        requires_motion=True,
        requires_contact=False, # Object transfers between hands
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["with_source", "transfer", "with_recipient"],
        min_peak_velocity=0.12,
        max_contact_distance=0.25,
    ),

    # 8. THROW: Object held -> rapid release -> ballistic trajectory away from actor
    PhysicalActionType.THROW: ActionEvidencePolicy(
        action_type=PhysicalActionType.THROW,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["held", "release", "moving_away"],
        min_peak_velocity=0.35,
        max_contact_distance=0.30,
    ),

    # 9. CATCH: Approaching object -> intercept/contact -> held
    PhysicalActionType.CATCH: ActionEvidencePolicy(
        action_type=PhysicalActionType.CATCH,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["moving_toward", "contact", "held"],
        min_peak_velocity=0.25,
        max_contact_distance=0.12,
    ),

    # 10. OPEN / CLOSE: Actor manipulates boundary/portal
    PhysicalActionType.OPEN: ActionEvidencePolicy(
        action_type=PhysicalActionType.OPEN,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=True,
        expected_event_sequence=["approach", "manipulation", "opened"],
        min_peak_velocity=0.10,
    ),
    PhysicalActionType.CLOSE: ActionEvidencePolicy(
        action_type=PhysicalActionType.CLOSE,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=True,
        expected_event_sequence=["approach", "manipulation", "closed"],
        min_peak_velocity=0.10,
    ),

    # 11. DRAW / SHEATHE: Weapon/tool transition from concealed/holstered to held
    PhysicalActionType.DRAW: ActionEvidencePolicy(
        action_type=PhysicalActionType.DRAW,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["reach", "extract_motion", "drawn_held"],
        min_peak_velocity=0.25,
    ),
    PhysicalActionType.SHEATHE: ActionEvidencePolicy(
        action_type=PhysicalActionType.SHEATHE,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["held", "stow_motion", "sheathed"],
        min_peak_velocity=0.20,
    ),

    # 12. RAISE / LOWER: Directed vertical motion
    PhysicalActionType.RAISE: ActionEvidencePolicy(
        action_type=PhysicalActionType.RAISE,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=False,
        expected_event_sequence=["upward_motion", "stabilize"],
        min_peak_velocity=0.15,
    ),
    PhysicalActionType.LOWER: ActionEvidencePolicy(
        action_type=PhysicalActionType.LOWER,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=False,
        expected_event_sequence=["downward_motion", "stabilize"],
        min_peak_velocity=0.15,
    ),

    # 13. POINT / WAVE / REACH
    PhysicalActionType.POINT: ActionEvidencePolicy(
        action_type=PhysicalActionType.POINT,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=False,
        expected_event_sequence=["extension", "hold_pose"],
        min_peak_velocity=0.12,
    ),
    PhysicalActionType.WAVE: ActionEvidencePolicy(
        action_type=PhysicalActionType.WAVE,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=False,
        expected_event_sequence=["oscillating_motion"],
        min_peak_velocity=0.15,
    ),
    PhysicalActionType.REACH: ActionEvidencePolicy(
        action_type=PhysicalActionType.REACH,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=False,
        expected_event_sequence=["extension_toward"],
        min_peak_velocity=0.15,
    ),

    # 14. HOLD: Sustained proximity and synchronized position
    PhysicalActionType.HOLD: ActionEvidencePolicy(
        action_type=PhysicalActionType.HOLD,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=False, # Holding can be stationary
        requires_contact=False,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["held_stable"],
        min_peak_velocity=0.0,
    ),
    PhysicalActionType.RELEASE: ActionEvidencePolicy(
        action_type=PhysicalActionType.RELEASE,
        requires_actor=True,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=True,
        requires_state_transition=False,
        expected_event_sequence=["held", "release", "separation"],
        min_peak_velocity=0.10,
    ),

    # 15. BREAK / SNAP: Physical destruction of structural entity
    PhysicalActionType.BREAK: ActionEvidencePolicy(
        action_type=PhysicalActionType.BREAK,
        requires_actor=False, # Can be broken by hand, weapon, or impact
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=True,
        expected_event_sequence=["pre_state_intact", "deformation_snap", "post_state_broken"],
        min_peak_velocity=0.15,
    ),
    PhysicalActionType.SNAP: ActionEvidencePolicy(
        action_type=PhysicalActionType.SNAP,
        requires_actor=False,
        requires_target=False,
        requires_object=True,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=True,
        expected_event_sequence=["pre_state_intact", "deformation_snap", "post_state_broken"],
        min_peak_velocity=0.15,
    ),

    # 16. STRIKE_WITH_OBJECT: Actor uses held weapon to strike target
    PhysicalActionType.STRIKE_WITH_OBJECT: ActionEvidencePolicy(
        action_type=PhysicalActionType.STRIKE_WITH_OBJECT,
        requires_actor=True,
        requires_target=True,
        requires_object=True,
        requires_motion=True,
        requires_contact=True,
        requires_hoi=True,
        requires_state_transition=False,
        supporting_reaction=True,
        expected_event_sequence=["swing_approach", "object_contact", "target_reaction"],
        min_peak_velocity=0.35,
        max_contact_distance=0.15,
    ),

    # 17. FALL: Downward acceleration of entity centroid
    PhysicalActionType.FALL: ActionEvidencePolicy(
        action_type=PhysicalActionType.FALL,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=False,
        expected_event_sequence=["downward_acceleration", "impact_rest"],
        min_peak_velocity=0.25,
    ),

    # 18. RUN / WALK: Continuous horizontal locomotion
    PhysicalActionType.RUN: ActionEvidencePolicy(
        action_type=PhysicalActionType.RUN,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=False,
        expected_event_sequence=["continuous_high_velocity_displacement"],
        min_peak_velocity=0.40,
    ),
    PhysicalActionType.WALK: ActionEvidencePolicy(
        action_type=PhysicalActionType.WALK,
        requires_actor=True,
        requires_target=False,
        requires_object=False,
        requires_motion=True,
        requires_contact=False,
        requires_hoi=False,
        requires_state_transition=False,
        expected_event_sequence=["continuous_moderate_displacement"],
        min_peak_velocity=0.12,
    ),
}


def get_action_policy(action_type: PhysicalActionType) -> ActionEvidencePolicy:
    """Retrieves the declarative evidence policy for an action type."""
    if action_type in ACTION_POLICIES:
        return ACTION_POLICIES[action_type]
    # Default fallback policy
    return ActionEvidencePolicy(
        action_type=action_type,
        requires_actor=True,
        requires_motion=True,
    )
