"""
STORY FORGE Visual Discovery Engine V2 (Step 9 Hardening)
================================================================================
Comprehensive visual discovery, composition assessment, and 9:16 crop safety engine:
- Part A: Semantic relevance, character identity, action match, composition, 9:16 safety, context.
- Part B: Structured shot composition assessment with normalized bounding boxes and shot scales.
- Part C: Hard framing rules (medium/two-shot preferred for narration, close-up only for emotion).
- Part D: Strict no face/body cropping policy.
- Part E: 9:16-first evaluation (simulate crop before ranking).
- Part F: Explicit deterministic visual scoring with severe crop penalties.
- Part G: Visual beat semantics contracts.
- Part H: No forced visuals (returns NO_VALID_VISUAL when no safe truthful candidate exists).
- Part I: Visual diversity and anti-loop guards.
"""

import os
import re
import math
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from core.composition_models import (
    ShotScale,
    NormalizedBBox,
    ShotCompositionAssessment,
)
from core.visual_beat_semantics import (
    VisualBeatRequirement,
    CANONICAL_CHARACTERS,
)

logger = logging.getLogger(__name__)

# Standard 16:9 cinema width to 9:16 vertical crop width ratio
# In a 16:9 frame (aspect ratio 1.7778), a 9:16 vertical crop (aspect ratio 0.5625)
# takes exactly (0.5625 / 1.7778) = 0.3164 of the total horizontal width.
CROP_9X16_WIDTH_RATIO = 9.0 / 16.0 / (16.0 / 9.0)  # ~0.3164


@dataclass
class CandidateMovieShot:
    """
    Candidate movie shot from the canonical Harry Potter movie archive.
    """
    shot_id: str
    movie_number: int
    start_seconds: float
    end_seconds: float
    duration: float
    scene_description: str
    characters_present: List[str] = field(default_factory=list)
    actions_depicted: List[str] = field(default_factory=list)
    environment: str = ""
    composition: Optional[ShotCompositionAssessment] = None
    metadata_tags: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "movie_number": self.movie_number,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration": self.duration,
            "scene_description": self.scene_description,
            "characters_present": self.characters_present,
            "actions_depicted": self.actions_depicted,
            "environment": self.environment,
            "composition": self.composition.to_dict() if self.composition else None,
            "metadata_tags": self.metadata_tags,
        }


@dataclass
class VisualScoringBreakdown:
    """
    Detailed, deterministic multi-criteria scoring breakdown for a candidate shot.
    """
    semantic_relevance: float = 0.0          # 0 - 100
    character_identity: float = 0.0          # 0 - 100
    action_match: float = 0.0                # 0 - 100
    shot_scale_suitability: float = 0.0      # 0 - 100
    subject_visibility: float = 0.0          # 0 - 100
    environment_context_visibility: float = 0.0  # 0 - 100
    crop_safety_9x16: float = 0.0            # 0 - 100
    temporal_continuity: float = 100.0       # 0 - 100
    visual_uniqueness: float = 100.0         # 0 - 100
    severe_crop_penalty: float = 0.0         # Subtracted penalty
    total_score: float = 0.0                 # 0 - 100 final composite score
    is_acceptable: bool = True
    rejection_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "semantic_relevance": round(self.semantic_relevance, 2),
            "character_identity": round(self.character_identity, 2),
            "action_match": round(self.action_match, 2),
            "shot_scale_suitability": round(self.shot_scale_suitability, 2),
            "subject_visibility": round(self.subject_visibility, 2),
            "environment_context_visibility": round(self.environment_context_visibility, 2),
            "crop_safety_9x16": round(self.crop_safety_9x16, 2),
            "temporal_continuity": round(self.temporal_continuity, 2),
            "visual_uniqueness": round(self.visual_uniqueness, 2),
            "severe_crop_penalty": round(self.severe_crop_penalty, 2),
            "total_score": round(self.total_score, 2),
            "is_acceptable": self.is_acceptable,
            "rejection_reasons": self.rejection_reasons,
        }


