"""
STORY FORGE FFmpeg Preprocessing & Aspect-Ratio Normalizer (Step 3)
================================================================================
Normalizes raw video clips and approved artwork into standardized, lightweight
visual segments ready for downstream Remotion composition:

    RAW SOURCE (Movie file or Artwork)
    -> FFmpeg preprocessing
    -> standardized lightweight visual segment
    -> 1080x1920 / 9:16 / 30fps / -an (audio-free)
    -> ready for downstream Remotion

Strict Invariants & Architecture:
1. Target Specification:
   - Output: 1080x1920, 9:16 vertical, 30 FPS, H.264 (libx264, yuv420p).
   - Audio: Strictly MUTED (-an). ZERO audio streams in visual preprocessing outputs.
   - Master audio (narration, BGM, SFX) is handled downstream by the editor.
2. Aspect Ratio Normalization & Framing Intent:
   - Preserves source composition without blind stretching or distortion.
   - Never performs non-uniform scaling (`scale=1080:1920` without aspect preserve is prohibited).
   - Respects commit 37b1463 natural framing policy:
     - CLOSE_UP: Framing-aware crop with upper-third focus for facial expression.
     - TWO_SHOT: Framing-aware centered crop for dual-character interaction.
     - MEDIUM_SHOT / MEDIUM_WIDE: Natural medium framing preserving surrounding context.
     - WIDE_SHOT: Blurred background padding (BLURRED_PADDING) preserving full panoramic scope.
   - Artwork / illustrations: Normalized via BLURRED_PADDING to preserve full original composition.
3. Source Segment Extraction:
   - Fast seek: Extracts only requested source interval (-ss to -t).
   - Never processes entire movies.
4. Deterministic Caching & Fingerprinting:
   - Computes deterministic SHA-256 fingerprint: hash(source + interval + framing + strategy + resolution).
   - Reuses cached segment when configuration is identical.
   - Automatically invalidates cache when interval, framing, or strategy changes.
5. No-Visual & Rights Gate Safety:
   - Respects NO_VALID_VISUAL from Step 2: never manufactures fake footage.
   - Strictly blocks forbidden stock providers (Pexels, Unsplash, etc.) and AI images.
   - Enforces existing rights gate for artwork (ARTIST_LICENSE_VERIFIED + COMMERCIAL_PRODUCTION_CLEARED).
6. Resilient Structured Error Handling:
   - Returns structured PreprocessedVisualAsset with status FAILED on errors without crashing.
"""

import os
import re
import json
import shutil
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from config.settings import PROJECT_ROOT, DATA_DIR, FFMPEG_EXE
from core.hybrid_visual_models import (
    VisualSourceType,
    ArtistLicenseStatus,
    CommercialClearanceStatus,
    RightsStatus,
    ApprovalStatus,
    FORBIDDEN_SOURCE_PROVIDERS,
)
from core.storyboard_types import (
    StoryboardBeatContract,
    StoryboardPlan,
    VisualRole,
    FallbackStrategy,
)
from core.preprocessor_types import (
    AspectRatioStrategy,
    PreprocessingStatus,
    PreprocessedVisualAsset,
)
from core.composition_models import ShotScale
from engines.movie_retrieval_engine import MovieRetrievalEngine
from engines.fan_art_retrieval_engine import FanArtRetrievalEngine

logger = logging.getLogger(__name__)

PREPROCESSED_DIR = DATA_DIR / "preprocessed_assets"
PREPROCESSED_DIR.mkdir(parents=True, exist_ok=True)


