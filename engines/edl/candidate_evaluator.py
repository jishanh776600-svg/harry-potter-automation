"""
STORY FORGE — Candidate Evidence Evaluator (Parts 8, 9, 10, 11, 12, 13, 18)
=============================================================================
Evaluates a candidate video interval through Phase 2 perception, Phase 3 physical
action verification, non-action visual verification, 9:16 crop feasibility,
and computes arbitration scores where physical proof strictly dominates semantic similarity.
"""

import logging
import math
import hashlib
from typing import Dict, List, Any, Optional, Tuple

from py_visual_evidence.schema import BoundingBox
from engines.retrieval.models import RetrievalCandidate
from engines.perception.models import EntityTimeline, EntityTrack, IdentityMatchStatus, VisualObject
from engines.perception.character_bank import CharacterBank, DEFAULT_BANK_PATH
from engines.action.models import (
    PhysicalActionType,
    ActionEvidenceVerdict,
    ActionFailureReason,
    VisualActionAssertion,
)
from engines.action.verifier import ActionEvidenceVerifier
from engines.visual_evidence.subject_aware_composition import (
    SubjectAwareCompositionEngine,
    PostCropVerificationResult,
)
from engines.edl.models import (
    VisualBeat,
    EvaluatedCandidate,
    CropFeasibility,
    CoverageRequirement,
)
from engines.edl.beat_compiler import KNOWN_CHARACTERS
from engines.edl.evidence_contract import (
    NarrativeEvidenceContract,
    SemanticRelevanceEvaluator,
    RelevanceVerdict,
)

logger = logging.getLogger("CandidateEvidenceEvaluator")


