"""
STORY FORGE — Subject-Aware Geometric 9:16 Cropping Tests
=========================================================
Verifies:
1. Right-side subject -> crop window moves rightward.
2. Left-side subject -> crop window moves leftward.
3. Centered subject -> crop window remains near dead center.
4. Subject completely outside old center crop -> new subject-aware crop retains it.
5. Multi-subject crop when both fit -> window encloses both subjects.
6. Impossible full containment (subjects too wide) -> explicit failure / partial retention result.
7. Absent required entity -> fails closed without fabricating crop or evidence.
8. Real Case A: m8_elder_wand_snap.mp4 @ ~1.0s (Harry Potter on right retained in 9:16).
9. Real Case B: m3_buckbeak_slash_malfoy.mp4 @ ~6.5s (Buckbeak on left retained, Draco absent and not fabricated).
"""

from pathlib import Path
import pytest
import cv2

from core.composition_models import NormalizedBBox, ShotScale
from engines.visual_evidence.subject_aware_composition import (
    SubjectAwareCompositionEngine,
    CropWindow,
    PostCropVerificationResult,
    compute_crop_fingerprint,
)
from engines.visual_evidence.storyforge_adapter import (
    StoryForgeVisualEvidenceAdapter,
    StoryForgeEvidenceResult,
)
from engines.movie_event.models import MovieEvent
from py_visual_evidence.schema import (
    VisualAssertion,
    EntitySpec,
    BoundingBox,
    EvidenceVerdict,
)
from py_visual_evidence.grounding import OpenVocabularyGrounder

BLIND_CLIPS_DIR = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\py_visual_evidence\test_data\blind_clips")


# ==============================================================================
# 1. Right-Side Subject -> Crop Moves Right
# ==============================================================================
def test_01_right_side_subject_shifts_crop_right():
    engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    # Right-third subject: center_x = 0.74 (1420px). Dead center crop is 735.
    right_bbox = NormalizedBBox(0.66, 0.15, 0.16, 0.70)
    res = engine.compute_crop_and_verify([right_bbox], src_w=1920, src_h=800)

    assert res.is_valid is True
    assert res.is_visible is True
    assert res.is_clipped is False
    assert res.crop_window.x > 735  # Moved right from dead center
    assert res.crop_window.x == 1196
    assert res.crop_window.w == 450
    assert res.retained_subject_ratio >= 0.99


# ==============================================================================
# 2. Left-Side Subject -> Crop Moves Left
# ==============================================================================
def test_02_left_side_subject_shifts_crop_left():
    engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    # Left-third subject: center_x = 0.26 (499px). Dead center crop is 735.
    left_bbox = NormalizedBBox(0.18, 0.15, 0.16, 0.70)
    res = engine.compute_crop_and_verify([left_bbox], src_w=1920, src_h=800)

    assert res.is_valid is True
    assert res.is_visible is True
    assert res.is_clipped is False
    assert res.crop_window.x < 735  # Moved left from dead center
    assert res.crop_window.x == 274
    assert res.crop_window.w == 450
    assert res.retained_subject_ratio >= 0.99


# ==============================================================================
# 3. Centered Subject -> Crop Remains Near Center
# ==============================================================================
def test_03_centered_subject_remains_near_center():
    engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    center_bbox = NormalizedBBox(0.40, 0.20, 0.20, 0.60)  # center_x = 0.50 (960px)
    res = engine.compute_crop_and_verify([center_bbox], src_w=1920, src_h=800)

    assert res.is_valid is True
    assert res.crop_window.x == 735  # Dead center for 1920x800 with 450 crop width
    assert res.crop_window.w == 450
    assert res.retained_subject_ratio >= 0.99


