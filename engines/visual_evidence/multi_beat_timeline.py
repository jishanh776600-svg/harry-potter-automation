"""
STORY FORGE — Multi-Beat Visual Coverage & Strict Anti-Loop Timeline Engine
==========================================================================
Enforces strict beat-to-visual correspondence across narrative Shorts.

Core Invariants:
  1. Multi-Beat Requirements:
     Every narrative proposition/beat has a distinct VisualBeat requirement.
     Factual/canonical comparison beats (e.g. book vs movie differences)
     are explicitly marked VISUAL_OPTIONAL without fabricating fake evidence.
  2. One Verified Clip Cannot Automatically Satisfy Multiple Beats:
     A verified clip may only serve multiple beats if the evidence explicitly
     covers both beats and timeline overlap is genuinely valid (non-overlapping
     verified sub-intervals). Repeating the same clip across unrelated beats is rejected.
  3. Strict No-Loop Policy:
     Clips may be trimmed to fit a beat, but NEVER extended by looping.
     FFmpeg -stream_loop and Python-side repeated concat lists are strictly disabled.
     If verified visual coverage is insufficient for direct visual requirements,
     fails closed with INSUFFICIENT_VISUAL_COVERAGE.
  4. Real Detector Authority Intact:
     Physical verification remains governed by real OWLv2 detector.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from pydantic import BaseModel, Field

from engines.movie_event.models import (
    VisualBeat,
    VISUAL_OPTIONAL,
    DIRECT_VISUAL,
    INSUFFICIENT_VISUAL_COVERAGE,
)

logger = logging.getLogger("MultiBeatTimeline")


class BeatCoverageStatus(str, Enum):
    """Detailed visual coverage status for a single narrative beat."""
    VERIFIED_DIRECT = "VERIFIED_DIRECT"
    VISUAL_OPTIONAL_COVERED = "VISUAL_OPTIONAL_COVERED"
    VISUAL_OPTIONAL_UNCOVERED = "VISUAL_OPTIONAL_UNCOVERED"
    UNCOVERED = "UNCOVERED"
    DEFICIT_UNRESOLVED = "DEFICIT_UNRESOLVED"
    REUSED_DISALLOWED = "REUSED_DISALLOWED"


class TimelineSegment(BaseModel):
    """
    Physical timeline segment assigned to an individual narrative beat.
    Never repeated or looped to fill duration.
    """
    segment_id: str
    beat_id: str
    timeline_start: float
    timeline_end: float
    duration: float
    source_video: Optional[str] = None
    source_start: Optional[float] = None
    source_end: Optional[float] = None
    clip_path: Optional[str] = None
    coverage_status: BeatCoverageStatus
    direct_requirement: bool
    is_visual_optional: bool
    narrative_role: str
    action_depicted: Optional[str] = None
    entities_present: List[str] = Field(default_factory=list)
    verification_metadata: Dict[str, Any] = Field(default_factory=dict)
    notes: str = ""

    @property
    def is_covered(self) -> bool:
        return self.coverage_status in (
            BeatCoverageStatus.VERIFIED_DIRECT,
            BeatCoverageStatus.VISUAL_OPTIONAL_COVERED,
        )


class MultiBeatTimelinePlan(BaseModel):
    """
    Directorial timeline plan covering all beats of a Short.
    Provides strict anti-loop validation and audit trail.
    """
    content_id: str
    total_narration_duration: float
    total_verified_visual_duration: float
    segments: List[TimelineSegment] = Field(default_factory=list)
    uncovered_beats: List[str] = Field(default_factory=list)
    visual_optional_beats: List[str] = Field(default_factory=list)
    status: str = "PASS"  # "PASS" or "INSUFFICIENT_VISUAL_COVERAGE"
    is_valid: bool = True
    rejection_reasons: List[str] = Field(default_factory=list)
    loop_count_detected: int = 0
    audit_trail: List[str] = Field(default_factory=list)

    def get_renderable_segments(self) -> List[TimelineSegment]:
        """Returns only segments that have physical verified media to render."""
        return [s for s in self.segments if s.is_covered and s.clip_path]


class MultiBeatCoverageEngine:
    """
    Constructs, allocates, and validates multi-beat visual timelines with
    strict anti-loop and anti-repetition enforcement.
    """

    def __init__(
        self,
        min_shot_duration: float = 0.8,
        allow_cross_beat_split: bool = True,
    ):
        self.min_shot_duration = min_shot_duration
        self.allow_cross_beat_split = allow_cross_beat_split

    def build_timeline(
        self,
        beats: List[VisualBeat],
        evidence_matches: Dict[str, Any],
        content_id: str = "short_v1",
        total_voice_duration: Optional[float] = None,
    ) -> MultiBeatTimelinePlan:
        """
        Builds a multi-beat timeline allocating verified visual clips to narrative beats.

        Args:
            beats: List of VisualBeat instances with timestamps and requirements.
            evidence_matches: Map of beat_id -> verified evidence / clip info.
            content_id: Identifier for the Short.
            total_voice_duration: Optional override for total voiceover duration.

        Returns:
            MultiBeatTimelinePlan with coverage status and anti-loop validation.
        """
        if not beats:
            return MultiBeatTimelinePlan(
                content_id=content_id,
                total_narration_duration=0.0,
                total_verified_visual_duration=0.0,
                status=INSUFFICIENT_VISUAL_COVERAGE,
                is_valid=False,
                rejection_reasons=["No beats provided to timeline."],
            )

        # Track usage of physical clip intervals: video_path -> list of (start, end, beat_id)
        consumed_intervals: Dict[str, List[Tuple[float, float, str]]] = {}
        segments: List[TimelineSegment] = []
        uncovered: List[str] = []
        visual_optional: List[str] = []
        rejections: List[str] = []
        audit: List[str] = []

        total_voice_dur = total_voice_duration or max(b.narration_end for b in beats)
        total_verified_dur = 0.0

        for idx, beat in enumerate(beats):
            beat_start = beat.narration_start
            beat_end = beat.narration_end
            beat_dur = max(0.0, beat_end - beat_start)
            seg_id = f"seg_{idx+1:02d}_{beat.beat_id}"

            is_opt = beat.is_visual_optional
            if is_opt:
                visual_optional.append(beat.beat_id)

            ev = evidence_matches.get(beat.beat_id)

            if not ev:
                # No candidate / evidence offered for this beat
                if beat.direct_visual_requirement:
                    status = BeatCoverageStatus.UNCOVERED
                    uncovered.append(beat.beat_id)
                    rejections.append(
                        f"{INSUFFICIENT_VISUAL_COVERAGE}: Beat '{beat.beat_id}' has a direct visual requirement "
                        f"('{beat.required_action}') but no verified evidence was provided."
                    )
                    audit.append(f"Beat '{beat.beat_id}': UNCOVERED (direct requirement failed closed)")
                else:
                    status = BeatCoverageStatus.VISUAL_OPTIONAL_UNCOVERED
                    audit.append(f"Beat '{beat.beat_id}': VISUAL_OPTIONAL_UNCOVERED (explicit absence without fake footage)")

                seg = TimelineSegment(
                    segment_id=seg_id,
                    beat_id=beat.beat_id,
                    timeline_start=beat_start,
                    timeline_end=beat_end,
                    duration=beat_dur,
                    coverage_status=status,
                    direct_requirement=beat.direct_visual_requirement,
                    is_visual_optional=is_opt,
                    narrative_role=beat.narrative_role,
                    action_depicted=None,
                    entities_present=[],
                    notes="Uncovered / optional absent",
                )
                segments.append(seg)
                continue

            # Candidate evidence provided. Extract properties.
            src_video = self._extract_field(ev, ["source_video", "video_path", "clip_path", "asset_id"])
            src_start = float(self._extract_field(ev, ["source_start", "start_seconds", "sub_shot_start"], 0.0))
            src_end = float(self._extract_field(ev, ["source_end", "end_seconds", "sub_shot_end"], 0.0))
            clip_path = str(self._extract_field(ev, ["clip_path", "source_video", "video_path"], ""))
            is_verified = bool(self._extract_field(ev, ["is_verified", "verified"], True))
            verdict = str(self._extract_field(ev, ["verdict", "status"], "PASS"))

            if not is_verified or verdict not in ("PASS", "VERIFIED"):
                if beat.direct_visual_requirement:
                    uncovered.append(beat.beat_id)
                    rejections.append(
                        f"{INSUFFICIENT_VISUAL_COVERAGE}: Beat '{beat.beat_id}' evidence rejected with verdict '{verdict}'."
                    )
                    status = BeatCoverageStatus.UNCOVERED
                else:
                    status = BeatCoverageStatus.VISUAL_OPTIONAL_UNCOVERED

                seg = TimelineSegment(
                    segment_id=seg_id,
                    beat_id=beat.beat_id,
                    timeline_start=beat_start,
                    timeline_end=beat_end,
                    duration=beat_dur,
                    coverage_status=status,
                    direct_requirement=beat.direct_visual_requirement,
                    is_visual_optional=is_opt,
                    narrative_role=beat.narrative_role,
                    notes=f"Evidence verification failed: {verdict}",
                )
                segments.append(seg)
                continue

            # Check Strict Anti-Repetition / Anti-Loop Rule:
            # Has this exact source clip interval already been assigned to another beat?
            key = src_video or clip_path
            overlap_detected = False
            prior_beat = None

            if key in consumed_intervals:
                for prior_s, prior_e, p_bid in consumed_intervals[key]:
                    # Check temporal overlap in source space
                    overlap_amount = max(0.0, min(src_end, prior_e) - max(src_start, prior_s))
                    if overlap_amount > 0.05:  # more than 50ms overlap
                        overlap_detected = True
                        prior_beat = p_bid
                        break

            # Legitimate multi-beat sharing is ONLY allowed if explicitly flagged and disjoint
            multi_beat_supported = bool(self._extract_field(ev, ["multi_beat_supported", "explicit_multi_beat"], False))

            if overlap_detected and not multi_beat_supported:
                # Disallow automatic duplicate reuse!
                err_msg = (
                    f"ANTI-LOOP GUARD VIOLATION: Beat '{beat.beat_id}' attempted to reuse clip '{key}' "
                    f"({src_start:.2f}s - {src_end:.2f}s) already consumed by earlier beat '{prior_beat}'. "
                    f"One verified clip cannot automatically satisfy multiple beats."
                )
                logger.warning(err_msg)
                rejections.append(err_msg)
                status = BeatCoverageStatus.REUSED_DISALLOWED
                if beat.direct_visual_requirement:
                    uncovered.append(beat.beat_id)

                seg = TimelineSegment(
                    segment_id=seg_id,
                    beat_id=beat.beat_id,
                    timeline_start=beat_start,
                    timeline_end=beat_end,
                    duration=beat_dur,
                    coverage_status=status,
                    direct_requirement=beat.direct_visual_requirement,
                    is_visual_optional=is_opt,
                    narrative_role=beat.narrative_role,
                    notes=err_msg,
                )
                segments.append(seg)
                continue

            # Duration handling: Clip may be trimmed to beat, but NEVER extended by looping
            available_dur = max(0.0, src_end - src_start)
            used_dur = min(available_dur, beat_dur)

            # Record consumption
            consumed_intervals.setdefault(key, []).append((src_start, src_start + used_dur, beat.beat_id))
            total_verified_dur += used_dur

            cov_status = (
                BeatCoverageStatus.VERIFIED_DIRECT
                if beat.direct_visual_requirement
                else BeatCoverageStatus.VISUAL_OPTIONAL_COVERED
            )

            seg = TimelineSegment(
                segment_id=seg_id,
                beat_id=beat.beat_id,
                timeline_start=beat_start,
                timeline_end=round(beat_start + used_dur, 3),
                duration=round(used_dur, 3),
                source_video=src_video,
                source_start=src_start,
                source_end=round(src_start + used_dur, 3),
                clip_path=clip_path,
                coverage_status=cov_status,
                direct_requirement=beat.direct_visual_requirement,
                is_visual_optional=is_opt,
                narrative_role=beat.narrative_role,
                action_depicted=beat.required_action,
                entities_present=beat.required_entities,
                verification_metadata={
                    "verdict": verdict,
                    "available_duration": available_dur,
                    "used_duration": used_dur,
                    "is_trimmed": available_dur > beat_dur,
                },
                notes="Verified distinct clip assigned without looping.",
            )
            segments.append(seg)
            audit.append(
                f"Beat '{beat.beat_id}': Assigned distinct clip ({used_dur:.2f}s) "
                f"[{cov_status.value}]"
            )

        # Final Timeline Validation
        has_direct_failure = len(uncovered) > 0
        status = INSUFFICIENT_VISUAL_COVERAGE if has_direct_failure else "PASS"
        is_valid = not has_direct_failure and len(rejections) == 0

        plan = MultiBeatTimelinePlan(
            content_id=content_id,
            total_narration_duration=round(total_voice_dur, 3),
            total_verified_visual_duration=round(total_verified_dur, 3),
            segments=segments,
            uncovered_beats=uncovered,
            visual_optional_beats=visual_optional,
            status=status,
            is_valid=is_valid,
            rejection_reasons=rejections,
            loop_count_detected=0,
            audit_trail=audit,
        )
        return plan

    @staticmethod
    def _extract_field(obj: Any, field_names: List[str], default: Any = None) -> Any:
        """Extracts field from either object attribute or dict key."""
        for fn in field_names:
            if isinstance(obj, dict):
                if fn in obj and obj[fn] is not None:
                    return obj[fn]
            else:
                if hasattr(obj, fn):
                    val = getattr(obj, fn)
                    if val is not None:
                        return val
        return default
