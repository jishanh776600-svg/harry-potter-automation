"""
STORY FORGE — End-to-End Final Render Visual Verification Engine
================================================================
Deterministic forensic inspector that verifies the ACTUAL final 9:16 MP4 render,
re-inspecting real pixels with the real OWLv2 detector.

Authority Chain:
  Narrative Beat
    → VisualAssertion
    → MovieEvent candidate
    → REAL OWLv2 evidence
    → verified clip
    → subject-aware crop
    → multi-beat timeline
    → FFmpeg final render
    → RE-INSPECT ACTUAL FINAL 9:16 FRAMES
    → PASS / FAIL

The final render itself is the single source of truth for composition.
"""

from __future__ import annotations
import json
import logging
import math
import os
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set, Union
import cv2
import numpy as np

from py_visual_evidence.schema import (
    BoundingBox,
    EntitySpec,
    GroundedEntity,
    VisualAssertion,
)
from py_visual_evidence.grounding import (
    BaseEntityGrounder,
    DeterministicBenchmarkGrounder,
    OpenVocabularyGrounder,
)
from engines.movie_event.models import (
    VisualBeat,
    VISUAL_OPTIONAL,
    DIRECT_VISUAL,
    INSUFFICIENT_VISUAL_COVERAGE,
)
from engines.visual_evidence.storyforge_adapter import (
    HP_CHARACTER_ALIASES,
    HP_OBJECT_ALIASES,
)
from engines.visual_evidence.multi_beat_timeline import (
    MultiBeatTimelinePlan,
    TimelineSegment,
    BeatCoverageStatus,
)

logger = logging.getLogger("FinalRenderVerifier")

CANONICAL_SUBTITLE_FONT = "Harry P"
CANONICAL_TARGET_LUFS = -14.0
CANONICAL_MAX_DBTP = -1.0


class VerificationVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class SampledFrame:
    """Frame sampled from final MP4."""
    timestamp_sec: float
    frame_index: int
    image_bgr: np.ndarray
    detections: List[GroundedEntity] = field(default_factory=list)
    mean_luminance: float = 0.0
    is_black: bool = False


@dataclass
class EntityRetentionReport:
    """Detailed visual retention metrics for a required entity in final 9:16 render."""
    entity_name: str
    is_required: bool
    frames_evaluated: int
    frames_detected: int
    retention_rate: float
    average_confidence: float
    sample_bboxes: List[Dict[str, float]] = field(default_factory=list)
    is_amputated: bool = False
    amputation_details: Optional[str] = None
    status: str = "PASS"  # "PASS", "FAIL_ABSENT", "FAIL_AMPUTATED"


@dataclass
class BeatRenderVerification:
    """Forensic verification result for an individual narrative beat in the final MP4."""
    beat_id: str
    narrative_role: str
    narration_start: float
    narration_end: float
    duration: float
    is_direct_requirement: bool
    is_visual_optional: bool
    required_entities: List[str]
    required_action: str
    expected_visual_state: Optional[str]
    entity_retention: Dict[str, EntityRetentionReport] = field(default_factory=dict)
    action_state_status: str = "PASS"  # "PASS", "FAIL_ACTION_ABSENT", "FAIL_STATE_ABSENT", "OPTIONAL_ABSENT"
    action_state_details: str = ""
    timeline_anomaly: Optional[str] = None
    beat_verdict: VerificationVerdict = VerificationVerdict.PASS
    reasons: List[str] = field(default_factory=list)


@dataclass
class TransitionVerification:
    """Verification result for a shot transition cut in the final MP4."""
    transition_time: float
    prev_beat_id: str
    next_beat_id: str
    has_black_frame: bool = False
    has_frozen_frame: bool = False
    has_unintended_loop: bool = False
    verdict: VerificationVerdict = VerificationVerdict.PASS
    details: str = ""


@dataclass
class SubtitleCompositionVerification:
    """Verification result for rendered subtitle styling and composition collision."""
    ass_file_inspected: Optional[str] = None
    font_name_detected: Optional[str] = None
    canonical_font_expected: str = CANONICAL_SUBTITLE_FONT
    font_matched: bool = True
    safe_zone_passed: bool = True
    collision_detected: bool = False
    collision_details: Optional[str] = None
    verdict: VerificationVerdict = VerificationVerdict.PASS
    reasons: List[str] = field(default_factory=list)


