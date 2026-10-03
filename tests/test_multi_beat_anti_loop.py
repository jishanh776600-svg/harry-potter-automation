"""
STORY FORGE — Multi-Beat Visual Coverage & Anti-Loop Test Suite
==============================================================
Validates:
  1. Three beats with three valid clips -> three separate timeline segments.
  2. Three beats where only Beat 1 has a valid clip -> Beat 2/3 are NOT filled by Beat 1.
  3. Short clip + longer narration -> clip is NOT looped or extended.
  4. Missing direct visual -> INSUFFICIENT_VISUAL_COVERAGE / explicit uncovered beat.
  5. VISUAL_OPTIONAL factual/context beat -> does not force fake footage, explicit absence.
  6. Same clip legitimately covering two adjacent beats -> allowed only when evidence explicitly supports it.
  7. Existing real detector authority remains intact.
  8. Elder Wand validation -> core visual beat gets clip, book canon beat is NOT filled with snapping clip.
"""

import pytest
from pathlib import Path
from typing import Dict, Any

from engines.movie_event.models import (
    VisualBeat,
    VISUAL_OPTIONAL,
    DIRECT_VISUAL,
    INSUFFICIENT_VISUAL_COVERAGE,
)
from engines.movie_event.storyboard_generator import VisualStoryboardGenerator, ClaimTransformer
from engines.visual_evidence.multi_beat_timeline import (
    MultiBeatCoverageEngine,
    MultiBeatTimelinePlan,
    TimelineSegment,
    BeatCoverageStatus,
)
from engines.visual_evidence.storyforge_adapter import StoryForgeVisualEvidenceAdapter
from py_visual_evidence.grounding import DeterministicBenchmarkGrounder, OpenVocabularyGrounder


