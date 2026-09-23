"""
Step 3: FFmpeg Pre-Processing & Aspect Ratio Normalizer Test Suite
================================================================================
Verifies all required capabilities of Step 3:
 1. Output specification (1080x1920, 30fps, H.264, yuv420p, requested duration).
 2. 9:16 aspect ratio normalization without distortion.
 3. No-stretch behavior (proportional scaling only; no non-uniform stretching).
 4. Framing intent preservation (ShotScale preserved in metadata and strategy logic).
 5. Interval extraction metadata (accurate start, end, duration).
 6. Deterministic fingerprint & cache key generation.
 7. Stale cache invalidation on parameter change.
 8. No-audio output configuration (-an strictly enforced).
 9. NO_VALID_VISUAL handling (truthful status, never manufactures fake footage).
10. Artwork normalization through existing rights gate.
11. Invalid timestamp handling (start >= end, start < 0 return structured errors).
12. Structured FFmpeg failure handling (resilient error return without crashing).
13. Backward compatibility with Step 2 storyboard contracts and plans.
"""

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from core.hybrid_visual_models import (
    VisualSourceType,
    ArtistLicenseStatus,
    CommercialClearanceStatus,
    ApprovalStatus,
    FORBIDDEN_SOURCE_PROVIDERS,
)
from core.storyboard_types import (
    VisualRole,
    TransitionIntent,
    FallbackStrategy,
    StoryboardBeatContract,
    StoryboardPlan,
)
from core.preprocessor_types import (
    AspectRatioStrategy,
    PreprocessingStatus,
    PreprocessedVisualAsset,
)
from engines.movie_retrieval_engine import ShotScale
from engines.ffmpeg_preprocessor import FFmpegVisualPreprocessor


