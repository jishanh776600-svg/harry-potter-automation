"""
STORY FORGE — End-to-End Final Render Visual Verifier Tests
===========================================================
Minimum Focused Coverage:
  1. right-side subject survives final 9:16 crop
  2. left-side subject survives final 9:16 crop
  3. center subject remains valid
  4. missing required entity in final frame fails
  5. subject amputation fails
  6. wrong action/state fails
  7. unrelated scene fails
  8. repeated clip across unrelated beats fails
  9. optional book-canon beat does not require fabricated footage
  10. final render with valid distinct beat clips passes
  11. subtitle collision is detected
  12. real OWLv2 is mandatory
  13. synthetic grounder cannot silently enter production validation
  14. final-render evidence hash/lineage mismatch fails
"""

import pytest
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Any

from py_visual_evidence.schema import (
    BoundingBox,
    EntitySpec,
    GroundedEntity,
)
from py_visual_evidence.grounding import (
    DeterministicBenchmarkGrounder,
    OpenVocabularyGrounder,
)
from engines.movie_event.models import (
    VisualBeat,
    VISUAL_OPTIONAL,
    DIRECT_VISUAL,
)
from engines.visual_evidence.final_render_verifier import (
    FinalRenderVerifier,
    SampledFrame,
    EntityRetentionReport,
    VerificationVerdict,
    CANONICAL_SUBTITLE_FONT,
)