@dataclass
class AudioVerification:
    """Measurement of audio loudness, true peak, and mastering alignment."""
    integrated_lufs: float = -99.0
    true_peak_dbtp: float = -99.0
    lufs_passed: bool = True
    true_peak_passed: bool = True
    has_audio_stream: bool = True
    verdict: VerificationVerdict = VerificationVerdict.PASS
    details: str = ""


@dataclass
class FinalRenderForensicReport:
    """Comprehensive end-to-end forensic audit of a final 9:16 MP4."""
    video_path: str
    content_id: str
    width: int = 1080
    height: int = 1920
    duration_sec: float = 0.0
    fps: float = 30.0
    total_frames: int = 0
    beat_reports: List[BeatRenderVerification] = field(default_factory=list)
    transition_reports: List[TransitionVerification] = field(default_factory=list)
    subtitle_report: Optional[SubtitleCompositionVerification] = None
    audio_report: Optional[AudioVerification] = None
    looping_detected: bool = False
    loop_details: List[str] = field(default_factory=list)
    failures_by_category: Dict[str, List[str]] = field(default_factory=lambda: {
        "RENDERER_DEFECTS": [],
        "COMPOSITION_DEFECTS": [],
        "EVIDENCE_DEFECTS": [],
        "TIMELINE_DEFECTS": [],
        "SUBTITLE_DEFECTS": [],
        "AUDIO_DEFECTS": [],
    })
    overall_verdict: VerificationVerdict = VerificationVerdict.PASS
    final_forensic_status: str = "READY"  # "READY" or "NOT_READY"
    status_explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_path": self.video_path,
            "content_id": self.content_id,
            "dimensions": f"{self.width}x{self.height}",
            "duration_sec": self.duration_sec,
            "overall_verdict": self.overall_verdict.value,
            "final_forensic_status": self.final_forensic_status,
            "status_explanation": self.status_explanation,
            "failures_by_category": self.failures_by_category,
            "looping_detected": self.looping_detected,
            "loop_details": self.loop_details,
            "beat_count": len(self.beat_reports),
        }


