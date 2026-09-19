"""
Harry Potter Autonomous Cloud Refill Engine
================================================================================
Autonomous replenisher for Harry Potter Shorts in Google Drive Vault (01_READY).
Ported from proven AL AMR autonomous producer reliability architecture.

Key Invariants:
  - 100% Autonomous: Detects deficit, schedules candidates, produces, and uploads.
  - Fail-Safe Idempotency: When buffer >= TARGET (8), exits immediately (<15s).
  - Hard Loop Bounds: Max batch ceiling (4 per run), max consecutive failures (2).
  - Movie Footage Only: BluRay Movie 1 footage (-an, zero movie audio).
  - Permanent Voice: Bella (Kokoro af_bella).
  - Anti-Loop Gate: 0.0% repetition strictly verified.
  - Dual Distributed Lock: ProcessLock + CloudLockManager (00_SYSTEM vault).
  - Bounded Strategy: Respects learned content mix [1:3 to 3:1] and subtype weights.
  - Dynamic Candidate Pool: Automatically sources pending scripts, plans new candidates,
    resolves visual shots, renders, QA checks, and deposits without starving.
  - Resilient Retry: Skips failed candidate and tries next pool candidate before tripping.
  - Strict Isolation: Zero AL AMR runtime dependencies or cross-account access.
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
from typing import Dict, Any, List, Optional, Tuple, Set

from config.settings import (
    PROJECT_ROOT, DB_PATH,
    MAX_BATCH_PRODUCTION_CEILING,
    MAX_BUFFER_RESERVE_CEILING,
    AUTOMATION_ID, EXPECTED_GOOGLE_ACCOUNT,
    EXPECTED_DRIVE_ROOT_ID, EXPECTED_YOUTUBE_CHANNEL_ID
)
from config.constants import TARGET_RESERVE_BUFFER
from core.database import SessionLocal
from core.models import HarryPotterScript, HPRender, HPMovieClip, NovStoryCandidate, DiscoveryCandidate
from core.lock import ProcessLock, ProcessLockError
from core.cloud_lock import CloudLockManager, CloudLockError
from engines.drive_engine import DriveVaultEngine
from engines.hp_script_engine import HarryPotterScriptEngine
from engines.hp_render_engine import HPRenderEngine
from engines.movie_retrieval_engine import MovieRetrievalEngine
from engines.content_planner import ContentPlannerEngine
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

    def verify_isolation_guardrails(self) -> None:
        """Enforces hard isolation parameters ensuring no cross-contamination."""
        if AUTOMATION_ID != "harry_potter":
            raise ValueError(f"Isolation violation: AUTOMATION_ID '{AUTOMATION_ID}' != 'harry_potter'")
        if EXPECTED_GOOGLE_ACCOUNT != "jishanh760@gmail.com":
            raise ValueError(f"Isolation violation: Account '{EXPECTED_GOOGLE_ACCOUNT}' != 'jishanh760@gmail.com'")
        if EXPECTED_DRIVE_ROOT_ID != "11K6v7PjLsnb8fVCsAm00YGmamvv4ygzC":
            raise ValueError(f"Isolation violation: Drive root '{EXPECTED_DRIVE_ROOT_ID}' mismatch")
        if EXPECTED_YOUTUBE_CHANNEL_ID != "UCsghEXDa3EzxI4d93cjT-bQ":
            raise ValueError(f"Isolation violation: YouTube channel '{EXPECTED_YOUTUBE_CHANNEL_ID}' mismatch")

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

    def get_ready_vault_script_ids(self) -> Set[str]:
        """Discovers all script IDs already deposited in Drive 01_READY."""
        script_ids = set()
        try:
            files = self.drive_engine.list_files_in_folder("01_READY")
            for f in files:
                fname = f.get("name", "")
                if fname.endswith(".mp4"):
                    script_ids.add(fname[:-4])
                props = f.get("properties") or {}
                if props.get("script_id"):
                    script_ids.add(props["script_id"])
        except Exception as e:
            logger.warning(f"Notice listing 01_READY vault files: {e}")
        return script_ids

    def _get_or_create_candidate_script(
        self,
        session,
        content_type: str,
        excluded_script_ids: Set[str]
    ) -> Optional[HarryPotterScript]:
        """
        Dynamically sources an eligible production script:
        1. Checks database for pending, unrendered approved scripts.
        2. If none, sources from unscripted NovStoryCandidate / DiscoveryCandidate.
        3. If candidate pool is exhausted, dynamically invokes ContentPlanner to plan new candidates,
           then generates broadcast script via HarryPotterScriptEngine.
        """
        # 1. Look for existing scripts in HarryPotterScript table not yet deposited
        deposited_scripts = session.query(HarryPotterScript.id).filter(
            HarryPotterScript.status.in_(["DEPOSITED", "PUBLISHED"])
        )

        existing_query = session.query(HarryPotterScript).filter(
            HarryPotterScript.content_type == content_type,
            HarryPotterScript.qa_status.in_(["APPROVED", "PASSED"]),
            ~HarryPotterScript.id.in_(deposited_scripts)
        )
        if excluded_script_ids:
            existing_query = existing_query.filter(~HarryPotterScript.id.in_(excluded_script_ids))

        script = existing_query.order_by(HarryPotterScript.created_at.asc()).first()
        if script:
            logger.info(f"[Refill:Pool] Found existing undeposited script: {script.id} ({content_type})")
            return script

        # 2. If no eligible script in DB, look for unscripted candidates
        logger.info(f"[Refill:Pool] No undeposited {content_type} scripts found in DB. Sourcing candidate pool...")
        script_engine = HarryPotterScriptEngine()
        existing_script_cand_ids = session.query(HarryPotterScript.candidate_id)

        if content_type == "novel_story":
            cand_query = session.query(NovStoryCandidate).filter(
                NovStoryCandidate.status == "ELIGIBLE",
                ~NovStoryCandidate.id.in_(existing_script_cand_ids)
            )
            if excluded_script_ids:
                cand_query = cand_query.filter(
                    ~NovStoryCandidate.id.in_([s.replace("hps_", "") for s in excluded_script_ids])
                )
            candidate = cand_query.order_by(NovStoryCandidate.global_chronology_start.asc()).first()

            # If no candidates in DB, invoke ContentPlanner to plan next chapter segments
            if not candidate:
                logger.info("[Refill:Pool] Sourcing fresh Novel Story candidates via ContentPlanner...")
                try:
                    planner = ContentPlannerEngine()
                    new_cands = planner.plan_novel_story_candidates(count=4)
                    if new_cands:
                        first_id = new_cands[0].get("candidate_id") or new_cands[0].get("id")
                        candidate = session.query(NovStoryCandidate).filter_by(id=first_id).first()
                except Exception as cp_err:
                    logger.warning(f"Notice during Novel Story candidate planning: {cp_err}")

            if candidate:
                logger.info(f"[Refill:Pool] Generating script for novel candidate {candidate.id}...")
                new_script = script_engine.generate_script_for_candidate(candidate, session)
                new_script.status = "APPROVED"
                session.commit()
                return new_script

        elif content_type == "discovery":
            cand_query = session.query(DiscoveryCandidate).filter(
                DiscoveryCandidate.status == "ELIGIBLE",
                ~DiscoveryCandidate.id.in_(existing_script_cand_ids)
            )
            if excluded_script_ids:
                cand_query = cand_query.filter(
                    ~DiscoveryCandidate.id.in_([s.replace("hps_", "") for s in excluded_script_ids])
                )
            candidate = cand_query.first()

            # If no discovery candidates in DB, invoke ContentPlanner
            if not candidate:
                logger.info("[Refill:Pool] Sourcing fresh Discovery candidates via ContentPlanner...")
                try:
                    planner = ContentPlannerEngine()
                    new_cands = planner.plan_discovery_candidates(count=4)
                    if new_cands:
                        first_id = new_cands[0].get("candidate_id") or new_cands[0].get("id")
                        candidate = session.query(DiscoveryCandidate).filter_by(id=first_id).first()
                except Exception as cp_err:
                    logger.warning(f"Notice during Discovery candidate planning: {cp_err}")

            if candidate:
                logger.info(f"[Refill:Pool] Generating script for discovery candidate {candidate.id}...")
                new_script = script_engine.generate_script_for_candidate(candidate, session)
                new_script.status = "APPROVED"
                session.commit()
                return new_script

        return None

    def _produce_single_script(
        self,
        session,
        script: HarryPotterScript
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Produces a single Harry Potter Short from a validated script:
        1. Resolves / extracts movie visual shots via MovieRetrievalEngine if missing.
        2. Renders vertical Short via HPRenderEngine (Kokoro af_bella + BGM + captions).
        3. Enforces automated QA gate.
        4. Deposits to Google Drive vault 01_READY.
        5. Updates database state idempotently.
        """
        script_id = script.id
        content_type = script.content_type
        logger.info(f"[Refill:Produce] Starting production pipeline for {script_id} ({content_type})...")

        # Step 2: Headless Composition & Rendering (Reuse verified local render if available)
        render_rec = session.query(HPRender).filter_by(script_id=script_id).first()
        video_path = None
        if render_rec and render_rec.qa_status == "PASSED" and render_rec.video_path and Path(render_rec.video_path).exists():
            logger.info(f"[Refill:Render] Reusing verified existing render for {script_id}: {render_rec.video_path}")
            video_path = Path(render_rec.video_path)
        else:
            # Step 1: Ensure Movie Visual Shots exist in HPMovieClip
            accepted_shots_count = session.query(HPMovieClip).filter_by(
                script_id=script_id,
                match_status="ACCEPTED"
            ).count()

            if accepted_shots_count == 0:
                logger.info(f"[Refill:Visual] Resolving movie shots for {script_id} via MovieRetrievalEngine...")
                try:
                    retrieval_engine = MovieRetrievalEngine()
                    shots = retrieval_engine.process_script_shots(script_id, allow_download=True)
                    accepted_shots_count = session.query(HPMovieClip).filter_by(
                        script_id=script_id,
                        match_status="ACCEPTED"
                    ).count()
                    if accepted_shots_count == 0:
                        return False, script_id, f"Visual retrieval yielded 0 accepted movie shots for {script_id}"
                    logger.info(f"[Refill:Visual] Successfully resolved {accepted_shots_count} movie shots for {script_id}")
                except Exception as ve:
                    logger.error(f"[Refill:Visual] Visual shot resolution failed for {script_id}: {ve}")
                    return False, script_id, f"Visual retrieval exception: {ve}"

            try:
                render_engine = HPRenderEngine()
                render_summary = render_engine.render_launch_short(script_id=script_id)
                if not render_summary.get("qa_report", {}).get("passed", False):
                    qa_details = render_summary.get("qa_report", {}).get("details", {})
                    return False, script_id, f"Technical QA verification failed: {qa_details}"

                video_path = Path(render_summary["video_path"])
            except Exception as re:
                logger.error(f"[Refill:Render] Render error for {script_id}: {re}", exc_info=True)
                return False, script_id, f"Rendering failed: {re}"

        # Step 3: Cloud Vault Buffer Deposit (01_READY)
        try:
            desc = (
                f"Harry Potter Novel Story: {script.chapter_title} [{script.part_marker or 'PART 01'}]"
                if content_type == "novel_story"
                else f"Harry Potter Discovery: {script.chapter_title or script_id}"
            )
            uploaded = self.drive_engine.upload_video_to_vault(
                local_path=video_path,
                target_folder="01_READY",
                description=desc,
                metadata_properties={
                    "automation_id": "harry_potter",
                    "script_id": script_id,
                    "content_type": content_type,
                    "voice": "af_bella",
                    "channel_id": "UCsghEXDa3EzxI4d93cjT-bQ"
                }
            )
            file_id = uploaded.get("id") if isinstance(uploaded, dict) else str(uploaded)
            logger.info(f"[Refill:Vault] Successfully deposited {script_id} into 01_READY (Drive ID: {file_id})")

            # Step 4: Persist DB status
            script.status = "DEPOSITED"
            if not render_rec:
                render_rec = session.query(HPRender).filter_by(script_id=script_id).first()
            if render_rec:
                render_rec.status = "DEPOSITED"
                render_rec.qa_status = "PASSED"
            session.commit()

            return True, script_id, None
        except Exception as ue:
            logger.error(f"[Refill:Vault] Drive upload failed for {script_id}: {ue}")
            return False, script_id, f"Drive deposit failed: {ue}"

    def _produce_next_novel_story(
        self,
        session,
        excluded_script_ids: Optional[Set[str]] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Produces next chronological Novel Story Short end-to-end."""
        script = self._get_or_create_candidate_script(session, "novel_story", excluded_script_ids or set())
        if not script:
            return False, None, "No eligible or discoverable novel_story candidates available"
        return self._produce_single_script(session, script)

    def _produce_next_discovery(
        self,
        session,
        excluded_script_ids: Optional[Set[str]] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Produces next unproduced Discovery Short end-to-end."""
        script = self._get_or_create_candidate_script(session, "discovery", excluded_script_ids or set())
        if not script:
            return False, None, "No eligible or discoverable discovery candidates available"
        return self._produce_single_script(session, script)

    def run_refill_cycle(
        self,
        target_buffer: int = TARGET_RESERVE_BUFFER,
        force_batch_count: int = 0
    ) -> RefillTelemetry:
        """
        Executes full autonomous refill cycle:
        1. Verifies isolation guardrails.
        2. Audits Drive stock. If buffer satisfied, exits cleanly in seconds (<15s).
        3. Acquires dual locks: ProcessLock + CloudLockManager.
        4. Consults bounded strategy for content mix (Novel vs Discovery).
        5. Produces candidates resiliently until target is satisfied or run ceiling is met.
        6. Performs technical QA, uploads to 01_READY, and releases locks in finally.
        """
        start_time = time.time()
        telemetry = RefillTelemetry(is_dry_run=self.is_dry_run)

        # 1. Isolation Guardrails Check
        try:
            self.verify_isolation_guardrails()
        except Exception as e:
            logger.critical(f"[Refill:Isolation] Guardrail check failed: {e}")
            telemetry.status = "FAILED"
            telemetry.failure_reasons.append(str(e))
            telemetry.duration_seconds = round(time.time() - start_time, 2)
            return telemetry

        # 2. Audit stock & compute deficit
        audit = self.audit_reserve_buffer(target_stock=target_buffer)
        telemetry.initial_ready_stock = audit["ready_stock"]
        telemetry.target_stock = audit["target_stock"]
        telemetry.final_ready_stock = audit["ready_stock"]

        # Determine effective deficit clamped by safe per-run ceiling (4)
        raw_deficit = force_batch_count if force_batch_count > 0 else audit["deficit"]
        effective_deficit = min(raw_deficit, MAX_RUN_REFILL_CEILING)
        telemetry.requested_deficit = effective_deficit

        # If buffer already satisfied and no force batch, return immediately (<15s)
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

        # 3. Dual Locking: ProcessLock + CloudLockManager
        process_lock = ProcessLock(name="hp_production", command_name="cloud-refill")
        if not process_lock.acquire():
            logger.warning("[Refill] Local process lock active. Exiting run safely.")
            telemetry.status = "BLOCKED"
            telemetry.failure_reasons.append("Local process lock active")
            telemetry.duration_seconds = round(time.time() - start_time, 2)
            return telemetry

        lock_mgr = CloudLockManager(
            drive_engine=self.drive_engine,
            run_id=telemetry.run_id,
            lock_name="cloud_production",
            force_break=self.force_unlock
        )

        try:
            if not lock_mgr.acquire():
                logger.warning("[Refill] Could not acquire cloud production lock in Drive vault. Safely deferring run.")
                telemetry.status = "BLOCKED"
                telemetry.failure_reasons.append("Cloud production lock held in Drive vault (00_SYSTEM)")
                telemetry.duration_seconds = round(time.time() - start_time, 2)
                return telemetry
        except CloudLockError as cle:
            logger.warning(f"[Refill] Cloud lock error: {cle}. Safely deferring run.")
            telemetry.status = "BLOCKED"
            telemetry.failure_reasons.append(str(cle))
            telemetry.duration_seconds = round(time.time() - start_time, 2)
            return telemetry
        finally:
            # If acquire returned False or failed, release local process lock before returning
            if telemetry.status == "BLOCKED":
                try:
                    process_lock.release()
                except Exception:
                    pass

        # 4. Production Phase under Locks
        session = SessionLocal()
        try:
            # Closed-loop strategy adaptation
            try:
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
            vaulted_ids = self.get_ready_vault_script_ids() if not self.is_dry_run else set()
            excluded_script_ids: Set[str] = set(vaulted_ids)

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

            # Real Resilient Production Loop
            # Step A: Produce Novel Story Shorts
            for idx in range(novel_needed):
                if consecutive_failures >= 2:
                    logger.error("[Refill] Circuit breaker tripped: 2 consecutive failures. Aborting batch early.")
                    telemetry.circuit_breaker_tripped = True
                    break

                slot_produced = False
                while not slot_produced and consecutive_failures < 2:
                    success, sid, reason = self._produce_next_novel_story(session, excluded_script_ids)
                    if success:
                        produced_count += 1
                        telemetry.novel_story_produced += 1
                        telemetry.videos_qa_passed += 1
                        telemetry.videos_deposited += 1
                        consecutive_failures = 0
                        slot_produced = True
                    else:
                        consecutive_failures += 1
                        telemetry.videos_qa_failed += 1
                        if sid:
                            excluded_script_ids.add(sid)
                        telemetry.failure_reasons.append(f"Novel Story candidate '{sid or idx+1}' failed: {reason}")
                        logger.warning(f"[Refill] Candidate '{sid}' failed. Trying next candidate from pool...")
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

                    slot_produced = False
                    while not slot_produced and consecutive_failures < 2:
                        success, sid, reason = self._produce_next_discovery(session, excluded_script_ids)
                        if success:
                            produced_count += 1
                            telemetry.discovery_produced += 1
                            telemetry.videos_qa_passed += 1
                            telemetry.videos_deposited += 1
                            consecutive_failures = 0
                            slot_produced = True
                        else:
                            consecutive_failures += 1
                            telemetry.videos_qa_failed += 1
                            if sid:
                                excluded_script_ids.add(sid)
                            telemetry.failure_reasons.append(f"Discovery candidate '{sid or idx+1}' failed: {reason}")
                            logger.warning(f"[Refill] Candidate '{sid}' failed. Trying next candidate from pool...")
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
            try:
                process_lock.release()
            except Exception as pe:
                logger.warning(f"[Refill] Error releasing process lock: {pe}")
            session.close()

        telemetry.duration_seconds = round(time.time() - start_time, 2)
        return telemetry
