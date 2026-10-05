"""
Master Video Evidence Engine (Orchestrator)
Orchestrates:
Tier 0 (Shot Boundary & Sub-Shot Decomposition)
-> Tier 1 (Sparse Keyframe Grounding)
-> Tier 2 (Optimized Spatio-Temporal Tracking)
-> Tier 3 (Adaptive Multi-Signal Action & State Transition Analysis)
-> Tier 4 (Spatial Relationship Verification)
-> Tier 5 (Aspect-Ratio-Aware Composition Validation)
"""

from __future__ import annotations
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import cv2
import numpy as np

from py_visual_evidence.schema import (
    VisualAssertion,
    ObservationEvidence,
    EvidenceVerdict,
    EntitySpec,
    GroundedEntity,
    EntityTrajectory,
    ActionResult,
    StateTransitionResult,
    CropVerificationResult,
)
from py_visual_evidence.video_reader import VideoClip
from py_visual_evidence.shot_detector import ShotBoundaryDetector
from py_visual_evidence.grounding import BaseEntityGrounder, DeterministicBenchmarkGrounder
from py_visual_evidence.tracking import FastSpatioTemporalTracker
from py_visual_evidence.action_analyzers.handover import HandoverActionAnalyzer
from py_visual_evidence.action_analyzers.motion import KinematicMotionAnalyzer
from py_visual_evidence.action_analyzers.state_transition import StructuralStateTransitionAnalyzer
from py_visual_evidence.action_analyzers.generic_transition import GenericStateTransitionAnalyzer
from py_visual_evidence.relationship import RelationshipVerifier
from py_visual_evidence.crop_validator import VerticalCropValidator
from py_visual_evidence.ambiguity_resolver import OptionalAmbiguityResolver, DisabledAmbiguityResolver


