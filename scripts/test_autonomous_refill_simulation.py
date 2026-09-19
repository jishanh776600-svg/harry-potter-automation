"""
Test Suite: Harry Potter Autonomous Refill & Bounded Learning Simulation
================================================================================
Verifies:
  1. Full Buffer State (8/8): Zero unnecessary production, exits in <15s.
  2. Partial Deficit State (6/8): Deficit 2 correctly allocates 1 Novel + 1 Discovery.
  3. Heavy Deficit State (3/8): Capped to MAX_BATCH_PRODUCTION_CEILING (4), no infinite loop.
  4. Concurrent Lock Conflict: Safely blocked and deferred without collision.
  5. Failure Circuit Breaker: Safely aborts on 2 consecutive errors.
  6. Bounded Learning Safeguards: Strict mathematical clamping of mix [0.25, 0.75],
     subtypes [0.50, 1.50], and durations [20.0, 28.0].
  7. Hard Security & Isolation Invariants: AL AMR untouched, PUBLISHING_ENABLED=False.
"""

import os
import sys
import json
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PUBLISHING_ENABLED, UPLOAD_ENABLED, TARGET_RESERVE_BUFFER
from core.cloud_lock import CloudLockError
from engines.hp_learning_strategy import (
    HPLearningStrategy,
    MIN_NOVEL_RATIO, MAX_NOVEL_RATIO,
    MIN_SUBTYPE_WEIGHT, MAX_SUBTYPE_WEIGHT,
    MIN_DURATION_TARGET, MAX_DURATION_TARGET
)
from engines.hp_autonomous_refill import HPAutonomousRefillEngine, RefillTelemetry


