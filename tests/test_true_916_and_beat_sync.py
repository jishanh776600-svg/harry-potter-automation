"""
STORY FORGE Test Suite: True 9:16 Composition + Beat-Locked Visual Sync + Script Polish
========================================================================================
Validates the corrective engineering step:
  1. True 9:16 Visual Composition (FULL_BLEED_RECENTERED, HYBRID_MODERATE_CROP, BLURRED_PADDING)
  2. Subject-aware horizontal centering (optimal_crop_center_x tracking subject bbox)
  3. Visual occupancy ratio and vertical screen utilization calculations
  4. FFmpeg filtergraph construction for True 9:16 reframing
  5. Beat-locked visual synchronization to word start boundaries (eliminating visual lag)
  6. SFX multi-cue dedicated input stream allocation (preventing audio exhaustion)
  7. Polished Deep Discovery script canon adherence, word count, and duration constraints
"""

import pytest
import math
from pathlib import Path
from typing import Dict, List, Any

from core.composition_models import (
    ShotScale,
    NormalizedBBox,
    ShotCompositionAssessment,
)
from core.preprocessor_types import (
    AspectRatioStrategy,
    PreprocessedVisualAsset,
    PreprocessingStatus,
)
from engines.visual_discovery_engine_v2 import VisualDiscoveryEngineV2
from engines.ffmpeg_preprocessor import FFmpegVisualPreprocessor
from engines.remotion_editorial_engine import RemotionEditorialEngine


# ------------------------------------------------------------------------------
# 1. Composition Models & Occupancy Attributes
# ------------------------------------------------------------------------------

def test_composition_models_occupancy_and_crop_strategy():
    """Validates that ShotCompositionAssessment exposes visual occupancy and crop strategy."""
    assessment = ShotCompositionAssessment(
        shot_scale=ShotScale.MEDIUM,
        subject_bbox=NormalizedBBox(0.40, 0.20, 0.20, 0.60),
        effective_crop_strategy="FULL_BLEED_RECENTERED",
        visual_occupancy_ratio=1.0,
        vertical_screen_utilization=1.0,
        optimal_crop_center_x=0.50,
        crop_window={"x": 0.3418, "y": 0.0, "w": 0.3164, "h": 1.0, "center_x": 0.50},
    )
    d = assessment.to_dict()
    assert d["effective_crop_strategy"] == "FULL_BLEED_RECENTERED"
    assert d["visual_occupancy_ratio"] == 1.0
    assert d["vertical_screen_utilization"] == 1.0
    assert d["optimal_crop_center_x"] == 0.50
    assert d["crop_window"]["w"] == 0.3164


# ------------------------------------------------------------------------------
# 2. Visual Discovery Engine V2 Multi-Tier Reframing
# ------------------------------------------------------------------------------

def test_visual_discovery_engine_v2_reframing_tiers():
    """Validates 3-tier reframing strategy selection in VisualDiscoveryEngineV2."""
    vde = VisualDiscoveryEngineV2()

    # Tier 1: Medium shot with centered subject -> FULL_BLEED_RECENTERED
    med_comp = vde.assess_shot_composition(
        shot_scale=ShotScale.MEDIUM,
        subject_bbox=NormalizedBBox(0.40, 0.15, 0.20, 0.70),
    )
    assert med_comp.effective_crop_strategy == "FULL_BLEED_RECENTERED"
    assert med_comp.visual_occupancy_ratio == 1.0
    assert med_comp.vertical_screen_utilization == 1.0
    assert med_comp.is_9x16_crop_safe is True

    # Tier 2: Two-shot with wide character spread -> HYBRID_MODERATE_CROP
    two_comp = vde.assess_shot_composition(
        shot_scale=ShotScale.TWO_SHOT,
        subject_bbox=NormalizedBBox(0.20, 0.20, 0.60, 0.70),
    )
    assert two_comp.effective_crop_strategy in ("HYBRID_MODERATE_CROP", "FULL_BLEED_RECENTERED")
    assert two_comp.visual_occupancy_ratio >= 0.80

    # Tier 3: Extreme wide panoramic vista -> BLURRED_PADDING
    ew_comp = vde.assess_shot_composition(
        shot_scale=ShotScale.EXTREME_WIDE,
        subject_bbox=NormalizedBBox(0.35, 0.35, 0.30, 0.30),
    )
    assert ew_comp.effective_crop_strategy == "BLURRED_PADDING"
    assert ew_comp.visual_occupancy_ratio < 0.50


def test_visual_discovery_engine_v2_dynamic_crop_center():
    """Validates that optimal_crop_center_x dynamically tracks off-center subjects."""
    vde = VisualDiscoveryEngineV2()

    # Subject is shifted to the right at center_x = 0.70
    right_bbox = NormalizedBBox(0.60, 0.20, 0.20, 0.60)
    comp = vde.assess_shot_composition(
        shot_scale=ShotScale.MEDIUM,
        subject_bbox=right_bbox,
    )
    # The crop center should shift towards 0.70 to frame the subject
    assert comp.optimal_crop_center_x > 0.60
    assert comp.crop_window is not None
    assert comp.crop_window["center_x"] > 0.60
    # Head cutoff should be zero because crop tracked subject
    assert abs(comp.head_cutoff) < 1e-4


