"""
STORY FORGE — Phase 5: Deterministic EDL Renderer
===================================================
The master orchestrator for Phase 5.  Parts 1–15 of the 34-part spec.

CORE DOCTRINE (Part 1):
  The renderer is NOT allowed to make semantic decisions.
  The EDL is the authority.  The renderer executes.
  The FinalRenderVerifier independently judges the rendered pixels.

PIPELINE:
  1.  EDL Validation (Part 2)        — EDLValidator
  2.  Clip Extraction (Part 3)       — ExactClipExtractor
  3.  Crop plan from EDL (Parts 6-7) — crop_requirements per entry
  4.  Timeline Assembly (Parts 4-5)  — TimelineAssembler
  5.  Subtitle Rendering (Parts 11-13) — Phase5SubtitleRenderer
  6.  Audio Mix (Parts 8-10, 14)     — Phase5AudioMixer
  7.  Final mux: video + audio + subtitles → 1080×1920 H.264/AAC (Part 15)

NO AUTO-REPAIR (Part 31):
  If any step fails, return the failure. Do NOT modify the EDL.
  Do NOT search again. Do NOT rerender automatically.

OUTPUT SPEC (Part 15):
  1080×1920, 9:16, 30 FPS, H.264 High Profile, AAC 192k, MOV/MP4 container.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

from engines.edl.models import VisualEDL, LockedNarrationInput
from engines.renderer.edl_validator import EDLValidator, EDLValidationResult, EDLValidationFailureCode
from engines.renderer.clip_extractor import ExactClipExtractor, ExtractedClip
from engines.renderer.timeline_assembler import TimelineAssembler, AssembledTimeline
from engines.renderer.subtitle_renderer import Phase5SubtitleRenderer, SubtitleRenderResult
from engines.renderer.audio_mixer import Phase5AudioMixer, AudioMixResult

logger = logging.getLogger("DeterministicEDLRenderer")


@dataclass
class Phase5RenderResult:
    """Complete result of a Phase 5 deterministic render."""
    content_id: str
    output_video_path: Optional[Path]
    output_ass_path: Optional[Path]

    # Sub-component results
    edl_validation: Optional[EDLValidationResult] = None
    extracted_clips: List[ExtractedClip] = field(default_factory=list)
    assembled_timeline: Optional[AssembledTimeline] = None
    subtitle_render: Optional[SubtitleRenderResult] = None
    audio_mix: Optional[AudioMixResult] = None

    # Overall status
    render_ok: bool = False
    failure_stage: Optional[str] = None
    failure_codes: List[str] = field(default_factory=list)
    error: Optional[str] = None
    render_duration_sec: float = 0.0

    # Output video properties (from final probe)
    output_width: int = 0
    output_height: int = 0
    output_fps: float = 0.0
    output_duration_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_id": self.content_id,
            "output_video_path": str(self.output_video_path) if self.output_video_path else None,
            "output_ass_path": str(self.output_ass_path) if self.output_ass_path else None,
            "render_ok": self.render_ok,
            "failure_stage": self.failure_stage,
            "failure_codes": self.failure_codes,
            "error": self.error,
            "render_duration_sec": round(self.render_duration_sec, 2),
            "output_resolution": f"{self.output_width}x{self.output_height}" if self.output_width else None,
            "output_fps": self.output_fps,
            "output_duration_sec": round(self.output_duration_sec, 4),
            "edl_validation": self.edl_validation.to_dict() if self.edl_validation else None,
            "clip_count": len(self.extracted_clips),
            "clips_ok": all(c.extraction_ok for c in self.extracted_clips),
            "timeline": self.assembled_timeline.to_dict() if self.assembled_timeline else None,
            "subtitle": self.subtitle_render.to_dict() if self.subtitle_render else None,
            "audio": self.audio_mix.to_dict() if self.audio_mix else None,
        }


class DeterministicEDLRenderer:
    """
    Phase 5 deterministic renderer.

    Accepts a locked VisualEDL and a locked LockedNarrationInput,
    executes each stage in order, and returns a structured Phase5RenderResult.

    ZERO SEMANTIC DECISIONS:
      - Does not search for better clips.
      - Does not modify the EDL.
      - Does not re-generate TTS.
      - Does not substitute BGM.
      - Does not auto-repair failures.
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        movies_dir: Optional[Path] = None,
        bgm_dir: Optional[Path] = None,
        scratch_dir: Optional[Path] = None,
        require_source_files: bool = True,
    ):
        try:
            from config.settings import PROJECT_ROOT
            _root = PROJECT_ROOT
        except ImportError:
            _root = Path(".")

        self.output_dir = Path(output_dir) if output_dir else _root / "data" / "renders" / "phase5"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.scratch_dir = Path(scratch_dir) if scratch_dir else _root / "data" / "temp" / "phase5"
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

        movies_dir = Path(movies_dir) if movies_dir else _root / "data" / "movies"
        bgm_dir = Path(bgm_dir) if bgm_dir else _root / "assets" / "music"

        self._validator = EDLValidator(movies_dir=movies_dir, require_source_files=require_source_files)
        self._extractor = ExactClipExtractor(
            movies_dir=movies_dir,
            scratch_dir=self.scratch_dir / "clips",
        )
        self._assembler = TimelineAssembler(scratch_dir=self.scratch_dir / "assembly")
        self._subtitler = Phase5SubtitleRenderer(output_dir=self.scratch_dir / "subs")
        self._mixer = Phase5AudioMixer(bgm_dir=bgm_dir, scratch_dir=self.scratch_dir / "audio")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        edl: VisualEDL,
        narration: LockedNarrationInput,
        narration_audio_path: Path,
        output_filename: Optional[str] = None,
    ) -> Phase5RenderResult:
        """
        Execute the full deterministic render pipeline.

        Args:
            edl: The locked, validated VisualEDL from Phase 4.
            narration: The LockedNarrationInput with word timestamps.
            narration_audio_path: Path to the locked narration WAV/MP3.
            output_filename: Optional custom output filename (default: {content_id}_phase5.mp4).

        Returns:
            Phase5RenderResult — check .render_ok.
            On failure: DO NOT modify EDL, DO NOT auto-repair.
        """
        t_start = time.time()
        content_id = edl.content_id
        fn = output_filename or f"{content_id}_phase5.mp4"
        out_video = self.output_dir / fn

        result = Phase5RenderResult(
            content_id=content_id,
            output_video_path=None,
            output_ass_path=None,
        )

        # ── Stage 1: EDL Validation ─────────────────────────────────────────
        logger.info("[%s] Stage 1: EDL validation", content_id)
        val = self._validator.validate(edl, narration_hash=narration.narration_hash)
        result.edl_validation = val
        if not val.passed:
            result.failure_stage = "EDL_VALIDATION"
            result.failure_codes = [c.value for c in val.failure_codes]
            result.error = "; ".join(val.failure_details)
            result.render_duration_sec = round(time.time() - t_start, 2)
            logger.error("[%s] EDL validation FAILED: %s", content_id, result.error)
            return result

        # ── Stage 2: Clip Extraction ─────────────────────────────────────────
        logger.info("[%s] Stage 2: Extracting %d clips", content_id, len(edl.entries))
        crop_filters = {
            entry.beat_id: ExactClipExtractor.build_crop_filter_from_edl(entry)
            for entry in edl.entries
        }
        clips = self._extractor.extract_all(
            entries=edl.entries,
            crop_filters=crop_filters,
            output_dir=self.scratch_dir / "clips",
        )
        result.extracted_clips = clips
        failed = [c for c in clips if not c.extraction_ok]
        if failed:
            result.failure_stage = "CLIP_EXTRACTION"
            result.failure_codes = ["CLIP_EXTRACTION_FAILED"]
            result.error = f"{len(failed)} clips failed: " + "; ".join(
                f"[{c.beat_id}: {c.error}]" for c in failed
            )
            result.render_duration_sec = round(time.time() - t_start, 2)
            logger.error("[%s] Clip extraction FAILED: %s", content_id, result.error)
            return result

        # ── Stage 3: Timeline Assembly ───────────────────────────────────────
        logger.info("[%s] Stage 3: Timeline assembly", content_id)
        silent_video = self.scratch_dir / "assembly" / f"{content_id}_silent.mp4"
        timeline = self._assembler.assemble(edl, clips, output_path=silent_video)
        result.assembled_timeline = timeline
        if not timeline.assembly_ok:
            result.failure_stage = "TIMELINE_ASSEMBLY"
            result.failure_codes = ["TIMELINE_ASSEMBLY_FAILED"]
            result.error = timeline.error
            result.render_duration_sec = round(time.time() - t_start, 2)
            logger.error("[%s] Timeline assembly FAILED: %s", content_id, result.error)
            return result

        # Anti-loop violations are non-fatal warnings if assembly passed — log them
        if timeline.anti_loop_violations:
            logger.warning(
                "[%s] Anti-loop violations detected: %s",
                content_id, timeline.anti_loop_violations,
            )

        # ── Stage 4: Subtitle Rendering ──────────────────────────────────────
        logger.info("[%s] Stage 4: Subtitle rendering", content_id)
        sub_result = self._subtitler.render(
            content_id=content_id,
            word_timestamps=narration.word_timestamps,
            edl=edl,
            check_evidence_collision=True,
        )
        result.subtitle_render = sub_result
        if not sub_result.render_ok:
            result.failure_stage = "SUBTITLE_RENDERING"
            result.failure_codes = ["SUBTITLE_RENDER_FAILED"]
            result.error = sub_result.error
            result.render_duration_sec = round(time.time() - t_start, 2)
            logger.error("[%s] Subtitle rendering FAILED: %s", content_id, result.error)
            return result
        if sub_result.evidence_collision_detected:
            logger.warning("[%s] SUBTITLE_EVIDENCE_COLLISION: %s", content_id, sub_result.collision_details)

        # ── Stage 5: Audio Mix ───────────────────────────────────────────────
        logger.info("[%s] Stage 5: Audio mixing", content_id)
        audio_out = self.scratch_dir / "audio" / f"{content_id}_mix.aac"
        audio_result = self._mixer.mix(
            narration_path=Path(narration_audio_path),
            locked_narration_hash=narration.narration_hash,
            total_video_duration=timeline.total_duration,
            output_path=audio_out,
        )
        result.audio_mix = audio_result
        if not audio_result.mix_ok:
            result.failure_stage = "AUDIO_MIX"
            result.failure_codes = audio_result.failure_codes
            result.error = audio_result.error or "; ".join(audio_result.failure_codes)
            result.render_duration_sec = round(time.time() - t_start, 2)
            logger.error("[%s] Audio mix FAILED: %s", content_id, result.error)
            return result

        # ── Stage 6: Final Mux — video + audio + subtitles ──────────────────
        logger.info("[%s] Stage 6: Final mux → %s", content_id, out_video)
        ass_path = sub_result.ass_path
        mux_error = self._mux(
            silent_video=silent_video,
            audio_path=audio_out,
            ass_path=ass_path,
            output_path=out_video,
            total_duration=timeline.total_duration,
        )
        if mux_error:
            result.failure_stage = "FINAL_MUX"
            result.failure_codes = ["FINAL_MUX_FAILED"]
            result.error = mux_error
            result.render_duration_sec = round(time.time() - t_start, 2)
            logger.error("[%s] Final mux FAILED: %s", content_id, result.error)
            return result

        # ── Stage 7: Output probe ─────────────────────────────────────────────
        w, h, fps, dur = self._probe_video(out_video)
        result.output_video_path = out_video
        result.output_ass_path = ass_path
        result.output_width = w
        result.output_height = h
        result.output_fps = fps
        result.output_duration_sec = dur

        # Final resolution check (Part 15)
        if w != 1080 or h != 1920:
            result.failure_stage = "OUTPUT_RESOLUTION"
            result.failure_codes = ["RESOLUTION_VIOLATION"]
            result.error = f"Output resolution {w}x{h} != 1080x1920."
            result.render_duration_sec = round(time.time() - t_start, 2)
            return result

        result.render_ok = True
        result.render_duration_sec = round(time.time() - t_start, 2)
        logger.info(
            "[%s] Render COMPLETE: %s | %.2fs | %dx%d | %.2fs",
            content_id, out_video.name, result.render_duration_sec, w, h, dur,
        )
        return result

    # ------------------------------------------------------------------
    # Stage 6: Final mux (Part 15)
    # ------------------------------------------------------------------

    def _mux(
        self,
        silent_video: Path,
        audio_path: Path,
        ass_path: Optional[Path],
        output_path: Path,
        total_duration: float,
    ) -> Optional[str]:
        """
        Mux silent video + audio + ASS subtitles into final 1080×1920 MP4.
        Output spec: 1080×1920, 9:16, 30 FPS, H.264 High, AAC 192k.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build video filter for subtitles
        if ass_path and ass_path.exists():
            # Escape Windows backslashes for FFmpeg ASS filter
            ass_str = str(ass_path).replace("\\", "/").replace(":", "\\:")
            vf = f"subtitles='{ass_str}'"
        else:
            vf = "null"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(silent_video),
            "-i", str(audio_path),
            "-vf", vf,
            "-c:v", "libx264",
            "-profile:v", "high",
            "-crf", "18",
            "-preset", "fast",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-movflags", "+faststart",
            "-t", str(total_duration),
            str(output_path),
        ]

        try:
            res = subprocess.run(
                cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, timeout=600,
            )
            if res.returncode != 0:
                return f"FFmpeg mux failed (code {res.returncode}): {res.stderr[-800:]}"
            return None
        except subprocess.TimeoutExpired:
            return "FFmpeg mux timed out."

    # ------------------------------------------------------------------
    # Output probe
    # ------------------------------------------------------------------

    @staticmethod
    def _probe_video(path: Path):
        """Return (width, height, fps, duration) of a video file."""
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,duration",
            "-of", "json",
            str(path),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            info = json.loads(r.stdout)
            st = info.get("streams", [{}])[0]
            w = int(st.get("width", 0))
            h = int(st.get("height", 0))
            fps_raw = st.get("r_frame_rate", "30/1")
            num, den = [float(x) for x in fps_raw.split("/")]
            fps = round(num / den, 3) if den else 30.0
            dur = float(st.get("duration", 0))
            return w, h, fps, dur
        except Exception:
            return 0, 0, 0.0, 0.0