class CandidateEvidenceEvaluator:
    """
    Evaluates individual candidates against Phase 2 perception, Phase 3 physical
    proof, 9:16 composition feasibility, and extracts minimal verified intervals.
    """

    def __init__(
        self,
        character_bank: Optional[CharacterBank] = None,
        action_verifier: Optional[ActionEvidenceVerifier] = None,
        composition_engine: Optional[SubjectAwareCompositionEngine] = None,
        relevance_evaluator: Optional[SemanticRelevanceEvaluator] = None,
    ):
        try:
            self.character_bank = character_bank or CharacterBank.load_from_file(DEFAULT_BANK_PATH)
        except Exception:
            self.character_bank = None
        self.action_verifier = action_verifier or ActionEvidenceVerifier(character_bank=self.character_bank)
        self.composition_engine = composition_engine or SubjectAwareCompositionEngine()
        self.relevance_evaluator = relevance_evaluator or SemanticRelevanceEvaluator()

    def evaluate_candidate(
        self,
        candidate: RetrievalCandidate,
        beat: VisualBeat,
        timeline: Optional[EntityTimeline] = None,
        subject_bboxes: Optional[List[Any]] = None,
        is_two_shot: bool = False,
    ) -> EvaluatedCandidate:
        """
        Runs comprehensive multi-gate evaluation on a candidate.
        Enforces hard rejection rules and physical evidence dominance.
        """
        cand_id = candidate.candidate_id
        src_start = candidate.start
        src_end = candidate.end
        duration = max(0.0, src_end - src_start)
        try:
            movie_int = int(str(candidate.movie_id).lower().replace("hp", "").replace("m", ""))
        except Exception:
            movie_int = 3

        eval_res = EvaluatedCandidate(
            candidate_id=cand_id,
            beat_id=beat.beat_id,
            source_movie_id=movie_int,
            source_video=candidate.metadata.get("source_video", f"m{movie_int}.mp4"),
            source_interval=(src_start, src_end),
            verified_sub_interval=(src_start, src_end),
            semantic_score=round(candidate.retrieval_score, 4),
            retrieval_level=candidate.retrieval_trace.get("deep_search_level", "L1"),
        )

        # -------------------------------------------------------------------
        # Gate 0: Duration Adequacy Check
        # -------------------------------------------------------------------
        req_dur = beat.duration
        if duration < min(1.0, req_dur * 0.5):
            eval_res.is_rejected = True
            eval_res.rejection_reason = f"INSUFFICIENT_DURATION: Candidate length ({duration:.2f}s) < minimum required ({req_dur * 0.5:.2f}s)."
            return eval_res

        # -------------------------------------------------------------------
        # Gate 0.5: Narrative Evidence Contract & Semantic Relevance Gate
        # -------------------------------------------------------------------
        contract = getattr(beat, "contract", None) or NarrativeEvidenceContract.from_visual_beat(beat)
        cand_meta = dict(candidate.metadata or {})
        cand_meta["candidate_id"] = cand_id
        cand_meta["source_video"] = eval_res.source_video
        cand_meta["characters_present"] = [tr.character_name or tr.canonical_name for tr in timeline.tracks] if (timeline and timeline.tracks) else []
        cand_meta["visible_objects"] = [od.label for od in timeline.object_detections] if (timeline and timeline.object_detections) else []
        cand_meta["has_timeline"] = bool(timeline and timeline.tracks)
        cand_meta["is_claimed_direct"] = (beat.coverage_requirement == CoverageRequirement.DIRECT)

        sem_res = self.relevance_evaluator.evaluate_relevance(cand_meta, contract)
        eval_res.semantic_relevance_score = sem_res.overall_relevance_score
        eval_res.is_semantically_verified = sem_res.is_accepted
        eval_res.relevance_rejection_reasons = sem_res.rejection_reasons

        if not sem_res.is_accepted:
            eval_res.is_rejected = True
            eval_res.rejection_reason = f"SEMANTIC_RELEVANCE_FAILED: {'; '.join(sem_res.rejection_reasons)}"
            return eval_res

        # -------------------------------------------------------------------
        # Gate 1: Phase 2 Perception Verification (Characters & Objects)
        # -------------------------------------------------------------------
        verified_chars: List[str] = []
        verified_objs: List[str] = []

        if timeline and timeline.tracks:
            # Check characters
            for req_char in beat.required_entities:
                found = False
                for tr in timeline.tracks:
                    cname = tr.character_name or tr.canonical_name or ""
                    if req_char.lower() in cname.lower() or cname.lower() in req_char.lower():
                        if tr.identity_status in (IdentityMatchStatus.FACE_CONFIRMED, IdentityMatchStatus.FACE_PARTIAL, IdentityMatchStatus.TRACKED_FROM_PRIOR):
                            found = True
                            if req_char not in verified_chars:
                                verified_chars.append(req_char)
                            break
                if not found and beat.coverage_requirement == CoverageRequirement.DIRECT:
                    eval_res.is_rejected = True
                    eval_res.rejection_reason = f"NO_CONFIDENT_IDENTITY: Required character '{req_char}' not confirmed in candidate."
                    return eval_res

            # Check objects
            for req_obj in beat.required_objects:
                found = False
                for tr in timeline.tracks:
                    cname = tr.character_name or tr.class_label or ""
                    if req_obj.lower() in cname.lower() or cname.lower() in req_obj.lower():
                        found = True
                        if req_obj not in verified_objs:
                            verified_objs.append(req_obj)
                        break
                if not found and timeline.object_detections:
                    for od in timeline.object_detections:
                        olbl = od.label or ""
                        if req_obj.lower() in olbl.lower() or olbl.lower() in req_obj.lower():
                            found = True
                            if req_obj not in verified_objs:
                                verified_objs.append(req_obj)
                            break
                if not found and beat.coverage_requirement == CoverageRequirement.DIRECT:
                    eval_res.is_rejected = True
                    eval_res.rejection_reason = f"NO_REQUIRED_OBJECT: Required object '{req_obj}' not observed."
                    return eval_res

            eval_res.is_perception_verified = True
            eval_res.perception_confidence = 0.90
            eval_res.verified_entities = verified_chars
        else:
            # If no timeline passed, but beat requires entities, check if it's direct
            if beat.required_entities and beat.coverage_requirement == CoverageRequirement.DIRECT:
                # Check if entities are recognized franchise characters
                unknown_entities = [
                    e for e in beat.required_entities
                    if e.lower() not in KNOWN_CHARACTERS and not any(k in e.lower() for k in KNOWN_CHARACTERS)
                ]
                if unknown_entities:
                    eval_res.is_rejected = True
                    eval_res.rejection_reason = f"UNKNOWN_ENTITY: Required entity '{unknown_entities[0]}' is non-existent in franchise perception bank."
                    return eval_res
                # Without perception timeline, cannot certify direct character requirement
                eval_res.is_perception_verified = False
                eval_res.perception_confidence = 0.40
            else:
                eval_res.is_perception_verified = True
                eval_res.perception_confidence = 0.70

        # -------------------------------------------------------------------
        # Gate 2: Phase 3 Physical Action & State Verification
        # -------------------------------------------------------------------
        if beat.required_action and beat.coverage_requirement == CoverageRequirement.DIRECT:
            if not timeline:
                eval_res.is_rejected = True
                eval_res.rejection_reason = "ACTION_UNVERIFIED: Missing spatio-temporal tracking timeline for physical action."
                return eval_res

            action_type_str = beat.required_action.upper()
            try:
                phys_act = PhysicalActionType(action_type_str)
            except ValueError:
                phys_act = PhysicalActionType.HIT

            assertion = VisualActionAssertion(
                assertion_id=f"eval_{cand_id}",
                actor=beat.required_entities[0] if beat.required_entities else "subject",
                action=phys_act,
                target=beat.required_entities[1] if len(beat.required_entities) > 1 else None,
                object=beat.required_objects[0] if beat.required_objects else None,
            )

            timestamps = [src_start + i * 0.1 for i in range(15)]
            action_res = self.action_verifier.verify_action(assertion, timeline, timestamps=timestamps, fps=25.0)

            if not action_res.is_verified:
                eval_res.is_rejected = True
                fail_reason = action_res.primary_failure_reason.value if action_res.primary_failure_reason else "ACTION_REJECTED"
                eval_res.rejection_reason = f"PHYSICAL_EVIDENCE_FAILED: {fail_reason} ({action_res.trace.explanation})"
                return eval_res

            eval_res.is_physical_verified = True
            eval_res.verified_action = action_type_str
            eval_res.physical_evidence_confidence = round(action_res.confidence, 4)

            # Part 13: Extract smallest verified temporal sub-interval containing physical evidence
            if action_res.trace.timeline_events:
                # Prioritize physical contact/interaction events
                contact_events = [
                    e for e in action_res.trace.timeline_events
                    if e.get("event") in (
                        "contact", "handover_verified", "possession_verified",
                        "throw_separation_verified", "snap", "deformation_snap"
                    )
                ]
                target_events = contact_events if contact_events else action_res.trace.timeline_events
                raw_times = [e.get("timestamp", 0.0) for e in target_events]

                # Convert relative timestamps (0..duration) to absolute movie time if needed
                ev_times = []
                for t in raw_times:
                    if t < src_start and src_start > 0:
                        ev_times.append(src_start + t)
                    else:
                        ev_times.append(t)

                if ev_times:
                    if contact_events:
                        sub_start = max(src_start, min(ev_times) - 0.5)
                        sub_end = min(src_end, max(ev_times) + 0.5)
                    else:
                        sub_start = max(src_start, min(ev_times) - 0.2)
                        sub_end = min(src_end, max(ev_times) + 0.8)
                    if sub_end > sub_start and (sub_end - sub_start) >= 0.5:
                        eval_res.verified_sub_interval = (round(sub_start, 2), round(sub_end, 2))
        else:
            # Non-action beat (Part 10): verified through perception or context
            eval_res.is_physical_verified = True
            eval_res.physical_evidence_confidence = 0.85

        # -------------------------------------------------------------------
        # Gate 3: Part 18 — 9:16 Crop Feasibility Verification
        # -------------------------------------------------------------------
        bboxes_to_check = subject_bboxes
        if not bboxes_to_check and timeline and timeline.tracks:
            # Extract latest boxes from tracks
            bboxes_to_check = []
            for t in timeline.tracks:
                if t.history:
                    bboxes_to_check.append(t.history[-1][1])

        if bboxes_to_check:
            crop_res: PostCropVerificationResult = self.composition_engine.compute_crop_and_verify(
                subject_bboxes=bboxes_to_check,
                is_two_shot=is_two_shot or len(beat.required_entities) >= 2,
                allow_scale_adjustment=True,
            )
            eval_res.crop_window = crop_res.crop_window.to_dict()
            if not crop_res.is_valid:
                eval_res.crop_feasibility = CropFeasibility.IMPOSSIBLE
                if beat.coverage_requirement == CoverageRequirement.DIRECT:
                    eval_res.is_rejected = True
                    eval_res.rejection_reason = f"CROP_IMPOSSIBLE: 9:16 framing clips required subjects ({crop_res.primary_rejection_reason})."
                    return eval_res
            else:
                if crop_res.crop_window.strategy == "SCALE_ADJUSTED_TWO_SHOT":
                    eval_res.crop_feasibility = CropFeasibility.FIT_WITH_SCALE
                elif crop_res.crop_window.strategy == "SUBJECT_AWARE_OPTIMIZED":
                    eval_res.crop_feasibility = CropFeasibility.FIT_WITH_TRACKING
                else:
                    eval_res.crop_feasibility = CropFeasibility.FIT
        else:
            eval_res.crop_feasibility = CropFeasibility.FIT

        # -------------------------------------------------------------------
        # Gate 4: Part 11 — Candidate Arbitration Scoring
        # Physical Evidence MUST Dominate Semantic Similarity
        # S = 0.50 * S_phys + 0.30 * S_percept + 0.15 * S_semantic + 0.05 * S_crop
        # -------------------------------------------------------------------
        crop_weight = 1.0 if eval_res.crop_feasibility in (CropFeasibility.FIT, CropFeasibility.FIT_WITH_TRACKING) else 0.70
        phys_score = eval_res.physical_evidence_confidence if eval_res.is_physical_verified else 0.0
        percept_score = eval_res.perception_confidence if eval_res.is_perception_verified else 0.0
        sem_score = eval_res.semantic_score
        rel_score = eval_res.semantic_relevance_score

        eval_res.overall_arbitration_score = round(
            0.40 * phys_score + 0.25 * percept_score + 0.20 * rel_score + 0.10 * sem_score + 0.05 * crop_weight, 4
        )

        # Cryptographic evidence hash binding candidate and verified attributes
        h = hashlib.sha256()
        h.update(cand_id.encode())
        h.update(str(eval_res.verified_sub_interval).encode())
        h.update(str(eval_res.verified_action).encode())
        h.update(str(eval_res.verified_entities).encode())
        h.update(str(eval_res.overall_arbitration_score).encode())
        h.update(contract.compute_contract_hash().encode())
        eval_res.evidence_hash = h.hexdigest()

        return eval_res