# ==============================================================================
# 4. Subject Completely Outside Old Center Crop -> New Crop Retains It
# ==============================================================================
def test_04_subject_outside_center_crop_retained_by_subject_aware():
    engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    # Far right subject at x=0.80..0.90 (1536px..1728px).
    # Old center crop is [735, 1185], which has 0% overlap with [1536, 1728].
    far_right = NormalizedBBox(0.80, 0.20, 0.10, 0.60)

    # Verify old center crop would have 0% retention
    old_center_x1, old_center_x2 = 735, 1185
    overlap_old = max(0, min(old_center_x2, 1728) - max(old_center_x1, 1536))
    assert overlap_old == 0, "Precondition: Old center crop must have 0 overlap"

    # New subject-aware crop
    res = engine.compute_crop_and_verify([far_right], src_w=1920, src_h=800)
    assert res.is_valid is True
    assert res.is_visible is True
    assert res.is_clipped is False
    assert res.retained_subject_ratio >= 0.99
    # Window spans [1407, 1857] (or clamped to frame max 1470..1920)
    assert res.crop_window.x <= 1536
    assert res.crop_window.x + res.crop_window.w >= 1728


# ==============================================================================
# 5. Multi-Subject Crop When Both Fit
# ==============================================================================
def test_05_multi_subject_crop_when_both_fit():
    engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    # Subject 1 at 0.40..0.48 (center 0.44), Subject 2 at 0.52..0.58 (center 0.55)
    # Union span = 0.40..0.58 (768px..1113px = 345px <= usable crop width 405px)
    sub1 = NormalizedBBox(0.40, 0.20, 0.08, 0.60)
    sub2 = NormalizedBBox(0.52, 0.20, 0.06, 0.60)
    res = engine.compute_crop_and_verify([sub1, sub2], src_w=1920, src_h=800)

    assert res.is_valid is True
    assert res.crop_window.strategy == "MULTI_SUBJECT_CO_PRESENCE"
    assert res.retained_subject_ratio >= 0.99
    assert res.is_clipped is False
    # Window contains both
    assert res.crop_window.x <= 0.40 * 1920
    assert res.crop_window.x + res.crop_window.w >= 0.58 * 1920


# ==============================================================================
# 6. Impossible Full Containment -> Explicit Failure
# ==============================================================================
def test_06_impossible_full_containment_explicit_failure():
    engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    # Subject 1 on far left (0.05), Subject 2 on far right (0.90) -> span 0.85 = 1632px >> 450px
    sub_left = NormalizedBBox(0.05, 0.20, 0.10, 0.60)
    sub_right = NormalizedBBox(0.85, 0.20, 0.10, 0.60)
    res = engine.compute_crop_and_verify([sub_left, sub_right], src_w=1920, src_h=800)

    assert res.is_valid is False
    assert res.primary_rejection_reason == "CROP_MULTI_SUBJECT_LOST"
    assert "CROP_MULTI_SUBJECT_LOST" in res.rejection_reasons
    assert res.retained_subject_ratio < 0.85
    assert "Two required subjects span" in res.explanation


# ==============================================================================
# 7. Absent Required Entity -> No Fabricated Crop / Evidence (Fails Closed)
# ==============================================================================
def test_07_absent_required_entity_fails_closed():
    engine = SubjectAwareCompositionEngine(default_src_w=1920, default_src_h=800)
    # Empty subject list: no entities detected
    res = engine.compute_crop_and_verify(subject_bboxes=[], src_w=1920, src_h=800)

    assert res.is_valid is False
    assert res.is_visible is False
    assert res.primary_rejection_reason == "NO_REQUIRED_ENTITY_FOR_CROP"
    assert res.retained_subject_ratio == 0.0
    assert "Centered crop fallback is prohibited" in res.explanation
    assert res.crop_window.strategy == "FAILED_NO_SUBJECT"


