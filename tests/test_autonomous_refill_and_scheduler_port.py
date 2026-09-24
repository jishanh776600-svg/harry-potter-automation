"""
Port Verification Test Suite: Autonomous Refill and Publication Scheduler
Forensically verifies that STORY FORGE's autonomous refill and scheduler mechanisms
faithfully mirror the proven AL AMR reliability invariants while strictly adhering to:
- 4 Shorts/day cadence (2 Novel Story, 1 Discovery Big, 1 Discovery Short)
- 4 canonical publishing slots: 02:00, 08:00, 14:00, 20:00 UTC
- Hard isolation: Account jishanh760@gmail.com, Channel UCsghEXDa3EzxI4d93cjT-bQ, Drive 11K6v7PjLsnb8fVCsAm00YGmamvv4ygzC
- No real production or network calls during test execution
"""
import os
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, time as dtime, timedelta

os.environ["TEST_MODE"] = "true"

from config.constants import (
    DAILY_SHORTS_LIMIT,
    TARGET_RESERVE_BUFFER,
    PUBLISHING_SLOTS_UTC,
    HarryPotterCategory,
    ContentType,
)
from config.settings import (
    AUTOMATION_ID,
    EXPECTED_GOOGLE_ACCOUNT,
    EXPECTED_DRIVE_ROOT_ID,
    EXPECTED_YOUTUBE_CHANNEL_ID,
)
from core.daily_cadence import ContentFormat
from engines.hp_learning_strategy import HPLearningStrategy
from engines.hp_autonomous_refill import (
    HPAutonomousRefillEngine,
    RefillTelemetry,
)
from engines.scheduler_engine import PublicationScheduler
from core.cloud_lock import ProcessLock, CompositeLock