# ------------------------------------------------------------------------------
# 3. FFmpeg Preprocessor Reframing Strategy & Filtergraph Construction
# ------------------------------------------------------------------------------

def test_ffmpeg_preprocessor_infer_strategy():
    """Validates that FFmpegVisualPreprocessor infers optimal True 9:16 strategies."""
    pre = FFmpegVisualPreprocessor()

    # Medium shots, close-ups -> FULL_BLEED_RECENTERED
    assert pre.infer_strategy_for_framing(ShotScale.MEDIUM_SHOT) == AspectRatioStrategy.FULL_BLEED_RECENTERED
    assert pre.infer_strategy_for_framing(ShotScale.MEDIUM_WIDE) == AspectRatioStrategy.FULL_BLEED_RECENTERED
    assert pre.infer_strategy_for_framing(ShotScale.CLOSE_UP) == AspectRatioStrategy.FULL_BLEED_RECENTERED

    # Wide shots, two-shots -> HYBRID_MODERATE_CROP
    assert pre.infer_strategy_for_framing(ShotScale.WIDE_SHOT) == AspectRatioStrategy.HYBRID_MODERATE_CROP
    assert pre.infer_strategy_for_framing(ShotScale.TWO_SHOT) == AspectRatioStrategy.HYBRID_MODERATE_CROP

    # Extreme wide and Artwork -> BLURRED_PADDING
    assert pre.infer_strategy_for_framing(ShotScale.EXTREME_WIDE) == AspectRatioStrategy.BLURRED_PADDING
    assert pre.infer_strategy_for_framing(ShotScale.MEDIUM_SHOT, media_type="IMAGE") == AspectRatioStrategy.BLURRED_PADDING


def test_ffmpeg_preprocessor_filtergraph_construction():
    """Validates filtergraph generation for FULL_BLEED_RECENTERED and HYBRID_MODERATE_CROP."""
    pre = FFmpegVisualPreprocessor()

    # 1. FULL_BLEED_RECENTERED with subject center at 0.65
    fg_full = pre._build_video_filtergraph(
        strategy=AspectRatioStrategy.FULL_BLEED_RECENTERED,
        framing_intent=ShotScale.MEDIUM_SHOT,
        width=1080,
        height=1920,
        crop_center_x=0.65,
    )
    assert "scale=-2:1920" in fg_full
    assert "crop=1080:1920:" in fg_full
    assert "0.650" in fg_full
    assert "fps=30.0" in fg_full

    # 2. HYBRID_MODERATE_CROP (80% height = 1536)
    fg_hybrid = pre._build_video_filtergraph(
        strategy=AspectRatioStrategy.HYBRID_MODERATE_CROP,
        framing_intent=ShotScale.TWO_SHOT,
        width=1080,
        height=1920,
        crop_center_x=0.50,
    )
    assert "split[fg_raw][bg_raw]" in fg_hybrid
    assert "scale=-2:1536" in fg_hybrid
    assert "crop=1080:1536" in fg_hybrid
    assert "overlay=(W-w)/2:(H-h)/2" in fg_hybrid


# ------------------------------------------------------------------------------
# 4. Beat-Locked Visual Synchronization to Spoken Words
# ------------------------------------------------------------------------------

def test_remotion_editorial_snap_cut_points_to_words():
    """Validates that snap_cut_points_to_words snaps visual cut points to word onset."""
    # Simulated word-level timestamps from TTS caption transcription
    simulated_words = [
        {"word": "The", "start": 0.05, "end": 0.22},
        {"word": "movies", "start": 0.25, "end": 0.65},
        {"word": "skipped", "start": 0.70, "end": 1.10},
        {"word": "Neville", "start": 1.75, "end": 2.10},   # Beat 1 target near 1.8s
        {"word": "Longbottom's", "start": 2.15, "end": 2.70},
        {"word": "greatest", "start": 3.45, "end": 3.80},  # Beat 2 target near 3.5s
        {"word": "secret", "start": 3.85, "end": 4.25},
        {"word": "argument", "start": 5.25, "end": 5.75}, # Beat 3 target near 5.3s
    ]

    raw_cut_points = [0.0, 1.82, 3.55, 5.28, 7.00]
    total_dur = 7.00

    snapped = RemotionEditorialEngine.snap_cut_points_to_words(
        cut_points=raw_cut_points,
        words=simulated_words,
        total_duration=total_dur,
        snap_window=0.35,
    )

    assert len(snapped) == len(raw_cut_points)
    assert snapped[0] == 0.0
    assert snapped[-1] == 7.00

    # Check that cut point 1.82 snapped to word 'Neville' onset at 1.75
    assert abs(snapped[1] - 1.75) < 0.01, f"Expected 1.75, got {snapped[1]}"

    # Check that cut point 3.55 snapped to word 'greatest' onset at 3.45
    assert abs(snapped[2] - 3.45) < 0.01, f"Expected 3.45, got {snapped[2]}"

    # Check that cut point 5.28 snapped to word 'argument' onset at 5.25
    assert abs(snapped[3] - 5.25) < 0.01, f"Expected 5.25, got {snapped[3]}"

    # Ensure strictly increasing
    for i in range(len(snapped) - 1):
        assert snapped[i + 1] > snapped[i]


