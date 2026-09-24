"""
STORY FORGE — Visual Evidence Validator
========================================
Implements proposition-level video evidence validation:
  1. Temporal micro-interval extraction (smallest useful interval, action onset aligned, <= 1.50s)
  2. Multi-frame video evidence analysis (beginning, middle, end)
  3. Action is the primary veto (subject/context/object matches cannot compensate for wrong action)
  4. Object and context verification gates
  5. Three evidence classes: DIRECT, CONTEXT, NO_VALID_VISUAL
  6. Context is never silently treated as direct evidence
  7. Strict fail-closed rule and human-readable rejection reasons
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Set

from engines.visual_evidence.evidence_models import (
    EvidenceClass,
    EvidenceRejectionReason,
    TemporalState,
    ObservedProposition,
    EvidenceScore,
    EvidenceValidatorConfig,
    EvidenceValidationResult,
)
from engines.visual_evidence.temporal_extractor import TemporalMicroIntervalExtractor
from engines.visual_evidence.frame_evidence_analyzer import VideoEvidenceAnalyzer
from engines.beast.beast_entity_verifiers import (
    CHARACTER_ALIASES,
    OBJECT_ALIASES,
    ACTION_CLUSTERS,
    BeastEntityVerifiers,
)
from engines.beast.beast_v2_action_verifier import (
    ACTION_KEYWORDS,
    ACTION_INCOMPATIBILITIES,
    BeastV2ActionVerifier,
)
from core.beast_v2_types import ActionCategory

logger = logging.getLogger("VisualEvidenceValidator")


class VisualEvidenceValidator:
    """
    Proposition-level video evidence validation engine.
    """

    def __init__(self, config: Optional[EvidenceValidatorConfig] = None):
        self.config = config or EvidenceValidatorConfig()

    def validate_candidate(
        self,
        proposition: Any,  # VisualProposition or dict
        candidate: Any,    # BeastCandidateShot or dict
        target_interval: Optional[Tuple[float, float]] = None,
    ) -> EvidenceValidationResult:
        """
        Validates a candidate video against a visual proposition.
        Returns EvidenceValidationResult with classification into DIRECT, CONTEXT, or NO_VALID_VISUAL.
        """
        # 1. Normalize proposition input
        prop_dict = self._normalize_proposition(proposition)
        cand_dict = self._normalize_candidate(candidate)

        cand_id = cand_dict.get("candidate_id") or cand_dict.get("shot_id") or "candidate_01"
        asset_id = cand_dict.get("asset_id") or cand_dict.get("source_video") or "asset_01"
        prop_id = prop_dict.get("proposition_id") or "prop_01"

        # Image Policy Check: VIDEO ONLY (Section 13)
        media_type = str(cand_dict.get("media_type") or cand_dict.get("media_category") or "video").lower()
        file_ext = str(asset_id).lower().split(".")[-1] if "." in str(asset_id) else ""
        if media_type in ("image", "still", "artwork", "photo") or file_ext in ("jpg", "jpeg", "png", "webp", "gif"):
            return EvidenceValidationResult(
                candidate_id=cand_id,
                asset_id=asset_id,
                proposition_id=prop_id,
                evidence_class=EvidenceClass.NO_VALID_VISUAL,
                is_valid=False,
                rejection_reasons=[EvidenceRejectionReason.IMAGE_NOT_PERMITTED],
                primary_rejection_reason=EvidenceRejectionReason.IMAGE_NOT_PERMITTED,
                rejection_explanation="Non-video media (images/stills) strictly forbidden by video-only policy.",
                expected_proposition=prop_dict,
                temporal_state=TemporalState.UNCERTAIN,
            )

        # 2. Extract Temporal Micro-Interval (Section 3 & 14)
        c_start = target_interval[0] if target_interval else float(cand_dict.get("start_seconds", 0.0))
        c_end = target_interval[1] if target_interval else float(cand_dict.get("end_seconds", c_start + 2.0))
        
        meta = cand_dict.get("metadata") or {}
        act_s = meta.get("action_start")
        act_p = meta.get("action_peak")
        act_e = meta.get("action_end")
        phase = meta.get("phase") or meta.get("action_phase")

        micro_interval, temp_state, temp_rejection, temp_expl = TemporalMicroIntervalExtractor.extract_micro_interval(
            source_start=c_start,
            source_end=c_end,
            action_start=act_s,
            action_peak=act_p,
            action_end=act_e,
            candidate_phase=phase,
            max_duration=self.config.max_shot_duration,
            min_duration=self.config.min_micro_interval_duration,
        )

        validated_dur = round(micro_interval[1] - micro_interval[0], 3)

        # 3. Analyze Video Evidence from Representative Frames (Section 4)
        observed = VideoEvidenceAnalyzer.analyze_candidate(
            candidate_data=cand_dict,
            interval=micro_interval,
            expected_subject=prop_dict.get("subject"),
            expected_action=prop_dict.get("action"),
            expected_object=prop_dict.get("object"),
            expected_context=prop_dict.get("context"),
        )

        # Override temporal state if extractor found definitive phase
        if temp_state in (TemporalState.BEFORE, TemporalState.AFTER):
            observed.temporal_state = temp_state

        # 4. Gated Checks & Component Scoring (Sections 5, 6, 7, 11)
        rejection_reasons: List[EvidenceRejectionReason] = []
        vetoes: List[str] = []

        # --- A. Temporal State Gate ---
        temporal_alignment = 1.0
        if temp_rejection:
            rejection_reasons.append(temp_rejection)
            vetoes.append(f"Temporal Phase Veto: {temp_expl}")
            temporal_alignment = 0.0
        elif observed.temporal_state != self.config.required_temporal_state and observed.temporal_state != TemporalState.ONSET:
            rejection_reasons.append(EvidenceRejectionReason.TEMPORAL_STATE_UNCERTAIN)
            vetoes.append(f"Temporal state {observed.temporal_state.value} does not meet required {self.config.required_temporal_state.value}")
            temporal_alignment = 0.3

        # --- B. Subject Check ---
        subject_alignment, subj_ok, subj_reason = self._check_subject(
            expected_subject=prop_dict.get("subject"),
            observed=observed,
        )
        if not subj_ok:
            rejection_reasons.append(EvidenceRejectionReason.SUBJECT_MISMATCH)
            vetoes.append(subj_reason)

        # --- C. Action Check (PRIMARY VETO - Section 5) ---
        action_alignment, action_ok, action_reason = self._check_action(
            expected_action=prop_dict.get("action"),
            observed=observed,
            candidate_desc=cand_dict.get("scene_description", ""),
        )
        if not action_ok:
            rejection_reasons.append(EvidenceRejectionReason.ACTION_MISMATCH)
            vetoes.append(action_reason)

        # --- D. Object Check (Section 6) ---
        object_alignment, obj_ok, obj_reason = self._check_object(
            expected_object=prop_dict.get("object"),
            observed=observed,
        )
        if not obj_ok:
            rejection_reasons.append(EvidenceRejectionReason.OBJECT_MISSING)
            vetoes.append(obj_reason)

        # --- E. Context Check (Section 7) ---
        context_alignment, ctx_ok, ctx_reason = self._check_context(
            expected_context=prop_dict.get("context"),
            observed=observed,
        )
        if not ctx_ok:
            rejection_reasons.append(EvidenceRejectionReason.CONTEXT_MISMATCH)
            vetoes.append(ctx_reason)

        # Compute composite score
        passed_gates = len(vetoes) == 0
        composite = (
            (subject_alignment * 0.25)
            + (action_alignment * 0.35)
            + (object_alignment * 0.20)
            + (context_alignment * 0.10)
            + (temporal_alignment * 0.10)
        )
        if not passed_gates:
            composite = min(composite, 0.40)

        scores = EvidenceScore(
            subject_alignment=subject_alignment,
            action_alignment=action_alignment,
            object_alignment=object_alignment,
            context_alignment=context_alignment,
            temporal_alignment=temporal_alignment,
            composite_score=round(composite, 3),
            passed_gates=passed_gates,
            vetoes=vetoes,
        )

        # 5. Evidence Classification: DIRECT vs CONTEXT vs NO_VALID_VISUAL (Sections 8, 9, 10)
        # Check for DIRECT qualification:
        req_rel = str(prop_dict.get("evidence_type") or prop_dict.get("visual_role") or "DIRECT").upper()

        if passed_gates and composite >= self.config.min_composite_threshold:
            evidence_class = EvidenceClass.DIRECT
            is_valid = True
            primary_reason = None
            explanation = f"DIRECT evidence confirmed: Action '{observed.action}', Subject '{observed.subject}', Object '{observed.object}' in context '{observed.context}'."
        else:
            # Check if this qualifies as CONTEXT (Section 8, 9)
            # Context requirement: Character or place is relevant, but action does NOT demonstrate the claim
            is_contextually_relevant = (
                subject_alignment >= self.config.min_subject_threshold
                and context_alignment >= self.config.min_context_threshold
                and EvidenceRejectionReason.SUBJECT_MISMATCH not in rejection_reasons
                and EvidenceRejectionReason.CONTEXT_MISMATCH not in rejection_reasons
            )
            # Action mismatch is the specific reason it's context rather than direct proof
            action_failed = EvidenceRejectionReason.ACTION_MISMATCH in rejection_reasons
            phase_failed = (
                EvidenceRejectionReason.BEFORE_PHASE_ONLY in rejection_reasons
                or EvidenceRejectionReason.AFTER_PHASE_ONLY in rejection_reasons
            )

            if is_contextually_relevant and (action_failed or phase_failed):
                # Valid as CONTEXT, but strictly rejected as DIRECT!
                evidence_class = EvidenceClass.CONTEXT
                is_valid = False  # Not valid as direct proof
                primary_reason = rejection_reasons[0] if rejection_reasons else EvidenceRejectionReason.ACTION_MISMATCH
                explanation = f"CONTEXTUAL ONLY (Action Mismatch): Footage depicts character/scene ({observed.subject} at {observed.context}), but does NOT demonstrate required action '{prop_dict.get('action')}'. Cannot serve as direct proof."
            else:
                # Complete rejection / Fail-closed (Section 10)
                evidence_class = EvidenceClass.NO_VALID_VISUAL
                is_valid = False
                primary_reason = rejection_reasons[0] if rejection_reasons else EvidenceRejectionReason.DIRECT_EVIDENCE_INSUFFICIENT
                explanation = f"NO_VALID_VISUAL: {'; '.join(vetoes) if vetoes else 'Footage lacks reliable evidence for proposition.'}"

        return EvidenceValidationResult(
            candidate_id=cand_id,
            asset_id=asset_id,
            proposition_id=prop_id,
            evidence_class=evidence_class,
            is_valid=is_valid,
            rejection_reasons=rejection_reasons,
            primary_rejection_reason=primary_reason,
            rejection_explanation=explanation,
            expected_proposition=prop_dict,
            observed_proposition=observed,
            scores=scores,
            source_interval=(c_start, c_end),
            validated_interval=micro_interval,
            validated_duration=validated_dur,
            temporal_state=observed.temporal_state,
            framing=self.config.default_framing,
            audit_metadata={
                "vetoes": vetoes,
                "passed_gates": passed_gates,
            }
        )

    # --------------------------------------------------------------------------
    # INTERNAL CHECK ROUTINES
    # --------------------------------------------------------------------------

    def _check_subject(
        self,
        expected_subject: Optional[str],
        observed: ObservedProposition,
    ) -> Tuple[float, bool, str]:
        if not expected_subject or expected_subject.strip().lower() in ("none", "", "ambient", "environment"):
            return 1.0, True, ""

        exp_clean = expected_subject.strip().lower()
        norm_exp = BeastEntityVerifiers._normalize_name(exp_clean)

        # Match against observed subject
        if observed.subject:
            norm_obs = BeastEntityVerifiers._normalize_name(observed.subject)
            if norm_exp == norm_obs:
                return 1.0, True, ""

        # Match against all detected subjects
        for s in observed.detected_subjects:
            if norm_exp == BeastEntityVerifiers._normalize_name(s):
                return 1.0, True, ""

        # Check aliases
        for canonical, aliases in CHARACTER_ALIASES.items():
            if norm_exp == canonical:
                if any(a in " ".join(observed.detected_subjects) for a in aliases):
                    return 1.0, True, ""

        return 0.0, False, f"Subject Mismatch: Expected '{expected_subject}' but observed subjects are '{observed.detected_subjects or 'None'}'"

    def _check_action(
        self,
        expected_action: Optional[str],
        observed: ObservedProposition,
        candidate_desc: str = "",
    ) -> Tuple[float, bool, str]:
        """
        ACTION IS THE PRIMARY VETO.
        """
        if not expected_action or expected_action.strip().lower() in ("none", "", "ambient", "establishing", "presence"):
            return 1.0, True, ""

        exp_act = expected_action.strip().lower()
        obs_act = (observed.action or "").strip().lower()

        # Classify required category
        req_cat = BeastV2ActionVerifier.classify_action(exp_act)
        cand_cat = BeastV2ActionVerifier.classify_action(f"{obs_act} {' '.join(observed.detected_actions)} {candidate_desc}")

        # Check explicit incompatibility matrix (e.g. DESTROY vs HOLD, CRY vs LAUGH, PLEAD vs FIGHT/ATTACK)
        for inc_req, inc_cand, reason in ACTION_INCOMPATIBILITIES:
            if req_cat == inc_req and cand_cat == inc_cand:
                return 0.0, False, f"Action Contradiction Veto: {reason}"

        # Exact category match
        if req_cat == cand_cat and req_cat != ActionCategory.OTHER:
            return 1.0, True, ""

        # Check action clusters (e.g. pleading in {"plead", "beg", "implore"})
        for cluster_name, keywords in ACTION_CLUSTERS.items():
            exp_in_cluster = any(kw in exp_act for kw in keywords)
            obs_in_cluster = any(kw in obs_act for kw in keywords) or any(any(kw in da for kw in keywords) for da in observed.detected_actions)
            if exp_in_cluster and obs_in_cluster:
                return 1.0, True, ""
            if exp_in_cluster and not obs_in_cluster and observed.detected_actions:
                # Specific mismatch within cluster (e.g. expected pleading, but observed sitting)
                return 0.20, False, f"Action Mismatch: Narration requires '{expected_action}' ({cluster_name}), but observed action is '{obs_act or observed.detected_actions}'"

        # Direct token overlap check
        exp_tokens = set(re.findall(r"\w+", exp_act)) - {"a", "an", "the", "in", "on", "at", "to", "for", "with", "from"}
        obs_tokens = set(re.findall(r"\w+", obs_act + " " + " ".join(observed.detected_actions))) - {"a", "an", "the", "in", "on", "at", "to", "for", "with", "from"}

        if exp_tokens and obs_tokens:
            overlap = exp_tokens.intersection(obs_tokens)
            if len(overlap) / len(exp_tokens) >= 0.5:
                return 0.85, True, ""

        return 0.15, False, f"Action Mismatch: Expected action '{expected_action}' was not depicted (observed: '{obs_act or 'static/none'}')"

    def _check_object(
        self,
        expected_object: Optional[str],
        observed: ObservedProposition,
    ) -> Tuple[float, bool, str]:
        if not expected_object or expected_object.strip().lower() in ("none", "", "environment"):
            return 1.0, True, ""

        exp_obj = expected_object.strip().lower()

        # Check observed object
        if observed.object and (exp_obj in observed.object.lower() or observed.object.lower() in exp_obj):
            return 1.0, True, ""

        # Check detected objects
        for obj in observed.detected_objects:
            if exp_obj in obj.lower() or obj.lower() in exp_obj:
                return 1.0, True, ""

        # Check canonical object aliases
        for canonical, aliases in OBJECT_ALIASES.items():
            if exp_obj == canonical or any(a in exp_obj for a in aliases):
                if any(any(a in o.lower() for a in aliases) for o in observed.detected_objects):
                    return 1.0, True, ""

        return 0.0, False, f"Object Missing: Required object '{expected_object}' is not visible in candidate footage"

    def _check_context(
        self,
        expected_context: Optional[str],
        observed: ObservedProposition,
    ) -> Tuple[float, bool, str]:
        if not expected_context or expected_context.strip().lower() in ("none", ""):
            return 1.0, True, ""

        exp_ctx = expected_context.strip().lower()
        obs_ctx = (observed.context or "").strip().lower()

        if exp_ctx in obs_ctx or obs_ctx in exp_ctx:
            return 1.0, True, ""

        for c in observed.detected_contexts:
            if exp_ctx in c.lower() or c.lower() in exp_ctx:
                return 1.0, True, ""

        # If context is explicitly contradictory (e.g. Great Hall vs common room)
        conflicting_rooms = {"great hall", "common room", "dungeons", "corridor", "forbidden forest", "courtyard"}
        if exp_ctx in conflicting_rooms and obs_ctx in conflicting_rooms and exp_ctx != obs_ctx:
            return 0.0, False, f"Context Mismatch: Expected '{expected_context}' but candidate is in '{observed.context}'"

        return 0.50, True, ""

    def _normalize_proposition(self, prop: Any) -> Dict[str, Any]:
        if isinstance(prop, dict):
            return dict(prop)
        return {
            "proposition_id": getattr(prop, "proposition_id", "prop_01"),
            "subject": getattr(prop, "subject", getattr(prop, "primary_subject", None)),
            "action": getattr(prop, "action", getattr(prop, "required_action", None)),
            "object": getattr(prop, "object", None) or (getattr(prop, "required_objects", [None])[0] if getattr(prop, "required_objects", None) else None),
            "context": getattr(prop, "context", getattr(prop, "required_location", None)),
            "required_temporal_state": getattr(prop, "required_temporal_state", "DURING"),
            "evidence_type": getattr(prop, "evidence_type", getattr(prop, "visual_role", "DIRECT")),
        }

    def _normalize_candidate(self, cand: Any) -> Dict[str, Any]:
        if isinstance(cand, dict):
            return dict(cand)
        return {
            "candidate_id": getattr(cand, "shot_id", getattr(cand, "candidate_id", "shot_01")),
            "asset_id": getattr(cand, "shot_id", getattr(cand, "asset_id", "shot_01")),
            "source_video": getattr(cand, "source_video", getattr(cand, "asset_id", "video.mp4")),
            "start_seconds": getattr(cand, "start_seconds", getattr(cand, "source_start", 0.0)),
            "end_seconds": getattr(cand, "end_seconds", getattr(cand, "source_end", 2.0)),
            "characters_present": getattr(cand, "characters_present", []),
            "actions_depicted": getattr(cand, "actions_depicted", []),
            "objects_present": getattr(cand, "objects_present", []),
            "environment": getattr(cand, "environment", None),
            "scene_description": getattr(cand, "scene_description", ""),
            "metadata": getattr(cand, "metadata", {}),
            "media_type": getattr(cand, "media_type", "video"),
        }