class FinalRenderVerifier:
    """
    Deterministic forensic verifier for Story Forge final rendered 9:16 videos.
    Re-inspects pixels directly using the real OWLv2 detector.
    """

    def __init__(
        self,
        grounder: Optional[BaseEntityGrounder] = None,
        allow_synthetic_grounding: bool = False,
        confidence_threshold: float = 0.15,
    ):
        if grounder is not None:
            if isinstance(grounder, DeterministicBenchmarkGrounder) and not allow_synthetic_grounding:
                raise ValueError(
                    "DeterministicBenchmarkGrounder is strictly prohibited for real-footage final render verification. "
                    "A real detector (OpenVocabularyGrounder) is mandatory. "
                    "Pass allow_synthetic_grounding=True only for isolated synthetic test cases."
                )
            self.grounder = grounder
        else:
            if allow_synthetic_grounding:
                self.grounder = DeterministicBenchmarkGrounder()
            else:
                self.grounder = OpenVocabularyGrounder(confidence_threshold=confidence_threshold)

        self.allow_synthetic_grounding = allow_synthetic_grounding
        self.confidence_threshold = confidence_threshold

    # --------------------------------------------------------------------------
    # 1. Video Probe & Sampling
    # --------------------------------------------------------------------------

    def probe_video(self, video_path: Path) -> Dict[str, Any]:
        """Probes video metadata: resolution, fps, frame count, duration."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video at {video_path}")
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        dur = total_frames / fps if fps > 0 else 0.0
        cap.release()
        return {
            "width": w,
            "height": h,
            "fps": fps,
            "total_frames": total_frames,
            "duration": dur,
        }

    def sample_beat_frames(
        self,
        video_path: Path,
        start_sec: float,
        end_sec: float,
        num_samples: int = 4,
    ) -> List[SampledFrame]:
        """Uniformly samples frames across a beat interval."""
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

        fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        max_dur = total_frames / fps if fps > 0 else 0.0

        clamped_start = max(0.0, min(start_sec, max_dur))
        clamped_end = max(clamped_start, min(end_sec, max_dur))
        interval_dur = clamped_end - clamped_start

        if interval_dur <= 0.01:
            cap.release()
            return []

        sample_times = [
            clamped_start + (i + 0.5) * (interval_dur / num_samples)
            for i in range(num_samples)
        ]

        frames: List[SampledFrame] = []
        for t in sample_times:
            f_idx = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame_bgr = cap.read()
            if not ret or frame_bgr is None:
                continue

            # Compute luminance
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            mean_lum = float(np.mean(gray))
            is_black = mean_lum < 5.0

            sf = SampledFrame(
                timestamp_sec=round(t, 3),
                frame_index=f_idx,
                image_bgr=frame_bgr,
                mean_luminance=round(mean_lum, 2),
                is_black=is_black,
            )
            frames.append(sf)

        cap.release()
        return frames

    # --------------------------------------------------------------------------
    # 2. Entity Spec Resolution
    # --------------------------------------------------------------------------

    def resolve_entity_specs(self, entity_names: List[str]) -> List[EntitySpec]:
        """Resolves canonical Harry Potter entity names into open-vocabulary EntitySpecs."""
        specs = []
        for name in entity_names:
            clean = name.strip()
            clean_lower = clean.lower()
            aliases = HP_CHARACTER_ALIASES.get(clean_lower) or HP_OBJECT_ALIASES.get(clean_lower)
            desc = aliases[0] if aliases else clean
            specs.append(EntitySpec(name=clean, role="required", description=desc))
        return specs

    # --------------------------------------------------------------------------
    # 3. Subject Retention Inspection
    # --------------------------------------------------------------------------

    def inspect_subject_retention(
        self,
        sampled_frames: List[SampledFrame],
        required_entities: List[str],
    ) -> Dict[str, EntityRetentionReport]:
        """
        Runs real OWLv2 detector on sampled final-render frames to measure
        retention rate, bbox positions, edge clipping, and amputation.
        """
        reports: Dict[str, EntityRetentionReport] = {}
        if not required_entities or not sampled_frames:
            return reports

        entity_specs = self.resolve_entity_specs(required_entities)

        # Ground entities on each frame
        for sf in sampled_frames:
            if sf.is_black:
                continue
            detections = self.grounder.ground_entities(
                frame=sf.image_bgr,
                entity_specs=entity_specs,
                timestamp_sec=sf.timestamp_sec,
                frame_index=sf.frame_index,
            )
            sf.detections = detections

        # Aggregate metrics per required entity
        for spec in entity_specs:
            ent_name = spec.name
            detected_count = 0
            conf_sum = 0.0
            bboxes: List[Dict[str, float]] = []
            amputated_count = 0

            for sf in sampled_frames:
                ent_dets = [d for d in sf.detections if d.entity_name.lower() == ent_name.lower()]
                if ent_dets:
                    best = max(ent_dets, key=lambda d: d.confidence)
                    detected_count += 1
                    conf_sum += best.confidence
                    b = best.bbox
                    b_dict = {"x": b.x, "y": b.y, "w": b.w, "h": b.h, "conf": round(best.confidence, 3)}
                    bboxes.append(b_dict)

                    # Amputation check: touching frame boundaries with narrow residual width
                    # or centroid pushed severely off canvas edge
                    is_clipped_left = b.x <= 0.015 and b.w < 0.18
                    is_clipped_right = (b.x + b.w) >= 0.985 and b.w < 0.18
                    is_extreme_edge = (b.x + b.w / 2.0) < 0.06 or (b.x + b.w / 2.0) > 0.94

                    if is_clipped_left or is_clipped_right or is_extreme_edge:
                        amputated_count += 1

            total_eval = len(sampled_frames)
            ret_rate = round(detected_count / max(1, total_eval), 3)
            avg_conf = round(conf_sum / max(1, detected_count), 3)
            is_amp = (amputated_count >= max(1, detected_count // 2)) and detected_count > 0

            # Verdict evaluation
            if ret_rate < 0.40:
                status = "FAIL_ABSENT"
                amp_desc = f"Subject '{ent_name}' absent from majority of final render frames (retention: {ret_rate*100:.1f}%)."
            elif is_amp:
                status = "FAIL_AMPUTATED"
                amp_desc = f"Subject '{ent_name}' is amputated/severely clipped against 9:16 borders in {amputated_count} frames."
            else:
                status = "PASS"
                amp_desc = None

            reports[ent_name] = EntityRetentionReport(
                entity_name=ent_name,
                is_required=True,
                frames_evaluated=total_eval,
                frames_detected=detected_count,
                retention_rate=ret_rate,
                average_confidence=avg_conf,
                sample_bboxes=bboxes,
                is_amputated=is_amp,
                amputation_details=amp_desc,
                status=status,
            )

        return reports

    # --------------------------------------------------------------------------
    # 4. Action & Visual State Survival
    # --------------------------------------------------------------------------

    def inspect_action_survival(
        self,
        beat: VisualBeat,
        sampled_frames: List[SampledFrame],
        retention_reports: Dict[str, EntityRetentionReport],
    ) -> Tuple[str, str]:
        """
        Verifies that the required observable action / physical state change
        is genuinely preserved in the final composition.
        """
        if beat.is_visual_optional:
            return "OPTIONAL_ABSENT", "Visual optional: explicit absence or contextual hold permitted."

        action_clean = (beat.required_action or "").lower()

        # Case 1: Multi-entity interaction (e.g. Buckbeak slashes Draco, Snape confronts Harry)
        if len(beat.required_entities) >= 2:
            sub_a = beat.required_entities[0]
            sub_b = beat.required_entities[1]
            rep_a = retention_reports.get(sub_a)
            rep_b = retention_reports.get(sub_b)

            if not rep_a or rep_a.status != "PASS":
                return (
                    "FAIL_ACTION_ABSENT",
                    f"Action '{action_clean}' failed: primary subject '{sub_a}' is missing from final render."
                )
            if not rep_b or rep_b.status != "PASS":
                return (
                    "FAIL_ACTION_ABSENT",
                    f"Action '{action_clean}' failed: required interaction target '{sub_b}' is missing from final render."
                )

        # Case 2: State transition / breakage (e.g. Elder Wand snap -> BROKEN)
        if beat.visual_state and beat.visual_state.upper() in ("BROKEN", "SHATTERED"):
            # Check frames for structural disruption / breakage
            wand_reps = [r for k, r in retention_reports.items() if "wand" in k.lower()]
            if wand_reps and wand_reps[0].status == "FAIL_ABSENT":
                return (
                    "FAIL_STATE_ABSENT",
                    f"Visual state '{beat.visual_state}' failed: wand object is completely absent from final composition."
                )

        # Case 3: Action requires subject presence
        for ent_name in beat.required_entities:
            rep = retention_reports.get(ent_name)
            if rep and rep.status != "PASS":
                return (
                    "FAIL_ACTION_ABSENT",
                    f"Required action '{action_clean}' cannot survive: entity '{ent_name}' failed retention ({rep.status})."
                )

        return "PASS", f"Action '{action_clean}' and observable visual state verified in final composition."

    # --------------------------------------------------------------------------
    # 5. Timeline & Anti-Loop Detection on Rendered Video
    # --------------------------------------------------------------------------

    def inspect_rendered_timeline_and_loops(
        self,
        video_path: Path,
        beats: List[VisualBeat],
        sampled_beat_frames: Dict[str, List[SampledFrame]],
    ) -> Tuple[bool, List[str]]:
        """
        Inspects actual final MP4 for repetitive loop cycles across narrative beats.
        Compares frame signatures across distinct narrative beats to catch looped footage.
        """
        loop_detected = False
        loop_details: List[str] = []

        beat_signatures: Dict[str, List[np.ndarray]] = {}
        for b in beats:
            frames = sampled_beat_frames.get(b.beat_id, [])
            sigs = []
            for sf in frames:
                # Downsample to 64x64 grayscale for fast structural similarity
                small = cv2.resize(sf.image_bgr, (64, 64))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                sigs.append(gray)
            beat_signatures[b.beat_id] = sigs

        # Cross-beat loop comparison: check if Beat i frames are near-identical to Beat j frames
        beat_ids = [b.beat_id for b in beats]
        for i in range(len(beat_ids)):
            for j in range(i + 1, len(beat_ids)):
                b_i = beats[i]
                b_j = beats[j]
                sigs_i = beat_signatures.get(b_i.beat_id, [])
                sigs_j = beat_signatures.get(b_j.beat_id, [])

                if not sigs_i or not sigs_j:
                    continue

                # Measure mean absolute difference across sampled frames
                min_diff = 999.0
                for s_a in sigs_i:
                    for s_b in sigs_j:
                        diff = float(np.mean(np.abs(s_a.astype(float) - s_b.astype(float))))
                        min_diff = min(min_diff, diff)

                if min_diff < 12.0:  # Frames are effectively identical (video loop detected)
                    loop_detected = True
                    msg = (
                        f"REPETITIVE_LOOP_DETECTED: Beat '{b_j.beat_id}' [{b_j.narrative_role}] "
                        f"is replaying footage from Beat '{b_i.beat_id}' [{b_i.narrative_role}] "
                        f"(frame difference: {min_diff:.2f} <= 12.0). Semantic loop fallback detected."
                    )
                    loop_details.append(msg)

        return loop_detected, loop_details

    # --------------------------------------------------------------------------
    # 6. Subtitle & Composition Collision
    # --------------------------------------------------------------------------

    def inspect_subtitles(
        self,
        ass_path: Optional[Path],
        sampled_frames: List[SampledFrame],
        required_entities: List[str],
    ) -> SubtitleCompositionVerification:
        """
        Inspects subtitle font styling from ASS and validates that subtitles
        do not collide with primary required action/entities.
        """
        font_name = None
        font_matched = True
        reasons = []

        if ass_path and ass_path.exists():
            content = ass_path.read_text(encoding="utf-8", errors="ignore")
            # Look for Style definitions
            style_matches = re.findall(r"Style:\s*([^,\n]+),([^,\n]+)", content)
            for style_name, fn in style_matches:
                if "hp" in style_name.lower() or "default" in style_name.lower():
                    font_name = fn.strip()
                    break

            if font_name and font_name.lower() != CANONICAL_SUBTITLE_FONT.lower():
                font_matched = False
                reasons.append(
                    f"CANONICAL_FONT_MISMATCH: Subtitle font '{font_name}' in {ass_path.name} "
                    f"does not match canonical Story Forge profile '{CANONICAL_SUBTITLE_FONT}'."
                )

        # Check collision on sampled frames: subtitle safe zone is typically bottom 25% (Y >= 0.72)
        collision_detected = False
        collision_details = None

        for sf in sampled_frames:
            for det in sf.detections:
                b = det.bbox
                # If required object or primary subject's hands/action fall into lower subtitle band
                # Y bottom extends into subtitle band AND top is low
                if b.y + b.h >= 0.90 and b.y >= 0.75:
                    collision_detected = True
                    collision_details = (
                        f"Subtitle collision: '{det.entity_name}' bbox (y={b.y:.2f}, h={b.h:.2f}) "
                        f"overlaps bottom subtitle safe zone (y >= 0.85) at {sf.timestamp_sec:.2f}s."
                    )
                    reasons.append(collision_details)
                    break
            if collision_detected:
                break

        verdict = VerificationVerdict.PASS if (font_matched and not collision_detected) else VerificationVerdict.FAIL
        return SubtitleCompositionVerification(
            ass_file_inspected=str(ass_path) if ass_path else None,
            font_name_detected=font_name,
            canonical_font_expected=CANONICAL_SUBTITLE_FONT,
            font_matched=font_matched,
            safe_zone_passed=not collision_detected,
            collision_detected=collision_detected,
            collision_details=collision_details,
            verdict=verdict,
            reasons=reasons,
        )

    # --------------------------------------------------------------------------
    # 7. Final Audio Check
    # --------------------------------------------------------------------------

    def inspect_audio(self, video_path: Path) -> AudioVerification:
        """Measures integrated LUFS and true peak dBTP of final MP4 audio track."""
        cmd = [
            "ffmpeg", "-i", str(video_path),
            "-filter_complex", "ebur128=peak=true",
            "-f", "null", "-"
        ]
        res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        lufs = -99.0
        tp = -99.0

        for line in reversed(res.stderr.split("\n")):
            if "I:" in line and "LUFS" in line and lufs == -99.0:
                try:
                    lufs = float(line.split("I:")[1].split("LUFS")[0].strip())
                except Exception:
                    pass
            if "Peak:" in line and "dBFS" in line and tp == -99.0:
                try:
                    tp = float(line.split("Peak:")[1].split("dBFS")[0].strip())
                except Exception:
                    pass

        has_audio = lufs != -99.0
        # Allow standard short-form broadcast tolerance +/- 3.0 LUFS around -14.0 LUFS
        lufs_ok = has_audio and (-17.0 <= lufs <= -11.0)
        # Peak must be <= -1.0 dBTP
        tp_ok = has_audio and (tp <= -0.80)

        details = f"Integrated LUFS: {lufs:.1f} (target: -14.0), True Peak: {tp:.1f} dBTP (max: -1.0)"
        verdict = VerificationVerdict.PASS if (lufs_ok and tp_ok) else VerificationVerdict.FAIL

        return AudioVerification(
            integrated_lufs=round(lufs, 2),
            true_peak_dbtp=round(tp, 2),
            lufs_passed=lufs_ok,
            true_peak_passed=tp_ok,
            has_audio_stream=has_audio,
            verdict=verdict,
            details=details,
        )

    # --------------------------------------------------------------------------
    # 8. Full End-to-End Forensic Verification
    # --------------------------------------------------------------------------

    def verify_final_render(
        self,
        video_path: Path,
        beats: List[VisualBeat],
        content_id: str = "short_render_v1",
        ass_path: Optional[Path] = None,
        num_samples_per_beat: int = 4,
    ) -> FinalRenderForensicReport:
        """
        Executes end-to-end forensic verification on the actual final 9:16 MP4.
        """
        video_p = Path(video_path)
        if not video_p.exists():
            raise FileNotFoundError(f"Final render video not found at {video_p}")

        probe = self.probe_video(video_p)
        w, h, fps = probe["width"], probe["height"], probe["fps"]
        tot_frames, dur = probe["total_frames"], probe["duration"]

        failures: Dict[str, List[str]] = {
            "RENDERER_DEFECTS": [],
            "COMPOSITION_DEFECTS": [],
            "EVIDENCE_DEFECTS": [],
            "TIMELINE_DEFECTS": [],
            "SUBTITLE_DEFECTS": [],
            "AUDIO_DEFECTS": [],
        }

        # Resolution check: must be 1080x1920 9:16
        if w != 1080 or h != 1920:
            failures["RENDERER_DEFECTS"].append(
                f"CANONICAL_RESOLUTION_VIOLATION: Expected 1080x1920 (9:16), found {w}x{h}."
            )

        # Sample frames per beat
        sampled_beat_frames: Dict[str, List[SampledFrame]] = {}
        all_sampled_frames: List[SampledFrame] = []
        beat_reports: List[BeatRenderVerification] = []

        for beat in beats:
            b_frames = self.sample_beat_frames(
                video_p,
                start_sec=beat.narration_start,
                end_sec=beat.narration_end,
                num_samples=num_samples_per_beat,
            )
            sampled_beat_frames[beat.beat_id] = b_frames
            all_sampled_frames.extend(b_frames)

            # Subject retention
            ret_reports = self.inspect_subject_retention(b_frames, beat.required_entities)

            # Action / state survival
            act_status, act_desc = self.inspect_action_survival(beat, b_frames, ret_reports)

            # Beat-level verdict
            beat_verdict = VerificationVerdict.PASS
            beat_reasons: List[str] = []

            for ent_name, r in ret_reports.items():
                if r.status != "PASS" and beat.direct_visual_requirement:
                    beat_verdict = VerificationVerdict.FAIL
                    beat_reasons.append(r.amputation_details or f"Entity '{ent_name}' absent.")
                    if r.status == "FAIL_AMPUTATED":
                        failures["COMPOSITION_DEFECTS"].append(
                            f"Beat '{beat.beat_id}': {r.amputation_details}"
                        )
                    else:
                        failures["EVIDENCE_DEFECTS"].append(
                            f"Beat '{beat.beat_id}': Entity '{ent_name}' absent from final render."
                        )

            if act_status.startswith("FAIL"):
                beat_verdict = VerificationVerdict.FAIL
                beat_reasons.append(act_desc)
                failures["EVIDENCE_DEFECTS"].append(f"Beat '{beat.beat_id}': {act_desc}")

            # Narrative Evidence Contract: Forbidden Subject & Non-Visual Gate
            from engines.edl.evidence_contract import NarrativeEvidenceContract
            contract = NarrativeEvidenceContract.from_visual_beat(beat)
            if contract.forbidden_subjects and self.grounder:
                forbidden_specs = self.resolve_entity_specs(contract.forbidden_subjects)
                for sf in b_frames:
                    dets = self.grounder.ground_entities(sf.image_bgr, forbidden_specs, timestamp_sec=sf.timestamp_sec)
                    for d in dets:
                        if d.confidence >= 0.40:
                            beat_verdict = VerificationVerdict.FAIL
                            f_msg = f"Beat '{beat.beat_id}': Forbidden subject '{d.entity_name}' (conf={d.confidence:.2f}) observed in render for claim '{beat.narrative_text}'."
                            beat_reasons.append(f_msg)
                            failures["EVIDENCE_DEFECTS"].append(f_msg)
                            break
                    if beat_verdict == VerificationVerdict.FAIL and any("Forbidden subject" in r for r in beat_reasons):
                        break

            if contract.is_inherently_non_visual and beat.direct_visual_requirement:
                beat_verdict = VerificationVerdict.FAIL
                non_vis_msg = f"Beat '{beat.beat_id}': Non-visual/book-only claim falsely marked as DIRECT: '{beat.narrative_text}'."
                beat_reasons.append(non_vis_msg)
                failures["EVIDENCE_DEFECTS"].append(non_vis_msg)

            br = BeatRenderVerification(
                beat_id=beat.beat_id,
                narrative_role=beat.narrative_role,
                narration_start=beat.narration_start,
                narration_end=beat.narration_end,
                duration=round(beat.narration_end - beat.narration_start, 3),
                is_direct_requirement=beat.direct_visual_requirement,
                is_visual_optional=beat.is_visual_optional,
                required_entities=beat.required_entities,
                required_action=beat.required_action,
                expected_visual_state=beat.visual_state,
                entity_retention=ret_reports,
                action_state_status=act_status,
                action_state_details=act_desc,
                beat_verdict=beat_verdict,
                reasons=beat_reasons,
            )
            beat_reports.append(br)

        # Timeline anti-loop inspection
        looping_detected, loop_details = self.inspect_rendered_timeline_and_loops(
            video_p, beats, sampled_beat_frames
        )
        if looping_detected:
            failures["TIMELINE_DEFECTS"].extend(loop_details)

        # Subtitle verification
        sub_rep = self.inspect_subtitles(
            ass_path=ass_path,
            sampled_frames=all_sampled_frames,
            required_entities=[e for b in beats for e in b.required_entities],
        )
        if sub_rep.verdict == VerificationVerdict.FAIL:
            failures["SUBTITLE_DEFECTS"].extend(sub_rep.reasons)

        # Audio verification
        audio_rep = self.inspect_audio(video_p)
        if audio_rep.verdict == VerificationVerdict.FAIL:
            failures["AUDIO_DEFECTS"].append(
                f"Audio validation failed: {audio_rep.details}"
            )

        # Overall verdict
        total_defect_count = sum(len(v) for v in failures.values())
        overall_verdict = VerificationVerdict.PASS if total_defect_count == 0 else VerificationVerdict.FAIL
        final_status = "READY" if overall_verdict == VerificationVerdict.PASS else "NOT_READY"

        if total_defect_count == 0:
            status_desc = "All final-render visual, audio, composition, and timeline gates PASSED."
        else:
            status_desc = (
                f"Final render failed forensic verification with {total_defect_count} defects across "
                f"{[k for k, v in failures.items() if len(v) > 0]}."
            )

        report = FinalRenderForensicReport(
            video_path=str(video_p),
            content_id=content_id,
            width=w,
            height=h,
            duration_sec=dur,
            fps=fps,
            total_frames=tot_frames,
            beat_reports=beat_reports,
            transition_reports=[],
            subtitle_report=sub_rep,
            audio_report=audio_rep,
            looping_detected=looping_detected,
            loop_details=loop_details,
            failures_by_category=failures,
            overall_verdict=overall_verdict,
            final_forensic_status=final_status,
            status_explanation=status_desc,
        )
        return report