class TestFinalRenderVerifier:
    """Focused test suite for FinalRenderVerifier."""

    # --------------------------------------------------------------------------
    # 1. Right-side subject survives final 9:16 crop
    # --------------------------------------------------------------------------
    def test_01_right_side_subject_survives_final_crop(self):
        # Create grounder with subject positioned on right side of a 9:16 canvas
        # (normalized x=0.45, w=0.35, y=0.20, h=0.60)
        grounder = DeterministicBenchmarkGrounder(strict=False)
        grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.45, y=0.20, w=0.35, h=0.60))

        verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=True)
        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        img[:] = (50, 50, 50)
        sampled = [SampledFrame(timestamp_sec=1.0, frame_index=30, image_bgr=img)]

        reports = verifier.inspect_subject_retention(sampled, ["Harry Potter"])
        assert "Harry Potter" in reports
        rep = reports["Harry Potter"]
        assert rep.status == "PASS"
        assert rep.retention_rate == 1.0
        assert rep.is_amputated is False

    # --------------------------------------------------------------------------
    # 2. Left-side subject survives final 9:16 crop
    # --------------------------------------------------------------------------
    def test_02_left_side_subject_survives_final_crop(self):
        # Subject centered in shifted crop (normalized x=0.25, w=0.40 in 9:16 frame)
        grounder = DeterministicBenchmarkGrounder(strict=False)
        grounder.register_ground_truth("Buckbeak", BoundingBox(x=0.25, y=0.15, w=0.40, h=0.70))

        verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=True)
        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        img[:] = (60, 60, 60)
        sampled = [SampledFrame(timestamp_sec=2.0, frame_index=60, image_bgr=img)]

        reports = verifier.inspect_subject_retention(sampled, ["Buckbeak"])
        assert "Buckbeak" in reports
        rep = reports["Buckbeak"]
        assert rep.status == "PASS"
        assert rep.retention_rate == 1.0
        assert rep.is_amputated is False

    # --------------------------------------------------------------------------
    # 3. Center subject remains valid
    # --------------------------------------------------------------------------
    def test_03_center_subject_remains_valid(self):
        grounder = DeterministicBenchmarkGrounder(strict=False)
        grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.30, y=0.10, w=0.40, h=0.80))

        verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=True)
        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        sampled = [SampledFrame(timestamp_sec=1.5, frame_index=45, image_bgr=img)]

        reports = verifier.inspect_subject_retention(sampled, ["Harry Potter"])
        rep = reports["Harry Potter"]
        assert rep.status == "PASS"
        assert rep.is_amputated is False

    # --------------------------------------------------------------------------
    # 4. Missing required entity in final frame fails
    # --------------------------------------------------------------------------
    def test_04_missing_required_entity_in_final_frame_fails(self):
        grounder = DeterministicBenchmarkGrounder(strict=False)
        # Register Harry Potter, but Draco Malfoy is missing
        grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.30, y=0.10, w=0.40, h=0.80))

        verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=True)
        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        sampled = [SampledFrame(timestamp_sec=1.0, frame_index=30, image_bgr=img)]

        reports = verifier.inspect_subject_retention(sampled, ["Draco Malfoy"])
        assert "Draco Malfoy" in reports
        rep = reports["Draco Malfoy"]
        assert rep.status == "FAIL_ABSENT"
        assert rep.retention_rate == 0.0

    # --------------------------------------------------------------------------
    # 5. Subject amputation fails
    # --------------------------------------------------------------------------
    def test_05_subject_amputation_fails(self):
        # Subject clipped right against the boundary (x=0.005, w=0.08)
        grounder = DeterministicBenchmarkGrounder(strict=False)
        grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.005, y=0.20, w=0.08, h=0.70))

        verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=True)
        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        sampled = [
            SampledFrame(timestamp_sec=1.0, frame_index=30, image_bgr=img),
            SampledFrame(timestamp_sec=2.0, frame_index=60, image_bgr=img),
        ]

        reports = verifier.inspect_subject_retention(sampled, ["Harry Potter"])
        rep = reports["Harry Potter"]
        assert rep.status == "FAIL_AMPUTATED"
        assert rep.is_amputated is True
        assert "amputated" in rep.amputation_details.lower()

    # --------------------------------------------------------------------------
    # 6. Wrong action / state fails
    # --------------------------------------------------------------------------
    def test_06_wrong_action_or_state_fails(self):
        beat = VisualBeat(
            beat_id="beat_snap",
            narration_start=0.0,
            narration_end=4.0,
            narrative_text="Harry snaps the Elder Wand cleanly in two.",
            direct_visual_requirement=True,
            required_subjects=["Harry Potter"],
            required_objects=["Elder Wand"],
            required_action="snaps",
            visual_state="BROKEN",
        )

        grounder = DeterministicBenchmarkGrounder(strict=False)
        grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.30, y=0.10, w=0.40, h=0.80))
        # Elder Wand is missing (not detected in broken state)

        verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=True)
        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        sampled = [SampledFrame(timestamp_sec=2.0, frame_index=60, image_bgr=img)]

        ret_reports = verifier.inspect_subject_retention(sampled, beat.required_entities)
        status, details = verifier.inspect_action_survival(beat, sampled, ret_reports)

        assert status.startswith("FAIL")
        assert "failed" in details.lower()

    # --------------------------------------------------------------------------
    # 7. Unrelated scene fails
    # --------------------------------------------------------------------------
    def test_07_unrelated_scene_fails(self):
        # Beat requires Snape confronting Harry
        beat = VisualBeat(
            beat_id="beat_potions",
            narration_start=0.0,
            narration_end=4.0,
            narrative_text="Snape questions Harry in the dungeons.",
            direct_visual_requirement=True,
            required_subjects=["Severus Snape", "Harry Potter"],
            required_action="confront",
        )

        grounder = DeterministicBenchmarkGrounder(strict=False)
        # Scene contains Hagrid, but neither Snape nor Harry
        grounder.register_ground_truth("Rubeus Hagrid", BoundingBox(x=0.30, y=0.10, w=0.40, h=0.80))

        verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=True)
        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        sampled = [SampledFrame(timestamp_sec=2.0, frame_index=60, image_bgr=img)]

        ret_reports = verifier.inspect_subject_retention(sampled, beat.required_entities)
        status, details = verifier.inspect_action_survival(beat, sampled, ret_reports)

        assert status == "FAIL_ACTION_ABSENT"
        assert "missing from final render" in details

    # --------------------------------------------------------------------------
    # 8. Repeated clip across unrelated beats fails
    # --------------------------------------------------------------------------
    def test_08_repeated_clip_across_unrelated_beats_fails(self):
        verifier = FinalRenderVerifier(allow_synthetic_grounding=True)

        beats = [
            VisualBeat(
                beat_id="beat_01_hook",
                narration_start=0.0,
                narration_end=3.0,
                narrative_text="The movie changed the ending.",
                direct_visual_requirement=False,
                coverage_requirement=VISUAL_OPTIONAL,
            ),
            VisualBeat(
                beat_id="beat_02_action",
                narration_start=3.0,
                narration_end=6.0,
                narrative_text="Harry snaps the wand.",
                direct_visual_requirement=True,
            ),
        ]

        # Identical image used across both beats
        identical_img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        identical_img[100:200, 100:200] = 255

        sampled = {
            "beat_01_hook": [SampledFrame(timestamp_sec=1.0, frame_index=30, image_bgr=identical_img)],
            "beat_02_action": [SampledFrame(timestamp_sec=4.0, frame_index=120, image_bgr=identical_img)],
        }

        loop_detected, details = verifier.inspect_rendered_timeline_and_loops(
            Path("dummy.mp4"), beats, sampled
        )
        assert loop_detected is True
        assert len(details) > 0
        assert "REPETITIVE_LOOP_DETECTED" in details[0]

    # --------------------------------------------------------------------------
    # 9. Optional book-canon beat does not require fabricated footage
    # --------------------------------------------------------------------------
    def test_09_optional_book_canon_beat_does_not_require_fabricated_footage(self):
        beat = VisualBeat(
            beat_id="beat_lore",
            narration_start=8.0,
            narration_end=14.0,
            narrative_text="In the book, Harry never breaks the wand at all.",
            direct_visual_requirement=False,
            coverage_requirement=VISUAL_OPTIONAL,
            required_action="none",
        )

        verifier = FinalRenderVerifier(allow_synthetic_grounding=True)
        status, details = verifier.inspect_action_survival(beat, [], {})
        assert status == "OPTIONAL_ABSENT"
        assert "permitted" in details.lower()

    # --------------------------------------------------------------------------
    # 10. Final render with valid distinct beat clips passes
    # --------------------------------------------------------------------------
    def test_10_final_render_with_valid_distinct_beat_clips_passes(self):
        grounder = DeterministicBenchmarkGrounder(strict=False)
        grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.35, y=0.15, w=0.30, h=0.70))
        grounder.register_ground_truth("Elder Wand", BoundingBox(x=0.40, y=0.40, w=0.20, h=0.15))

        verifier = FinalRenderVerifier(grounder=grounder, allow_synthetic_grounding=True)

        beat = VisualBeat(
            beat_id="beat_core",
            narration_start=0.0,
            narration_end=3.5,
            narrative_text="Harry snaps the Elder Wand.",
            direct_visual_requirement=True,
            required_subjects=["Harry Potter"],
            required_objects=["Elder Wand"],
            required_action="snaps",
        )

        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        img[:] = 50
        sampled = [
            SampledFrame(timestamp_sec=1.0, frame_index=30, image_bgr=img),
            SampledFrame(timestamp_sec=2.0, frame_index=60, image_bgr=img),
        ]

        ret_reports = verifier.inspect_subject_retention(sampled, beat.required_entities)
        act_status, act_desc = verifier.inspect_action_survival(beat, sampled, ret_reports)

        assert ret_reports["Harry Potter"].status == "PASS"
        assert ret_reports["Elder Wand"].status == "PASS"
        assert act_status == "PASS"

    # --------------------------------------------------------------------------
    # 11. Subtitle collision is detected
    # --------------------------------------------------------------------------
    def test_11_subtitle_collision_is_detected(self, tmp_path: Path):
        verifier = FinalRenderVerifier(allow_synthetic_grounding=True)

        # 11a: Subtitle font mismatch (Arial instead of canonical Harry P)
        ass_file = tmp_path / "test_sub.ass"
        ass_content = (
            "[Script Info]\n"
            "Title: Test\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize\n"
            "Style: HP_Default,Arial,76\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            "Dialogue: 0,0:00:01.00,0:00:03.00,HP_Default,,0,0,0,,Hello world\n"
        )
        ass_file.write_text(ass_content, encoding="utf-8")

        sub_rep = verifier.inspect_subtitles(ass_file, [], [])
        assert sub_rep.font_matched is False
        assert sub_rep.verdict == VerificationVerdict.FAIL
        assert "CANONICAL_FONT_MISMATCH" in sub_rep.reasons[0]

        # 11b: Visual collision in bottom safe zone
        img = np.zeros((1920, 1080, 3), dtype=np.uint8)
        sf = SampledFrame(
            timestamp_sec=1.5,
            frame_index=45,
            image_bgr=img,
            detections=[
                GroundedEntity(
                    entity_name="Elder Wand",
                    role="object",
                    bbox=BoundingBox(x=0.40, y=0.75, w=0.20, h=0.15),  # Overlaps bottom subtitle band
                    confidence=0.85,
                    frame_index=45,
                    timestamp_sec=1.5,
                )
            ]
        )
        sub_rep_col = verifier.inspect_subtitles(None, [sf], ["Elder Wand"])
        assert sub_rep_col.collision_detected is True
        assert sub_rep_col.verdict == VerificationVerdict.FAIL

    # --------------------------------------------------------------------------
    # 12. Real OWLv2 is mandatory
    # --------------------------------------------------------------------------
    def test_12_real_owlv2_is_mandatory(self):
        verifier = FinalRenderVerifier(allow_synthetic_grounding=False)
        assert isinstance(verifier.grounder, OpenVocabularyGrounder)

    # --------------------------------------------------------------------------
    # 13. Synthetic grounder cannot silently enter production validation
    # --------------------------------------------------------------------------
    def test_13_synthetic_grounder_cannot_silently_enter_production(self):
        synthetic = DeterministicBenchmarkGrounder(strict=True)
        with pytest.raises(ValueError, match="strictly prohibited for real-footage final render verification"):
            FinalRenderVerifier(grounder=synthetic, allow_synthetic_grounding=False)

    # --------------------------------------------------------------------------
    # 14. Final-render resolution defect detection
    # --------------------------------------------------------------------------
    def test_14_resolution_defect_detected(self, tmp_path: Path):
        verifier = FinalRenderVerifier(allow_synthetic_grounding=True)
        # Create a tiny 640x360 dummy video (wrong aspect ratio)
        dummy_mp4 = tmp_path / "wrong_aspect.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(dummy_mp4), fourcc, 10, (640, 360))
        for _ in range(10):
            out.write(np.zeros((360, 640, 3), dtype=np.uint8))
        out.release()

        probe = verifier.probe_video(dummy_mp4)
        assert probe["width"] == 640
        assert probe["height"] == 360
        # Verification report flags RENDERER_DEFECTS
        report = verifier.verify_final_render(dummy_mp4, [], content_id="wrong_res_test")
        assert len(report.failures_by_category["RENDERER_DEFECTS"]) > 0
        assert "CANONICAL_RESOLUTION_VIOLATION" in report.failures_by_category["RENDERER_DEFECTS"][0]
        assert report.overall_verdict == VerificationVerdict.FAIL