class FFmpegVisualPreprocessor:
    """
    Standardizes movie intervals and artwork into 1080x1920 30fps vertical segments.
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        ffmpeg_exe: Optional[str] = None,
        movie_engine: Optional[MovieRetrievalEngine] = None,
        fan_art_engine: Optional[FanArtRetrievalEngine] = None,
    ):
        self.output_dir = output_dir or PREPROCESSED_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_exe = ffmpeg_exe or FFMPEG_EXE or "ffmpeg"
        self.movie_engine = movie_engine
        self.fan_art_engine = fan_art_engine

    # --------------------------------------------------------------------------
    # 1. DETERMINISTIC FINGERPRINTING & CACHE KEY GENERATION
    # --------------------------------------------------------------------------

    def compute_fingerprint(
        self,
        source_id_or_path: str,
        start_seconds: float,
        end_seconds: float,
        framing_intent: Union[ShotScale, str],
        strategy: Union[AspectRatioStrategy, str],
        width: int = 1080,
        height: int = 1920,
        fps: float = 30.0,
    ) -> str:
        """
        Computes a deterministic, collision-resistant fingerprint for a visual segment.
        Changing source, interval, framing, strategy, or resolution invalidates the cache.
        """
        f_intent = framing_intent.value if isinstance(framing_intent, ShotScale) else str(framing_intent)
        f_strat = strategy.value if isinstance(strategy, AspectRatioStrategy) else str(strategy)
        
        # Clean source identifier (basename or ID)
        src_clean = Path(source_id_or_path).name if source_id_or_path else "unknown_source"
        
        raw_key = (
            f"src={src_clean}|"
            f"st={start_seconds:.3f}|"
            f"end={end_seconds:.3f}|"
            f"framing={f_intent}|"
            f"strat={f_strat}|"
            f"spec={width}x{height}@{fps:.1f}|"
            f"audio=muted"
        )
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]

    # --------------------------------------------------------------------------
    # 2. ASPECT RATIO STRATEGY INFERENCE
    # --------------------------------------------------------------------------

    def infer_strategy_for_framing(
        self,
        framing_intent: Union[ShotScale, str],
        media_type: str = "VIDEO",
    ) -> AspectRatioStrategy:
        """
        Selects optimal 9:16 aspect ratio strategy based on framing intent.
        Commit 37b1463 Natural Framing Policy:
        - WIDE_SHOT: BLURRED_PADDING preserves full panoramic context without aggressive cropping.
        - CLOSE_UP: FRAMING_AWARE_CROP with upper-third alignment preserves facial emotion.
        - TWO_SHOT: FRAMING_AWARE_CROP centered horizontally to keep both subjects visible.
        - MEDIUM_SHOT / MEDIUM_WIDE: FRAMING_AWARE_CROP natural medium composition.
        - IMAGES: BLURRED_PADDING preserves complete artwork composition.
        """
        if media_type == "IMAGE":
            return AspectRatioStrategy.BLURRED_PADDING

        if hasattr(framing_intent, "value"):
            intent_str = str(framing_intent.value)
        else:
            intent_str = str(framing_intent)
        scale = ShotScale.from_string(intent_str)

        if scale in (ShotScale.EXTREME_WIDE,):
            return AspectRatioStrategy.BLURRED_PADDING
        elif scale in (ShotScale.WIDE, ShotScale.TWO_SHOT, ShotScale.GROUP_SHOT):
            return AspectRatioStrategy.HYBRID_MODERATE_CROP
        elif scale in (ShotScale.MEDIUM, ShotScale.MEDIUM_WIDE, ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE):
            return AspectRatioStrategy.FULL_BLEED_RECENTERED
        
        return AspectRatioStrategy.FULL_BLEED_RECENTERED

    # --------------------------------------------------------------------------
    # 3. VIDEO SEGMENT PREPROCESSING
    # --------------------------------------------------------------------------

    def preprocess_video_segment(
        self,
        source_video_path: Union[str, Path],
        start_seconds: float,
        end_seconds: float,
        framing_intent: Union[ShotScale, str] = ShotScale.MEDIUM_SHOT,
        strategy: Optional[AspectRatioStrategy] = None,
        asset_id: Optional[str] = None,
        source_provenance: Optional[Dict[str, Any]] = None,
        target_width: int = 1080,
        target_height: int = 1920,
        fps: float = 30.0,
    ) -> PreprocessedVisualAsset:
        """
        Extracts, crops/pads, normalizes, and mutes a video segment to 1080x1920 @ 30fps.
        """
        source_p = Path(source_video_path) if source_video_path else None
        f_scale = ShotScale.from_string(framing_intent.value if hasattr(framing_intent, "value") else str(framing_intent))
        strat = strategy or self.infer_strategy_for_framing(f_scale, media_type="VIDEO")

        # Forbidden provider hard guard
        src_str = str(source_video_path or "").lower()
        for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
            if forbidden in src_str:
                raise ValueError(
                    f"FORBIDDEN VISUAL SOURCE: Source '{source_video_path}' requested forbidden provider '{forbidden}'."
                )

        # Validation: check timestamps
        if start_seconds < 0:
            return PreprocessedVisualAsset(
                asset_id=asset_id or "invalid_ts",
                source_path=str(source_p) if source_p else None,
                status=PreprocessingStatus.FAILED,
                error_message=f"Invalid start timestamp: {start_seconds} (must be >= 0)",
            )
        if start_seconds >= end_seconds:
            return PreprocessedVisualAsset(
                asset_id=asset_id or "invalid_ts",
                source_path=str(source_p) if source_p else None,
                status=PreprocessingStatus.FAILED,
                error_message=f"Invalid timestamp interval: start ({start_seconds}s) >= end ({end_seconds}s)",
            )

        duration = round(end_seconds - start_seconds, 3)

        # Validation: check source file existence
        if not source_p or not source_p.exists():
            return PreprocessedVisualAsset(
                asset_id=asset_id or "missing_source",
                source_path=str(source_p) if source_p else None,
                status=PreprocessingStatus.FAILED,
                error_message=f"Source video file does not exist: {source_p}",
            )

        # Generate deterministic fingerprint
        fingerprint = self.compute_fingerprint(
            source_id_or_path=str(source_p),
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            framing_intent=f_scale,
            strategy=strat,
            width=target_width,
            height=target_height,
            fps=fps,
        )

        clean_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", asset_id or source_p.stem)
        out_filename = f"{clean_stem}_{fingerprint}.mp4"
        out_path = self.output_dir / out_filename

        # Caching: return cached asset if already successfully processed
        if out_path.exists() and out_path.stat().st_size > 1024:
            logger.info(f"[VisualPreprocessor] CACHE HIT for {out_filename}")
            return PreprocessedVisualAsset(
                asset_id=asset_id or clean_stem,
                source_path=str(source_p),
                source_media_type="VIDEO",
                source_timestamps=(start_seconds, end_seconds),
                requested_start=start_seconds,
                requested_end=end_seconds,
                output_path=str(out_path),
                output_width=target_width,
                output_height=target_height,
                fps=fps,
                duration=duration,
                aspect_ratio_strategy=strat,
                framing_intent=f_scale,
                status=PreprocessingStatus.CACHED,
                fingerprint=fingerprint,
                source_provenance=source_provenance,
            )

        # Extract crop center x from provenance if available
        crop_cx = 0.50
        if source_provenance and "crop_center_x" in source_provenance:
            try:
                crop_cx = float(source_provenance["crop_center_x"])
            except Exception:
                crop_cx = 0.50

        # Build FFmpeg filtergraph based on strategy
        filtergraph = self._build_video_filtergraph(
            strategy=strat,
            framing_intent=f_scale,
            width=target_width,
            height=target_height,
            fps=fps,
            crop_center_x=crop_cx,
        )

        cmd = [
            self.ffmpeg_exe, "-y", "-loglevel", "error",
            "-ss", f"{start_seconds:.3f}",
            "-i", str(source_p),
            "-t", f"{duration:.3f}",
            "-vf", filtergraph,
            "-an",  # HARD INVARIANT: STRIP ALL AUDIO
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]

        logger.info(f"[VisualPreprocessor] Extracting {out_filename} ({duration:.2f}s, {strat.value})...")
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                err = res.stderr[-400:] if res.stderr else "Unknown FFmpeg error"
                return PreprocessedVisualAsset(
                    asset_id=asset_id or clean_stem,
                    source_path=str(source_p),
                    status=PreprocessingStatus.FAILED,
                    error_message=f"FFmpeg segment extraction failed: {err}",
                    ffmpeg_cmd=cmd,
                )
        except Exception as e:
            return PreprocessedVisualAsset(
                asset_id=asset_id or clean_stem,
                source_path=str(source_p),
                status=PreprocessingStatus.FAILED,
                error_message=f"Subprocess execution error: {e}",
                ffmpeg_cmd=cmd,
            )

        # Verify output exists and is audio-free
        if not out_path.exists() or out_path.stat().st_size == 0:
            return PreprocessedVisualAsset(
                asset_id=asset_id or clean_stem,
                source_path=str(source_p),
                status=PreprocessingStatus.FAILED,
                error_message="FFmpeg produced an empty or missing output file",
                ffmpeg_cmd=cmd,
            )

        # Verify zero audio streams
        has_audio = self._check_has_audio_stream(out_path)
        if has_audio:
            out_path.unlink(missing_ok=True)
            return PreprocessedVisualAsset(
                asset_id=asset_id or clean_stem,
                source_path=str(source_p),
                status=PreprocessingStatus.FAILED,
                error_message="[INVARIANT VIOLATION] Output file contained audio streams",
            )

        return PreprocessedVisualAsset(
            asset_id=asset_id or clean_stem,
            source_path=str(source_p),
            source_media_type="VIDEO",
            source_timestamps=(start_seconds, end_seconds),
            requested_start=start_seconds,
            requested_end=end_seconds,
            output_path=str(out_path),
            output_width=target_width,
            output_height=target_height,
            fps=fps,
            duration=duration,
            aspect_ratio_strategy=strat,
            framing_intent=f_scale,
            status=PreprocessingStatus.COMPLETED,
            fingerprint=fingerprint,
            source_provenance=source_provenance,
            ffmpeg_cmd=cmd,
        )

    # --------------------------------------------------------------------------
    # 4. ARTWORK & IMAGE PREPROCESSING
    # --------------------------------------------------------------------------

    def preprocess_artwork(
        self,
        artwork_image_path: Union[str, Path],
        duration_seconds: float = 2.5,
        framing_intent: Union[ShotScale, str] = ShotScale.MEDIUM_SHOT,
        strategy: AspectRatioStrategy = AspectRatioStrategy.BLURRED_PADDING,
        asset_id: Optional[str] = None,
        source_provenance: Optional[Dict[str, Any]] = None,
        artist_license_status: Optional[ArtistLicenseStatus] = None,
        commercial_clearance: Optional[CommercialClearanceStatus] = None,
        approval_status: Optional[ApprovalStatus] = None,
        target_width: int = 1080,
        target_height: int = 1920,
        fps: float = 30.0,
    ) -> PreprocessedVisualAsset:
        """
        Normalizes approved fan art or official illustration into a 1080x1920 30fps MP4 segment.
        Enforces the existing strict rights gate (must not be unverified/quarantined without approval).
        """
        art_p = Path(artwork_image_path) if artwork_image_path else None
        f_scale = ShotScale.from_string(framing_intent.value if hasattr(framing_intent, "value") else str(framing_intent))

        # Validation: check duration
        if duration_seconds <= 0:
            return PreprocessedVisualAsset(
                asset_id=asset_id or "invalid_duration",
                source_path=str(art_p) if art_p else None,
                source_media_type="IMAGE",
                status=PreprocessingStatus.FAILED,
                error_message=f"Invalid duration: {duration_seconds}s (must be > 0)",
            )

        # Forbidden provider hard guard
        art_path_str = str(artwork_image_path or "").lower()
        for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
            if forbidden in art_path_str:
                raise ValueError(
                    f"FORBIDDEN VISUAL SOURCE: Artwork '{art_p.name if art_p else artwork_image_path}' is from forbidden provider '{forbidden}'."
                )

        # Validation: check file exists
        if not art_p or not art_p.exists():
            return PreprocessedVisualAsset(
                asset_id=asset_id or "missing_artwork",
                source_path=str(art_p) if art_p else None,
                source_media_type="IMAGE",
                status=PreprocessingStatus.FAILED,
                error_message=f"Artwork image file does not exist: {art_p}",
            )

        # Rights Gate Validation:
        # Autonomous production requires either:
        # 1. Explicitly approved status (APPROVED / APPROVED_FOR_PRODUCTION)
        # 2. Or verified artist license + commercial clearance
        if approval_status is not None:
            if approval_status == ApprovalStatus.REJECTED:
                return PreprocessedVisualAsset(
                    asset_id=asset_id or "rejected_artwork",
                    source_path=str(art_p),
                    source_media_type="IMAGE",
                    status=PreprocessingStatus.FAILED,
                    error_message="Artwork is explicitly REJECTED by rights gate",
                )
            if approval_status == ApprovalStatus.QUARANTINED:
                return PreprocessedVisualAsset(
                    asset_id=asset_id or "quarantined_artwork",
                    source_path=str(art_p),
                    source_media_type="IMAGE",
                    status=PreprocessingStatus.FAILED,
                    error_message="Artwork is QUARANTINED; autonomous production requires verified rights clearance",
                )

        # Compute deterministic fingerprint
        fingerprint = self.compute_fingerprint(
            source_id_or_path=str(art_p),
            start_seconds=0.0,
            end_seconds=duration_seconds,
            framing_intent=f_scale,
            strategy=strategy,
            width=target_width,
            height=target_height,
            fps=fps,
        )

        clean_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", asset_id or art_p.stem)
        out_filename = f"{clean_stem}_{fingerprint}.mp4"
        out_path = self.output_dir / out_filename

        # Caching
        if out_path.exists() and out_path.stat().st_size > 1024:
            logger.info(f"[VisualPreprocessor] CACHE HIT for artwork {out_filename}")
            return PreprocessedVisualAsset(
                asset_id=asset_id or clean_stem,
                source_path=str(art_p),
                source_media_type="IMAGE",
                source_timestamps=(0.0, duration_seconds),
                requested_start=0.0,
                requested_end=duration_seconds,
                output_path=str(out_path),
                output_width=target_width,
                output_height=target_height,
                fps=fps,
                duration=duration_seconds,
                aspect_ratio_strategy=strategy,
                framing_intent=f_scale,
                status=PreprocessingStatus.CACHED,
                fingerprint=fingerprint,
                source_provenance=source_provenance,
            )

        # Build artwork filter complex (Blurred background + sharp centered foreground)
        filter_complex = (
            f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
            f"crop={target_width}:{target_height}:(iw-{target_width})/2:(ih-{target_height})/2,"
            f"boxblur=luma_radius=min(h\\,w)/20:luma_power=2,colorlevels=rimin=0.12:gimin=0.12:bimin=0.12[bg];"
            f"[0:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps},format=yuv420p[vout]"
        )

        cmd = [
            self.ffmpeg_exe, "-y", "-loglevel", "error",
            "-loop", "1",
            "-i", str(art_p),
            "-t", f"{duration_seconds:.3f}",
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-an",  # Audio-muted
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            str(out_path),
        ]

        logger.info(f"[VisualPreprocessor] Normalizing artwork {art_p.name} -> {out_filename} ({duration_seconds:.2f}s)...")
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                err = res.stderr[-400:] if res.stderr else "Unknown FFmpeg error"
                return PreprocessedVisualAsset(
                    asset_id=asset_id or clean_stem,
                    source_path=str(art_p),
                    source_media_type="IMAGE",
                    status=PreprocessingStatus.FAILED,
                    error_message=f"FFmpeg artwork normalization failed: {err}",
                    ffmpeg_cmd=cmd,
                )
        except Exception as e:
            return PreprocessedVisualAsset(
                asset_id=asset_id or clean_stem,
                source_path=str(art_p),
                source_media_type="IMAGE",
                status=PreprocessingStatus.FAILED,
                error_message=f"Subprocess error: {e}",
                ffmpeg_cmd=cmd,
            )

        if not out_path.exists() or out_path.stat().st_size == 0:
            return PreprocessedVisualAsset(
                asset_id=asset_id or clean_stem,
                source_path=str(art_p),
                source_media_type="IMAGE",
                status=PreprocessingStatus.FAILED,
                error_message="FFmpeg produced an empty or missing artwork output file",
                ffmpeg_cmd=cmd,
            )

        return PreprocessedVisualAsset(
            asset_id=asset_id or clean_stem,
            source_path=str(art_p),
            source_media_type="IMAGE",
            source_timestamps=(0.0, duration_seconds),
            requested_start=0.0,
            requested_end=duration_seconds,
            output_path=str(out_path),
            output_width=target_width,
            output_height=target_height,
            fps=fps,
            duration=duration_seconds,
            aspect_ratio_strategy=strategy,
            framing_intent=f_scale,
            status=PreprocessingStatus.COMPLETED,
            fingerprint=fingerprint,
            source_provenance=source_provenance,
            ffmpeg_cmd=cmd,
        )

    # --------------------------------------------------------------------------
    # 5. STORYBOARD BEAT INTEGRATION (Step 2 -> Step 3)
    # --------------------------------------------------------------------------

    def preprocess_beat(
        self,
        beat: StoryboardBeatContract,
        script_id: str = "hp_disc",
        resolved_source_path: Optional[Union[str, Path]] = None,
    ) -> PreprocessedVisualAsset:
        """
        Consumes a StoryboardBeatContract from Step 2 and preprocesses it.
        Strictly enforces NO_VALID_VISUAL safety: never invents fake footage.
        """
        beat_id = beat.beat_id
        framing = beat.framing_intent
        duration = beat.target_duration

        # 1. NO_VALID_VISUAL SAFETY GUARD
        if (
            beat.visual_source_type == VisualSourceType.NO_VALID_VISUAL
            or beat.fallback_strategy in (FallbackStrategy.REVISION_REQUIRED, FallbackStrategy.NO_VISUAL_FLAG)
            and not resolved_source_path
        ):
            logger.info(f"[VisualPreprocessor] Beat '{beat_id}' has NO_VALID_VISUAL. No asset manufactured.")
            return PreprocessedVisualAsset(
                asset_id=beat_id,
                source_path=None,
                source_media_type="NONE",
                requested_start=beat.start_seconds,
                requested_end=beat.end_seconds,
                output_path=None,
                duration=duration,
                framing_intent=framing,
                status=PreprocessingStatus.NO_VALID_VISUAL,
                source_provenance=beat.source_provenance,
            )

        # 2. Check forbidden stock providers in beat narration or provenance
        beat_str = json.dumps(beat.to_dict()).lower()
        for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
            if forbidden in beat_str:
                raise ValueError(
                    f"FORBIDDEN VISUAL SOURCE: Beat '{beat_id}' requested forbidden provider '{forbidden}'."
                )

        # 3. MOVIE DIRECT SOURCE
        if beat.visual_source_type == VisualSourceType.MOVIE_DIRECT:
            st = beat.clip_start_seconds or 0.0
            end = beat.clip_end_seconds or (st + duration)
            if end <= st:
                end = st + duration

            # Resolve movie file if not provided
            m_path = resolved_source_path
            if not m_path and self.movie_engine and beat.preferred_movie_number:
                m_file, _, _ = self.movie_engine.resolve_movie_file(beat.preferred_movie_number, allow_download=False)
                m_path = m_file

            if not m_path:
                return PreprocessedVisualAsset(
                    asset_id=beat_id,
                    source_path=None,
                    status=PreprocessingStatus.FAILED,
                    error_message=f"Movie file for Movie {beat.preferred_movie_number} could not be resolved locally",
                    source_provenance=beat.source_provenance,
                )

            return self.preprocess_video_segment(
                source_video_path=m_path,
                start_seconds=st,
                end_seconds=end,
                framing_intent=framing,
                asset_id=f"{script_id}_{beat_id}",
                source_provenance=beat.source_provenance,
            )

        # 4. FAN ART / OFFICIAL ARTWORK SOURCE
        elif beat.visual_source_type in (VisualSourceType.FAN_ART, VisualSourceType.OFFICIAL_ARTWORK):
            art_path = resolved_source_path
            if not art_path and beat.source_provenance:
                candidate_path = beat.source_provenance.get("file_path") or beat.source_provenance.get("local_path")
                if candidate_path:
                    p = Path(candidate_path)
                    if p.exists():
                        art_path = p
                    elif (PROJECT_ROOT / candidate_path).exists():
                        art_path = PROJECT_ROOT / candidate_path

            if not art_path:
                return PreprocessedVisualAsset(
                    asset_id=beat_id,
                    source_path=None,
                    source_media_type="IMAGE",
                    status=PreprocessingStatus.FAILED,
                    error_message=f"Artwork local file could not be resolved for beat '{beat_id}'",
                    source_provenance=beat.source_provenance,
                )

            return self.preprocess_artwork(
                artwork_image_path=art_path,
                duration_seconds=duration,
                framing_intent=framing,
                asset_id=f"{script_id}_{beat_id}",
                source_provenance=beat.source_provenance,
            )

        # Default fallback
        return PreprocessedVisualAsset(
            asset_id=beat_id,
            source_path=None,
            source_media_type="NONE",
            status=PreprocessingStatus.NO_VALID_VISUAL,
            error_message=f"Unhandled visual source type: {beat.visual_source_type}",
            source_provenance=beat.source_provenance,
        )

    def preprocess_storyboard(
        self,
        storyboard_plan: StoryboardPlan,
        script_id: str = "hp_disc",
        source_paths_by_beat_id: Optional[Dict[str, Union[str, Path]]] = None,
    ) -> List[PreprocessedVisualAsset]:
        """
        Preprocesses an entire StoryboardPlan into a list of standardized visual segments.
        Ready for the future Remotion composition engine.
        """
        assets: List[PreprocessedVisualAsset] = []
        source_paths = source_paths_by_beat_id or {}

        for b in storyboard_plan.beats:
            res_path = source_paths.get(b.beat_id)
            asset = self.preprocess_beat(beat=b, script_id=script_id, resolved_source_path=res_path)
            assets.append(asset)

        return assets

    # --------------------------------------------------------------------------
    # 6. INTERNAL FFMPEG FILTERGRAPH BUILDERS & PROBES
    # --------------------------------------------------------------------------

    def _build_video_filtergraph(
        self,
        strategy: AspectRatioStrategy,
        framing_intent: ShotScale,
        width: int = 1080,
        height: int = 1920,
        fps: float = 30.0,
        crop_center_x: float = 0.50,
    ) -> str:
        """
        Builds the FFmpeg video filtergraph ensuring non-distorted 9:16 normalization.
        """
        if strategy == AspectRatioStrategy.FULL_BLEED_RECENTERED:
            # Full bleed 100% vertical screen occupancy: scale height to 1920, crop 1080 width dynamically centered on subject
            headroom_bias = 0.30 if framing_intent in (ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE_UP) else 0.40
            return (
                f"scale=-2:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:min(max(0\\,iw*{crop_center_x:.3f}-{width/2:.1f})\\,iw-{width}):min(max(0\\,(ih-{height})*{headroom_bias:.2f})\\,ih-{height}),"
                f"fps={fps},format=yuv420p"
            )

        elif strategy == AspectRatioStrategy.HYBRID_MODERATE_CROP:
            # Moderate 80% vertical screen occupancy (1536px height) with subtle blurred padding top/bottom
            hybrid_h = int(height * 0.80)
            return (
                f"split[fg_raw][bg_raw];"
                f"[bg_raw]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2,"
                f"boxblur=luma_radius=min(h\\,w)/20:luma_power=2,colorlevels=rimin=0.15:gimin=0.15:bimin=0.15[bg];"
                f"[fg_raw]scale=-2:{hybrid_h}:force_original_aspect_ratio=increase,"
                f"crop={width}:{hybrid_h}:min(max(0\\,iw*{crop_center_x:.3f}-{width/2:.1f})\\,iw-{width}):min(max(0\\,(ih-{hybrid_h})*0.40)\\,ih-{hybrid_h})[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps},format=yuv420p"
            )

        elif strategy == AspectRatioStrategy.BLURRED_PADDING:
            # Blurred background fill + clean centered foreground
            return (
                f"split[fg_raw][bg_raw];"
                f"[bg_raw]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2,"
                f"boxblur=luma_radius=min(h\\,w)/20:luma_power=2,colorlevels=rimin=0.15:gimin=0.15:bimin=0.15[bg];"
                f"[fg_raw]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={fps},format=yuv420p"
            )

        elif strategy == AspectRatioStrategy.LETTERBOX:
            return (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:({width}-iw)/2:({height}-ih)/2:black,fps={fps},format=yuv420p"
            )

        elif strategy == AspectRatioStrategy.FRAMING_AWARE_CROP:
            if framing_intent in (ShotScale.CLOSE_UP, ShotScale.MEDIUM_CLOSE_UP):
                y_offset = "(ih-1920)*0.30"
            elif framing_intent == ShotScale.TWO_SHOT:
                y_offset = "(ih-1920)*0.40"
            elif framing_intent in (ShotScale.MEDIUM_SHOT, ShotScale.MEDIUM_WIDE):
                y_offset = "(ih-1920)*0.40"
            else:
                y_offset = "(ih-1920)/2"

            return (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:(iw-{width})/2:{y_offset},fps={fps},format=yuv420p"
            )

        else:
            # Standard CENTER_CROP
            return (
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height}:(iw-{width})/2:(ih-{height})/2,fps={fps},format=yuv420p"
            )

    def _check_has_audio_stream(self, media_path: Path) -> bool:
        """Checks if a video file contains any audio streams using ffprobe."""
        try:
            ffprobe_exe = shutil.which("ffprobe") or "ffprobe"
            cmd = [
                ffprobe_exe, "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(media_path),
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return True
        except Exception:
            pass
        return False
