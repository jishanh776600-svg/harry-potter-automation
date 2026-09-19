"""
Harry Potter Autonomous Cloud Refill Engine
================================================================================
Autonomous replenisher for Harry Potter Shorts in Google Drive Vault (01_READY).

Key Invariants:
  - 100% Autonomous: Detects deficit, schedules candidates, produces, and uploads.
  - Fail-Safe Idempotency: When buffer >= TARGET (8), exits immediately (<15s).
  - Hard Loop Bounds: Max batch ceiling (4 per run), max consecutive failures (2).
  - Movie Footage Only: BluRay Movie 1 footage (-an, zero movie audio).
  - Permanent Voice: Bella (Kokoro af_bella).
  - Anti-Loop Gate: 0.0% repetition strictly verified.
  - Safe Cloud Lock: Prevents race conditions with concurrent runners.
  - Bounded Strategy: Respects learned content mix [1:3 to 3:1] and subtype weights.
  - ZERO direct YouTube uploads or publishing (PUBLISHING_ENABLED=False).
"""

import os
import sys
import json
import time
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config.settings import (
    PROJECT_ROOT, DB_PATH,
    MAX_BATCH_PRODUCTION_CEILING,
    MAX_BUFFER_RESERVE_CEILING
)
from config.constants import TARGET_RESERVE_BUFFER
from core.database import SessionLocal
from core.models import HarryPotterScript, HPRender, HPMovieClip, NovStoryCandidate, DiscoveryCandidate
from core.cloud_lock import CloudLockManager, CloudLockError
from engines.drive_engine import DriveVaultEngine
from engines.hp_script_engine import HarryPotterScriptEngine
from engines.hp_render_engine import HPRenderEngine
from engines.hp_learning_strategy import HPLearningStrategy

logger = logging.getLogger("hp_autonomous_refill")


MAX_RUN_REFILL_CEILING = int(os.getenv("MAX_RUN_REFILL_CEILING", "4"))


@dataclass
class RefillTelemetry:
    run_id: str = field(default_factory=lambda: f"refill_{uuid.uuid4().hex[:8]}")
    status: str = "PENDING"  # SUCCEEDED, PARTIAL, BLOCKED, FAILED, BUFFER_SATISFIED
    initial_ready_stock: int = 0
    final_ready_stock: int = 0
    target_stock: int = TARGET_RESERVE_BUFFER
    requested_deficit: int = 0
    videos_deposited: int = 0
    videos_qa_passed: int = 0
    videos_qa_failed: int = 0
    videos_rendered: int = 0
    scripts_generated: int = 0
    visual_plans_generated: int = 0
    events_discovered: int = 0
    events_rejected: int = 0
    novel_story_produced: int = 0
    discovery_produced: int = 0
    failure_reasons: List[str] = field(default_factory=list)
    circuit_breaker_tripped: bool = False
    is_dry_run: bool = False
    duration_seconds: float = 0.0