class VisualDiscoveryEngineV2:
    """
    Visual Discovery Engine V2.
    Implements 9:16-first candidate evaluation, hard framing rules,
    rigorous crop rejection, and anti-loop diversity.
    """

    def __init__(
        self,
        min_acceptance_threshold: float = 50.0,
        beast_engine: Optional[Any] = None,
    ):
        self.min_acceptance_threshold = min_acceptance_threshold
        self.beast_engine = beast_engine

    def match_beast_requirement(
        self,
        requirement: Any,
        candidate_pool: List[Any],
        target_duration: float = 2.0,
    ) -> Optional[Tuple[Any, Any]]:
        """Delegates multi-stage retrieval and temporal verification to the BEAST engine."""
        if not self.beast_engine:
            from engines.beast_visual_matching_engine import BeastVisualMatchingEngine
            self.beast_engine = BeastVisualMatchingEngine(min_confidence_threshold=self.min_acceptance_threshold)
        return self.beast_engine.find_best_visual_match(
            requirement=requirement,
            candidate_pool=candidate_pool,
            target_duration=target_duration,
        )

    # --------------------------------------------------------------------------
    # 1. 9:16 CROP SIMULATION & COMPOSITION ASSESSMENT
    # --------------------------------------------------------------------------
    def assess_shot_composition(
        self,
        shot_scale: ShotScale,
        subject_bbox: Optional[NormalizedBBox] = None,
        characters_present: Optional[List[str]] = None,
        environment: str = "",
        crop_center_x: Optional[float] = None,
    ) -> ShotCompositionAssessment:
        """
        Simulates the 9:16 vertical crop from 16:9 source and assesses composition risk.
        """
        chars = characters_present or []
        rejection_reasons = []

        # If no subject bbox provided, estimate default bbox based on shot scale
        if subject_bbox is None:
            if shot_scale == ShotScale.EXTREME_WIDE:
                bbox = NormalizedBBox(0.40, 0.40, 0.20, 0.20)
            elif shot_scale == ShotScale.WIDE:
                bbox = NormalizedBBox(0.35, 0.25, 0.30, 0.60)
            elif shot_scale == ShotScale.MEDIUM_WIDE:
                bbox = NormalizedBBox(0.35, 0.20, 0.30, 0.70)
            elif shot_scale == ShotScale.MEDIUM:
                bbox = NormalizedBBox(0.38, 0.15, 0.24, 0.75)
            elif shot_scale == ShotScale.MEDIUM_CLOSE:
                bbox = NormalizedBBox(0.35, 0.10, 0.30, 0.80)
            elif shot_scale == ShotScale.CLOSE_UP:
                bbox = NormalizedBBox(0.38, 0.10, 0.24, 0.75)
            elif shot_scale == ShotScale.EXTREME_CLOSE_UP:
                bbox = NormalizedBBox(0.20, 0.05, 0.60, 0.90)
            elif shot_scale == ShotScale.TWO_SHOT:
                bbox = NormalizedBBox(0.20, 0.20, 0.60, 0.70)
            elif shot_scale == ShotScale.GROUP_SHOT:
                bbox = NormalizedBBox(0.15, 0.20, 0.70, 0.70)
            else:
                bbox = NormalizedBBox(0.35, 0.20, 0.30, 0.60)
        else:
            bbox = subject_bbox

        # Define 9:16 vertical crop window on 16:9 frame
        crop_w = CROP_9X16_WIDTH_RATIO  # ~0.3164

        # Compute subject-aware optimal horizontal crop center
        # If caller explicitly provided crop_center_x, respect it.
        # Otherwise, dynamically center on subject bbox while clamping to frame edges.
        if crop_center_x is not None:
            effective_center_x = crop_center_x
        elif bbox is not None:
            effective_center_x = min(1.0 - crop_w / 2.0, max(crop_w / 2.0, bbox.center_x))
        else:
            effective_center_x = 0.50

        crop_x1 = max(0.0, effective_center_x - crop_w / 2.0)
        crop_x2 = min(1.0, effective_center_x + crop_w / 2.0)
        crop_bbox = NormalizedBBox(crop_x1, 0.0, crop_w, 1.0)

        # Calculate subject intersection with 9:16 crop window
        overlap_area = bbox.intersection_area(crop_bbox)
        subject_area = max(0.001, bbox.area)
        retained_subject_ratio = min(1.0, overlap_area / subject_area)

        # Horizontal cutoff
        horizontal_crop_risk = max(0.0, min(1.0, 1.0 - retained_subject_ratio))

        # Head cutoff estimation (upper 20% of subject bbox)
        head_h = bbox.h * 0.20
        head_bbox = NormalizedBBox(bbox.x, bbox.y, bbox.w, head_h)
        head_overlap = head_bbox.intersection_area(crop_bbox)
        head_cutoff = max(0.0, min(1.0, 1.0 - (head_overlap / max(0.0001, head_bbox.area))))

        # Body cutoff estimation (lower 80% of subject bbox)
        body_h = bbox.h * 0.80
        body_bbox = NormalizedBBox(bbox.x, bbox.y + head_h, bbox.w, body_h)
        body_overlap = body_bbox.intersection_area(crop_bbox)
        body_cutoff = max(0.0, min(1.0, 1.0 - (body_overlap / max(0.0001, body_bbox.area))))

        # Center safe score: distance of subject center from crop center
        center_dist = abs(bbox.center_x - effective_center_x)
        center_safe_score = max(0.0, 1.0 - (center_dist / 0.50))

        # Face visibility
        face_visibility = max(0.0, 1.0 - head_cutoff)

        # Multi-character visibility for TWO_SHOT and GROUP_SHOT
        if shot_scale in (ShotScale.TWO_SHOT, ShotScale.GROUP_SHOT):
            # If shot has 2+ characters and bbox width > crop_w, characters on edges are cut off
            if bbox.w > crop_w * 1.2:
                multi_char_vis = max(0.2, crop_w / bbox.w)
            else:
                multi_char_vis = 0.90
        else:
            multi_char_vis = 1.0

        # Background visibility in 9:16 vertical crop
        if shot_scale in (ShotScale.EXTREME_WIDE, ShotScale.WIDE):
            background_vis = 0.90
            env_context_score = 0.95
        elif shot_scale in (ShotScale.MEDIUM_WIDE, ShotScale.MEDIUM):
            background_vis = 0.70
            env_context_score = 0.75
        elif shot_scale == ShotScale.TWO_SHOT:
            background_vis = 0.65
            env_context_score = 0.70
        elif shot_scale == ShotScale.CLOSE_UP:
            background_vis = 0.25
            env_context_score = 0.30
        elif shot_scale == ShotScale.EXTREME_CLOSE_UP:
            background_vis = 0.05
            env_context_score = 0.10
        else:
            background_vis = 0.50
            env_context_score = 0.50

        # Vertical crop risk: close-ups have high vertical risk because forehead/chin are near borders
        if shot_scale in (ShotScale.CLOSE_UP, ShotScale.EXTREME_CLOSE_UP):
            vertical_crop_risk = 0.50 if bbox.h > 0.85 else 0.25
        else:
            vertical_crop_risk = 0.10

        # 9:16 safe score calculation
        safe_score = (
            0.35 * (1.0 - head_cutoff) +
            0.25 * (1.0 - horizontal_crop_risk) +
            0.20 * center_safe_score +
            0.10 * multi_char_vis +
            0.10 * (1.0 - vertical_crop_risk)
        )
        safe_score = max(0.0, min(1.0, safe_score))

        # Rejection checks
        is_safe = True
        has_severe_crop = False

        if head_cutoff > 0.20:
            is_safe = False
            has_severe_crop = True
            rejection_reasons.append(f"Severe head cutoff: {head_cutoff*100:.1f}% of head cropped out")

        if horizontal_crop_risk > 0.50:
            is_safe = False
            has_severe_crop = True
            rejection_reasons.append(f"Severe horizontal body cutoff: {horizontal_crop_risk*100:.1f}% cropped out")

        if shot_scale in (ShotScale.TWO_SHOT, ShotScale.GROUP_SHOT) and multi_char_vis < 0.60:
            is_safe = False
            rejection_reasons.append("Two-shot / group framing cuts off secondary character in 9:16 crop")

        if shot_scale == ShotScale.EXTREME_CLOSE_UP:
            is_safe = False
            has_severe_crop = True
            rejection_reasons.append("Extreme close-up causes unacceptable 9:16 facial distortion")

        # Intelligent 3-Tier 9:16 Reframing Strategy Selection:
        # Tier 1: FULL_BLEED_RECENTERED (100% vertical screen occupancy for medium, medium-wide, close-up)
        # Tier 2: HYBRID_MODERATE_CROP (~80% vertical screen occupancy for two-shots, wide shots, or moderate spread)
        # Tier 3: BLURRED_PADDING (~31.6% vertical occupancy, reserved for extreme wide vistas)
        if shot_scale == ShotScale.EXTREME_WIDE:
            effective_strategy = "BLURRED_PADDING"
            occupancy = 0.316
            utilization = 0.316
        elif (
            shot_scale in (ShotScale.TWO_SHOT, ShotScale.WIDE)
            or (0.15 < head_cutoff <= 0.25)
            or (0.35 < horizontal_crop_risk <= 0.50)
        ) and multi_char_vis >= 0.40:
            effective_strategy = "HYBRID_MODERATE_CROP"
            occupancy = 0.80
            utilization = 0.80
        elif head_cutoff <= 0.15 and horizontal_crop_risk <= 0.35 and multi_char_vis >= 0.70:
            effective_strategy = "FULL_BLEED_RECENTERED"
            occupancy = 1.0
            utilization = 1.0
        else:
            effective_strategy = "BLURRED_PADDING"
            occupancy = 0.316
            utilization = 0.316

        crop_win = {
            "x": round(crop_x1, 4),
            "y": 0.0,
            "w": round(crop_w, 4),
            "h": 1.0,
            "center_x": round(effective_center_x, 4),
        }

        return ShotCompositionAssessment(
            shot_scale=shot_scale,
            subject_bbox=bbox,
            subject_area_ratio=bbox.area,
            face_visibility=face_visibility,
            head_cutoff=head_cutoff,
            body_cutoff=body_cutoff,
            background_visibility=background_vis,
            environment_context_score=env_context_score,
            multi_character_visibility=multi_char_vis,
            center_safe_score=center_safe_score,
            vertical_crop_risk=vertical_crop_risk,
            horizontal_crop_risk=horizontal_crop_risk,
            safe_9x16_score=safe_score,
            is_9x16_crop_safe=is_safe,
            crop_rejection_reasons=rejection_reasons,
            optimal_crop_center_x=effective_center_x,
            has_severe_crop=has_severe_crop,
            effective_crop_strategy=effective_strategy,
            visual_occupancy_ratio=occupancy,
            vertical_screen_utilization=utilization,
            crop_window=crop_win,
        )

    # --------------------------------------------------------------------------
    # 2. VISUAL SCORING MODEL (PART F)
    # --------------------------------------------------------------------------
    def score_candidate(
        self,
        candidate: CandidateMovieShot,
        beat_req: VisualBeatRequirement,
        recent_history: Optional[List[CandidateMovieShot]] = None,
    ) -> VisualScoringBreakdown:
        """
        Computes an explicit, deterministic multi-criteria score for a candidate shot.
        Applies hard framing rules and severe crop penalties.
        """
        history = recent_history or []
        rejection_reasons: List[str] = []
        is_acceptable = True

        comp = candidate.composition
        if not comp:
            comp = self.assess_shot_composition(ShotScale.MEDIUM)
            candidate.composition = comp

        # A. Semantic Relevance (0 - 100)
        # Check text match between narration and scene description / actions
        narration_lower = beat_req.narration_text.lower()
        desc_lower = candidate.scene_description.lower()
        env_lower = candidate.environment.lower()

        semantic_score = 30.0  # baseline
        # Check word overlaps
        narration_words = set(re.findall(r"\b\w{4,}\b", narration_lower))
        scene_words = set(re.findall(r"\b\w{4,}\b", desc_lower + " " + env_lower))
        overlap = narration_words.intersection(scene_words)
        if overlap:
            semantic_score += min(50.0, len(overlap) * 15.0)

        # B. Named-Character Identity (0 - 100)
        char_score = 0.0
        if beat_req.required_characters:
            matched_chars = 0
            for rc in beat_req.required_characters:
                rc_lower = rc.lower()
                for c in candidate.characters_present:
                    if rc_lower in c.lower():
                        matched_chars += 1
                        break
            if matched_chars == len(beat_req.required_characters):
                char_score = 100.0
            elif matched_chars > 0:
                char_score = 50.0 * (matched_chars / len(beat_req.required_characters))
            else:
                char_score = 0.0
                is_acceptable = False
                rejection_reasons.append(
                    f"Required character(s) '{beat_req.required_characters}' missing from candidate (has '{candidate.characters_present}')"
                )
        else:
            char_score = 80.0  # character neutral beat

        # Check forbidden characters
        for fc in beat_req.forbidden_characters:
            if any(fc.lower() in c.lower() for c in candidate.characters_present):
                char_score = 0.0
                is_acceptable = False
                rejection_reasons.append(f"Forbidden character '{fc}' present in candidate")

        # C. Action Match (0 - 100)
        action_score = 50.0
        if beat_req.required_actions:
            action_matches = 0
            for ra in beat_req.required_actions:
                ra_lower = ra.lower()
                for act in candidate.actions_depicted:
                    if ra_lower in act.lower():
                        action_matches += 1
                        break
            if action_matches > 0:
                action_score = 100.0
            else:
                action_score = 30.0

        # D. Shot-Scale Suitability & Hard Framing Rules (PART C)
        # Normal character narration -> PREFER MEDIUM, MEDIUM_WIDE, TWO_SHOT
        # Close-up disallowed for normal narration
        scale = comp.shot_scale
        scale_score = 50.0

        if scale in beat_req.preferred_shot_scales:
            scale_score = 100.0
        elif scale in beat_req.disallowed_shot_scales:
            scale_score = 10.0
            is_acceptable = False
            rejection_reasons.append(
                f"Shot scale '{scale.value}' is disallowed for beat '{beat_req.beat_id}' (preferred: {[s.value for s in beat_req.preferred_shot_scales]})"
            )
        elif scale == ShotScale.CLOSE_UP and not beat_req.allow_close_up:
            # HARD RULE: A close-up must NOT be selected merely because it scores highly for character identity
            scale_score = 15.0
            is_acceptable = False
            rejection_reasons.append("CLOSE_UP rejected: Normal character narration forbids close-ups without explicit emotional requirement")
        elif scale == ShotScale.EXTREME_CLOSE_UP and not beat_req.allow_extreme_close_up:
            scale_score = 0.0
            is_acceptable = False
            rejection_reasons.append("EXTREME_CLOSE_UP rejected: Unjustified extreme close-up")
        else:
            scale_score = 65.0

        # E. Subject Visibility (0 - 100)
        subject_vis_score = comp.face_visibility * 100.0 if beat_req.require_face_visible else comp.center_safe_score * 100.0

        # F. Environment / Context Visibility (0 - 100)
        env_score = comp.environment_context_score * 100.0
        if beat_req.required_context_or_environment:
            req_env = beat_req.required_context_or_environment.lower()
            hogwarts_matches = (req_env == "hogwarts" and any(loc in env_lower or loc in desc_lower for loc in ("courtyard", "great hall", "gryffindor", "dungeon", "potions", "grounds", "castle")))
            if req_env in env_lower or req_env in desc_lower or hogwarts_matches:
                env_score = min(100.0, env_score + 30.0)
            else:
                env_score = 0.0
                if beat_req.require_context_visible:
                    is_acceptable = False
                    rejection_reasons.append(f"Required context '{beat_req.required_context_or_environment}' missing from candidate")

        # G. 9:16 Crop Safety (0 - 100)
        crop_safety_score = comp.safe_9x16_score * 100.0
        if not comp.is_9x16_crop_safe:
            is_acceptable = False
            rejection_reasons.extend(comp.crop_rejection_reasons)

        # H. Temporal Continuity & Diversity Guard (PART I)
        temporal_continuity = 100.0
        visual_uniqueness = 100.0
        for past_shot in history:
            # Anti-loop: Check identical shot or overlapping timestamps
            if past_shot.shot_id == candidate.shot_id:
                visual_uniqueness = 0.0
                is_acceptable = False
                rejection_reasons.append(f"Duplicate shot reuse: '{candidate.shot_id}' already used in this Short")
                break
            if (
                past_shot.movie_number == candidate.movie_number
                and abs(past_shot.start_seconds - candidate.start_seconds) < 3.0
            ):
                visual_uniqueness = 10.0
                is_acceptable = False
                rejection_reasons.append("Near-duplicate movie timestamp loop detected")
                break

        # Check consecutive shot-scale fatigue (3 identical scales in a row)
        if len(history) >= 2:
            if history[-1].composition and history[-2].composition:
                if (
                    history[-1].composition.shot_scale == scale
                    and history[-2].composition.shot_scale == scale
                ):
                    temporal_continuity = 40.0

        # J. Severe Crop Penalty (PART D, F)
        severe_crop_penalty = 0.0
        if comp.has_severe_crop:
            severe_crop_penalty = 60.0
            is_acceptable = False

        if comp.head_cutoff > 0.15:
            severe_crop_penalty += 40.0
            is_acceptable = False
            rejection_reasons.append(f"Unacceptable face cutoff ({comp.head_cutoff*100:.1f}%)")

        if comp.body_cutoff > 0.40 and scale not in (ShotScale.CLOSE_UP, ShotScale.EXTREME_CLOSE_UP):
            severe_crop_penalty += 35.0
            is_acceptable = False
            rejection_reasons.append(f"Unacceptable body cutoff ({comp.body_cutoff*100:.1f}%)")

        # Composite Score Calculation (Normalized Weights)
        # Weights:
        # Semantic: 20%, Char: 20%, Action: 15%, Scale: 15%, Env: 10%, 9:16 Safety: 20%
        raw_weighted_score = (
            0.20 * min(100.0, semantic_score) +
            0.20 * min(100.0, char_score) +
            0.15 * min(100.0, action_score) +
            0.15 * min(100.0, scale_score) +
            0.10 * min(100.0, env_score) +
            0.20 * min(100.0, crop_safety_score)
        )

        # Apply uniqueness and temporal adjustments
        uniqueness_factor = visual_uniqueness / 100.0
        continuity_factor = temporal_continuity / 100.0

        total_score = (raw_weighted_score * uniqueness_factor * continuity_factor) - severe_crop_penalty
        total_score = max(0.0, min(100.0, total_score))

        if total_score < self.min_acceptance_threshold:
            is_acceptable = False
            if f"Score {total_score:.1f} below threshold {self.min_acceptance_threshold}" not in rejection_reasons:
                rejection_reasons.append(f"Score {total_score:.1f} below minimum acceptance threshold {self.min_acceptance_threshold}")

        return VisualScoringBreakdown(
            semantic_relevance=semantic_score,
            character_identity=char_score,
            action_match=action_score,
            shot_scale_suitability=scale_score,
            subject_visibility=subject_vis_score,
            environment_context_visibility=env_score,
            crop_safety_9x16=crop_safety_score,
            temporal_continuity=temporal_continuity,
            visual_uniqueness=visual_uniqueness,
            severe_crop_penalty=severe_crop_penalty,
            total_score=total_score if is_acceptable else 0.0,
            is_acceptable=is_acceptable,
            rejection_reasons=rejection_reasons,
        )

    # --------------------------------------------------------------------------
    # 3. 9:16-FIRST CANDIDATE RANKING & SELECTION (PART E, H)
    # --------------------------------------------------------------------------
    def select_best_shot(
        self,
        beat_req: VisualBeatRequirement,
        candidates: List[CandidateMovieShot],
        recent_history: Optional[List[CandidateMovieShot]] = None,
    ) -> Tuple[Optional[CandidateMovieShot], Optional[VisualScoringBreakdown]]:
        """
        9:16-First Evaluation Pipeline:
          1. Evaluate composition and simulate 9:16 crop for each candidate
          2. Calculate crop safety and reject unsafe compositions
          3. Score surviving candidates
          4. Rank surviving candidates (wider shot preferred over tighter shot when comparable)
          5. Return best surviving shot, or None (NO_VALID_VISUAL) if none pass
        """
        scored_candidates: List[Tuple[CandidateMovieShot, VisualScoringBreakdown]] = []

        for cand in candidates:
            # Assess composition if not present
            if not cand.composition:
                cand.composition = self.assess_shot_composition(
                    shot_scale=ShotScale.MEDIUM,
                    characters_present=cand.characters_present,
                    environment=cand.environment
                )

            # Score candidate
            breakdown = self.score_candidate(cand, beat_req, recent_history)
            if breakdown.is_acceptable and breakdown.total_score >= self.min_acceptance_threshold:
                scored_candidates.append((cand, breakdown))

        if not scored_candidates:
            logger.warning(
                f"[VisualDiscoveryEngineV2] NO_VALID_VISUAL for beat '{beat_req.beat_id}'. "
                f"All {len(candidates)} candidates rejected by composition, safety, or scoring."
            )
            return None, None

        # Sort surviving candidates by total score descending.
        # Tie-breaker: prefer wider shot over tighter shot when scores are within 5.0 points!
        def sort_key(item: Tuple[CandidateMovieShot, VisualScoringBreakdown]):
            cand, bd = item
            scale = cand.composition.shot_scale if cand.composition else ShotScale.MEDIUM
            # Bonus for natural wider framing (MEDIUM / MEDIUM_WIDE) over tight framing
            framing_bonus = 0.0
            if scale in (ShotScale.MEDIUM, ShotScale.MEDIUM_WIDE, ShotScale.TWO_SHOT):
                framing_bonus = 2.0
            return bd.total_score + framing_bonus

        scored_candidates.sort(key=sort_key, reverse=True)
        best_cand, best_bd = scored_candidates[0]
        logger.info(
            f"[VisualDiscoveryEngineV2] Selected '{best_cand.shot_id}' for beat '{beat_req.beat_id}' "
            f"(Score: {best_bd.total_score:.1f}, Scale: {best_cand.composition.shot_scale.value if best_cand.composition else 'N/A'})"
        )
        return best_cand, best_bd