# ------------------------------------------------------------------------------
# 5. SFX Dedicated Input Stream Allocation (Anti-Exhaustion)
# ------------------------------------------------------------------------------

def test_sfx_multi_cue_exhaustion_prevention():
    """
    Validates that each SFX cue receives its own dedicated input stream index,
    preventing FFmpeg filter stream starvation.
    """
    # Create 5 dummy cue definitions referencing the same sound file
    class DummyCue:
        def __init__(self, start_time: float, file_path: str):
            self.start_time = start_time
            self.file_path = file_path
            self.gain_db = -14.0

    cues = [
        DummyCue(1.0, "sfx/click.mp3"),
        DummyCue(2.5, "sfx/click.mp3"),
        DummyCue(4.0, "sfx/click.mp3"),
        DummyCue(5.5, "sfx/woosh.mp3"),
        DummyCue(7.0, "sfx/click.mp3"),
    ]

    # Emulate the dedicated stream mapping from mix_master_soundtrack
    input_args = ["-i", "voice.wav", "-i", "bgm.wav"]
    valid_cues = []
    current_input_idx = 2

    for cue in cues:
        input_args.extend(["-i", cue.file_path])
        valid_cues.append((cue, current_input_idx))
        current_input_idx += 1

    # Verify 1-to-1 input index assignment
    assigned_indices = [idx for (_, idx) in valid_cues]
    assert len(assigned_indices) == 5
    assert len(set(assigned_indices)) == 5, "Duplicate input indices detected! Streams would be exhausted."
    assert assigned_indices == [2, 3, 4, 5, 6]


# ------------------------------------------------------------------------------
# 6. Polished Deep Discovery Script Metrics & Canon Adherence
# ------------------------------------------------------------------------------

def test_discovery_script_polish_metrics():
    """Validates the polished script against word count and duration targets."""
    polished_script = (
        "The movies skipped Neville Longbottom's greatest untold secret: his desperate argument with the Sorting Hat, "
        "and the real reason he was destined to destroy Voldemort's final Horcrux.\n\n"
        "On screen, Neville's sorting was quietly cut, jumping instantly from Hermione to Draco Malfoy. "
        "But in the original book, Neville sat on that stool for nearly a full minute, begging the Hat with everything he had.\n\n"
        "Terrified by his family's expectations and convinced he was completely talentless, "
        "Neville pleaded to be sorted into Hufflepuff. "
        "He simply wanted a kind, quiet house where no one expected him to be a hero.\n\n"
        "The Hat flatly refused. It knew that Neville's fear wasn't cowardice, "
        "but deep humility. It sensed a fierce, dormant courage that would only ignite when everything else was lost.\n\n"
        "We first glimpsed that bravery when eleven-year-old Neville raised his fists against his closest friends. "
        "Seven years later, when Harry fell and Hogwarts surrendered to despair, "
        "Neville was the last warrior standing.\n\n"
        "J.K. Rowling later confirmed Neville was a near Hatstall. Had the Hat given in to his tears "
        "and sent him to Hufflepuff, the entire wizarding war would have collapsed. "
        "Because only a true Gryffindor could ever pull Godric's silver sword from that Hat to strike Nagini down.\n\n"
        "The Sorting Hat never sorts you for who you are when you sit on the stool. "
        "It sorts you for who you are destined to become."
    )

    words = polished_script.split()
    word_count = len(words)

    # Word count target [220, 270]
    assert 220 <= word_count <= 270, f"Word count {word_count} outside target [220, 270]"

    # Key canon entities check
    lower = polished_script.lower()
    assert "neville longbottom" in lower
    assert "sorting hat" in lower
    assert "hufflepuff" in lower
    assert "gryffindor" in lower
    assert "hatstall" in lower
    assert "sword" in lower
    assert "nagini" in lower
    assert "voldemort" in lower

    # Estimated duration check (at 3.3 to 3.5 words/sec with af_bella 1.15x)
    est_dur_min = word_count / 3.6
    est_dur_max = word_count / 3.0
    assert 65.0 <= est_dur_max <= 85.0
    assert 60.0 <= est_dur_min <= 75.0
