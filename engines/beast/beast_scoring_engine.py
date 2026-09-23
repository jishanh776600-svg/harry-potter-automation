"""
STORY FORGE — BEAST Scoring & Exact Timestamp Refiner (Phases 11 & 14)
================================================================================
Implements configurable multi-stage scoring and sub-interval temporal refinement:
  1. Computes composite weighted score from semantic, entity, action, object, location, and VLM inputs.
  2. Applies hard penalties for contradictions, crop risks, and visual repetition.
  3. Evaluates framing and shot scale compatibility.
  4. Refines exact source sub-timestamps [start, end] to fit the editorial beat without stretching or looping.
  5. Enforces fail-closed thresholding: returns NO_VALID_VISUAL if final confidence is below threshold.
"""

import math
import logging
from typing import List, Dict, Any, Optional, Tuple, Set

from core.beast_visual_types import (
    BeastVisualRequirement,
    BeastCandidateShot,
    BeastScoringWeights,
    BeastScoringBreakdown,
    BeastVLMVerificationResult,
)
from core.composition_models import ShotScale

logger = logging.getLogger("BeastScoringEngine")


class BeastScoringEngine:
    """
    Reranking, scoring, and sub-interval extraction engine for candidate video shots.
    """

    def __init__(self, weights: Optional[BeastScoringWeights] = None):
        self.weights = weights or BeastScoringWeights()

    def score_candidate(
        self,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
        semantic_sim: float,
        primary_char_score: float,
        secondary_char_score: float,
        action_score: float,
        object_score: float,
        location_score: float,
        has_contradiction: bool,
        contradiction_reasons: List[str],
        vlm_verdict: Optional[BeastVLMVerificationResult] = None,
        recently_used_shot_ids: Optional[Set[str]] = None,
        target_beat_duration: float = 2.0,
    ) -> BeastScoringBreakdown:
        """
        Computes composite multi-stage score and extracts exact source timestamps.
        """
        rejection_reasons: List[str] = list(contradiction_reasons)

        # 1. Framing & Shot Scale Score
        framing_score = 100.0
        if requirement.preferred_framing:
            if shot.shot_scale in requirement.preferred_framing:
                framing_score = 100.0
            elif shot.shot_scale in (ShotScale.MEDIUM_SHOT, ShotScale.MEDIUM_WIDE, ShotScale.TWO_SHOT):
                framing_score = 75.0
            elif shot.shot_scale == ShotScale.CLOSE_UP and requirement.allow_close_up:
                framing_score = 85.0
            else:
                framing_score = 40.0

        # 2. VLM Score
        vlm_score = 50.0  # neutral if unverified
        if vlm_verdict:
            if vlm_verdict.match:
                vlm_score = max(vlm_verdict.confidence, 70.0)
            else:
                vlm_score = min(vlm_verdict.confidence, 30.0)
                rejection_reasons.append(f"VLM Gate Rejected: {vlm_verdict.reason}")

        # 3. Penalties
        # Contradiction penalty
        contra_penalty = self.weights.p_contradiction if has_contradiction else 0.0

        # Crop risk penalty
        crop_risk_penalty = 0.0
        if shot.composition:
            if not shot.composition.is_9x16_crop_safe:
                crop_risk_penalty = self.weights.p_crop_risk
                rejection_reasons.extend(shot.composition.crop_rejection_reasons)

        # Repetition penalty
        repetition_penalty = 0.0
        if recently_used_shot_ids and shot.shot_id in recently_used_shot_ids:
            repetition_penalty = self.weights.p_repetition
            rejection_reasons.append(f"Shot '{shot.shot_id}' was recently used (repetition guard)")

        # 4. Temporal Coherence Score
        temporal_coherence = 100.0
        if shot.duration < 0.8:
            temporal_coherence = 30.0
            rejection_reasons.append(f"Shot duration ({shot.duration:.2f}s) is too brief for mobile readability")

        # 5. Weighted Score Calculation
        w = self.weights
        composite = (
            w.w_semantic * semantic_sim
            + w.w_character * primary_char_score
            + w.w_secondary_character * secondary_char_score
            + w.w_action * action_score
            + w.w_object * object_score
            + w.w_location * location_score
            + w.w_temporal * temporal_coherence
            + w.w_vlm * vlm_score
        )

        final_score = max(0.0, composite - contra_penalty - crop_risk_penalty - repetition_penalty)

        # 6. Acceptance Decision
        is_acceptable = (
            not has_contradiction
            and (vlm_verdict is None or vlm_verdict.match)
            and final_score >= requirement.confidence_threshold
        )

        if not is_acceptable and not rejection_reasons:
            rejection_reasons.append(
                f"Score {final_score:.1f} below required confidence threshold {requirement.confidence_threshold:.1f}"
            )

        # 7. Exact Timestamp Refinement (Phase 14)
        extracted_interval = self.refine_sub_interval(shot, target_beat_duration)

        return BeastScoringBreakdown(
            shot_id=shot.shot_id,
            semantic_similarity=semantic_sim,
            character_score=primary_char_score,
            secondary_character_score=secondary_char_score,
            action_score=action_score,
            object_score=object_score,
            location_score=location_score,
            temporal_coherence=temporal_coherence,
            vlm_score=vlm_score,
            framing_score=framing_score,
            contradiction_penalty=contra_penalty,
            crop_risk_penalty=crop_risk_penalty,
            repetition_penalty=repetition_penalty,
            final_score=final_score,
            is_acceptable=is_acceptable,
            rejection_reasons=rejection_reasons,
            vlm_verdict=vlm_verdict,
            extracted_interval=extracted_interval,
        )

    def refine_sub_interval(
        self,
        shot: BeastCandidateShot,
        target_duration: float,
    ) -> Tuple[float, float]:
        """
        Calculates exact [start_sec, end_sec] sub-window inside shot without stretching or looping.
        """
        shot_start = shot.start_seconds
        shot_end = shot.end_seconds
        shot_dur = shot.duration

        # If shot is shorter or equal to target duration, use the whole natural shot
        if shot_dur <= target_duration:
            return (round(shot_start, 3), round(shot_end, 3))

        # Center the sub-interval around the midpoint of the shot to capture peak action
        excess = shot_dur - target_duration
        sub_start = shot_start + (excess / 2.0)
        sub_end = sub_start + target_duration

        return (round(sub_start, 3), round(sub_end, 3))