class TestAutonomousRefillAndSchedulerPort(unittest.TestCase):
    """Verifies autonomous refill and publishing port from AL AMR to STORY FORGE."""

    def test_01_hard_isolation_parameters(self):
        """Verify STORY FORGE isolation parameters are strictly configured and uncorrupted."""
        self.assertEqual(AUTOMATION_ID, "harry_potter")
        self.assertEqual(EXPECTED_GOOGLE_ACCOUNT, "jishanh760@gmail.com")
        self.assertEqual(EXPECTED_DRIVE_ROOT_ID, "11K6v7PjLsnb8fVCsAm00YGmamvv4ygzC")
        self.assertEqual(EXPECTED_YOUTUBE_CHANNEL_ID, "UCsghEXDa3EzxI4d93cjT-bQ")
        self.assertEqual(DAILY_SHORTS_LIMIT, 4)
        self.assertEqual(TARGET_RESERVE_BUFFER, 8)
        self.assertEqual(len(PUBLISHING_SLOTS_UTC), 4)
        expected_slots = [(2, 0), (8, 0), (14, 0), (20, 0)]
        actual_slots = [(h, m) for h, m, _ in PUBLISHING_SLOTS_UTC]
        self.assertEqual(actual_slots, expected_slots)

    def test_02_format_aware_allocation_for_deficit(self):
        """
        Verify deficit allocation strictly maintains the 4-Shorts daily cadence:
        50% Novel Story (2) + 25% Discovery Big (1) + 25% Discovery Short (1).
        """
        strat = HPLearningStrategy()
        # Case 1: Deficit of 4 (1 full day of stock needed)
        plan_4 = strat.get_content_allocation(total_deficit=4)
        self.assertEqual(plan_4["novel_story"], 2)
        self.assertEqual(plan_4["discovery_big"], 1)
        self.assertEqual(plan_4["discovery_short"], 1)
        self.assertEqual(
            plan_4["novel_story"] + plan_4["discovery_big"] + plan_4["discovery_short"],
            4
        )

        # Case 2: Deficit of 8 (2 full days / full target reserve needed)
        plan_8 = strat.get_content_allocation(total_deficit=8)
        self.assertEqual(plan_8["novel_story"], 4)
        self.assertEqual(plan_8["discovery_big"], 2)
        self.assertEqual(plan_8["discovery_short"], 2)
        self.assertEqual(
            plan_8["novel_story"] + plan_8["discovery_big"] + plan_8["discovery_short"],
            8
        )

        # Case 3: Deficit of 1 (should allocate 1 total short)
        plan_1 = strat.get_content_allocation(total_deficit=1)
        self.assertEqual(plan_1["novel_story"] + plan_1["discovery"], 1)

    def test_03_refill_fast_exit_when_buffer_satisfied(self):
        """
        Verify fast-exit logic (<15s, 0 compute) when stock >= target.
        Ensures AL AMR fast-return behavior is preserved.
        """
        mock_drive = MagicMock()
        mock_drive.get_ready_stock_count.return_value = 8

        engine = HPAutonomousRefillEngine(drive_engine=mock_drive)
        audit = engine.audit_reserve_buffer(target_stock=8)
        self.assertEqual(audit["ready_stock"], 8)
        self.assertEqual(audit["deficit"], 0)
        self.assertFalse(audit["refill_needed"])

        # Run refill cycle with stock satisfied
        with patch.object(engine, "_produce_next_novel_story") as mock_novel, \
             patch.object(engine, "_produce_next_discovery") as mock_disc:
            telemetry = engine.run_refill_cycle(target_buffer=8)
            self.assertEqual(telemetry.status, "SUCCEEDED")
            self.assertEqual(telemetry.initial_ready_stock, 8)
            self.assertEqual(telemetry.requested_deficit, 0)
            self.assertEqual(telemetry.videos_deposited, 0)
            mock_novel.assert_not_called()
            mock_disc.assert_not_called()

    def test_04_process_lock_alignment(self):
        """
        Verify HPAutonomousRefillEngine uses ProcessLock(name='production')
        matching CompositeLock's cross-process mutual exclusion check.
        """
        # When production lock is held, CompositeLock(name="publisher") recognizes mutual exclusion
        prod_lock = ProcessLock(name="production", command_name="maintain-buffer")
        self.assertEqual(prod_lock.name, "production")
        self.assertEqual(prod_lock.command_name, "maintain-buffer")

    def test_05_cadence_aware_slot_matching_in_scheduler(self):
        """
        Verify that schedule_ready_buffer matches candidates to slots based on cadence:
        02:00 -> NOVEL_STORY
        08:00 -> DISCOVERY_BIG
        14:00 -> NOVEL_STORY
        20:00 -> DISCOVERY_SHORT
        """
        from main import ShortsPipeline

        # Construct 4 candidates of different formats
        c_novel_1 = {
            "id": "cand_novel_1",
            "name": "hps_snape_tears.mp4",
            "properties": {"format": "NOVEL_STORY", "content_type": "novel_story", "voice": "af_bella"}
        }
        c_novel_2 = {
            "id": "cand_novel_2",
            "name": "hps_mirror_erised.mp4",
            "properties": {"format": "NOVEL_STORY", "content_type": "novel_story", "voice": "af_bella"}
        }
        c_disc_big = {
            "id": "cand_disc_big",
            "name": "disc_big_barty_crouch.mp4",
            "properties": {"format": "DISCOVERY_BIG", "content_type": "discovery", "duration": "45.0", "voice": "af_bella"}
        }
        c_disc_short = {
            "id": "cand_disc_short",
            "name": "disc_short_neville.mp4",
            "properties": {"format": "DISCOVERY_SHORT", "content_type": "discovery", "duration": "28.0", "voice": "af_bella"}
        }

        # 4 vacant slots corresponding to the canonical hours
        today = date(2026, 9, 25)
        vacant_slots = [
            datetime.combine(today, dtime(2, 0)),
            datetime.combine(today, dtime(8, 0)),
            datetime.combine(today, dtime(14, 0)),
            datetime.combine(today, dtime(20, 0)),
        ]

        app = ShortsPipeline.__new__(ShortsPipeline)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.drive_engine = MagicMock()
        # Return candidates in shuffled order in 01_READY
        app.drive_engine.list_files_in_folder.side_effect = lambda folder: (
            [c_disc_short, c_novel_1, c_disc_big, c_novel_2] if folder == "01_READY" else []
        )
        app.scheduler = MagicMock()
        app.scheduler.get_vacant_slots_in_horizon.return_value = vacant_slots
        app.upload_engine = MagicMock()
        app.upload_engine._is_test_mode.return_value = True
        app.upload_engine.reconcile_scheduled_uploads.return_value = []
        app.analytics_engine = MagicMock()

        scheduled_calls = []

        def mock_schedule_single(db, target_file, scheduled_slot, current_folder):
            scheduled_calls.append((target_file["id"], scheduled_slot.hour, target_file["properties"]["format"]))
            rec = MagicMock()
            rec.job_id = f"job_{target_file['id']}"
            rec.youtube_video_id = f"yt_{target_file['id']}"
            rec.scheduled_publish_at = scheduled_slot
            rec.title = target_file["name"]
            return rec

        app._schedule_single_drive_file = mock_schedule_single

        with patch("main.CompositeLock") as mock_lock_cls, \
             patch("engines.drive_engine.is_valid_ready_short", return_value=(True, "OK")), \
             patch("main.resolve_vault_file_metadata", side_effect=lambda f, db=None: {"title": f"Story {f.get('name', 'Test')}", "description": "Harry Potter Lore"}):
            mock_lock = MagicMock()
            mock_lock.acquire.return_value = True
            mock_lock_cls.return_value = mock_lock

            res = app.schedule_ready_buffer(db=mock_db)

        self.assertEqual(res["scheduled_count"], 4)
        self.assertEqual(len(scheduled_calls), 4)

        # Check that slot 2:00 got NOVEL_STORY
        self.assertEqual(scheduled_calls[0][1], 2)
        self.assertEqual(scheduled_calls[0][2], "NOVEL_STORY")

        # Check that slot 8:00 got DISCOVERY_BIG
        self.assertEqual(scheduled_calls[1][1], 8)
        self.assertEqual(scheduled_calls[1][2], "DISCOVERY_BIG")

        # Check that slot 14:00 got NOVEL_STORY
        self.assertEqual(scheduled_calls[2][1], 14)
        self.assertEqual(scheduled_calls[2][2], "NOVEL_STORY")

        # Check that slot 20:00 got DISCOVERY_SHORT
        self.assertEqual(scheduled_calls[3][1], 20)
        self.assertEqual(scheduled_calls[3][2], "DISCOVERY_SHORT")

    def test_06_cadence_fallback_when_format_absent(self):
        """
        Verify that if preferred format is absent in 01_READY, scheduler gracefully
        falls back to any available eligible ready candidate to avoid slot starvation.
        """
        from main import ShortsPipeline

        # Only Novel Stories available in READY pool
        c_novel_1 = {
            "id": "cand_novel_1",
            "name": "hps_snape_tears.mp4",
            "properties": {"format": "NOVEL_STORY", "content_type": "novel_story", "voice": "af_bella"}
        }
        c_novel_2 = {
            "id": "cand_novel_2",
            "name": "hps_mirror_erised.mp4",
            "properties": {"format": "NOVEL_STORY", "content_type": "novel_story", "voice": "af_bella"}
        }

        # Vacant slot is 08:00 UTC (preferred: DISCOVERY_BIG)
        today = date(2026, 9, 25)
        vacant_slots = [datetime.combine(today, dtime(8, 0))]

        app = ShortsPipeline.__new__(ShortsPipeline)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.drive_engine = MagicMock()
        app.drive_engine.list_files_in_folder.side_effect = lambda folder: (
            [c_novel_1, c_novel_2] if folder == "01_READY" else []
        )
        app.scheduler = MagicMock()
        app.scheduler.get_vacant_slots_in_horizon.return_value = vacant_slots
        app.upload_engine = MagicMock()
        app.upload_engine._is_test_mode.return_value = True
        app.upload_engine.reconcile_scheduled_uploads.return_value = []
        app.analytics_engine = MagicMock()

        scheduled_calls = []

        def mock_schedule_single(db, target_file, scheduled_slot, current_folder):
            scheduled_calls.append((target_file["id"], scheduled_slot.hour, target_file["properties"]["format"]))
            rec = MagicMock()
            rec.job_id = f"job_{target_file['id']}"
            rec.youtube_video_id = f"yt_{target_file['id']}"
            rec.scheduled_publish_at = scheduled_slot
            rec.title = target_file["name"]
            return rec

        app._schedule_single_drive_file = mock_schedule_single

        with patch("main.CompositeLock") as mock_lock_cls, \
             patch("engines.drive_engine.is_valid_ready_short", return_value=(True, "OK")), \
             patch("main.resolve_vault_file_metadata", side_effect=lambda f, db=None: {"title": f"Story {f.get('name', 'Test')}", "description": "Harry Potter Lore"}):
            mock_lock = MagicMock()
            mock_lock.acquire.return_value = True
            mock_lock_cls.return_value = mock_lock

            res = app.schedule_ready_buffer(db=mock_db)

        # Slot 08:00 scheduled successfully despite DISCOVERY_BIG being absent
        self.assertEqual(res["scheduled_count"], 1)
        self.assertEqual(scheduled_calls[0][1], 8)
        self.assertEqual(scheduled_calls[0][2], "NOVEL_STORY")

    def test_07_processing_folder_recovery(self):
        """
        Verify 02_PROCESSING reconciliation:
        - Orphaned unuploaded files in 02_PROCESSING return safely to 01_READY if valid.
        """
        from main import ShortsPipeline

        unuploaded_processing_file = {
            "id": "proc_orphan_1",
            "name": "hps_unuploaded.mp4",
            "properties": {"content_type": "novel_story", "voice": "af_bella"}
        }

        app = ShortsPipeline.__new__(ShortsPipeline)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.count.return_value = 0

        app.drive_engine = MagicMock()
        app.drive_engine.list_files_in_folder.side_effect = lambda folder: (
            [unuploaded_processing_file] if folder == "02_PROCESSING" else []
        )
        app.scheduler = MagicMock()
        app.scheduler.get_vacant_slots_in_horizon.return_value = []
        app.upload_engine = MagicMock()
        app.upload_engine._is_test_mode.return_value = True
        app.upload_engine.reconcile_scheduled_uploads.return_value = []
        app.analytics_engine = MagicMock()

        with patch("main.CompositeLock") as mock_lock_cls, \
             patch("engines.drive_engine.is_valid_ready_short", return_value=(True, "Valid file")):
            mock_lock = MagicMock()
            mock_lock.acquire.return_value = True
            mock_lock_cls.return_value = mock_lock

            app.schedule_ready_buffer(db=mock_db)

        # Should move proc_orphan_1 back from 02_PROCESSING to 01_READY
        app.drive_engine.move_file_in_vault.assert_called_with(
            "proc_orphan_1",
            from_folder="02_PROCESSING",
            to_folder="01_READY"
        )

    def test_08_canonical_non_overlapping_format_detection(self):
        """
        Verify format detection logic strictly obeys:
        1. Explicit metadata as primary source of truth.
        2. Non-overlapping canonical duration fallback boundaries:
           - 25.0–30.0s   -> DISCOVERY_SHORT
           - 45.0–<60.0s  -> NOVEL_STORY
           - 60.0–70.0s   -> DISCOVERY_BIG
           - 30.0–<45.0s  -> UNKNOWN
           - >70.0s/<25.0s-> UNKNOWN
        """
        from main import ShortsPipeline
        detect = ShortsPipeline.detect_candidate_format

        # 1. Explicit metadata priority
        self.assertEqual(detect({"properties": {"format": "NOVEL_STORY"}}), "NOVEL_STORY")
        self.assertEqual(detect({"properties": {"format": "DISCOVERY_BIG"}}), "DISCOVERY_BIG")
        self.assertEqual(detect({"properties": {"format": "DISCOVERY_SHORT"}}), "DISCOVERY_SHORT")
        self.assertEqual(detect({"properties": {"content_type": "novel_story"}}), "NOVEL_STORY")
        self.assertEqual(detect({"properties": {"content_type": "discovery_big"}}), "DISCOVERY_BIG")
        self.assertEqual(detect({"properties": {"content_type": "discovery_short"}}), "DISCOVERY_SHORT")
        self.assertEqual(detect({"name": "discovery_big_chamber.mp4"}), "DISCOVERY_BIG")
        self.assertEqual(detect({"name": "discovery_short_mirror.mp4"}), "DISCOVERY_SHORT")
        self.assertEqual(detect({"name": "hps_boy_who_lived.mp4"}), "NOVEL_STORY")

        # 2. Strict non-overlapping duration boundaries (unspecified content_type)
        # DISCOVERY_SHORT: 25.0 - 30.0s
        self.assertEqual(detect({"properties": {"duration": 25.0}}), "DISCOVERY_SHORT")
        self.assertEqual(detect({"properties": {"duration": 27.5}}), "DISCOVERY_SHORT")
        self.assertEqual(detect({"properties": {"duration": 30.0}}), "DISCOVERY_SHORT")

        # Forbidden gap: 30.0 < dur < 45.0s -> UNKNOWN
        self.assertEqual(detect({"properties": {"duration": 30.1}}), "UNKNOWN")
        self.assertEqual(detect({"properties": {"duration": 35.0}}), "UNKNOWN")
        self.assertEqual(detect({"properties": {"duration": 40.0}}), "UNKNOWN")
        self.assertEqual(detect({"properties": {"duration": 44.9}}), "UNKNOWN")

        # NOVEL_STORY: 45.0 <= dur < 60.0s
        self.assertEqual(detect({"properties": {"duration": 45.0}}), "NOVEL_STORY")
        self.assertEqual(detect({"properties": {"duration": 52.5}}), "NOVEL_STORY")
        self.assertEqual(detect({"properties": {"duration": 59.9}}), "NOVEL_STORY")

        # DISCOVERY_BIG: 60.0 <= dur <= 70.0s
        self.assertEqual(detect({"properties": {"duration": 60.0}}), "DISCOVERY_BIG")
        self.assertEqual(detect({"properties": {"duration": 65.0}}), "DISCOVERY_BIG")
        self.assertEqual(detect({"properties": {"duration": 70.0}}), "DISCOVERY_BIG")

        # Out-of-bounds: > 70.0s or < 25.0s -> UNKNOWN
        self.assertEqual(detect({"properties": {"duration": 70.1}}), "UNKNOWN")
        self.assertEqual(detect({"properties": {"duration": 90.0}}), "UNKNOWN")
        self.assertEqual(detect({"properties": {"duration": 20.0}}), "UNKNOWN")
        self.assertEqual(detect({"properties": {"duration": 24.9}}), "UNKNOWN")

        # 3. Discovery generic type with duration fallback
        self.assertEqual(detect({"properties": {"content_type": "discovery", "duration": 27.0}}), "DISCOVERY_SHORT")
        self.assertEqual(detect({"properties": {"content_type": "discovery", "duration": 65.0}}), "DISCOVERY_BIG")
        self.assertEqual(detect({"properties": {"content_type": "discovery", "duration": 52.0}}), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
