"""
STORY FORGE — Editorial Treatment, Motion & Transition Selector
================================================================================
Selects intentional visual treatments, transitions, and emphasis primitives:
  - Controlled punch-ins (default max 1.15x; strictly rejected when gratuitous)
  - Subject-focused motion and True 9:16 composition mapping
  - Precise spotlight and callout geometry for hidden details
  - Match-cut detection (object match, character continuity)
  - Smash-cut selection for contradictions and cognitive surprise
  - Audio-led J-cuts and L-cuts
  - Split-screen and Picture-in-Picture (PIP) for comparisons and citations
  - Selects from 14 canonical VisualEmphasisPrimitives
"""

import logging
from typing import Dict, List, Any, Optional, Tuple, Set

from core.editorial_v2_types import (
    VisualEmphasisPrimitive,
    EditorialTransitionType,
    MotionTreatment,
    CompositionTreatment,
    SpotlightCalloutConfig,
)
from core.beast_v2_types import EvidenceType, BeastV2Decision
from core.beast_visual_types import BeastCandidateShot
from core.composition_models import ShotScale
from core.multi_fact_types import VisualProposition

logger = logging.getLogger("EditorialTreatmentSelector")


class EditorialTreatmentSelector:
    """
    Directorial logic for choosing camera motion, composition, transitions, and callouts.
    """

    @classmethod
    def select_motion_treatment(
        cls,
        narrative_weight: float,
        is_anchor: bool = False,
        is_revelation: bool = False,
        is_hidden_detail: bool = False,
        recent_punch_ins: int = 0,
    ) -> MotionTreatment:
        """
        Determines controlled digital camera motion.
        Enforces default maximum 1.15x punch-in and strictly prevents continuous zoom spam.
        """
        # Anti-spam guard: if already punched-in recently, use static or gentle push
        if recent_punch_ins >= 2:
            return MotionTreatment.SLOW_PUSH_IN if is_anchor else MotionTreatment.STATIC

        if is_revelation or (narrative_weight >= 0.85 and is_anchor):
            return MotionTreatment.PUNCH_IN_115

        if is_hidden_detail:
            return MotionTreatment.PUNCH_IN_115

        if is_anchor or narrative_weight >= 0.70:
            return MotionTreatment.SLOW_PUSH_IN

        return MotionTreatment.STATIC

    @classmethod
    def select_composition_treatment(
        cls,
        shot_scale: ShotScale = ShotScale.MEDIUM_SHOT,
        is_book_vs_movie_comparison: bool = False,
        is_citation_or_bts_inset: bool = False,
        is_archival_document: bool = False,
    ) -> CompositionTreatment:
        """
        Selects True 9:16 composition framing without letterboxing regressions.
        """
        if is_book_vs_movie_comparison:
            return CompositionTreatment.SPLIT_SCREEN_VERTICAL

        if is_citation_or_bts_inset:
            return CompositionTreatment.PICTURE_IN_PICTURE_OVERLAY

        if is_archival_document:
            return CompositionTreatment.BLURRED_PADDING

        scale_val = shot_scale.value if hasattr(shot_scale, "value") else str(shot_scale)
        scale = ShotScale.from_string(scale_val)

        if scale in (ShotScale.CLOSE_UP, ShotScale.EXTREME_CLOSE_UP):
            return CompositionTreatment.FULL_BLEED_RECENTERED

        # Natural cinematic movie framing (MEDIUM_SHOT, TWO_SHOT, MEDIUM_WIDE, WIDE, GROUP_SHOT):
        # Preserves subject and surrounding cinematic context without aggressive digital cropping
        return CompositionTreatment.HYBRID_MODERATE_CROP

    @classmethod
    def select_callout(
        cls,
        proposition: VisualProposition,
        is_hidden_detail: bool = False,
        is_prop_inscription: bool = False,
    ) -> Optional[SpotlightCalloutConfig]:
        """
        Generates short, precise callouts for hidden visual details.
        """
        if not (is_hidden_detail or is_prop_inscription or "hidden" in (proposition.action or "").lower()):
            return None

        callout_type = "MAGNIFIER" if is_prop_inscription else "CIRCULAR_HIGHLIGHT"
        label = proposition.object if proposition.object and proposition.object.lower() != "none" else "Detail"

        return SpotlightCalloutConfig(
            callout_type=callout_type,
            target_x=0.50,
            target_y=0.45,
            radius=0.18,
            label=label,
            start_seconds=0.2,
            duration_seconds=1.2,
        )

    @classmethod
    def select_transition(
        cls,
        prev_shot: Optional[BeastCandidateShot],
        curr_shot: Optional[BeastCandidateShot],
        narrative_role: str = "BODY",
        movie_contrast: float = 0.0,
        is_audio_led_j_cut: bool = False,
        is_audio_led_l_cut: bool = False,
        recent_transitions: Optional[List[EditorialTransitionType]] = None,
    ) -> Tuple[EditorialTransitionType, str]:
        """
        Chooses an intentional transition between outgoing and incoming visual events.
        Detects match-cuts, smash-cuts, J-cuts, and L-cuts.
        """
        recent = recent_transitions or []

        # 1. J-cut and L-cut audio leads
        if is_audio_led_j_cut:
            return EditorialTransitionType.J_CUT, "Audio lead-in: Narration starts before visual cut"
        if is_audio_led_l_cut:
            return EditorialTransitionType.L_CUT, "Audio overlap: Previous dialogue extends into new visual"

        # 2. Smash-cut on contradiction, shock, or surprise
        if "SURPRISE" in narrative_role.upper() or movie_contrast >= 0.85:
            if not (len(recent) >= 2 and recent[-1] == EditorialTransitionType.SMASH_CUT and recent[-2] == EditorialTransitionType.SMASH_CUT):
                return EditorialTransitionType.SMASH_CUT, "Smash cut on sharp contrast / cognitive surprise"

        # 3. Match-cut on shared objects or visual continuity
        if prev_shot and curr_shot:
            prev_objs = set(o.lower() for o in prev_shot.objects_present)
            curr_objs = set(o.lower() for o in curr_shot.objects_present)
            shared_objs = prev_objs.intersection(curr_objs)
            if shared_objs:
                orig_match = next((o for o in prev_shot.objects_present if o.lower() in shared_objs), list(shared_objs)[0])
                return EditorialTransitionType.MATCH_CUT, f"Match cut on shared prop continuity: {orig_match}"

            prev_chars = set(c.lower() for c in prev_shot.characters_present)
            curr_chars = set(c.lower() for c in curr_shot.characters_present)
            if prev_chars and prev_chars == curr_chars and prev_shot.shot_scale == curr_shot.shot_scale:
                return EditorialTransitionType.VISUAL_MATCH, "Visual match on identical subject framing"

        # Default crisp hard cut
        return EditorialTransitionType.HARD_CUT, "Standard editorial cut"

    @classmethod
    def assemble_emphasis_primitives(
        cls,
        motion: MotionTreatment,
        composition: CompositionTreatment,
        callout: Optional[SpotlightCalloutConfig],
        narrative_role: str,
        is_reaction: bool = False,
        is_object_prop: bool = False,
    ) -> List[VisualEmphasisPrimitive]:
        """
        Assembles the list of active VisualEmphasisPrimitives for an editorial unit.
        """
        primitives: List[VisualEmphasisPrimitive] = []

        if motion == MotionTreatment.PUNCH_IN_115:
            primitives.append(VisualEmphasisPrimitive.PUNCH_IN)
        elif motion == MotionTreatment.DYNAMIC_CROP:
            primitives.append(VisualEmphasisPrimitive.CROP_EMPHASIS)

        if composition == CompositionTreatment.SPLIT_SCREEN_VERTICAL:
            primitives.append(VisualEmphasisPrimitive.SPLIT_SCREEN)
        elif composition == CompositionTreatment.PICTURE_IN_PICTURE_OVERLAY:
            primitives.append(VisualEmphasisPrimitive.PICTURE_IN_PICTURE)

        if callout:
            primitives.append(VisualEmphasisPrimitive.CALLOUT)
            if callout.label:
                primitives.append(VisualEmphasisPrimitive.TEXT_CALLOUT)

        if is_object_prop:
            primitives.append(VisualEmphasisPrimitive.OBJECT_SPOTLIGHT)

        if is_reaction:
            primitives.append(VisualEmphasisPrimitive.REACTION_INSERT)

        if "CLIMAX" in narrative_role.upper() or "PAYOFF" in narrative_role.upper():
            primitives.append(VisualEmphasisPrimitive.MICRO_HOLD)

        return primitives
