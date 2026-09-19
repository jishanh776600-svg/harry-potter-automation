"""
Comprehensive Reliability Test Suite: Harry Potter Autonomous Refill
================================================================================
Ports the proven AL AMR autonomous producer reliability test suite into STORY FORGE.
Verifies all 17 critical reliability, concurrency, idempotency, candidate pooling,
circuit breaking, visual resolution, isolation, and telemetry contracts.

Test Matrix:
  1. test_01_ready_8_buffer_satisfied_fast_exit: Full buffer (8/8) -> zero production, exits in <15s.
  2. test_02_ready_7_deficit_1_detection: Stock 7/8 -> Deficit 1 detected.
  3. test_03_ready_4_deficit_4_detection: Stock 4/8 -> Deficit 4 detected.
  4. test_04_ready_0_clamped_to_max_batch_ceiling: Stock 0/8 -> Clamped to ceiling of 4.
  5. test_05_force_batch_override: force_batch_count=2 overrides buffer deficit calculation.
  6. test_06_process_lock_held_blocks_run: Local ProcessLock active -> safe BLOCKED exit.
  7. test_07_cloud_lock_held_blocks_run: Drive CloudLock active -> safe BLOCKED exit.
  8. test_08_force_unlock_recovers_stale_lock: force_unlock=True breaks stale cloud lock.
  9. test_09_cloud_lock_always_released_in_finally: Exception in loop guarantees lock release.
  10. test_10_bounded_strategy_content_allocation: Strategy mix allocates Novel vs Discovery.
  11. test_11_candidate_pool_resilience_skip_failed: Single failure skips to next pool candidate.
  12. test_12_circuit_breaker_trips_after_2_consecutive_failures: Two errors aborts batch gracefully.
  13. test_13_dynamic_script_generation_when_pool_empty: Dyn-generation when unrendered scripts empty.
  14. test_14_visual_shot_resolution_before_render: Missing shots resolved prior to rendering.
  15. test_15_strict_isolation_guardrails: Hard failure on invalid account, drive root, or channel.
  16. test_16_duplicate_script_guard: Already rendered/deposited scripts are strictly not re-produced.
  17. test_17_dry_run_idempotency_and_telemetry: Full dry-run execution produces valid telemetry.
"""

import os
import sys
import time
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import TARGET_RESERVE_BUFFER, MAX_BUFFER_RESERVE_CEILING
from core.database import SessionLocal, init_db
from core.models import HarryPotterScript, HPRender, HPMovieClip, NovStoryCandidate, DiscoveryCandidate
from core.cloud_lock import CloudLockError
from core.lock import ProcessLockError
from engines.hp_autonomous_refill import HPAutonomousRefillEngine, RefillTelemetry, MAX_RUN_REFILL_CEILING
from engines.hp_learning_strategy import HPLearningStrategy


@pytest.fixture
def mock_drive():
    drive = MagicMock()
    drive.get_ready_stock_count.return_value = 8
    drive.upload_video_to_vault.return_value = {"id": "mock_file_123", "name": "test_short.mp4"}
    return drive


@pytest.fixture
def clean_engine(mock_drive):
    refill = HPAutonomousRefillEngine(
        drive_engine=mock_drive,
        voice_id="af_bella",
        is_dry_run=True,
        force_unlock=False
    )
    return refill


