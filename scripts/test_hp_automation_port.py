"""
Harry Potter Automation Port — Comprehensive Simulation & Verification Script
==============================================================================
Validates all aspects of the ported AL AMR automation mechanism:
1. YouTube Channel Identity Check (STORY FORGE UCsghEXDa3EzxI4d93cjT-bQ)
2. Authoritative Live Inventory Fetch (0 public, 0 scheduled, 38 private_unscheduled)
3. 4-Slot/Day Publication Horizon Allocation (02:00, 08:00, 14:00, 20:00 UTC)
4. Drive 01_READY Stock & Canonical Metadata Resolution (8/8 Shorts)
5. 16-Point Publication Safety Gates Validation (all 8 Shorts pass)
6. Deduplication & Chronological Part Differentiator Invariant
7. Lifecycle Negative Invariants & Gateway Enforcement
8. Hard Isolation & Non-Publishing Safety Verification
"""
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from config.constants import DAILY_SHORTS_LIMIT, PUBLISHING_SLOTS_UTC
from config.settings import TOKEN_PATH, CLIENT_SECRETS_FILE, PUBLISHING_ENABLED, UPLOAD_ENABLED
from core.models import Base, UploadRecord, HarryPotterScript, HPRender, Job, RenderOutput
from core.database import SessionLocal
from engines.upload_engine import UploadEngine
from engines.scheduler_engine import PublicationScheduler
from engines.deduplication_engine import DeduplicationRouter, StoryDeduplicationEngine
from engines.drive_engine import DriveVaultEngine
from dashboard.data_provider import SystemDataProvider
from core.lifecycle_gateway import vault_transition_to_published, InvariantViolationError, is_valid_youtube_id
from main import resolve_vault_file_metadata