class VideoEvidenceEngine:
    def __init__(
        self,
        grounder: Optional[BaseEntityGrounder] = None,
        shot_detector: Optional[ShotBoundaryDetector] = None,
        tracker: Optional[FastSpatioTemporalTracker] = None,
        crop_validator: Optional[VerticalCropValidator] = None,
        ambiguity_resolver: Optional[OptionalAmbiguityResolver] = None,
    ):
        self.grounder = grounder or DeterministicBenchmarkGrounder()
        self.shot_detector = shot_detector or ShotBoundaryDetector()
        self.tracker = tracker or FastSpatioTemporalTracker()
        self.crop_validator = crop_validator or VerticalCropValidator()
        self.ambiguity_resolver = ambiguity_resolver or DisabledAmbiguityResolver()

        self.handover_analyzer = HandoverActionAnalyzer()
        self.motion_analyzer = KinematicMotionAnalyzer()
        self.state_analyzer = StructuralStateTransitionAnalyzer()
        self.generic_analyzer = GenericStateTransitionAnalyzer()
        self.relationship_verifier = RelationshipVerifier()

    def inspect_clip(
        self,
        video_path: str | Path,
        assertion: VisualAssertion,
        start_sec: float = 0.0,
        end_sec: Optional[float] = None,
        crop_window: Optional[Dict[str, int]] = None,
    ) -> ObservationEvidence:
        """
        Conducts deep physical inspection of a candidate video clip against a visual assertion.
        Performs sub-shot decomposition across multi-shot candidate intervals, evaluating
        each continuous camera shot independently. Returns PASS if any valid sub-shot
        independently satisfies the visual assertion; otherwise returns a fail-closed verdict.
        """
        video_p = Path(video_path)
        timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Ingestion Probe
        clip_probe = VideoClip(video_p, start_sec=start_sec, end_sec=end_sec)
        effective_range = (clip_probe.start_sec, clip_probe.start_sec + clip_probe.duration)

        # 1. Tier 0: Shot Boundary Analysis Across Candidate Window
        shot_res = self.shot_detector.analyze(
            video_p, start_sec=effective_range[0], end_sec=effective_range[1]
        )

        # Check if assertion explicitly demands an uninterrupted/continuous shot across the window
        is_explicitly_continuous = (
            "uninterrupted" in assertion.source_script_line.lower()
            or "continuous shot" in assertion.source_script_line.lower()
            or (assertion.temporal_requirements and assertion.temporal_requirements.get("require_uninterrupted_shot"))
        )
        if is_explicitly_continuous and shot_res.shot_count > 1 and shot_res.contains_cut_between(
            effective_range[0] + 0.15, effective_range[1] - 0.15
        ):
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_p),
                time_range=effective_range,
                shot_count=shot_res.shot_count,
                parent_candidate_interval=effective_range,
                contains_internal_cut=True,
                verdict=EvidenceVerdict.SHOT_BOUNDARY_CONFLICT,
                rejection_reason=f"Candidate interval crosses {shot_res.shot_count - 1} camera hard cuts; single continuous event cannot be established.",
                timestamp_iso=timestamp_iso,
                metrics=shot_res.to_dict(),
            )

        # If candidate interval is a single continuous shot:
        if shot_res.shot_count <= 1:
            return self._inspect_single_shot(
                video_path=video_p,
                assertion=assertion,
                start_sec=effective_range[0],
                end_sec=effective_range[1],
                crop_window=crop_window,
                parent_candidate_interval=effective_range,
                sub_shot_id="shot_0",
                sub_shot_start=effective_range[0],
                sub_shot_end=effective_range[1],
                sub_shot_index=0,
                contains_internal_cut=False,
                shot_count=1,
            )

        # Multi-shot candidate interval: Sub-Shot Decomposition
        sub_shot_evidences: List[ObservationEvidence] = []
        for i, (s_start, s_end) in enumerate(shot_res.scenes):
            # Check minimum duration for action analysis
            if (s_end - s_start) < 0.20:
                continue

            sub_ev = self._inspect_single_shot(
                video_path=video_p,
                assertion=assertion,
                start_sec=s_start,
                end_sec=s_end,
                crop_window=crop_window,
                parent_candidate_interval=effective_range,
                sub_shot_id=f"shot_{i}",
                sub_shot_start=round(s_start, 3),
                sub_shot_end=round(s_end, 3),
                sub_shot_index=i,
                contains_internal_cut=False,
                shot_count=shot_res.shot_count,
            )

            # If this sub-shot independently satisfies the assertion: WINNING EVIDENCE!
            if sub_ev.verdict == EvidenceVerdict.PASS:
                return sub_ev

            sub_shot_evidences.append(sub_ev)

        # If no single sub-shot satisfied the assertion, return fail-closed verdict
        best_verdict = EvidenceVerdict.SHOT_BOUNDARY_CONFLICT
        best_reason = (
            f"Sub-shot decomposition evaluated {shot_res.shot_count} shots; "
            f"no single continuous sub-shot satisfied assertion '{assertion.assertion_id}'."
        )

        best_ev = None
        for ev in sub_shot_evidences:
            if ev.verdict != EvidenceVerdict.INSUFFICIENT_EVIDENCE:
                best_verdict = ev.verdict
                best_reason = ev.rejection_reason
                best_ev = ev
                break
        if best_ev is None and sub_shot_evidences:
            best_ev = sub_shot_evidences[0]

        return self._build_verdict(
            assertion=assertion,
            video_path=str(video_p),
            time_range=effective_range,
            shot_count=shot_res.shot_count,
            parent_candidate_interval=effective_range,
            sub_shot_id=best_ev.sub_shot_id if best_ev else None,
            sub_shot_start=best_ev.sub_shot_start if best_ev else None,
            sub_shot_end=best_ev.sub_shot_end if best_ev else None,
            sub_shot_index=best_ev.sub_shot_index if best_ev else None,
            contains_internal_cut=True,
            grounded_entities=best_ev.grounded_entities if best_ev else [],
            trajectories=best_ev.trajectories if best_ev else {},
            action_result=best_ev.action_result if best_ev else None,
            state_transition_result=best_ev.state_transition_result if best_ev else None,
            relationship_verified=best_ev.relationship_verified if best_ev else False,
            crop_result=best_ev.crop_result if best_ev else None,
            verdict=best_verdict,
            rejection_reason=best_reason,
            timestamp_iso=timestamp_iso,
            metrics={
                "shot_count": shot_res.shot_count,
                "scenes": shot_res.scenes,
                "sub_shot_verdicts": [e.verdict.value for e in sub_shot_evidences],
            },
        )

    def _inspect_single_shot(
        self,
        video_path: Path,
        assertion: VisualAssertion,
        start_sec: float,
        end_sec: Optional[float],
        crop_window: Optional[Dict[str, int]],
        parent_candidate_interval: Optional[Tuple[float, float]],
        sub_shot_id: str,
        sub_shot_start: float,
        sub_shot_end: float,
        sub_shot_index: int,
        contains_internal_cut: bool,
        shot_count: int,
    ) -> ObservationEvidence:
        """
        Evaluates an internally continuous shot candidate against the visual assertion.
        """
        timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        clip = VideoClip(video_path, start_sec=start_sec, end_sec=end_sec)
        effective_range = (clip.start_sec, clip.start_sec + clip.duration)
        frames = clip.read_all_frames()

        if not frames:
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=contains_internal_cut,
                verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE,
                rejection_reason="No readable video frames found in the specified sub-shot interval.",
                timestamp_iso=timestamp_iso,
            )

        img_h, img_w, _ = frames[0].shape

        # Verify this sub-shot contains no internal hard cut
        internal_shots = self.shot_detector.analyze(
            video_path, start_sec=clip.start_sec, end_sec=clip.start_sec + clip.duration
        )
        if internal_shots.shot_count > 1 and internal_shots.contains_cut_between(
            clip.start_sec + 0.15, clip.start_sec + clip.duration - 0.15
        ):
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=True,
                verdict=EvidenceVerdict.SHOT_BOUNDARY_CONFLICT,
                rejection_reason=f"Sub-shot contains internal camera hard cut; single continuous event cannot be established.",
                timestamp_iso=timestamp_iso,
                metrics=internal_shots.to_dict(),
            )

        # Tier 1: Sparse Keyframe Grounding
        req_specs: List[EntitySpec] = [assertion.subject]
        if assertion.object:
            req_specs.append(assertion.object)
        if assertion.recipient:
            req_specs.append(assertion.recipient)
        for sec_ent in assertion.secondary_entities:
            req_specs.append(sec_ent)

        grounded = self.grounder.ground_entities(
            frame=frames[0],
            entity_specs=req_specs,
            timestamp_sec=clip.start_sec,
            frame_index=0,
        )

        grounded_names = {g.entity_name for g in grounded}

        # Check required subject
        if assertion.subject.name not in grounded_names:
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=contains_internal_cut,
                grounded_entities=grounded,
                verdict=EvidenceVerdict.NO_REQUIRED_ENTITY,
                rejection_reason=f"Required subject '{assertion.subject.name}' was not detected in candidate video.",
                timestamp_iso=timestamp_iso,
            )

        # Check required object
        if assertion.object and assertion.object.name not in grounded_names:
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=contains_internal_cut,
                grounded_entities=grounded,
                verdict=EvidenceVerdict.NO_REQUIRED_ENTITY,
                rejection_reason=f"Required object '{assertion.object.name}' was not detected in candidate video.",
                timestamp_iso=timestamp_iso,
            )

        # Check required recipient
        if assertion.recipient and assertion.recipient.name not in grounded_names:
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=contains_internal_cut,
                grounded_entities=grounded,
                verdict=EvidenceVerdict.NO_REQUIRED_ENTITY,
                rejection_reason=f"Required recipient '{assertion.recipient.name}' was not detected in candidate video.",
                timestamp_iso=timestamp_iso,
            )

        # Tier 2: Optimized Spatio-Temporal Tracking
        trajectories = self.tracker.track_entities(
            frames=frames,
            initial_entities=grounded,
            fps=clip.fps,
            start_sec=clip.start_sec,
        )

        # Tier 3: Action & Physical State Transition Analysis
        action_name = assertion.action.lower()
        action_result: Optional[ActionResult] = None
        state_result: Optional[StateTransitionResult] = None

        if "hand" in action_name or "give" in action_name or "transfer" in action_name:
            action_result = self.handover_analyzer.analyze_action(frames, trajectories, assertion, fps=clip.fps)
        elif "wave" in action_name or "swing" in action_name or "sweep" in action_name or "gesture" in action_name or "punch" in action_name or "strike" in action_name:
            action_result = self.motion_analyzer.analyze_action(frames, trajectories, assertion, fps=clip.fps)
        elif assertion.expected_state_transition and "shatter" in assertion.expected_state_transition.final_state.lower():
            state_result = self.state_analyzer.evaluate_state_transition(frames, trajectories, assertion)
            action_result = self.state_analyzer.analyze_action(frames, trajectories, assertion, fps=clip.fps)
        elif assertion.expected_state_transition:
            action_result = self.generic_analyzer.analyze_action(frames, trajectories, assertion, fps=clip.fps)
        else:
            # General motion fallback
            action_result = self.motion_analyzer.analyze_action(frames, trajectories, assertion, fps=clip.fps)

        # Check action verdict
        if action_result and not action_result.detected:
            if assertion.expected_state_transition:
                return self._build_verdict(
                    assertion=assertion,
                    video_path=str(video_path),
                    time_range=effective_range,
                    shot_count=shot_count,
                    parent_candidate_interval=parent_candidate_interval,
                    sub_shot_id=sub_shot_id,
                    sub_shot_start=sub_shot_start,
                    sub_shot_end=sub_shot_end,
                    sub_shot_index=sub_shot_index,
                    contains_internal_cut=contains_internal_cut,
                    grounded_entities=grounded,
                    trajectories=trajectories,
                    action_result=action_result,
                    state_transition_result=state_result,
                    verdict=EvidenceVerdict.STATE_TRANSITION_ABSENT,
                    rejection_reason=f"STATE_TRANSITION_ABSENT: Expected state transition '{assertion.expected_state_transition.initial_state} -> {assertion.expected_state_transition.final_state}' did not occur.",
                    timestamp_iso=timestamp_iso,
                )
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=contains_internal_cut,
                grounded_entities=grounded,
                trajectories=trajectories,
                action_result=action_result,
                state_transition_result=state_result,
                verdict=EvidenceVerdict.ACTION_ABSENT,
                rejection_reason=f"ACTION_ABSENT: Required action '{assertion.action}' was not physically observed in the clip.",
                timestamp_iso=timestamp_iso,
            )

        # Check state transition verdict if required
        if assertion.expected_state_transition and state_result and not state_result.detected:
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=contains_internal_cut,
                grounded_entities=grounded,
                trajectories=trajectories,
                action_result=action_result,
                state_transition_result=state_result,
                verdict=EvidenceVerdict.STATE_TRANSITION_ABSENT,
                rejection_reason=f"STATE_TRANSITION_ABSENT: Disruption ratio {state_result.disruption_ratio:.2f} < threshold {assertion.expected_state_transition.min_disruption_threshold:.2f}",
                timestamp_iso=timestamp_iso,
            )

        # Tier 4: Spatial Relationship Verification
        rel_verified, rel_summary, rel_details = self.relationship_verifier.verify_relationship(
            assertion=assertion,
            trajectories=trajectories,
        )

        if not rel_verified:
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=contains_internal_cut,
                grounded_entities=grounded,
                trajectories=trajectories,
                action_result=action_result,
                state_transition_result=state_result,
                relationship_verified=False,
                relationship_summary=rel_summary,
                verdict=EvidenceVerdict.RELATIONSHIP_ABSENT,
                rejection_reason=f"RELATIONSHIP_ABSENT: {rel_summary}",
                timestamp_iso=timestamp_iso,
                metrics=rel_details,
            )

        # Tier 5: Aspect-Ratio-Aware Post-Crop Validation
        req_crop_names = [assertion.subject.name]
        if assertion.object:
            req_crop_names.append(assertion.object.name)
        if assertion.recipient:
            req_crop_names.append(assertion.recipient.name)

        crop_res = self.crop_validator.validate_crop(
            trajectories=trajectories,
            crop_window=crop_window,
            crop_spec=assertion.crop_spec,
            required_entity_names=req_crop_names,
            src_w=img_w,
            src_h=img_h,
        )

        if not crop_res.passed:
            return self._build_verdict(
                assertion=assertion,
                video_path=str(video_path),
                time_range=effective_range,
                shot_count=shot_count,
                parent_candidate_interval=parent_candidate_interval,
                sub_shot_id=sub_shot_id,
                sub_shot_start=sub_shot_start,
                sub_shot_end=sub_shot_end,
                sub_shot_index=sub_shot_index,
                contains_internal_cut=contains_internal_cut,
                grounded_entities=grounded,
                trajectories=trajectories,
                action_result=action_result,
                state_transition_result=state_result,
                relationship_verified=True,
                relationship_summary=rel_summary,
                crop_result=crop_res,
                verdict=EvidenceVerdict.CROP_SUBJECT_LOST,
                rejection_reason=crop_res.rejection_reason,
                timestamp_iso=timestamp_iso,
            )

        # All Tiers Passed -> Emit PASS Verdict
        overall_conf = round(
            min(
                0.98,
                (action_result.confidence if action_result else 0.85) * 0.50
                + (crop_res.retained_subject_ratio * 0.30)
                + 0.20,
            ),
            3,
        )

        return self._build_verdict(
            assertion=assertion,
            video_path=str(video_path),
            time_range=effective_range,
            shot_count=shot_count,
            parent_candidate_interval=parent_candidate_interval,
            sub_shot_id=sub_shot_id,
            sub_shot_start=sub_shot_start,
            sub_shot_end=sub_shot_end,
            sub_shot_index=sub_shot_index,
            contains_internal_cut=contains_internal_cut,
            grounded_entities=grounded,
            trajectories=trajectories,
            action_result=action_result,
            state_transition_result=state_result,
            relationship_verified=True,
            relationship_summary=rel_summary,
            crop_result=crop_res,
            verdict=EvidenceVerdict.PASS,
            rejection_reason=None,
            confidence=overall_conf,
            timestamp_iso=timestamp_iso,
        )

    def _build_verdict(
        self,
        assertion: VisualAssertion,
        video_path: str,
        time_range: Tuple[float, float],
        shot_count: int,
        verdict: EvidenceVerdict,
        rejection_reason: Optional[str] = None,
        parent_candidate_interval: Optional[Tuple[float, float]] = None,
        sub_shot_id: Optional[str] = None,
        sub_shot_start: Optional[float] = None,
        sub_shot_end: Optional[float] = None,
        sub_shot_index: Optional[int] = None,
        contains_internal_cut: bool = False,
        grounded_entities: Optional[List[GroundedEntity]] = None,
        trajectories: Optional[Dict[str, EntityTrajectory]] = None,
        action_result: Optional[ActionResult] = None,
        state_transition_result: Optional[StateTransitionResult] = None,
        relationship_verified: bool = False,
        relationship_summary: str = "",
        crop_result: Optional[CropVerificationResult] = None,
        confidence: float = 0.0,
        metrics: Optional[Dict[str, Any]] = None,
        timestamp_iso: str = "",
    ) -> ObservationEvidence:
        return ObservationEvidence(
            assertion_id=assertion.assertion_id,
            video_path=video_path,
            time_range=time_range,
            shot_count=shot_count,
            parent_candidate_interval=parent_candidate_interval,
            sub_shot_id=sub_shot_id,
            sub_shot_start=sub_shot_start,
            sub_shot_end=sub_shot_end,
            sub_shot_index=sub_shot_index,
            contains_internal_cut=contains_internal_cut,
            grounded_entities=grounded_entities or [],
            trajectories=trajectories or {},
            action_result=action_result,
            state_transition_result=state_transition_result,
            relationship_verified=relationship_verified,
            relationship_summary=relationship_summary,
            causal_order_passed=True,
            crop_result=crop_result,
            verdict=verdict,
            rejection_reason=rejection_reason,
            confidence=confidence,
            metrics=metrics or {},
            timestamp_iso=timestamp_iso,
        )