@pytest.fixture
def temp_workspace(tmp_path):
    """Provides isolated temporary directories and synthetic media for testing."""
    cache_dir = tmp_path / "preprocessed_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Create tiny synthetic test video (2 seconds, 640x360 16:9, muted) using FFmpeg if available
    synthetic_video = tmp_path / "synthetic_source_16x9.mp4"
    ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"

    cmd = [
        ffmpeg_exe, "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=duration=3:size=640x360:rate=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an",
        str(synthetic_video),
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    except Exception:
        # Fallback dummy file if ffmpeg is unavailable in test environment
        synthetic_video.write_bytes(b"dummy_mp4_bytes")

    # Create tiny synthetic test image (640x480)
    synthetic_image = tmp_path / "synthetic_artwork.jpg"
    img_cmd = [
        ffmpeg_exe, "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=purple:s=640x480:d=1",
        "-vframes", "1",
        str(synthetic_image),
    ]
    try:
        subprocess.run(img_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    except Exception:
        synthetic_image.write_bytes(b"dummy_image_bytes")

    preprocessor = FFmpegVisualPreprocessor(output_dir=cache_dir)
    return {
        "preprocessor": preprocessor,
        "cache_dir": cache_dir,
        "video": synthetic_video,
        "image": synthetic_image,
    }


# ── Test 1: Output Specification ──────────────────────────────────────────────

def test_01_output_specification(temp_workspace):
    """Verifies target video specification (1080x1920, 30fps, duration, metadata)."""
    prep = temp_workspace["preprocessor"]
    video = temp_workspace["video"]

    asset = prep.preprocess_video_segment(
        source_video_path=video,
        start_seconds=0.5,
        end_seconds=2.0,
        framing_intent=ShotScale.MEDIUM_SHOT,
        asset_id="test_spec_01",
    )

    assert asset.output_width == 1080
    assert asset.output_height == 1920
    assert asset.fps == 30.0
    assert round(asset.duration, 2) == 1.50
    assert asset.requested_start == 0.5
    assert asset.requested_end == 2.0
    assert asset.status in (PreprocessingStatus.COMPLETED, PreprocessingStatus.CACHED)

    # Verify output file exists
    out_file = Path(asset.output_path)
    assert out_file.exists()
    assert out_file.stat().st_size > 0


# ── Test 2: 9:16 Normalization ────────────────────────────────────────────────

def test_02_9_16_normalization(temp_workspace):
    """Verifies strict 9:16 aspect ratio output from a 16:9 source."""
    prep = temp_workspace["preprocessor"]
    video = temp_workspace["video"]

    asset = prep.preprocess_video_segment(
        source_video_path=video,
        start_seconds=0.0,
        end_seconds=1.5,
        framing_intent=ShotScale.MEDIUM_SHOT,
        strategy=AspectRatioStrategy.CENTER_CROP,
        asset_id="test_aspect_02",
    )

    # 1080 / 1920 == 9 / 16 (0.5625)
    aspect_ratio = asset.output_width / asset.output_height
    assert round(aspect_ratio, 4) == round(9 / 16, 4)
    assert asset.aspect_ratio_strategy == AspectRatioStrategy.CENTER_CROP


# ── Test 3: No-Stretch Behavior ───────────────────────────────────────────────

def test_03_no_stretch_behavior(temp_workspace):
    """Verifies that proportional scaling is strictly used, never non-uniform stretching."""
    prep = temp_workspace["preprocessor"]

    # Test all filtergraphs generated by the preprocessor
    for strat in [
        AspectRatioStrategy.CENTER_CROP,
        AspectRatioStrategy.FRAMING_AWARE_CROP,
        AspectRatioStrategy.BLURRED_PADDING,
        AspectRatioStrategy.LETTERBOX,
    ]:
        fg = prep._build_video_filtergraph(
            strategy=strat,
            framing_intent=ShotScale.MEDIUM_SHOT,
            width=1080,
            height=1920,
            fps=30.0,
        )
        # Forbidden: blind distortion `scale=1080:1920` without force_original_aspect_ratio
        assert "scale=1080:1920," not in fg, f"Non-uniform distortion detected in {strat}"
        assert "force_original_aspect_ratio=" in fg, f"Missing proportional aspect ratio constraint in {strat}"


# ── Test 4: Framing Intent Preservation ───────────────────────────────────────

def test_04_framing_intent_preservation(temp_workspace):
    """Verifies framing intent from Step 2 is preserved and drives strategy inference."""
    prep = temp_workspace["preprocessor"]

    # WIDE_SHOT maps to BLURRED_PADDING to prevent losing panoramic landscape
    strat_wide = prep.infer_strategy_for_framing(ShotScale.WIDE_SHOT, media_type="VIDEO")
    assert strat_wide == AspectRatioStrategy.BLURRED_PADDING

    # CLOSE_UP maps to FRAMING_AWARE_CROP with upper-third facial focus
    strat_cu = prep.infer_strategy_for_framing(ShotScale.CLOSE_UP, media_type="VIDEO")
    assert strat_cu == AspectRatioStrategy.FRAMING_AWARE_CROP

    # TWO_SHOT maps to FRAMING_AWARE_CROP
    strat_two = prep.infer_strategy_for_framing(ShotScale.TWO_SHOT, media_type="VIDEO")
    assert strat_two == AspectRatioStrategy.FRAMING_AWARE_CROP

    # Verify filtergraph adjustments for close-up (upper-third vertical crop)
    cu_filter = prep._build_video_filtergraph(
        strategy=AspectRatioStrategy.FRAMING_AWARE_CROP,
        framing_intent=ShotScale.CLOSE_UP,
    )
    assert "(ih-1920)*0.30" in cu_filter


# ── Test 5: Interval Extraction Metadata ──────────────────────────────────────

def test_05_interval_extraction_metadata(temp_workspace):
    """Verifies interval start/end and duration are accurately recorded."""
    prep = temp_workspace["preprocessor"]
    video = temp_workspace["video"]

    asset = prep.preprocess_video_segment(
        source_video_path=video,
        start_seconds=1.25,
        end_seconds=2.75,
        asset_id="test_interval_05",
    )

    assert asset.requested_start == 1.25
    assert asset.requested_end == 2.75
    assert asset.duration == 1.50
    assert asset.source_timestamps == (1.25, 2.75)


# ── Test 6: Deterministic Fingerprint and Cache ────────────────────────────────

def test_06_deterministic_fingerprint_and_cache(temp_workspace):
    """Verifies deterministic fingerprinting and cache hit reuse."""
    prep = temp_workspace["preprocessor"]
    video = temp_workspace["video"]

    fp1 = prep.compute_fingerprint(
        source_id_or_path=str(video),
        start_seconds=0.0,
        end_seconds=1.0,
        framing_intent=ShotScale.MEDIUM_SHOT,
        strategy=AspectRatioStrategy.CENTER_CROP,
    )
    fp2 = prep.compute_fingerprint(
        source_id_or_path=str(video),
        start_seconds=0.0,
        end_seconds=1.0,
        framing_intent=ShotScale.MEDIUM_SHOT,
        strategy=AspectRatioStrategy.CENTER_CROP,
    )
    assert fp1 == fp2

    # First run: completes
    asset1 = prep.preprocess_video_segment(
        source_video_path=video,
        start_seconds=0.0,
        end_seconds=1.0,
        framing_intent=ShotScale.MEDIUM_SHOT,
        strategy=AspectRatioStrategy.CENTER_CROP,
        asset_id="test_cache_06",
    )
    assert asset1.status in (PreprocessingStatus.COMPLETED, PreprocessingStatus.CACHED)

    # Second run with exact same configuration: CACHED hit
    asset2 = prep.preprocess_video_segment(
        source_video_path=video,
        start_seconds=0.0,
        end_seconds=1.0,
        framing_intent=ShotScale.MEDIUM_SHOT,
        strategy=AspectRatioStrategy.CENTER_CROP,
        asset_id="test_cache_06",
    )
    assert asset2.status == PreprocessingStatus.CACHED
    assert asset2.fingerprint == asset1.fingerprint
    assert asset2.output_path == asset1.output_path


# ── Test 7: Stale Cache Invalidation ──────────────────────────────────────────

def test_07_stale_cache_invalidation(temp_workspace):
    """Verifies that changing interval, framing, or strategy invalidates the cache key."""
    prep = temp_workspace["preprocessor"]
    video = temp_workspace["video"]

    base_fp = prep.compute_fingerprint(
        source_id_or_path=str(video),
        start_seconds=0.0,
        end_seconds=1.0,
        framing_intent=ShotScale.MEDIUM_SHOT,
        strategy=AspectRatioStrategy.CENTER_CROP,
    )

    # Alter interval
    diff_interval_fp = prep.compute_fingerprint(
        source_id_or_path=str(video),
        start_seconds=0.5,
        end_seconds=1.5,
        framing_intent=ShotScale.MEDIUM_SHOT,
        strategy=AspectRatioStrategy.CENTER_CROP,
    )
    assert base_fp != diff_interval_fp

    # Alter framing
    diff_framing_fp = prep.compute_fingerprint(
        source_id_or_path=str(video),
        start_seconds=0.0,
        end_seconds=1.0,
        framing_intent=ShotScale.CLOSE_UP,
        strategy=AspectRatioStrategy.CENTER_CROP,
    )
    assert base_fp != diff_framing_fp

    # Alter strategy
    diff_strategy_fp = prep.compute_fingerprint(
        source_id_or_path=str(video),
        start_seconds=0.0,
        end_seconds=1.0,
        framing_intent=ShotScale.MEDIUM_SHOT,
        strategy=AspectRatioStrategy.BLURRED_PADDING,
    )
    assert base_fp != diff_strategy_fp


# ── Test 8: No-Audio Output Configuration ─────────────────────────────────────

def test_08_no_audio_output_configuration(temp_workspace):
    """Verifies that FFmpeg command strictly disables audio with -an."""
    prep = temp_workspace["preprocessor"]
    video = temp_workspace["video"]

    asset = prep.preprocess_video_segment(
        source_video_path=video,
        start_seconds=0.0,
        end_seconds=1.0,
        asset_id="test_no_audio_08",
    )

    if asset.ffmpeg_cmd:
        assert "-an" in asset.ffmpeg_cmd

    # Check that output file has no audio streams
    if asset.output_path and Path(asset.output_path).exists():
        has_audio = prep._check_has_audio_stream(Path(asset.output_path))
        assert has_audio is False


# ── Test 9: NO_VALID_VISUAL Handling ──────────────────────────────────────────

def test_09_no_valid_visual_handling(temp_workspace):
    """Verifies beat marked NO_VALID_VISUAL returns explicit status without inventing footage."""
    prep = temp_workspace["preprocessor"]

    beat = StoryboardBeatContract(
        beat_id="beat_unfilmed_01",
        narrative_phase="EVIDENCE",
        visual_role=VisualRole.DIRECT_EVIDENCE,
        visual_source_type=VisualSourceType.NO_VALID_VISUAL,
        fallback_strategy=FallbackStrategy.REVISION_REQUIRED,
        target_duration=2.5,
    )

    asset = prep.preprocess_beat(beat)
    assert asset.status == PreprocessingStatus.NO_VALID_VISUAL
    assert asset.output_path is None
    assert asset.source_path is None


# ── Test 10: Artwork Normalization Through Existing Rights Gate ───────────────

def test_10_artwork_normalization_through_rights_gate(temp_workspace):
    """Verifies artwork normalization respects rights and blocks quarantined/forbidden assets."""
    prep = temp_workspace["preprocessor"]
    img = temp_workspace["image"]

    # 1. Approved artwork: succeeds
    asset_approved = prep.preprocess_artwork(
        artwork_image_path=img,
        duration_seconds=2.0,
        approval_status=ApprovalStatus.APPROVED,
        asset_id="art_approved_10",
    )
    assert asset_approved.status in (PreprocessingStatus.COMPLETED, PreprocessingStatus.CACHED)
    assert Path(asset_approved.output_path).exists()

    # 2. Quarantined artwork: fails without clearance
    asset_quarantined = prep.preprocess_artwork(
        artwork_image_path=img,
        duration_seconds=2.0,
        approval_status=ApprovalStatus.QUARANTINED,
        asset_id="art_quarantine_10",
    )
    assert asset_quarantined.status == PreprocessingStatus.FAILED
    assert "QUARANTINED" in asset_quarantined.error_message

    # 3. Forbidden stock provider: raises ValueError immediately
    with pytest.raises(ValueError, match="FORBIDDEN VISUAL SOURCE"):
        prep.preprocess_artwork(
            artwork_image_path=Path("C:/data/artworks/pexels_free_wand.jpg"),
            duration_seconds=2.0,
        )


# ── Test 11: Invalid Timestamp Handling ───────────────────────────────────────

def test_11_invalid_timestamp_handling(temp_workspace):
    """Verifies invalid intervals (start >= end or start < 0) return structured failures."""
    prep = temp_workspace["preprocessor"]
    video = temp_workspace["video"]

    # start >= end
    asset_inverted = prep.preprocess_video_segment(
        source_video_path=video,
        start_seconds=5.0,
        end_seconds=2.0,
    )
    assert asset_inverted.status == PreprocessingStatus.FAILED
    assert "start (5.0s) >= end (2.0s)" in asset_inverted.error_message

    # start < 0
    asset_negative = prep.preprocess_video_segment(
        source_video_path=video,
        start_seconds=-1.0,
        end_seconds=2.0,
    )
    assert asset_negative.status == PreprocessingStatus.FAILED
    assert "Invalid start timestamp" in asset_negative.error_message


# ── Test 12: Structured FFmpeg Failure Handling ────────────────────────────────

def test_12_structured_ffmpeg_failure_handling(temp_workspace):
    """Verifies missing source or FFmpeg failure returns structured error without crashing."""
    prep = temp_workspace["preprocessor"]

    non_existent = Path(temp_workspace["cache_dir"]) / "non_existent_movie.mp4"
    asset = prep.preprocess_video_segment(
        source_video_path=non_existent,
        start_seconds=0.0,
        end_seconds=2.0,
    )

    assert asset.status == PreprocessingStatus.FAILED
    assert "does not exist" in asset.error_message


# ── Test 13: Backward Compatibility with Step 2 Storyboard Contracts ──────────

def test_13_backward_compatibility_with_step2_storyboard_contracts(temp_workspace):
    """Verifies seamless consumption of Step 2 StoryboardBeatContract and StoryboardPlan."""
    prep = temp_workspace["preprocessor"]
    video = temp_workspace["video"]
    img = temp_workspace["image"]

    b1 = StoryboardBeatContract(
        beat_id="beat_01_hook",
        narrative_phase="HOOK",
        start_seconds=0.0,
        end_seconds=1.0,
        target_duration=1.0,
        visual_role=VisualRole.DIRECT_EVIDENCE,
        visual_source_type=VisualSourceType.MOVIE_DIRECT,
        clip_start_seconds=0.0,
        clip_end_seconds=1.0,
        preferred_movie_number=1,
    )
    b2 = StoryboardBeatContract(
        beat_id="beat_02_anchor",
        narrative_phase="ANCHOR",
        start_seconds=1.0,
        end_seconds=3.7,
        target_duration=2.7,
        is_anchor=True,
        visual_role=VisualRole.DIRECT_EVIDENCE,
        visual_source_type=VisualSourceType.FAN_ART,
        source_provenance={"file_path": str(img)},
    )
    b3 = StoryboardBeatContract(
        beat_id="beat_03_unfilmed",
        narrative_phase="EVIDENCE",
        start_seconds=3.7,
        end_seconds=5.3,
        target_duration=1.6,
        visual_role=VisualRole.DIRECT_EVIDENCE,
        visual_source_type=VisualSourceType.NO_VALID_VISUAL,
        fallback_strategy=FallbackStrategy.REVISION_REQUIRED,
    )

    plan = StoryboardPlan(
        storyboard_id="sb_compat_test",
        topic_id="disc_neville_test",
        beats=[b1, b2, b3],
        anchor_beat_ids=["beat_02_anchor"],
        total_target_duration=5.3,
    )

    # Preprocess entire storyboard
    source_paths = {"beat_01_hook": video, "beat_02_anchor": img}
    results = prep.preprocess_storyboard(plan, script_id="test_hps", source_paths_by_beat_id=source_paths)

    assert len(results) == 3
    assert results[0].status in (PreprocessingStatus.COMPLETED, PreprocessingStatus.CACHED)
    assert results[0].output_width == 1080
    assert results[0].output_height == 1920

    assert results[1].status in (PreprocessingStatus.COMPLETED, PreprocessingStatus.CACHED)
    assert results[1].source_media_type == "IMAGE"

    assert results[2].status == PreprocessingStatus.NO_VALID_VISUAL
    assert results[2].output_path is None