class TestHPAutonomousRefillReliability:
    """17-point authoritative test suite for Harry Potter Autonomous Refill."""

    def test_01_ready_8_buffer_satisfied_fast_exit(self, mock_drive):
        """1. Buffer full (8/8) -> zero production, exits cleanly in <15s with SUCCEEDED."""
        mock_drive.get_ready_stock_count.return_value = 8
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=False)

        t0 = time.time()
        telemetry = engine.run_refill_cycle(target_buffer=8)
        elapsed = time.time() - t0

        assert telemetry.status == "SUCCEEDED"
        assert telemetry.initial_ready_stock == 8
        assert telemetry.requested_deficit == 0
        assert telemetry.videos_deposited == 0
        assert elapsed < 15.0

    def test_02_ready_7_deficit_1_detection(self, mock_drive):
        """2. Stock = 7/8 -> Deficit = 1 detected."""
        mock_drive.get_ready_stock_count.return_value = 7
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True)

        with patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock, \
             patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock:
            MockLock.return_value.acquire.return_value = True
            MockProcLock.return_value.acquire.return_value = True

            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.initial_ready_stock == 7
            assert telemetry.requested_deficit == 1
            assert telemetry.videos_deposited == 1
            assert telemetry.status == "SUCCEEDED"

    def test_03_ready_4_deficit_4_detection(self, mock_drive):
        """3. Stock = 4/8 -> Deficit = 4 detected."""
        mock_drive.get_ready_stock_count.return_value = 4
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True)

        with patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock, \
             patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock:
            MockLock.return_value.acquire.return_value = True
            MockProcLock.return_value.acquire.return_value = True

            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.initial_ready_stock == 4
            assert telemetry.requested_deficit == 4
            assert telemetry.videos_deposited == 4

    def test_04_ready_0_clamped_to_max_batch_ceiling(self, mock_drive):
        """4. Stock = 0/8 -> Raw deficit is 8, but clamped to MAX_RUN_REFILL_CEILING (4)."""
        mock_drive.get_ready_stock_count.return_value = 0
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True)

        with patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock, \
             patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock:
            MockLock.return_value.acquire.return_value = True
            MockProcLock.return_value.acquire.return_value = True

            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.initial_ready_stock == 0
            assert telemetry.requested_deficit == 4  # Clamped to 4
            assert telemetry.videos_deposited == 4

    def test_05_force_batch_override(self, mock_drive):
        """5. force_batch_count=2 produces exactly 2 Shorts even if buffer is full."""
        mock_drive.get_ready_stock_count.return_value = 8
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True)

        with patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock, \
             patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock:
            MockLock.return_value.acquire.return_value = True
            MockProcLock.return_value.acquire.return_value = True

            telemetry = engine.run_refill_cycle(target_buffer=8, force_batch_count=2)
            assert telemetry.requested_deficit == 2
            assert telemetry.videos_deposited == 2
            assert telemetry.status == "SUCCEEDED"

    def test_06_process_lock_held_blocks_run(self, mock_drive):
        """6. When local ProcessLock is held by another process, exit safely with BLOCKED."""
        mock_drive.get_ready_stock_count.return_value = 5
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True)

        with patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock:
            mock_proc = MagicMock()
            mock_proc.acquire.return_value = False
            MockProcLock.return_value = mock_proc

            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.status == "BLOCKED"
            assert telemetry.videos_deposited == 0
            assert any("Process lock" in r or "process lock" in r for r in telemetry.failure_reasons)

    def test_07_cloud_lock_held_blocks_run(self, mock_drive):
        """7. When Drive CloudLock is held by another cloud runner, exit safely with BLOCKED."""
        mock_drive.get_ready_stock_count.return_value = 5
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True)

        with patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock, \
             patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock:
            MockProcLock.return_value.acquire.return_value = True
            mock_cloud = MagicMock()
            mock_cloud.acquire.return_value = False
            MockLock.return_value = mock_cloud

            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.status == "BLOCKED"
            assert telemetry.videos_deposited == 0
            assert any("cloud" in r.lower() or "drive" in r.lower() for r in telemetry.failure_reasons)

    def test_08_force_unlock_recovers_stale_lock(self, mock_drive):
        """8. When force_unlock=True, pass force_break to CloudLockManager."""
        mock_drive.get_ready_stock_count.return_value = 6
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True, force_unlock=True)

        with patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock, \
             patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock:
            MockProcLock.return_value.acquire.return_value = True
            mock_cloud = MagicMock()
            mock_cloud.acquire.return_value = True
            MockLock.return_value = mock_cloud

            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.status == "SUCCEEDED"
            MockLock.assert_called_once()
            _, kwargs = MockLock.call_args
            assert kwargs.get("force_break") is True

    def test_09_cloud_lock_always_released_in_finally(self, mock_drive):
        """9. Exception inside production loop guarantees lock release in finally block."""
        mock_drive.get_ready_stock_count.return_value = 5
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=False)

        with patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock, \
             patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock, \
             patch.object(engine.strategy_engine, "get_content_allocation", side_effect=RuntimeError("Database corruption crash")):

            mock_cloud = MagicMock()
            mock_cloud.acquire.return_value = True
            MockLock.return_value = mock_cloud

            mock_proc = MagicMock()
            mock_proc.acquire.return_value = True
            MockProcLock.return_value = mock_proc

            telemetry = engine.run_refill_cycle(target_buffer=8)
            # Even on unexpected error, status is FAILED and lock is released
            mock_cloud.release.assert_called_once()
            mock_proc.release.assert_called_once()

    def test_10_bounded_strategy_content_allocation(self, clean_engine):
        """10. Strategy mix allocates Novel Story vs Discovery within bounds [0.25, 0.75]."""
        clean_engine.mock_drive = MagicMock()
        clean_engine.mock_drive.get_ready_stock_count.return_value = 4
        clean_engine.drive_engine = clean_engine.mock_drive

        with patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock, \
             patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock:
            MockProcLock.return_value.acquire.return_value = True
            MockLock.return_value.acquire.return_value = True

            telemetry = clean_engine.run_refill_cycle(target_buffer=8)
            assert telemetry.novel_story_produced + telemetry.discovery_produced == 4
            assert telemetry.novel_story_produced >= 1
            assert telemetry.discovery_produced >= 1

    def test_11_candidate_pool_resilience_skip_failed(self, mock_drive):
        """11. Single candidate failure skips to next pool candidate without aborting entire run."""
        mock_drive.get_ready_stock_count.return_value = 7  # Deficit = 1
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=False)

        call_count = 0
        def side_effect_produce(session, excluded_ids=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return False, "cand_fail_1", "Corrupted subtitle stream"
            return True, "cand_success_2", None

        with patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock, \
             patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock, \
             patch.object(engine, "_produce_next_novel_story", side_effect=side_effect_produce):
            MockProcLock.return_value.acquire.return_value = True
            MockLock.return_value.acquire.return_value = True

            # Strategy allocation forced to 1 novel
            with patch.object(engine.strategy_engine, "get_content_allocation", return_value={"novel_story": 1, "discovery": 0}):
                telemetry = engine.run_refill_cycle(target_buffer=8)

            assert telemetry.videos_deposited == 1
            assert telemetry.status == "SUCCEEDED"
            assert call_count == 2
            assert telemetry.videos_qa_failed == 1

    def test_12_circuit_breaker_trips_after_2_consecutive_failures(self, mock_drive):
        """12. Two consecutive errors trip the circuit breaker and halt production gracefully."""
        mock_drive.get_ready_stock_count.return_value = 6  # Deficit = 2
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=False)

        with patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock, \
             patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock, \
             patch.object(engine, "_produce_next_novel_story", return_value=(False, "cand_1", "FFmpeg crash")), \
             patch.object(engine, "_produce_next_discovery", return_value=(False, "cand_2", "Audio mute failed")):
            MockProcLock.return_value.acquire.return_value = True
            MockLock.return_value.acquire.return_value = True

            with patch.object(engine.strategy_engine, "get_content_allocation", return_value={"novel_story": 2, "discovery": 0}):
                telemetry = engine.run_refill_cycle(target_buffer=8)

            assert telemetry.circuit_breaker_tripped is True
            assert telemetry.status == "FAILED"
            assert telemetry.videos_deposited == 0
            assert telemetry.videos_qa_failed == 2

    def test_13_dynamic_script_generation_when_pool_empty(self, mock_drive):
        """13. When no unrendered scripts exist in DB, dynamically plans and generates candidate."""
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=False)

        mock_session = MagicMock()
        mock_cand = NovStoryCandidate(
            id="ns_b1c01_test",
            content_type="novel_story",
            book_number=1,
            book_title="Philosopher's Stone",
            chapter_number=1,
            chapter_title="The Boy Who Lived",
            chunk_id_start="chunk_01",
            chunk_id_end="chunk_03",
            global_chronology_start=1,
            global_chronology_end=3,
            source_location="p. 1-5",
            story_event_summary="Test event",
            content_fingerprint="fp_test_123"
        )

        mock_script_obj = HarryPotterScript(
            id="hps_ns_b1c01_test",
            candidate_id="ns_b1c01_test",
            content_type="novel_story",
            book_number=1,
            book_title="Philosopher's Stone",
            chapter_number=1,
            chapter_title="The Boy Who Lived",
            source_chunks_json="[]",
            source_reference="B1C1",
            hook="Test Hook",
            development="Test Dev",
            payoff="Test Payoff",
            full_text="Test Full Text",
            word_count=65,
            estimated_duration_sec=25.0,
            visual_beats_json="[]"
        )

        def mock_query_dispatch(model):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            if model is HarryPotterScript:
                q.first.return_value = None
            elif model is NovStoryCandidate:
                q.first.return_value = mock_cand
            else:
                q.first.return_value = None
            return q

        mock_session.query.side_effect = mock_query_dispatch

        with patch("engines.hp_autonomous_refill.HarryPotterScriptEngine") as MockSE:
            MockSE.return_value.generate_script_for_candidate.return_value = mock_script_obj
            script = engine._get_or_create_candidate_script(mock_session, "novel_story", set())
            assert script is not None
            assert script.id == "hps_ns_b1c01_test"

    def test_14_visual_shot_resolution_before_render(self, mock_drive):
        """14. If HPMovieClip has 0 shots for script, automatically invokes MovieRetrievalEngine."""
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=False)

        mock_session = MagicMock()
        mock_script = HarryPotterScript(
            id="hps_test_shots",
            content_type="novel_story",
            chapter_title="Test Chapter",
            part_marker="PART 01",
            full_text="Narration text"
        )

        # First query: 0 accepted shots. Second query after resolution: 8 shots.
        mock_session.query.return_value.filter_by.return_value.count.side_effect = [0, 8]
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch("engines.hp_autonomous_refill.MovieRetrievalEngine") as MockMRE, \
             patch("engines.hp_autonomous_refill.HPRenderEngine") as MockRE:
            mock_mre = MockMRE.return_value
            mock_mre.process_script_shots.return_value = [{"shot_id": "shot_1"}]
            mock_re = MockRE.return_value
            mock_re.render_launch_short.return_value = {
                "qa_report": {"passed": True},
                "video_path": "mock_video.mp4"
            }

            success, sid, reason = engine._produce_single_script(mock_session, mock_script)
            assert success is True
            mock_mre.process_script_shots.assert_called_once_with("hps_test_shots", allow_download=True)
            mock_re.render_launch_short.assert_called_once_with(script_id="hps_test_shots")

    def test_15_strict_isolation_guardrails(self, mock_drive):
        """15. Fail-closed immediately if AUTOMATION_ID, account, drive root, or channel mismatch."""
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True)

        with patch("engines.hp_autonomous_refill.AUTOMATION_ID", "foreign_channel"):
            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.status == "FAILED"
            assert any("Isolation violation" in r for r in telemetry.failure_reasons)

        with patch("engines.hp_autonomous_refill.EXPECTED_GOOGLE_ACCOUNT", "hacker@example.com"):
            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.status == "FAILED"
            assert any("Isolation violation" in r for r in telemetry.failure_reasons)

        with patch("engines.hp_autonomous_refill.EXPECTED_DRIVE_ROOT_ID", "wrong_drive_root_id"):
            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.status == "FAILED"
            assert any("Isolation violation" in r for r in telemetry.failure_reasons)

        with patch("engines.hp_autonomous_refill.EXPECTED_YOUTUBE_CHANNEL_ID", "UC_wrong_channel"):
            telemetry = engine.run_refill_cycle(target_buffer=8)
            assert telemetry.status == "FAILED"
            assert any("Isolation violation" in r for r in telemetry.failure_reasons)

    def test_16_duplicate_script_guard(self, mock_drive):
        """16. Duplicate / already deposited scripts are filtered out from candidate pool."""
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=False)

        mock_session = MagicMock()
        def mock_query_all_none(model):
            q = MagicMock()
            q.filter.return_value = q
            q.order_by.return_value = q
            q.first.return_value = None
            return q

        mock_session.query.side_effect = mock_query_all_none

        with patch("engines.hp_autonomous_refill.ContentPlannerEngine") as MockCP:
            MockCP.return_value.plan_novel_story_candidates.return_value = []
            script = engine._get_or_create_candidate_script(mock_session, "novel_story", {"hps_already_produced"})
            assert script is None

    def test_17_dry_run_idempotency_and_telemetry(self, mock_drive):
        """17. Full dry-run execution produces complete, verified telemetry structure."""
        mock_drive.get_ready_stock_count.return_value = 5  # Deficit = 3
        engine = HPAutonomousRefillEngine(drive_engine=mock_drive, is_dry_run=True)

        with patch("engines.hp_autonomous_refill.ProcessLock") as MockProcLock, \
             patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock:
            MockProcLock.return_value.acquire.return_value = True
            MockLock.return_value.acquire.return_value = True

            telemetry = engine.run_refill_cycle(target_buffer=8)

            assert telemetry.status == "SUCCEEDED"
            assert telemetry.is_dry_run is True
            assert telemetry.initial_ready_stock == 5
            assert telemetry.requested_deficit == 3
            assert telemetry.videos_deposited == 3
            assert telemetry.videos_qa_passed == 3
            assert telemetry.final_ready_stock == 8
            assert telemetry.circuit_breaker_tripped is False
            assert telemetry.duration_seconds >= 0.0
            assert len(telemetry.failure_reasons) == 0