class HPAutonomousRefillEngine:
    """End-to-end autonomous refill controller for Harry Potter channel vault."""

    def __init__(
        self,
        drive_engine: Optional[DriveVaultEngine] = None,
        voice_id: str = "af_bella",
        is_dry_run: bool = False,
        force_unlock: bool = False
    ):
        self.drive_engine = drive_engine or DriveVaultEngine()
        self.voice_id = voice_id or "af_bella"
        self.is_dry_run = is_dry_run
        self.force_unlock = force_unlock
        self.strategy_engine = HPLearningStrategy()

    def audit_reserve_buffer(self, target_stock: int = TARGET_RESERVE_BUFFER) -> Dict[str, Any]:
        """Audits current stock in Google Drive 01_READY vault and calculates deficit."""
        effective_target = max(target_stock, TARGET_RESERVE_BUFFER)
        clamped_target = min(effective_target, MAX_BUFFER_RESERVE_CEILING)

        ready_count = 0
        try:
            ready_count = self.drive_engine.get_ready_stock_count()
        except Exception as e:
            logger.error(f"Failed to query Drive 01_READY stock: {e}")

        deficit = max(0, clamped_target - ready_count)
        return {
            "target_stock": clamped_target,
            "ready_stock": ready_count,
            "deficit": deficit,
            "refill_needed": deficit > 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def run_refill_cycle(
        self,
        target_buffer: int = TARGET_RESERVE_BUFFER,
        force_batch_count: int = 0
    ) -> RefillTelemetry:
        """
        Executes full autonomous refill cycle:
        1. Audits Drive stock. If buffer satisfied, exits cleanly in seconds.
        2. Acquires distributed cloud lock.
        3. Consults bounded strategy for content mix (Novel vs Discovery).
        4. Produces candidates until target is satisfied or run ceiling is met.
        5. Performs technical QA, uploads to 01_READY, and releases lock.
        """
        start_time = time.time()
        telemetry = RefillTelemetry(is_dry_run=self.is_dry_run)

        # 1. Audit stock
        audit = self.audit_reserve_buffer(target_stock=target_buffer)
        telemetry.initial_ready_stock = audit["ready_stock"]
        telemetry.target_stock = audit["target_stock"]
        telemetry.final_ready_stock = audit["ready_stock"]

        # Determine effective deficit clamped by safe per-run ceiling (4)
        raw_deficit = force_batch_count if force_batch_count > 0 else audit["deficit"]
        effective_deficit = min(raw_deficit, MAX_RUN_REFILL_CEILING)
        telemetry.requested_deficit = effective_deficit

        # If buffer already satisfied and no force batch, return immediately
        if effective_deficit == 0:
            telemetry.status = "SUCCEEDED"
            telemetry.duration_seconds = round(time.time() - start_time, 2)
            logger.info(
                f"[Refill] Buffer target already satisfied: {telemetry.initial_ready_stock}/{telemetry.target_stock} in 01_READY. "
                "Zero production required. Exiting cleanly."
            )
            return telemetry

        logger.info(
            f"[Refill] Target: {telemetry.target_stock}, Current: {telemetry.initial_ready_stock}, "
            f"Deficit: {effective_deficit}. Initiating autonomous production..."
        )

        # 2. Acquire Distributed Cloud Lock
        lock_mgr = CloudLockManager(
            drive_engine=self.drive_engine,
            lock_name="cloud_production",
            force_break=self.force_unlock
        )

        try:
            lock_mgr.acquire()
        except CloudLockError as e:
            logger.warning(f"[Refill] Could not acquire cloud production lock: {e}. Safely deferring run.")
            telemetry.status = "BLOCKED"
            telemetry.failure_reasons.append(str(e))
            telemetry.duration_seconds = round(time.time() - start_time, 2)
            return telemetry

        # 3. Production Phase under Lock
        try:
            session = SessionLocal()
            try:
                # Closed-loop strategy adaptation
                self.strategy_engine.adapt_from_performance(session)
            except Exception as se:
                logger.warning(f"Strategy adaptation skipped: {se}")

            # Compute content allocation
            allocation = self.strategy_engine.get_content_allocation(effective_deficit)
            novel_needed = allocation.get("novel_story", 0)
            discovery_needed = allocation.get("discovery", 0)
            logger.info(f"[Refill] Planned Allocation: {novel_needed} Novel Story + {discovery_needed} Discovery Shorts")

            consecutive_failures = 0
            produced_count = 0

            # Dry Run branch
            if self.is_dry_run:
                logger.info("[Refill] DRY-RUN MODE: Simulating production without FFmpeg or Drive upload.")
                time.sleep(0.5)
                telemetry.videos_deposited = effective_deficit
                telemetry.videos_qa_passed = effective_deficit
                telemetry.novel_story_produced = novel_needed
                telemetry.discovery_produced = discovery_needed
                telemetry.final_ready_stock = telemetry.initial_ready_stock + effective_deficit
                telemetry.status = "SUCCEEDED"
                telemetry.duration_seconds = round(time.time() - start_time, 2)
                return telemetry

            # Real Production Loop
            # Step A: Produce Novel Story Shorts
            for idx in range(novel_needed):
                if consecutive_failures >= 2:
                    logger.error("[Refill] Circuit breaker tripped: 2 consecutive failures. Aborting batch early.")
                    telemetry.circuit_breaker_tripped = True
                    break

                success, sid, reason = self._produce_next_novel_story(session)
                if success:
                    produced_count += 1
                    telemetry.novel_story_produced += 1
                    telemetry.videos_qa_passed += 1
                    telemetry.videos_deposited += 1
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    telemetry.videos_qa_failed += 1
                    telemetry.failure_reasons.append(f"Novel Story #{idx+1} failed: {reason}")
                    if consecutive_failures >= 2:
                        telemetry.circuit_breaker_tripped = True
                        break

            # Step B: Produce Discovery Shorts
            if not telemetry.circuit_breaker_tripped:
                for idx in range(discovery_needed):
                    if consecutive_failures >= 2:
                        logger.error("[Refill] Circuit breaker tripped: 2 consecutive failures. Aborting batch early.")
                        telemetry.circuit_breaker_tripped = True
                        break

                    success, sid, reason = self._produce_next_discovery(session)
                    if success:
                        produced_count += 1
                        telemetry.discovery_produced += 1
                        telemetry.videos_qa_passed += 1
                        telemetry.videos_deposited += 1
                        consecutive_failures = 0
                    else:
                        consecutive_failures += 1
                        telemetry.videos_qa_failed += 1
                        telemetry.failure_reasons.append(f"Discovery #{idx+1} failed: {reason}")
                        if consecutive_failures >= 2:
                            telemetry.circuit_breaker_tripped = True
                            break

            # Finalize Stock Count
            try:
                telemetry.final_ready_stock = self.drive_engine.get_ready_stock_count()
            except Exception:
                telemetry.final_ready_stock = telemetry.initial_ready_stock + telemetry.videos_deposited

            if telemetry.videos_deposited >= effective_deficit:
                telemetry.status = "SUCCEEDED"
            elif telemetry.videos_deposited > 0:
                telemetry.status = "PARTIAL"
            else:
                telemetry.status = "FAILED"

        except Exception as ex:
            logger.error(f"[Refill] Unexpected error in production loop: {ex}", exc_info=True)
            telemetry.status = "FAILED"
            telemetry.failure_reasons.append(str(ex))
        finally:
            try:
                lock_mgr.release()
            except Exception as le:
                logger.warning(f"[Refill] Error releasing cloud lock: {le}")
            session.close()

        telemetry.duration_seconds = round(time.time() - start_time, 2)
        return telemetry

    def _produce_next_novel_story(self, session) -> Tuple[bool, Optional[str], Optional[str]]:
        """Produces next chronological Novel Story Short end-to-end."""
        # Find next unproduced candidate or script
        script = session.query(HarryPotterScript).filter_by(
            content_type="novel_story", status="APPROVED"
        ).filter(
            ~HarryPotterScript.id.in_(
                session.query(HPRender.script_id).filter(HPRender.status == "READY_FOR_REVIEW")
            )
        ).first()

        if not script:
            return False, None, "No pending approved novel_story script available in database"

        script_id = script.id
        logger.info(f"[Refill:Novel] Rendering {script_id}...")

        try:
            render_engine = HPRenderEngine()
            render_summary = render_engine.render_launch_short(script_id=script_id)
            if not render_summary.get("qa_report", {}).get("passed", False):
                return False, script_id, "Technical QA failed during rendering"

            video_path = Path(render_summary["video_path"])
            # Upload to Drive 01_READY
            uploaded = self.drive_engine.upload_video_to_vault(
                local_path=video_path,
                target_folder="01_READY",
                description=f"Harry Potter Novel Story: {script.chapter_title} [{script.part_marker}]",
                metadata_properties={
                    "automation_id": "harry_potter",
                    "script_id": script_id,
                    "content_type": "novel_story",
                    "voice": "af_bella"
                }
            )
            logger.info(f"[Refill:Novel] Successfully deposited {script_id} to 01_READY (Drive ID: {uploaded.get('id')})")
            return True, script_id, None
        except Exception as e:
            logger.error(f"[Refill:Novel] Production failed for {script_id}: {e}")
            return False, script_id, str(e)

    def _produce_next_discovery(self, session) -> Tuple[bool, Optional[str], Optional[str]]:
        """Produces next unproduced Discovery Short end-to-end."""
        script = session.query(HarryPotterScript).filter_by(
            content_type="discovery", status="APPROVED"
        ).filter(
            ~HarryPotterScript.id.in_(
                session.query(HPRender.script_id).filter(HPRender.status == "READY_FOR_REVIEW")
            )
        ).first()

        if not script:
            return False, None, "No pending approved discovery script available in database"

        script_id = script.id
        logger.info(f"[Refill:Discovery] Rendering {script_id}...")

        try:
            render_engine = HPRenderEngine()
            render_summary = render_engine.render_launch_short(script_id=script_id)
            if not render_summary.get("qa_report", {}).get("passed", False):
                return False, script_id, "Technical QA failed during rendering"

            video_path = Path(render_summary["video_path"])
            uploaded = self.drive_engine.upload_video_to_vault(
                local_path=video_path,
                target_folder="01_READY",
                description=f"Harry Potter Discovery: {script.chapter_title or script_id}",
                metadata_properties={
                    "automation_id": "harry_potter",
                    "script_id": script_id,
                    "content_type": "discovery",
                    "voice": "af_bella"
                }
            )
            logger.info(f"[Refill:Discovery] Successfully deposited {script_id} to 01_READY (Drive ID: {uploaded.get('id')})")
            return True, script_id, None
        except Exception as e:
            logger.error(f"[Refill:Discovery] Production failed for {script_id}: {e}")
            return False, script_id, str(e)
