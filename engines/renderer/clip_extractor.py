"""
STORY FORGE — Phase 5: Exact Clip Extractor
============================================
Part 3 of the 34-part Phase 5 specification.

Extracts precise source intervals from movie files using FFmpeg.

INVARIANTS:
  - NO stretch, loop, repeat, reverse, or semantic extension.
  - Exactly source_clip_start → source_clip_end from the source movie.
  - If the clip is shorter than the narration interval, the renderer
    pads with the clip's natural end rather than looping.
  - The anti-loop enforcement is the caller's responsibility.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from engines.edl.models import EDLEntry

logger = logging.getLogger("ExactClipExtractor")


@dataclass
class ExtractedClip:
    """Result of extracting one source clip."""
    beat_id: str
    source_video: str
    source_start: float
    source_end: float
    output_path: Path
    duration: float
    sha256: str = ""
    extraction_ok: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "source_video": self.source_video,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "output_path": str(self.output_path),
            "duration": round(self.duration, 4),
            "sha256": self.sha256,
            "extraction_ok": self.extraction_ok,
            "error": self.error,
        }


class ExactClipExtractor:
    """
    Extracts exact source intervals from movie files.

    This is a DUMB extractor — it reads the EDL clip window
    and produces exactly that segment.  No semantic decisions.
    """

    def __init__(
        self,
        movies_dir: Optional[Path] = None,
        scratch_dir: Optional[Path] = None,
        video_codec: str = "libx264",
        video_crf: int = 18,
        fps: int = 30,
    ):
        if movies_dir is None:
            try:
                from config.settings import PROJECT_ROOT
                movies_dir = PROJECT_ROOT / "data" / "movies"
            except ImportError:
                movies_dir = Path("data/movies")
        self.movies_dir = Path(movies_dir)

        if scratch_dir is None:
            try:
                from config.settings import PROJECT_ROOT
                scratch_dir = PROJECT_ROOT / "data" / "temp" / "phase5_clips"
            except ImportError:
                scratch_dir = Path("data/temp/phase5_clips")
        self.scratch_dir = Path(scratch_dir)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

        self.video_codec = video_codec
        self.video_crf = video_crf
        self.fps = fps

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_clip(
        self,
        entry: EDLEntry,
        crop_filter: Optional[str] = None,
        output_dir: Optional[Path] = None,
    ) -> ExtractedClip:
        """
        Extract exactly entry.source_clip_start → entry.source_clip_end
        from entry.source_video, applying the crop_filter if provided.

        Args:
            entry: EDL entry specifying the source interval.
            crop_filter: Optional FFmpeg video filter string from the crop plan
                         (e.g. "crop=540:960:690:0,scale=1080:1920:flags=lanczos,fps=30").
                         If None, a default centre-crop to 9:16 is applied.
            output_dir: Where to place the extracted clip.

        Returns:
            ExtractedClip — check .extraction_ok before using.
        """
        source_path = self._resolve_source(entry)
        out_dir = Path(output_dir) if output_dir else self.scratch_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        out_name = f"clip_{entry.beat_id}_{entry.source_clip_start:.3f}_{entry.source_clip_end:.3f}.mp4"
        out_path = out_dir / out_name

        clip_duration = round(entry.source_clip_end - entry.source_clip_start, 6)

        if not source_path.exists():
            return ExtractedClip(
                beat_id=entry.beat_id,
                source_video=entry.source_video,
                source_start=entry.source_clip_start,
                source_end=entry.source_clip_end,
                output_path=out_path,
                duration=clip_duration,
                extraction_ok=False,
                error=f"Source file not found: {source_path}",
            )

        vf = crop_filter if crop_filter else self._default_crop_filter(source_path)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(entry.source_clip_start),
            "-t", str(clip_duration),
            "-i", str(source_path),
            # NO -stream_loop — absolute prohibition (Part 5)
            "-vf", vf,
            "-c:v", self.video_codec,
            "-crf", str(self.video_crf),
            "-preset", "fast",
            # Strip all source audio — movie dialogue removal (Part 10)
            "-an",
            "-movflags", "+faststart",
            str(out_path),
        ]

        logger.info(
            "Extracting clip beat='%s' src='%s' [%.3f → %.3f] dur=%.3f",
            entry.beat_id, source_path.name,
            entry.source_clip_start, entry.source_clip_end, clip_duration,
        )

        try:
            result = subprocess.run(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                return ExtractedClip(
                    beat_id=entry.beat_id,
                    source_video=entry.source_video,
                    source_start=entry.source_clip_start,
                    source_end=entry.source_clip_end,
                    output_path=out_path,
                    duration=clip_duration,
                    extraction_ok=False,
                    error=f"FFmpeg error (code {result.returncode}): {result.stderr[-500:]}",
                )
        except subprocess.TimeoutExpired:
            return ExtractedClip(
                beat_id=entry.beat_id,
                source_video=entry.source_video,
                source_start=entry.source_clip_start,
                source_end=entry.source_clip_end,
                output_path=out_path,
                duration=clip_duration,
                extraction_ok=False,
                error="FFmpeg timed out extracting clip.",
            )

        # Compute SHA-256 fingerprint of extracted clip
        sha = self._sha256(out_path) if out_path.exists() else ""

        return ExtractedClip(
            beat_id=entry.beat_id,
            source_video=entry.source_video,
            source_start=entry.source_clip_start,
            source_end=entry.source_clip_end,
            output_path=out_path,
            duration=clip_duration,
            sha256=sha,
            extraction_ok=True,
        )

    def extract_all(
        self,
        entries: List[EDLEntry],
        crop_filters: Optional[Dict[str, str]] = None,
        output_dir: Optional[Path] = None,
    ) -> List[ExtractedClip]:
        """Extract clips for all EDL entries in order."""
        crop_filters = crop_filters or {}
        clips: List[ExtractedClip] = []
        for entry in entries:
            crop_f = crop_filters.get(entry.beat_id)
            clip = self.extract_clip(entry, crop_filter=crop_f, output_dir=output_dir)
            clips.append(clip)
        return clips

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_source(self, entry: EDLEntry) -> Path:
        """Resolve the full path of an EDL source video."""
        if Path(entry.source_video).is_absolute():
            return Path(entry.source_video)
        candidate = self.movies_dir / entry.source_video
        if candidate.exists():
            return candidate
        return self.movies_dir / f"hp{entry.source_movie_id}" / entry.source_video

    def _default_crop_filter(self, source_path: Path) -> str:
        """
        Probe source dimensions and compute a centre-crop to 9:16.
        This should normally NOT be reached — the EDL crop_requirements
        should always provide an explicit crop window from SubjectAwareCompositionEngine.
        """
        try:
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "json",
                str(source_path),
            ]
            r = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=15)
            info = json.loads(r.stdout)
            w = info["streams"][0]["width"]
            h = info["streams"][0]["height"]
        except Exception:
            # Assume 1920x800 (HP source format)
            w, h = 1920, 800

        # Compute 9:16 crop from centre
        target_h = h
        target_w = int(round(target_h * 9 / 16))
        if target_w > w:
            target_w = w
            target_h = int(round(target_w * 16 / 9))
        x = (w - target_w) // 2
        y = (h - target_h) // 2
        return f"crop={target_w}:{target_h}:{x}:{y},scale=1080:1920:flags=lanczos,fps={self.fps}"

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def build_crop_filter_from_edl(entry: EDLEntry, src_w: int = 1920, src_h: int = 800) -> str:
        """
        Build an FFmpeg crop filter from the EDL entry's crop_requirements dict.
        Uses the crop_window stored in EDL; falls back to centre-crop.
        """
        crop = entry.crop_requirements
        if crop and isinstance(crop, dict):
            cw = crop.get("crop_window") or crop
            x = cw.get("x")
            y = cw.get("y")
            w = cw.get("w")
            h = cw.get("h")
            sw = cw.get("src_w", src_w)
            sh = cw.get("src_h", src_h)
            if all(v is not None for v in [x, y, w, h]):
                return f"crop={int(w)}:{int(h)}:{int(x)}:{int(y)},scale=1080:1920:flags=lanczos,fps=30"

        # Fallback: centre-crop from known HP source dimensions
        target_h = src_h
        target_w = int(round(target_h * 9 / 16))
        if target_w > src_w:
            target_w = src_w
            target_h = int(round(target_w * 16 / 9))
        xc = (src_w - target_w) // 2
        yc = (src_h - target_h) // 2
        return f"crop={target_w}:{target_h}:{xc}:{yc},scale=1080:1920:flags=lanczos,fps=30"
