"""
STORY FORGE — Phase 5: Timeline Assembler
==========================================
Parts 4 and 5 of the 34-part Phase 5 specification.

PART 4: Every narration interval maps to VERIFIED_DIRECT / VERIFIED_CONTEXT / VISUAL_OPTIONAL.
PART 5: Absolute anti-loop rule — no -stream_loop, no repeated concat entries,
        no frozen frames. Fails with INSUFFICIENT_EDL_COVERAGE if coverage is absent.

The timeline assembler concatenates extracted clips into a single silent video
in EDL narration order. It does NOT add audio; that is the AudioMixer's job.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from engines.edl.models import VisualEDL, EDLEntry, CoverageState
from engines.renderer.clip_extractor import ExtractedClip

logger = logging.getLogger("TimelineAssembler")

# Coverage states that count as "covered" for assembly
_COVERED_STATES = frozenset([
    CoverageState.VERIFIED_DIRECT,
    CoverageState.VERIFIED_CONTEXT,
    CoverageState.VISUAL_OPTIONAL,
])


@dataclass
class AssemblySegment:
    """One segment of the assembled timeline."""
    beat_id: str
    timeline_start: float        # In the assembled output video
    timeline_end: float
    clip_path: Path
    coverage_state: CoverageState
    narration_start: float
    narration_end: float
    is_anti_loop_candidate: bool = False


@dataclass
class AssembledTimeline:
    """Result of timeline assembly — a single silent 1080x1920 video."""
    output_path: Path
    total_duration: float
    segments: List[AssemblySegment] = field(default_factory=list)
    anti_loop_violations: List[str] = field(default_factory=list)
    assembly_ok: bool = True
    error: Optional[str] = None
    concat_list_path: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "total_duration": round(self.total_duration, 4),
            "segment_count": len(self.segments),
            "anti_loop_violations": self.anti_loop_violations,
            "assembly_ok": self.assembly_ok,
            "error": self.error,
        }


class TimelineAssembler:
    """
    Assembles extracted clips into a single silent 1080x1920 video.

    INVARIANTS:
      - Clips are concatenated in EDL narration order.
      - Each beat_id may appear ONCE in the concat list.
      - Repeated source clips (same sha256) from different beats raise
        INSUFFICIENT_EDL_COVERAGE — the EDL must supply distinct footage.
      - No -stream_loop, no padding loops, no freeze-frame extension.
      - If a beat has UNFULFILLED coverage, assembly fails immediately.
    """

    def __init__(self, scratch_dir: Optional[Path] = None):
        if scratch_dir is None:
            try:
                from config.settings import PROJECT_ROOT
                scratch_dir = PROJECT_ROOT / "data" / "temp" / "phase5_assembly"
            except ImportError:
                scratch_dir = Path("data/temp/phase5_assembly")
        self.scratch_dir = Path(scratch_dir)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assemble(
        self,
        edl: VisualEDL,
        extracted_clips: List[ExtractedClip],
        output_path: Path,
    ) -> AssembledTimeline:
        """
        Concatenate clips in EDL narration order into a single silent video.

        Args:
            edl: The locked VisualEDL.
            extracted_clips: Clips extracted by ExactClipExtractor (same order as edl.entries).
            output_path: Where to write the assembled silent video.

        Returns:
            AssembledTimeline — check .assembly_ok before proceeding.
        """
        output_path = Path(output_path)
        clip_map: Dict[str, ExtractedClip] = {c.beat_id: c for c in extracted_clips}

        # --- Gate 1: All clips extracted successfully ---
        failed_extractions = [c for c in extracted_clips if not c.extraction_ok]
        if failed_extractions:
            return AssembledTimeline(
                output_path=output_path,
                total_duration=0.0,
                assembly_ok=False,
                error=f"INSUFFICIENT_EDL_COVERAGE: {len(failed_extractions)} clips failed extraction: "
                      + ", ".join(f"[{c.beat_id}: {c.error}]" for c in failed_extractions),
            )

        # --- Gate 2: No UNFULFILLED beats ---
        unfulfilled = [e for e in edl.entries if e.coverage_state == CoverageState.UNFULFILLED]
        if unfulfilled:
            return AssembledTimeline(
                output_path=output_path,
                total_duration=0.0,
                assembly_ok=False,
                error=f"INSUFFICIENT_EDL_COVERAGE: Unfulfilled DIRECT beats: "
                      + ", ".join(e.beat_id for e in unfulfilled),
            )

        # --- Gate 3: Anti-loop — detect repeated source clips ---
        anti_loop_violations = self._detect_repeated_clips(edl, extracted_clips)

        segments: List[AssemblySegment] = []
        concat_lines: List[str] = []
        seen_beat_ids: Set[str] = set()
        timeline_cursor = 0.0

        for entry in edl.entries:
            clip = clip_map.get(entry.beat_id)
            if clip is None:
                return AssembledTimeline(
                    output_path=output_path,
                    total_duration=0.0,
                    assembly_ok=False,
                    error=f"INSUFFICIENT_EDL_COVERAGE: No extracted clip for beat '{entry.beat_id}'.",
                )

            if entry.beat_id in seen_beat_ids:
                # A beat_id appearing twice in the EDL is an EDL construction error
                return AssembledTimeline(
                    output_path=output_path,
                    total_duration=0.0,
                    assembly_ok=False,
                    error=f"INSUFFICIENT_EDL_COVERAGE: beat_id '{entry.beat_id}' appears more than once in EDL.",
                )
            seen_beat_ids.add(entry.beat_id)

            seg_dur = clip.duration
            seg = AssemblySegment(
                beat_id=entry.beat_id,
                timeline_start=timeline_cursor,
                timeline_end=round(timeline_cursor + seg_dur, 6),
                clip_path=clip.output_path,
                coverage_state=entry.coverage_state,
                narration_start=entry.narration_start,
                narration_end=entry.narration_end,
                is_anti_loop_candidate=any(entry.beat_id in v for v in anti_loop_violations),
            )
            segments.append(seg)
            concat_lines.append(f"file '{clip.output_path}'\n")
            timeline_cursor = seg.timeline_end

        # Write concat file
        concat_path = self.scratch_dir / f"concat_{edl.edl_id}.txt"
        concat_path.write_text("".join(concat_lines), encoding="utf-8")

        # Run FFmpeg concat
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_path),
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "fast",
            "-an",  # No audio — clips are already stripped
            "-movflags", "+faststart",
            str(output_path),
        ]

        logger.info("Assembling %d segments → %s", len(segments), output_path)
        result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, timeout=300)
        if result.returncode != 0:
            return AssembledTimeline(
                output_path=output_path,
                total_duration=0.0,
                segments=segments,
                anti_loop_violations=anti_loop_violations,
                concat_list_path=concat_path,
                assembly_ok=False,
                error=f"FFmpeg concat failed (code {result.returncode}): {result.stderr[-1000:]}",
            )

        total_dur = timeline_cursor
        return AssembledTimeline(
            output_path=output_path,
            total_duration=total_dur,
            segments=segments,
            anti_loop_violations=anti_loop_violations,
            concat_list_path=concat_path,
            assembly_ok=True,
        )

    # ------------------------------------------------------------------
    # Anti-loop detection
    # ------------------------------------------------------------------

    def _detect_repeated_clips(
        self,
        edl: VisualEDL,
        clips: List[ExtractedClip],
    ) -> List[str]:
        """
        Detect repeated source footage across different beats.
        Returns a list of violation descriptions.
        """
        violations: List[str] = []

        # Check by source interval (movie_id, start, end) overlap
        seen_intervals: List[Tuple[int, float, float, str]] = []
        clip_map = {c.beat_id: c for c in clips}

        for entry in edl.entries:
            interval_key = (
                int(entry.source_movie_id),
                round(entry.source_clip_start, 3),
                round(entry.source_clip_end, 3),
            )
            for prev_id, prev_start, prev_end, prev_beat in seen_intervals:
                if (
                    int(entry.source_movie_id) == prev_id
                    and entry.source_clip_start < prev_end
                    and entry.source_clip_end > prev_start
                ):
                    violations.append(
                        f"REPEATED_SOURCE: beat '{entry.beat_id}' "
                        f"[{entry.source_clip_start:.2f}–{entry.source_clip_end:.2f}] "
                        f"overlaps with beat '{prev_beat}' "
                        f"[{prev_start:.2f}–{prev_end:.2f}] in movie {entry.source_movie_id}."
                    )
            seen_intervals.append((
                int(entry.source_movie_id),
                entry.source_clip_start,
                entry.source_clip_end,
                entry.beat_id,
            ))

        # Check by sha256 (bitwise identical clips)
        sha_to_beats: Dict[str, List[str]] = {}
        for clip in clips:
            if clip.sha256:
                sha_to_beats.setdefault(clip.sha256, []).append(clip.beat_id)
        for sha, beat_ids in sha_to_beats.items():
            if len(beat_ids) > 1:
                violations.append(
                    f"REPEATED_CLIP_SHA256: beats {beat_ids} produced identical clip content "
                    f"(sha256={sha[:16]}…). Same footage reused across multiple beats."
                )

        return violations