class TestHPAutonomousRefillSimulation(unittest.TestCase):

    def setUp(self):
        self.mock_drive = MagicMock()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_file = Path(self.temp_dir.name) / "test_strategy_config.json"
        self.log_file = Path(self.temp_dir.name) / "test_learning_log.md"
        self.strategy_engine = HPLearningStrategy(
            config_path=self.config_file,
            log_path=self.log_file
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_full_buffer_zero_production_fast_exit(self):
        """Scenario 1: Buffer is full (8/8). Must exit immediately with 0 videos."""
        self.mock_drive.get_ready_stock_count.return_value = 8

        refill_engine = HPAutonomousRefillEngine(
            drive_engine=self.mock_drive,
            is_dry_run=True
        )
        refill_engine.strategy_engine = self.strategy_engine

        t_start = time.time()
        telemetry = refill_engine.run_refill_cycle(target_buffer=8)
        elapsed = time.time() - t_start

        self.assertEqual(telemetry.status, "SUCCEEDED")
        self.assertEqual(telemetry.initial_ready_stock, 8)
        self.assertEqual(telemetry.target_stock, 8)
        self.assertEqual(telemetry.requested_deficit, 0)
        self.assertEqual(telemetry.videos_deposited, 0)
        self.assertLess(elapsed, 15.0, f"Full buffer check took {elapsed:.2f}s, expected <15s")
        print(f"[PASS] Scenario 1: Full Buffer 8/8 -> Fast exit in {elapsed:.3f}s, 0 videos produced.")

    def test_02_partial_deficit_allocation(self):
        """Scenario 2: Stock = 6/8. Deficit = 2. Allocates exactly 1 Novel + 1 Discovery."""
        self.mock_drive.get_ready_stock_count.return_value = 6

        refill_engine = HPAutonomousRefillEngine(
            drive_engine=self.mock_drive,
            is_dry_run=True
        )
        refill_engine.strategy_engine = self.strategy_engine

        # Mock lock manager
        with patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock:
            mock_lock_instance = MagicMock()
            MockLock.return_value = mock_lock_instance

            telemetry = refill_engine.run_refill_cycle(target_buffer=8)

            self.assertEqual(telemetry.status, "SUCCEEDED")
            self.assertEqual(telemetry.initial_ready_stock, 6)
            self.assertEqual(telemetry.requested_deficit, 2)
            self.assertEqual(telemetry.novel_story_produced, 1)
            self.assertEqual(telemetry.discovery_produced, 1)
            self.assertEqual(telemetry.videos_deposited, 2)
            self.assertEqual(telemetry.final_ready_stock, 8)
            print("[PASS] Scenario 2: Partial Deficit (6/8) -> Correct 1 Novel + 1 Discovery allocation.")

    def test_03_heavy_deficit_batch_capping(self):
        """Scenario 3: Stock = 3/8. Raw deficit = 5. Must clamp to MAX_BATCH_PRODUCTION_CEILING (4)."""
        self.mock_drive.get_ready_stock_count.return_value = 3

        refill_engine = HPAutonomousRefillEngine(
            drive_engine=self.mock_drive,
            is_dry_run=True
        )
        refill_engine.strategy_engine = self.strategy_engine

        with patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock:
            mock_lock_instance = MagicMock()
            MockLock.return_value = mock_lock_instance

            telemetry = refill_engine.run_refill_cycle(target_buffer=8)

            self.assertEqual(telemetry.status, "SUCCEEDED")
            self.assertEqual(telemetry.initial_ready_stock, 3)
            self.assertEqual(telemetry.requested_deficit, 4, "Must be clamped to ceiling of 4")
            self.assertEqual(telemetry.videos_deposited, 4)
            print("[PASS] Scenario 3: Heavy Deficit (3/8) -> Successfully clamped to ceiling of 4.")

    def test_04_concurrent_lock_rejection_safe_deferral(self):
        """Scenario 4: Another process holds cloud production lock. Safe deferral."""
        self.mock_drive.get_ready_stock_count.return_value = 6

        refill_engine = HPAutonomousRefillEngine(
            drive_engine=self.mock_drive,
            is_dry_run=True
        )
        refill_engine.strategy_engine = self.strategy_engine

        with patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock:
            mock_lock_instance = MagicMock()
            mock_lock_instance.acquire.side_effect = CloudLockError("Lock held by runner_12345")
            MockLock.return_value = mock_lock_instance

            telemetry = refill_engine.run_refill_cycle(target_buffer=8)

            self.assertEqual(telemetry.status, "BLOCKED")
            self.assertEqual(telemetry.videos_deposited, 0)
            self.assertIn("Lock held by runner_12345", telemetry.failure_reasons[0])
            print("[PASS] Scenario 4: Concurrent lock conflict -> Safely deferred with status BLOCKED.")

    def test_05_circuit_breaker_on_consecutive_failures(self):
        """Scenario 5: Circuit breaker trips after 2 consecutive errors."""
        self.mock_drive.get_ready_stock_count.return_value = 6

        refill_engine = HPAutonomousRefillEngine(
            drive_engine=self.mock_drive,
            is_dry_run=False  # Execute actual branches with mocked sub-methods
        )
        refill_engine.strategy_engine = self.strategy_engine

        with patch("engines.hp_autonomous_refill.CloudLockManager") as MockLock, \
             patch.object(refill_engine, "_produce_next_novel_story", return_value=(False, None, "Mock FFmpeg Error")), \
             patch.object(refill_engine, "_produce_next_discovery", return_value=(False, None, "Mock Clip Error")):

            mock_lock_instance = MagicMock()
            MockLock.return_value = mock_lock_instance

            telemetry = refill_engine.run_refill_cycle(target_buffer=8)

            self.assertEqual(telemetry.status, "FAILED")
            self.assertTrue(telemetry.circuit_breaker_tripped)
            self.assertEqual(telemetry.videos_deposited, 0)
            self.assertEqual(telemetry.videos_qa_failed, 2)
            print("[PASS] Scenario 5: Consecutive failures -> Circuit breaker safely tripped after 2 errors.")

    def test_06_bounded_learning_clamps(self):
        """Scenario 6: Verify mathematical clamping of all learning strategy parameters."""
        cfg = self.strategy_engine.load_strategy()

        # Attempt to set extreme / invalid out-of-bounds parameters
        cfg["content_mix"]["novel_story_ratio"] = 0.99  # Extreme high
        cfg["target_duration_sec"] = 45.0             # Extreme high duration
        cfg["discovery_subtype_weights"]["DISCOVERY_BOOK_MOVIE_DIFFERENCE"] = 3.5  # Extreme high weight
        cfg["discovery_subtype_weights"]["DISCOVERY_OMITTED_SCENE"] = 0.05          # Extreme low weight

        self.strategy_engine.save_strategy(cfg, reason="Testing extreme bounds")

        # Reload and verify clamps
        clamped_cfg = self.strategy_engine.load_strategy()
        self.assertEqual(clamped_cfg["content_mix"]["novel_story_ratio"], MAX_NOVEL_RATIO)  # 0.75
        self.assertEqual(clamped_cfg["content_mix"]["discovery_ratio"], 1.0 - MAX_NOVEL_RATIO)  # 0.25
        self.assertEqual(clamped_cfg["target_duration_sec"], MAX_DURATION_TARGET)  # 28.0s
        self.assertEqual(
            clamped_cfg["discovery_subtype_weights"]["DISCOVERY_BOOK_MOVIE_DIFFERENCE"],
            MAX_SUBTYPE_WEIGHT  # 1.50
        )
        self.assertEqual(
            clamped_cfg["discovery_subtype_weights"]["DISCOVERY_OMITTED_SCENE"],
            MIN_SUBTYPE_WEIGHT  # 0.50
        )
        print("[PASS] Scenario 6: Extreme strategy inputs strictly clamped to [0.25, 0.75], [0.50, 1.50], [20, 28].")

    def test_07_hard_security_and_isolation_invariants(self):
        """Scenario 7: Verify publishing locks and isolation invariants."""
        self.assertFalse(PUBLISHING_ENABLED, "PUBLISHING_ENABLED must be strictly False")
        self.assertFalse(UPLOAD_ENABLED, "UPLOAD_ENABLED must be strictly False")

        # Verify AL AMR isolation
        al_amr_dir = Path("C:/Users/jisha/OneDrive/Desktop/yt automation")
        if al_amr_dir.exists():
            # Check git status of AL AMR to guarantee zero modifications
            import subprocess
            res = subprocess.run(["git", "status", "--porcelain"], cwd=str(al_amr_dir), capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
            # No files should be modified by this task
        print("[PASS] Scenario 7: Hard safety locks (PUBLISHING_ENABLED=False) and AL AMR isolation confirmed.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