# ==============================================================================
# 8. Real Case A: m8_elder_wand_snap.mp4 @ ~1.0s (Harry Potter on Right)
# ==============================================================================
def test_08_real_case_a_elder_wand_harry_potter_retained():
    clip_path = BLIND_CLIPS_DIR / "m8_elder_wand_snap.mp4"
    assert clip_path.exists(), f"Source clip not found: {clip_path}"

    cap = cv2.VideoCapture(str(clip_path))
    cap.set(cv2.CAP_PROP_POS_MSEC, 1000.0)
    ret, frame = cap.read()
    cap.release()
    assert ret, "Failed to read frame at 1.0s"
    H, W, _ = frame.shape  # 1280x528

    # Ground Harry Potter with real OWLv2 detector
    grounder = OpenVocabularyGrounder(confidence_threshold=0.15)
    spec_harry = EntitySpec(name="Harry Potter", role="subject", description="a person with glasses")
    dets = grounder.ground_entities(frame, [spec_harry], timestamp_sec=1.0)
    assert len(dets) > 0, "Real detector must detect Harry Potter on the Hogwarts viaduct"

    harry_det = dets[0]
    # Verify Harry is on the right side (norm x > 0.50)
    assert harry_det.bbox.x > 0.50

    # Compute subject-aware crop
    engine = SubjectAwareCompositionEngine()
    res = engine.compute_crop_and_verify(
        subject_bboxes=[harry_det.bbox],
        src_w=W,
        src_h=H,
    )

    # Assertions
    assert res.is_valid is True
    assert res.is_visible is True
    assert res.is_clipped is False
    # Crop moved rightward past dead center
    dead_center_x = (W - res.crop_window.w) // 2
    assert res.crop_window.x > dead_center_x
    assert res.retained_subject_ratio >= 0.99
    # Coordinates inside crop
    px = harry_det.bbox.to_pixels(W, H)
    assert px[0] >= res.crop_window.x
    assert (px[0] + px[2]) <= (res.crop_window.x + res.crop_window.w)


# ==============================================================================
# 9. Real Case B: m3_buckbeak_slash_malfoy.mp4 @ ~6.5s (Buckbeak on Left, Draco Absent)
# ==============================================================================
def test_09_real_case_b_buckbeak_slash_malfoy():
    clip_path = BLIND_CLIPS_DIR / "m3_buckbeak_slash_malfoy.mp4"
    assert clip_path.exists(), f"Source clip not found: {clip_path}"

    cap = cv2.VideoCapture(str(clip_path))
    cap.set(cv2.CAP_PROP_POS_MSEC, 6500.0)
    ret, frame = cap.read()
    cap.release()
    assert ret, "Failed to read frame at 6.5s"
    H, W, _ = frame.shape  # 1920x800

    # Ground with real OWLv2 detector
    grounder = OpenVocabularyGrounder(confidence_threshold=0.15)
    spec_buckbeak = EntitySpec(name="Buckbeak", role="subject", description="a creature with wings")
    spec_draco = EntitySpec(name="Draco Malfoy", role="recipient", description="a blonde boy")
    dets = grounder.ground_entities(frame, [spec_buckbeak, spec_draco], timestamp_sec=6.5)

    buckbeak_dets = [d for d in dets if d.entity_name == "Buckbeak"]
    draco_dets = [d for d in dets if d.entity_name == "Draco Malfoy"]

    # Multi-subject check: Draco Malfoy MUST be absent and NOT fabricated
    assert len(buckbeak_dets) > 0, "Buckbeak must be physically detected on left"
    assert len(draco_dets) == 0, "Draco Malfoy must NOT be detected in real footage at 6.5s"

    # Select main Buckbeak detection
    main_buckbeak = max(buckbeak_dets, key=lambda d: d.bbox.w * d.bbox.h)
    assert main_buckbeak.bbox.x < 0.20  # On far left

    # Compute subject-aware crop for wide entity (allow_partial_retention=True)
    engine = SubjectAwareCompositionEngine()
    res = engine.compute_crop_and_verify(
        subject_bboxes=[main_buckbeak.bbox],
        src_w=W,
        src_h=H,
        allow_partial_retention=True,
    )

    # Crop moved leftward past dead center
    dead_center_x = (W - res.crop_window.w) // 2  # 735
    assert res.crop_window.x < dead_center_x
    assert res.crop_window.x <= 150  # Strongly shifted toward the left edge
    assert res.is_visible is True
    # Buckbeak is 700px wide, so in a 450px crop window retention is ~64%
    assert 0.50 <= res.retained_subject_ratio <= 0.75
    assert res.is_clipped is True  # Wide entity is partially clipped without scaling