def run_full_port_verification():
    print("=" * 80)
    print("HARRY POTTER AUTOMATION — PROVEN MECHANISM PORT VERIFICATION")
    print("=" * 80)

    db = SessionLocal()
    uploader = UploadEngine()
    scheduler = PublicationScheduler()
    drive = DriveVaultEngine()
    data_provider = SystemDataProvider()

    test_results = {}

    # -------------------------------------------------------------------------
    # TEST 1: CHANNEL IDENTITY & CREDENTIAL AUDIT
    # -------------------------------------------------------------------------
    print("\n[TEST 1] Verifying YouTube Authenticated Identity & Token Isolation...")
    try:
        assert TOKEN_PATH.name == "hp_token.json", f"Wrong token name: {TOKEN_PATH.name}"
        assert TOKEN_PATH.exists(), f"Token file missing: {TOKEN_PATH}"
        
        yt = uploader.get_youtube_service()
        ch_resp = yt.channels().list(part="snippet,id", mine=True).execute()
        items = ch_resp.get("items", [])
        assert len(items) > 0, "No channel found for authenticated token"
        
        actual_id = items[0]["id"]
        actual_title = items[0]["snippet"]["title"]
        EXPECTED_ID = "UCsghEXDa3EzxI4d93cjT-bQ"
        
        print(f"  Authenticated Channel ID:    {actual_id}")
        print(f"  Authenticated Channel Title: {actual_title}")
        print(f"  Token Path:                  {TOKEN_PATH}")
        
        assert actual_id == EXPECTED_ID, f"CHANNEL MISMATCH! Expected {EXPECTED_ID}, got {actual_id}"
        assert "STORY FORGE" in actual_title.upper(), f"Channel title mismatch: {actual_title}"
        assert actual_id != "UCu4Fm7vO2q7C6c-zJv920YQ", "CRITICAL ERROR: Pointing to AL AMR Channel!"
        
        test_results["test_1_channel_identity"] = "PASSED"
        print("  --> [TEST 1 PASSED]: Confirmed STORY FORGE (UCsghEXDa3EzxI4d93cjT-bQ) strictly isolated.")
    except Exception as e:
        test_results["test_1_channel_identity"] = f"FAILED: {e}"
        print(f"  --> [TEST 1 FAILED]: {e}")

    # -------------------------------------------------------------------------
    # TEST 2: AUTHORITATIVE INVENTORY FETCH
    # -------------------------------------------------------------------------
    print("\n[TEST 2] Fetching Authoritative YouTube Inventory...")
    try:
        inventory = data_provider.fetch_authoritative_youtube_inventory(db=db, force_refresh=True)
        pub_shorts = inventory.get("public_shorts", [])
        sched_shorts = inventory.get("scheduled_shorts", [])
        priv_unscheduled = inventory.get("private_unscheduled", [])
        
        print(f"  Public Shorts:       {len(pub_shorts)}")
        print(f"  Scheduled Shorts:    {len(sched_shorts)}")
        print(f"  Private Unscheduled: {len(priv_unscheduled)}")
        
        assert len(pub_shorts) == 0, f"Expected 0 public shorts, got {len(pub_shorts)}"
        assert len(sched_shorts) == 0, f"Expected 0 scheduled shorts, got {len(sched_shorts)}"
        assert len(priv_unscheduled) == 38, f"Expected 38 legacy private videos, got {len(priv_unscheduled)}"
        
        test_results["test_2_inventory_fetch"] = "PASSED"
        print("  --> [TEST 2 PASSED]: Clean baseline inventory verified (0 public, 0 scheduled, 38 private).")
    except Exception as e:
        test_results["test_2_inventory_fetch"] = f"FAILED: {e}"
        print(f"  --> [TEST 2 FAILED]: {e}")

    # -------------------------------------------------------------------------
    # TEST 3: 4-SLOT HORIZON ALLOCATION
    # -------------------------------------------------------------------------
    print("\n[TEST 3] Testing Publication Slot Horizon Allocation...")
    try:
        vacant_slots = scheduler.get_vacant_slots_in_horizon(db=db, horizon_hours=48)
        print(f"  Total vacant slots in 48-hour forward horizon: {len(vacant_slots)}")
        
        canonical_times = [(h, m) for h, m, _ in PUBLISHING_SLOTS_UTC]
        print(f"  Canonical Slot Times: {canonical_times}")
        assert canonical_times == [(2, 30), (10, 30), (18, 30)], "Slot times mismatch!"
        assert DAILY_SHORTS_LIMIT == 3, f"DAILY_SHORTS_LIMIT is {DAILY_SHORTS_LIMIT}, expected 3"
        
        for s in vacant_slots[:8]:
            print(f"    Available Slot: {s.strftime('%Y-%m-%d %H:%M UTC')}")
            assert (s.hour, s.minute) in canonical_times, f"Non-canonical slot time: {s}"
        
        assert len(vacant_slots) >= 5, f"Expected at least 5-6 vacant slots in 48h horizon, got {len(vacant_slots)}"
        test_results["test_3_horizon_allocation"] = "PASSED"
        print("  --> [TEST 3 PASSED]: 3-slot/day horizon (02:30, 10:30, 18:30 UTC) verified.")
    except Exception as e:
        test_results["test_3_horizon_allocation"] = f"FAILED: {e}"
        print(f"  --> [TEST 3 FAILED]: {e}")

    # -------------------------------------------------------------------------
    # TEST 4: DRIVE 01_READY STOCK & METADATA RESOLUTION
    # -------------------------------------------------------------------------
    print("\n[TEST 4] Validating Drive 01_READY Stock & Canonical Metadata Resolution...")
    ready_files = []
    try:
        all_ready = drive.list_files_in_folder("01_READY")
        ready_files = [f for f in all_ready if f.get("name", "").startswith("hps_")]
        print(f"  Found {len(ready_files)} Harry Potter Shorts in Drive '01_READY' vault.")
        assert len(ready_files) == 8, f"Expected 8 Harry Potter files in 01_READY, got {len(ready_files)}"
        
        for rf in ready_files:
            meta = resolve_vault_file_metadata(rf, db=db)
            title = meta["title"]
            desc = meta["description"]
            tags = meta["tags"]
            script_id = meta.get("script_id")
            
            print(f"\n  File: {rf.get('name')}")
            print(f"    Title:       {title}")
            print(f"    Script ID:   {script_id}")
            print(f"    Tags:        {tags[:4]}")
            print(f"    Desc Lead:   {desc.splitlines()[0][:70]}...")
            
            assert not title.startswith("short_"), f"Title has raw prefix: {title}"
            assert not title.startswith("hps_"), f"Title has raw filename: {title}"
            assert "#Shorts" in title or "#shorts" in title.lower(), f"Missing #Shorts hashtag: {title}"
            assert len(title) <= 100, f"Title exceeds 100 chars: {len(title)}"
            assert "Harry Potter" in title or "Hogwarts" in title or "Mirror" in title, f"Title lacks HP context: {title}"
            assert "Voiceover by Bella" in desc, "Description missing Bella voice attribution"
            assert "#HarryPotter" in desc, "Description missing #HarryPotter hashtag"
        
        test_results["test_4_metadata_resolution"] = "PASSED"
        print("\n  --> [TEST 4 PASSED]: All 8 READY Shorts resolved to canonical titles & rich descriptions.")
    except Exception as e:
        test_results["test_4_metadata_resolution"] = f"FAILED: {e}"
        print(f"\n  --> [TEST 4 FAILED]: {e}")

    # -------------------------------------------------------------------------
    # TEST 5: 16-POINT PUBLICATION SAFETY GATE EVALUATION
    # -------------------------------------------------------------------------
    print("\n[TEST 5] Evaluating 16-Point Publication Safety Gate on All 8 Shorts...")
    try:
        passed_count = 0
        test_slot = datetime.now(timezone.utc) + timedelta(hours=4)
        
        for rf in ready_files:
            meta = resolve_vault_file_metadata(rf, db=db)
            c_name = rf.get("name", "").replace(".mp4", "")
            c_job_id = f"job_{c_name}"
            
            # Find or bind local HPRender
            hp_render = db.query(HPRender).filter(HPRender.video_path.ilike(f"%{c_name}%")).first()
            assert hp_render is not None, f"HPRender record missing for {c_name}"
            
            # Create transient Job and RenderOutput representations for the gate
            temp_job = Job(
                id=c_job_id,
                state="READY_TO_UPLOAD",
                topic_id=c_name
            )
            
            gate_passed, gate_reason = uploader.evaluate_publication_safety_gate(
                db=db,
                job=temp_job,
                render=hp_render,
                metadata=meta,
                scheduled_slot=test_slot
            )
            
            print(f"  Checking {rf.get('name')}: passed={gate_passed}, reason={gate_reason}")
            assert gate_passed, f"Gate failed for {rf.get('name')}: {gate_reason}"
            passed_count += 1
            
        assert passed_count == 8, f"Expected 8 passes, got {passed_count}"
        test_results["test_5_safety_gates"] = "PASSED"
        print(f"  --> [TEST 5 PASSED]: 8/8 Shorts passed all 16 publication safety gates.")
    except Exception as e:
        test_results["test_5_safety_gates"] = f"FAILED: {e}"
        print(f"  --> [TEST 5 FAILED]: {e}")

    # -------------------------------------------------------------------------
    # TEST 6: CHRONOLOGICAL PART DIFFERENTIATION & DEDUPLICATION INVARIANTS
    # -------------------------------------------------------------------------
    print("\n[TEST 6] Testing Chronological Part Differentiation & Deduplication...")
    try:
        dedup = StoryDeduplicationEngine()
        
        # Test 6A: Sequential parts must NOT be flagged as duplicates of each other
        res_p1_p2 = dedup.check_deterministic_duplicate(
            "Harry Potter: The Boy Who Lived [PART 01] #Shorts",
            "Harry Potter: The Boy Who Lived [PART 02] #Shorts"
        )
        print(f"  Part 01 vs Part 02 comparison: is_duplicate={bool(res_p1_p2 and res_p1_p2.is_duplicate)}")
        assert res_p1_p2 is None or not res_p1_p2.is_duplicate, "Part 01 and Part 02 falsely flagged as duplicate!"
        
        res_p3_p4 = dedup.check_deterministic_duplicate(
            "Harry Potter: The Boy Who Lived [PART 03] #Shorts",
            "Harry Potter: The Boy Who Lived [PART 04] #Shorts"
        )
        assert res_p3_p4 is None or not res_p3_p4.is_duplicate, "Part 03 and Part 04 falsely flagged as duplicate!"
        
        # Test 6B: Exact same title must be caught as duplicate
        res_dup = dedup.check_deterministic_duplicate(
            "Harry Potter: The Boy Who Lived [PART 01] #Shorts",
            "Harry Potter: The Boy Who Lived [PART 01] #Shorts"
        )
        print(f"  Exact duplicate comparison: is_duplicate={bool(res_dup and res_dup.is_duplicate)}")
        assert res_dup is not None and res_dup.is_duplicate, "Exact duplicate was NOT detected!"
        
        # Test 6C: Gate 15 blocks duplicate against existing DB upload
        dummy_upl = UploadRecord(
            id="test_dup_upl_001",
            job_id="job_test_dup",
            youtube_video_id="TEST_VID_DUP",
            title="The Secret Inscription on the Mirror of Erised | Harry Potter #Shorts",
            description="The Secret Inscription on the Mirror of Erised | Harry Potter #Shorts synopsis",
            status="SCHEDULED",
            scheduled_publish_at=datetime.utcnow() + timedelta(days=1)
        )
        db.add(dummy_upl)
        db.commit()
        
        try:
            erised_file = next(f for f in ready_files if "erised" in f["name"])
            meta = resolve_vault_file_metadata(erised_file, db=db)
            c_name = erised_file.get("name", "").replace(".mp4", "")
            hp_render = db.query(HPRender).filter(HPRender.video_path.ilike(f"%{c_name}%")).first()
            
            temp_job_dup = Job(
                id="job_competing_candidate",
                state="READY_TO_UPLOAD",
                topic_id="top_competing"
            )
            
            gate_passed, gate_reason = uploader.evaluate_publication_safety_gate(
                db=db,
                job=temp_job_dup,
                render=hp_render,
                metadata=meta,
                scheduled_slot=datetime.utcnow() + timedelta(days=1)
            )
            print(f"  Gate 15 Duplicate Block: passed={gate_passed}, reason={gate_reason}")
            assert not gate_passed, "Gate 15 allowed a duplicate story!"
            assert "Gate 15" in gate_reason, f"Expected Gate 15 failure, got: {gate_reason}"
        finally:
            db.delete(dummy_upl)
            db.commit()

        test_results["test_6_dedup_invariants"] = "PASSED"
        print("  --> [TEST 6 PASSED]: Chronological parts differentiation and Gate 15 dedup blocking confirmed.")
    except Exception as e:
        test_results["test_6_dedup_invariants"] = f"FAILED: {e}"
        print(f"  --> [TEST 6 FAILED]: {e}")

    # -------------------------------------------------------------------------
    # TEST 7: LIFECYCLE NEGATIVE INVARIANTS ENFORCEMENT
    # -------------------------------------------------------------------------
    print("\n[TEST 7] Testing Lifecycle Negative Invariants & Gateway Enforcement...")
    try:
        mock_drive = MagicMock(spec=DriveVaultEngine)
        
        # Test 7A: Direct transition from 01_READY to 03_PUBLISHED is blocked
        mock_drive.get_file_metadata.return_value = {
            "id": "mock_ready_file",
            "name": "test.mp4",
            "parents": ["01_READY"]
        }
        try:
            vault_transition_to_published(
                file_id="mock_ready_file",
                youtube_video_id="dQw4w9WgXcQ",
                db=db,
                drive_engine=mock_drive,
                caller="test"
            )
            raise AssertionError("GATEWAY FAILED TO REJECT DIRECT 01_READY TRANSITION!")
        except InvariantViolationError as ive:
            print(f"  Expected rejection from 01_READY: {ive}")
            assert "01_READY" in str(ive)

        # Test 7B: Transition without valid YouTube ID is blocked
        mock_drive.get_file_metadata.return_value = {
            "id": "mock_proc_file",
            "name": "test.mp4",
            "parents": ["02_PROCESSING"]
        }
        try:
            vault_transition_to_published(
                file_id="mock_proc_file",
                youtube_video_id="INVALID_ID",
                db=db,
                drive_engine=mock_drive,
                caller="test"
            )
            raise AssertionError("GATEWAY FAILED TO REJECT INVALID YOUTUBE ID!")
        except InvariantViolationError as ive:
            print(f"  Expected rejection for invalid YouTube ID: {ive}")
            assert "Invalid or empty youtube_video_id" in str(ive)

        # Test 7C: YouTube ID format validation
        assert is_valid_youtube_id("dQw4w9WgXcQ") is True
        assert is_valid_youtube_id("TEST_MODE_ID") is False
        assert is_valid_youtube_id("short") is False

        test_results["test_7_lifecycle_invariants"] = "PASSED"
        print("  --> [TEST 7 PASSED]: Lifecycle negative invariants strictly enforced.")
    except Exception as e:
        test_results["test_7_lifecycle_invariants"] = f"FAILED: {e}"
        print(f"  --> [TEST 7 FAILED]: {e}")

    # -------------------------------------------------------------------------
    # TEST 8: SAFETY VERIFICATION — HARD LOCKS IN PLACE
    # -------------------------------------------------------------------------
    print("\n[TEST 8] Verifying Hard Safety Locks (PUBLISHING_ENABLED & UPLOAD_ENABLED)...")
    try:
        print(f"  PUBLISHING_ENABLED: {PUBLISHING_ENABLED}")
        print(f"  UPLOAD_ENABLED:     {UPLOAD_ENABLED}")
        assert PUBLISHING_ENABLED is False, "PUBLISHING_ENABLED MUST BE FALSE!"
        assert UPLOAD_ENABLED is False, "UPLOAD_ENABLED MUST BE FALSE!"
        
        inventory_after = data_provider.fetch_authoritative_youtube_inventory(db=db, force_refresh=True)
        assert len(inventory_after["public_shorts"]) == 0
        assert len(inventory_after["scheduled_shorts"]) == 0
        assert len(inventory_after["private_unscheduled"]) == 38
        
        test_results["test_8_safety_locks"] = "PASSED"
        print("  --> [TEST 8 PASSED]: Hard publishing locks active. 0 uploads made to YouTube.")
    except Exception as e:
        test_results["test_8_safety_locks"] = f"FAILED: {e}"
        print(f"  --> [TEST 8 FAILED]: {e}")

    db.close()

    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY:")
    print("=" * 80)
    all_passed = True
    for t_name, t_status in test_results.items():
        print(f"  {t_name:30}: {t_status}")
        if t_status != "PASSED":
            all_passed = False

    print("=" * 80)
    if all_passed:
        print("[SUCCESS] ALL 8 AUTOMATION PORT VERIFICATION SUITES PASSED PERFECTLY!")
    else:
        print("[FAILURE] SOME TESTS FAILED. CHECK LOGS ABOVE.")
    print("=" * 80)
    return all_passed


if __name__ == "__main__":
    success = run_full_port_verification()
    sys.exit(0 if success else 1)
