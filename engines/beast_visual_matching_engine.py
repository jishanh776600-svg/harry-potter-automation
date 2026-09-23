"""
STORY FORGE — THE BEAST VISUAL MATCHING ENGINE
Unified Multi-Stage Video Semantic Retrieval + Temporal Verification System
================================================================================
Unifies all 19 phases into an aggressive, multi-stage retrieval & verification engine:
  Phase 1:  Visual Requirement Understanding (Semantic & Compositional parsing)
  Phase 2:  Shot-Boundary Detection (PySceneDetect AdaptiveDetector)
  Phase 3:  Multi-Frame Temporal Sequence Understanding (10%, 30%, 50%, 70%, 90%)
  Phase 4:  Semantic Retrieval (Multi-representation vector search)
  Phase 5:  Character / Person Verification (Primary, Secondary, Multi-Character)
  Phase 6:  Object Verification (Sorting Hat, Sword, Mirror, etc.)
  Phase 7:  Action Verification (Dynamic motion & cluster matching)
  Phase 8:  Location / Scene Verification (Great Hall, Forest, etc.)
  Phase 9:  Vision-Language Verification Gate (Multimodal Gemini VLM)
  Phase 10: Temporal Coherence (No stretching, no looping, no repetition)
  Phase 11: Multi-Stage Reranking (Configurable weighted composite scoring)
  Phase 12: Contradiction Detection (Hard rejection of mismatched character footage)
  Phase 13: Visual Role Matching (DIRECT_EVIDENCE, CONTEXTUAL_ENVIRONMENT, etc.)
  Phase 14: Exact Timestamp Extraction (Source-accurate start and end intervals)
  Phase 15: Narration <-> Visual Timeline Integration (Beat-lock alignment)
  Phase 16: Failure Behavior (NO_VALID_VISUAL fail-closed guarantee)
  Phase 17: Caching & Persistence (Deterministic fingerprints & catalogs)
  Phase 18: Headless / CPU Fallback & GitHub Actions Compatibility
  Phase 19: Pipeline Integration with True 9:16 and Remotion
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from core.beast_visual_types import (
    BeastVisualRequirement,
    BeastCandidateShot,
    MultiFrameSample,
    BeastVLMVerificationResult,
    BeastScoringBreakdown,
    BeastScoringWeights,
    NarrativeEra,
)
from core.composition_models import ShotScale
from core.storyboard_types import VisualRole
from engines.beast.beast_shot_detector import BeastShotDetector
from engines.beast.beast_semantic_retriever import BeastSemanticRetriever
from engines.beast.beast_entity_verifiers import BeastEntityVerifiers
from engines.beast.beast_contradiction_guard import BeastContradictionGuard
from engines.beast.beast_vlm_verifier import BeastVLMVerifier
from engines.beast.beast_scoring_engine import BeastScoringEngine

logger = logging.getLogger("BeastVisualMatchingEngine")


class BeastVisualMatchingEngine:
    """
    The BEAST Visual Matching Engine.
    Coordinates multi-stage retrieval, entity verification, contradiction filtering,
    and VLM gatekeeping to guarantee footage visually supports narration.
    """

    def __init__(
        self,
        shot_detector: Optional[BeastShotDetector] = None,
        semantic_retriever: Optional[BeastSemanticRetriever] = None,
        entity_verifiers: Optional[BeastEntityVerifiers] = None,
        contradiction_guard: Optional[BeastContradictionGuard] = None,
        vlm_verifier: Optional[BeastVLMVerifier] = None,
        scoring_engine: Optional[BeastScoringEngine] = None,
        min_confidence_threshold: float = 65.0,
        repetition_window_size: int = 4,
    ):
        self.shot_detector = shot_detector or BeastShotDetector()
        self.semantic_retriever = semantic_retriever or BeastSemanticRetriever()
        self.entity_verifiers = entity_verifiers or BeastEntityVerifiers()
        self.contradiction_guard = contradiction_guard or BeastContradictionGuard()
        self.vlm_verifier = vlm_verifier or BeastVLMVerifier()
        self.scoring_engine = scoring_engine or BeastScoringEngine()
        self.min_confidence_threshold = min_confidence_threshold
        self.repetition_window_size = repetition_window_size
        from collections import deque
        self._recently_used_queue: deque = deque(maxlen=repetition_window_size)
        self._recently_used_shots: Set[str] = set()

    # --------------------------------------------------------------------------
    # PHASE 1: VISUAL REQUIREMENT UNDERSTANDING
    # --------------------------------------------------------------------------
    def parse_narration_beat(
        self,
        beat_id: str,
        narration_text: str,
        narrative_phase: str = "EVIDENCE",
        visual_role: VisualRole = VisualRole.DIRECT_EVIDENCE,
        target_duration: float = 2.0,
    ) -> BeastVisualRequirement:
        """
        Parses narration beat into fine-grained compositional requirement contract.
        """
        text_lower = narration_text.lower()

        # Subject extraction
        primary_subject = ""
        secondary_subject = None

        if "neville" in text_lower:
            primary_subject = "Neville Longbottom"
        elif "harry" in text_lower:
            primary_subject = "Harry Potter"
        elif "snape" in text_lower:
            primary_subject = "Severus Snape"
        elif "hermione" in text_lower:
            primary_subject = "Hermione Granger"
        elif "ron" in text_lower:
            primary_subject = "Ron Weasley"
        elif "dumbledore" in text_lower:
            primary_subject = "Albus Dumbledore"
        elif "voldemort" in text_lower:
            primary_subject = "Lord Voldemort"

        # Secondary subject / interaction target
        if "sorting hat" in text_lower:
            if primary_subject and primary_subject != "Sorting Hat":
                secondary_subject = "Sorting Hat"
            else:
                primary_subject = "Sorting Hat"
        elif "malfoy" in text_lower and primary_subject != "Draco Malfoy":
            secondary_subject = "Draco Malfoy"
        elif "nagini" in text_lower and primary_subject != "Nagini":
            secondary_subject = "Nagini"

        # Required objects
        req_objs = []
        if "sorting hat" in text_lower or "the hat" in text_lower:
            req_objs.append("Sorting Hat")
        if "sword" in text_lower:
            req_objs.append("Sword of Gryffindor")
        if "stool" in text_lower:
            req_objs.append("Stool")
        if "mirror" in text_lower or "erised" in text_lower:
            req_objs.append("Mirror of Erised")
        if "horcrux" in text_lower or "nagini" in text_lower:
            req_objs.append("Horcrux")

        # Action extraction
        req_action = ""
        if any(w in text_lower for w in ["begged", "begging", "pleaded", "pleading"]):
            req_action = "pleading and begging"
        elif any(w in text_lower for w in ["argued", "arguing", "argument"]):
            req_action = "arguing with the Sorting Hat"
        elif any(w in text_lower for w in ["pull", "pulling", "pulled", "drew", "drawing"]):
            req_action = "drawing the sword from the hat"
        elif any(w in text_lower for w in ["slay", "strike", "striking", "killed", "decapitating"]):
            req_action = "striking and slaying Nagini"
        elif any(w in text_lower for w in ["raised his fists", "fists"]):
            req_action = "standing and raising fists against friends"
        elif any(w in text_lower for w in ["staring", "gazed", "looking"]):
            req_action = "staring in wonder or fear"

        # Location extraction
        req_loc = None
        if any(w in text_lower for w in ["great hall", "stool", "sorting"]):
            req_loc = "Great Hall"
        elif any(w in text_lower for w in ["battle", "war", "ruins", "courtyard"]):
            req_loc = "Hogwarts Courtyard"
        elif any(w in text_lower for w in ["forest", "forbidden forest"]):
            req_loc = "Forbidden Forest"
        elif any(w in text_lower for w in ["dungeon", "potions"]):
            req_loc = "Dungeons"

        # Era resolution
        expected_era = NarrativeEra.ANY
        if any(w in text_lower for w in ["sorting hat", "first year", "eleven-year-old", "on that stool"]):
            expected_era = NarrativeEra.YEAR_1
        elif any(w in text_lower for w in ["seven years later", "final horcrux", "battle of hogwarts", "last warrior"]):
            expected_era = NarrativeEra.YEAR_7

        # Negative constraints
        negatives = []
        if expected_era == NarrativeEra.YEAR_1:
            negatives.extend(["reject battle of hogwarts", "reject year 7", "reject sword combat"])
        elif expected_era == NarrativeEra.YEAR_7:
            negatives.extend(["reject year 1 sorting", "reject childhood stool"])

        # Preferred framing
        if "sorting" in text_lower or secondary_subject:
            preferred_framing = [ShotScale.MEDIUM_SHOT, ShotScale.TWO_SHOT, ShotScale.MEDIUM_WIDE]
        elif visual_role == VisualRole.CONTEXTUAL_ENVIRONMENT:
            preferred_framing = [ShotScale.WIDE_SHOT, ShotScale.MEDIUM_WIDE]
        else:
            preferred_framing = [ShotScale.MEDIUM_SHOT, ShotScale.MEDIUM_WIDE]

        allow_close_up = (
            visual_role == VisualRole.CHARACTER_REACTION
            or any(w in text_lower for w in ["terrified", "fear", "crying", "horrified", "shocked", "epiphany"])
        )

        return BeastVisualRequirement(
            beat_id=beat_id,
            narration_text=narration_text,
            narrative_phase=narrative_phase,
            primary_subject=primary_subject,
            secondary_subject=secondary_subject,
            required_action=req_action,
            required_objects=req_objs,
            required_location=req_loc,
            interaction_type=f"{primary_subject} <-> {secondary_subject}" if secondary_subject else "",
            visual_role=visual_role,
            preferred_framing=preferred_framing,
            negative_constraints=negatives,
            expected_era=expected_era,
            allow_close_up=allow_close_up,
            confidence_threshold=self.min_confidence_threshold,
        )

    # --------------------------------------------------------------------------
    # RETRIEVE AND VERIFY CANDIDATE
    # --------------------------------------------------------------------------
    def find_best_visual_match(
        self,
        requirement: BeastVisualRequirement,
        candidate_pool: List[BeastCandidateShot],
        target_duration: float = 2.0,
        enable_vlm_gate: bool = True,
    ) -> Optional[Tuple[BeastCandidateShot, BeastScoringBreakdown]]:
        """
        Executes the full multi-stage retrieval and verification pipeline:
          1. Semantic retrieval: finds top 50 initial candidates.
          2. Multi-entity & action verifications.
          3. Contradiction detection: hard filters out conflicting footage.
          4. VLM verification gate on top 3 candidates.
          5. Composite scoring and exact timestamp refinement.
          6. Fail-closed: returns None (NO_VALID_VISUAL) if best score < threshold.
        """
        if not candidate_pool:
            logger.warning("Empty candidate pool for beat '%s'", requirement.beat_id)
            return None

        # 1. Coarse Semantic Retrieval (Phase 4)
        ranked_pool = self.semantic_retriever.retrieve_candidates(
            requirement=requirement,
            candidates=candidate_pool,
            top_k=min(50, len(candidate_pool)),
        )

        scored_candidates: List[Tuple[BeastCandidateShot, BeastScoringBreakdown]] = []

        # 2. Entity, Action, and Contradiction Verification (Phases 5, 6, 7, 8, 12)
        for shot, sem_sim in ranked_pool:
            p_char_score, s_char_score, _ = self.entity_verifiers.verify_character(requirement, shot)
            obj_score, _ = self.entity_verifiers.verify_object(requirement, shot)
            act_score, _ = self.entity_verifiers.verify_action(requirement, shot)
            loc_score, _ = self.entity_verifiers.verify_location(requirement, shot)

            has_contra, _, contra_reasons = self.contradiction_guard.evaluate_contradiction(requirement, shot)

            breakdown = self.scoring_engine.score_candidate(
                requirement=requirement,
                shot=shot,
                semantic_sim=sem_sim,
                primary_char_score=p_char_score,
                secondary_char_score=s_char_score,
                action_score=act_score,
                object_score=obj_score,
                location_score=loc_score,
                has_contradiction=has_contra,
                contradiction_reasons=contra_reasons,
                vlm_verdict=None,
                recently_used_shot_ids=self._recently_used_shots,
                target_beat_duration=target_duration,
            )

            scored_candidates.append((shot, breakdown))

        # Sort by preliminary final score descending
        scored_candidates.sort(key=lambda item: item[1].final_score, reverse=True)

        # 3. Vision-Language Model Verification Gate on Top 3 Candidates (Phase 9)
        top_candidates = scored_candidates[:3]
        validated_candidates: List[Tuple[BeastCandidateShot, BeastScoringBreakdown]] = []

        for shot, prev_breakdown in top_candidates:
            if prev_breakdown.contradiction_penalty > 0:
                # Contradicted candidates are already disqualified
                validated_candidates.append((shot, prev_breakdown))
                continue

            vlm_verdict: Optional[BeastVLMVerificationResult] = None
            if enable_vlm_gate:
                vlm_verdict = self.vlm_verifier.verify_candidate(requirement, shot)

            # Re-score with VLM verdict
            p_char_score, s_char_score, _ = self.entity_verifiers.verify_character(requirement, shot)
            obj_score, _ = self.entity_verifiers.verify_object(requirement, shot)
            act_score, _ = self.entity_verifiers.verify_action(requirement, shot)
            loc_score, _ = self.entity_verifiers.verify_location(requirement, shot)
            has_contra, _, contra_reasons = self.contradiction_guard.evaluate_contradiction(requirement, shot)

            updated_breakdown = self.scoring_engine.score_candidate(
                requirement=requirement,
                shot=shot,
                semantic_sim=prev_breakdown.semantic_similarity,
                primary_char_score=p_char_score,
                secondary_char_score=s_char_score,
                action_score=act_score,
                object_score=obj_score,
                location_score=loc_score,
                has_contradiction=has_contra,
                contradiction_reasons=contra_reasons,
                vlm_verdict=vlm_verdict,
                recently_used_shot_ids=self._recently_used_shots,
                target_beat_duration=target_duration,
            )
            validated_candidates.append((shot, updated_breakdown))

        # Re-sort after VLM gate
        validated_candidates.sort(key=lambda item: item[1].final_score, reverse=True)

        if not validated_candidates:
            logger.info("NO_VALID_VISUAL: No candidates evaluated for beat '%s'", requirement.beat_id)
            return None

        best_shot, best_breakdown = validated_candidates[0]

        # 4. Fail-Closed Threshold Gate (Phase 16)
        if not best_breakdown.is_acceptable or best_breakdown.final_score < requirement.confidence_threshold:
            logger.info(
                "NO_VALID_VISUAL for beat '%s': Best candidate '%s' scored %.1f (below threshold %.1f). Rejection: %s",
                requirement.beat_id,
                best_shot.shot_id,
                best_breakdown.final_score,
                requirement.confidence_threshold,
                "; ".join(best_breakdown.rejection_reasons),
            )
            return None

        # Register shot in recently used sliding window to guard repetition
        self._recently_used_queue.append(best_shot.shot_id)
        self._recently_used_shots = set(self._recently_used_queue)
        return best_shot, best_breakdown

    def clear_session(self) -> None:
        """Resets session tracking states between production runs."""
        self._recently_used_queue.clear()
        self._recently_used_shots.clear()