class TestMultiBeatVisualCoverageAndAntiLoop:
    """Focused test suite verifying multi-beat coverage and strict anti-loop behavior."""

    @pytest.fixture
    def engine(self) -> MultiBeatCoverageEngine:
        return MultiBeatCoverageEngine()

    @pytest.fixture
    def storyboard_gen(self) -> VisualStoryboardGenerator:
        return VisualStoryboardGenerator()

    # --------------------------------------------------------------------------
    # 1. Three beats with three valid clips -> three separate timeline segments
    # --------------------------------------------------------------------------
    def test_01_three_beats_three_distinct_clips(self, engine: MultiBeatCoverageEngine):
        beats = [
            VisualBeat(
                beat_id="beat_01",
                narration_start=0.0,
                narration_end=3.0,
                narrative_text="Harry enters the potions classroom.",
                direct_visual_requirement=True,
                required_action="enter",
                required_subjects=["Harry Potter"],
            ),
            VisualBeat(
                beat_id="beat_02",
                narration_start=3.0,
                narration_end=6.0,
                narrative_text="Snape confronts him at the front desk.",
                direct_visual_requirement=True,
                required_action="confront",
                required_subjects=["Severus Snape", "Harry Potter"],
            ),
            VisualBeat(
                beat_id="beat_03",
                narration_start=6.0,
                narration_end=9.0,
                narrative_text="Harry draws his wand defensively.",
                direct_visual_requirement=True,
                required_action="draw",
                required_subjects=["Harry Potter"],
            ),
        ]

        evidence = {
            "beat_01": {
                "source_video": "movie1_scene1.mp4",
                "source_start": 10.0,
                "source_end": 13.0,
                "clip_path": "/vault/clip_01.mp4",
                "is_verified": True,
                "verdict": "PASS",
            },
            "beat_02": {
                "source_video": "movie1_scene2.mp4",
                "source_start": 25.0,
                "source_end": 28.0,
                "clip_path": "/vault/clip_02.mp4",
                "is_verified": True,
                "verdict": "PASS",
            },
            "beat_03": {
                "source_video": "movie1_scene3.mp4",
                "source_start": 40.0,
                "source_end": 43.0,
                "clip_path": "/vault/clip_03.mp4",
                "is_verified": True,
                "verdict": "PASS",
            },
        }

        plan = engine.build_timeline(beats, evidence, content_id="test_01")
        assert plan.is_valid is True
        assert plan.status == "PASS"
        assert len(plan.segments) == 3

        # Three distinct separate segments
        assert plan.segments[0].clip_path == "/vault/clip_01.mp4"
        assert plan.segments[1].clip_path == "/vault/clip_02.mp4"
        assert plan.segments[2].clip_path == "/vault/clip_03.mp4"

        # Unique clips assigned
        assigned_clips = [s.clip_path for s in plan.segments]
        assert len(set(assigned_clips)) == 3
        assert plan.total_verified_visual_duration == 9.0

    # --------------------------------------------------------------------------
    # 2. Three beats where only Beat 1 has a valid clip -> Beat 2/3 are NOT filled by Beat 1
    # --------------------------------------------------------------------------
    def test_02_only_beat1_valid_prevents_cloning_across_beats(self, engine: MultiBeatCoverageEngine):
        beats = [
            VisualBeat(
                beat_id="beat_01",
                narration_start=0.0,
                narration_end=3.0,
                narrative_text="Harry grips the Elder Wand.",
                direct_visual_requirement=True,
                required_action="hold",
            ),
            VisualBeat(
                beat_id="beat_02",
                narration_start=3.0,
                narration_end=7.0,
                narrative_text="Hermione and Ron watch from the stone archway.",
                direct_visual_requirement=True,
                required_action="watch",
            ),
            VisualBeat(
                beat_id="beat_03",
                narration_start=7.0,
                narration_end=11.0,
                narrative_text="In the book, the wand is returned to Dumbledore's tomb.",
                direct_visual_requirement=False,
                coverage_requirement=VISUAL_OPTIONAL,
                required_action="none",
            ),
        ]

        # Only Beat 1 has evidence; caller tries to also pass Beat 1's clip into Beat 2
        evidence = {
            "beat_01": {
                "source_video": "elder_wand.mp4",
                "source_start": 0.0,
                "source_end": 3.0,
                "clip_path": "/vault/wand_snap.mp4",
                "is_verified": True,
                "verdict": "PASS",
            },
            "beat_02": {
                # Attempted improper reuse of beat 1's clip
                "source_video": "elder_wand.mp4",
                "source_start": 0.0,
                "source_end": 3.0,
                "clip_path": "/vault/wand_snap.mp4",
                "is_verified": True,
                "verdict": "PASS",
            },
            # beat_03 has no evidence
        }

        plan = engine.build_timeline(beats, evidence, content_id="test_02")

        # Beat 1 received the clip
        assert plan.segments[0].coverage_status == BeatCoverageStatus.VERIFIED_DIRECT
        assert plan.segments[0].clip_path == "/vault/wand_snap.mp4"

        # Beat 2 was NOT filled with Beat 1's clip: REUSED_DISALLOWED
        assert plan.segments[1].coverage_status == BeatCoverageStatus.REUSED_DISALLOWED
        assert plan.segments[1].clip_path is None

        # Beat 3 is VISUAL_OPTIONAL_UNCOVERED (explicit absence, not fake footage)
        assert plan.segments[2].coverage_status == BeatCoverageStatus.VISUAL_OPTIONAL_UNCOVERED
        assert plan.segments[2].clip_path is None

        # Total renderable segments is exactly 1 (not duplicated)
        renderable = plan.get_renderable_segments()
        assert len(renderable) == 1

        # Direct requirement for Beat 2 was not met -> fail closed
        assert plan.is_valid is False
        assert plan.status == INSUFFICIENT_VISUAL_COVERAGE

    # --------------------------------------------------------------------------
    # 3. Short clip + longer narration -> clip is NOT looped
    # --------------------------------------------------------------------------
    def test_03_short_clip_is_not_looped(self, engine: MultiBeatCoverageEngine):
        beat = VisualBeat(
            beat_id="beat_01",
            narration_start=0.0,
            narration_end=8.0,  # 8.0s narration
            narrative_text="Harry breaks the Elder Wand cleanly in half.",
            direct_visual_requirement=True,
            required_action="snaps",
        )

        evidence = {
            "beat_01": {
                "source_video": "elder_wand.mp4",
                "source_start": 1.0,
                "source_end": 3.5,  # Only 2.5s clip
                "clip_path": "/vault/short_snap.mp4",
                "is_verified": True,
                "verdict": "PASS",
            }
        }

        plan = engine.build_timeline([beat], evidence, content_id="test_03")

        # Clip was used for its exact available duration (2.5s), NOT looped to 8.0s
        seg = plan.segments[0]
        assert seg.duration == 2.5
        assert seg.source_end == 3.5
        assert plan.total_verified_visual_duration == 2.5
        assert plan.loop_count_detected == 0

    # --------------------------------------------------------------------------
    # 4. Missing direct visual -> INSUFFICIENT_VISUAL_COVERAGE
    # --------------------------------------------------------------------------
    def test_04_missing_direct_visual_fails_closed(self, engine: MultiBeatCoverageEngine):
        beat = VisualBeat(
            beat_id="beat_climax",
            narration_start=0.0,
            narration_end=5.0,
            narrative_text="Hermione punches Malfoy in the face.",
            direct_visual_requirement=True,
            required_action="punch",
        )

        # No evidence provided
        plan = engine.build_timeline([beat], {}, content_id="test_04")

        assert plan.is_valid is False
        assert plan.status == INSUFFICIENT_VISUAL_COVERAGE
        assert "beat_climax" in plan.uncovered_beats
        assert len(plan.rejection_reasons) > 0
        assert "no verified evidence" in plan.rejection_reasons[0].lower()

    # --------------------------------------------------------------------------
    # 5. VISUAL_OPTIONAL factual/context beat -> does not force fake footage
    # --------------------------------------------------------------------------
    def test_05_visual_optional_beat_allows_explicit_absence(
        self,
        engine: MultiBeatCoverageEngine,
        storyboard_gen: VisualStoryboardGenerator,
    ):
        text = "In the book, Harry never breaks the wand at all. He repairs his phoenix wand."
        beat, classification = storyboard_gen.generate_beat_from_narration(
            beat_id="beat_book_lore",
            narration_text=text,
            start_time=0.0,
            end_time=6.0,
            narrative_role="LORE_COMPARISON",
        )

        assert beat.is_visual_optional is True
        assert beat.coverage_requirement == VISUAL_OPTIONAL
        assert beat.direct_visual_requirement is False

        # Build timeline without visual evidence for this beat
        plan = engine.build_timeline([beat], {}, content_id="test_05")

        # Must NOT fail closed for VISUAL_OPTIONAL beat
        assert plan.is_valid is True
        assert plan.status == "PASS"
        assert len(plan.uncovered_beats) == 0
        assert "beat_book_lore" in plan.visual_optional_beats
        assert plan.segments[0].coverage_status == BeatCoverageStatus.VISUAL_OPTIONAL_UNCOVERED

    # --------------------------------------------------------------------------
    # 6. Same clip legitimately covering two adjacent beats -> supported only with disjoint intervals
    # --------------------------------------------------------------------------
    def test_06_legitimate_multi_beat_sharing(self, engine: MultiBeatCoverageEngine):
        beats = [
            VisualBeat(
                beat_id="beat_01",
                narration_start=0.0,
                narration_end=3.0,
                narrative_text="Harry raises the wand.",
                direct_visual_requirement=True,
                required_action="raises",
            ),
            VisualBeat(
                beat_id="beat_02",
                narration_start=3.0,
                narration_end=6.0,
                narrative_text="He snaps it in two.",
                direct_visual_requirement=True,
                required_action="snaps",
            ),
        ]

        # Valid continuous master take covering both beats with disjoint source sub-intervals
        evidence = {
            "beat_01": {
                "source_video": "master_take_01.mp4",
                "source_start": 10.0,
                "source_end": 13.0,
                "clip_path": "/vault/take_part1.mp4",
                "is_verified": True,
                "verdict": "PASS",
                "multi_beat_supported": True,
            },
            "beat_02": {
                "source_video": "master_take_01.mp4",
                "source_start": 13.0,
                "source_end": 16.0,
                "clip_path": "/vault/take_part2.mp4",
                "is_verified": True,
                "verdict": "PASS",
                "multi_beat_supported": True,
            },
        }

        plan = engine.build_timeline(beats, evidence, content_id="test_06")
        assert plan.is_valid is True
        assert plan.status == "PASS"
        assert len(plan.segments) == 2
        assert plan.segments[0].coverage_status == BeatCoverageStatus.VERIFIED_DIRECT
        assert plan.segments[1].coverage_status == BeatCoverageStatus.VERIFIED_DIRECT
        assert plan.segments[0].source_end == 13.0
        assert plan.segments[1].source_start == 13.0

    # --------------------------------------------------------------------------
    # 7. Existing real detector authority remains intact
    # --------------------------------------------------------------------------
    def test_07_real_detector_authority_preserved(self):
        # Synthetic benchmark grounder MUST raise ValueError when allow_synthetic_grounding=False
        bench_grounder = DeterministicBenchmarkGrounder(strict=True)
        with pytest.raises(ValueError, match="strictly prohibited for real-footage visual evidence"):
            StoryForgeVisualEvidenceAdapter(grounder=bench_grounder, allow_synthetic_grounding=False)

        # Real detector (OpenVocabularyGrounder) succeeds
        real_grounder = OpenVocabularyGrounder(confidence_threshold=0.15)
        adapter = StoryForgeVisualEvidenceAdapter(grounder=real_grounder)
        assert isinstance(adapter.grounder, OpenVocabularyGrounder)

    # --------------------------------------------------------------------------
    # 8. Elder Wand Validation Case
    # --------------------------------------------------------------------------
    def test_08_elder_wand_book_canon_not_filled_with_snap_clip(
        self,
        engine: MultiBeatCoverageEngine,
        storyboard_gen: VisualStoryboardGenerator,
    ):
        """
        Verify that in the real Elder Wand case:
          Beat 1 (Visual core: wand snapping)
          Beat 2 (Book canon: "Harry never breaks it in the book")
        are NOT automatically filled with the same snapping clip,
        and no 5x looping occurs.
        """
        b1, _ = storyboard_gen.generate_beat_from_narration(
            beat_id="disc_p2_visual_core",
            narration_text="Harry grips the Elder Wand with both hands and snaps it cleanly in two pieces.",
            start_time=0.0,
            end_time=3.629,
            narrative_role="CLIMAX",
            direct_visual_requirement=True,
            visual_state="BROKEN",
        )

        b2, _ = storyboard_gen.generate_beat_from_narration(
            beat_id="disc_p3_lore_truth",
            narration_text="In the book, Harry never breaks it at all. He repairs his phoenix wand.",
            start_time=3.629,
            end_time=11.0,
            narrative_role="PAYOFF",
        )

        # Real evidence: Only the 3.629s wand snap clip exists for Beat 1
        evidence = {
            "disc_p2_visual_core": {
                "source_video": "m8_elder_wand_snap.mp4",
                "source_start": 0.0,
                "source_end": 3.629,
                "clip_path": "clip_disc_elder_wand_snap_v1_shot01.mp4",
                "is_verified": True,
                "verdict": "PASS",
            }
            # Notice: No visual evidence provided for disc_p3_lore_truth
        }

        plan = engine.build_timeline([b1, b2], evidence, content_id="disc_elder_wand_snap_v1")

        # 1. Timeline is valid because b1 is verified and b2 is VISUAL_OPTIONAL
        assert plan.is_valid is True
        assert plan.status == "PASS"

        # 2. Exactly 1 renderable segment exists (no looping of the snap clip)
        renderable = plan.get_renderable_segments()
        assert len(renderable) == 1
        assert renderable[0].beat_id == "disc_p2_visual_core"
        assert renderable[0].duration == 3.629

        # 3. Beat 2 is explicitly VISUAL_OPTIONAL_UNCOVERED (NOT filled with wand snap!)
        assert plan.segments[1].beat_id == "disc_p3_lore_truth"
        assert plan.segments[1].coverage_status == BeatCoverageStatus.VISUAL_OPTIONAL_UNCOVERED
        assert plan.segments[1].clip_path is None

        # 4. Zero repeated looping detected
        assert plan.loop_count_detected == 0
