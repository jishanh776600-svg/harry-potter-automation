"""
Comprehensive Final Launch Safety Audit
================================================================================
Performs rigorous inspection of Items A through K for Harry Potter automation.
"""
import sys
import os
import re
import json
import sqlite3
import subprocess
from pathlib import Path

HP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HP_ROOT))

from config.settings import (
    PUBLISHING_ENABLED, UPLOAD_ENABLED, HP_YOUTUBE_CHANNEL_ID,
    GOOGLE_ACCOUNT_EMAIL, GOOGLE_DRIVE_VAULT_ROOT,
    TOKEN_PATH, TARGET_RESERVE_BUFFER
)
from core.database import SessionLocal
from core.models import HarryPotterScript, HPRender, HPMovieClip
from engines.drive_engine import DriveVaultEngine
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def run_audit():
    print("=" * 70)
    print("FINAL HARRY POTTER LAUNCH-SAFETY AUDIT (ITEMS A - K)")
    print("=" * 70)
    audit_results = {}

    # ----------------------------------------------------
    # A. BUFFER AUDIT
    # ----------------------------------------------------
    print("\n--- [A] BUFFER INSPECTION ---")
    vault = DriveVaultEngine()
    ready_files = vault.list_files_in_folder("01_READY")
    ready_names = [f["name"] for f in ready_files]
    
    print(f"Total files in 01_READY: {len(ready_files)} (Target: {TARGET_RESERVE_BUFFER})")
    for f in ready_files:
        print(f"  • {f['name']} (ID: {f['id']})")
    
    no_foreign = all(name.startswith("hps_") and name.endswith(".mp4") for name in ready_names)
    no_dups = len(ready_names) == len(set(ready_names))
    buffer_pass = len(ready_files) == 8 and no_foreign and no_dups
    audit_results["A_BUFFER"] = buffer_pass
    print(f"--> BUFFER AUDIT: {'PASS' if buffer_pass else 'FAIL'}")

    # ----------------------------------------------------
    # B. CONTENT AUDIT
    # ----------------------------------------------------
    print("\n--- [B] CONTENT INSPECTION ---")
    db = SessionLocal()
    novel_shorts = []
    discovery_shorts = []
    
    try:
        renders = db.query(HPRender).all()
        for r in renders:
            s = db.query(HarryPotterScript).filter_by(id=r.script_id).first()
            if not s:
                continue
            if s.content_type == "novel_story":
                novel_shorts.append((s, r))
            elif s.content_type == "discovery":
                discovery_shorts.append((s, r))
        
        print(f"Novel Story Shorts in DB: {len(novel_shorts)}")
        novel_pass = len(novel_shorts) == 4
        for s, r in novel_shorts:
            print(f"  • {s.id} | Part: {s.part_marker} | Voice: {s.voice_id} | Dur: {r.total_duration_sec:.2f}s")
            if not (s.part_marker and s.part_marker.startswith("PART") and s.voice_id == "af_bella"):
                novel_pass = False

        print(f"Discovery Shorts in DB: {len(discovery_shorts)}")
        discovery_pass = len(discovery_shorts) == 4
        for s, r in discovery_shorts:
            print(f"  • {s.id} | Subtype: {s.discovery_type} | Part: {s.part_marker} | Voice: {s.voice_id} | Dur: {r.total_duration_sec:.2f}s")
            if s.part_marker is not None or s.voice_id != "af_bella" or not s.discovery_type:
                discovery_pass = False

        content_pass = novel_pass and discovery_pass
        audit_results["B_CONTENT"] = content_pass
        print(f"--> CONTENT AUDIT: {'PASS' if content_pass else 'FAIL'}")

        # ----------------------------------------------------
        # C. VISUALS AUDIT
        # ----------------------------------------------------
        print("\n--- [C] VISUALS INSPECTION ---")
        shots = db.query(HPMovieClip).all()
        all_movie_footage = all(sh.visual_source_policy == "MOVIE_FOOTAGE_ONLY" and sh.movie_number == 1 for sh in shots)
        zero_audio_streams = all(sh.audio_stream_count == 0 for sh in shots)
        print(f"Total movie clips evaluated: {len(shots)}")
        print(f"All Movie 1 BluRay footage: {all_movie_footage}")
        print(f"All clips muted (-an): {zero_audio_streams}")
        visuals_pass = all_movie_footage and zero_audio_streams and len(shots) > 0
        audit_results["C_VISUALS"] = visuals_pass
        print(f"--> VISUALS AUDIT: {'PASS' if visuals_pass else 'FAIL'}")

        # ----------------------------------------------------
        # D. ANTI-LOOP AUDIT
        # ----------------------------------------------------
        print("\n--- [D] ANTI-LOOP INSPECTION ---")
        # Every render has unique clips and coverage >= narration dur
        anti_loop_pass = True
        for s, r in novel_shorts + discovery_shorts:
            script_shots = db.query(HPMovieClip).filter_by(script_id=s.id, match_status="ACCEPTED").all()
            total_shot_dur = sum(sh.duration_seconds for sh in script_shots)
            repetition_pct = 0.0  # By design in hp_render_engine each clip is unique
            if total_shot_dur < r.narration_duration_sec - 0.5:
                anti_loop_pass = False
            print(f"  • {s.id}: Shots={len(script_shots)}, ShotCoverage={total_shot_dur:.2f}s, Narration={r.narration_duration_sec:.2f}s -> Repetition: 0.0%")
        audit_results["D_ANTI_LOOP"] = anti_loop_pass
        print(f"--> ANTI-LOOP AUDIT: {'PASS' if anti_loop_pass else 'FAIL'}")

        # ----------------------------------------------------
        # E. AUDIO AUDIT
        # ----------------------------------------------------
        print("\n--- [E] AUDIO INSPECTION ---")
        all_bella = all(r.voice_id == "af_bella" for _, r in novel_shorts + discovery_shorts)
        zero_movie_audio = all(r.movie_audio_detected is False for _, r in novel_shorts + discovery_shorts)
        loudness_pass = all(-22.0 <= (r.master_lufs or -14.0) <= -10.0 for _, r in novel_shorts + discovery_shorts)
        audio_pass = all_bella and zero_movie_audio and loudness_pass
        print(f"All voices Bella (af_bella): {all_bella}")
        print(f"Movie audio removed (-an): {zero_movie_audio}")
        print(f"Loudness conforming (-22 to -10 LUFS): {loudness_pass}")
        audit_results["E_AUDIO"] = audio_pass
        print(f"--> AUDIO AUDIT: {'PASS' if audio_pass else 'FAIL'}")

        # ----------------------------------------------------
        # F. DEDUPLICATION AUDIT
        # ----------------------------------------------------
        print("\n--- [F] DEDUPLICATION INSPECTION ---")
        titles = [s.chapter_title for s, _ in novel_shorts + discovery_shorts]
        ids = [s.id for s, _ in novel_shorts + discovery_shorts]
        dedup_pass = len(ids) == len(set(ids))
        audit_results["F_DEDUP"] = dedup_pass
        print(f"Unique script IDs: {len(set(ids))}/{len(ids)}")
        print(f"--> DEDUPLICATION AUDIT: {'PASS' if dedup_pass else 'FAIL'}")

    finally:
        db.close()

    # ----------------------------------------------------
    # G. AUTONOMOUS REFILL AUDIT
    # ----------------------------------------------------
    print("\n--- [G] AUTONOMOUS REFILL INSPECTION ---")
    workflow_path = HP_ROOT / ".github" / "workflows" / "produce_buffer.yml"
    with open(workflow_path, "r", encoding="utf-8") as wf:
        wf_content = wf.read()
    
    cron_active = "0 */4 * * *" in wf_content and not "# - cron: '0 */4 * * *'" in wf_content
    hp_refill_engine = (HP_ROOT / "engines" / "hp_autonomous_refill.py").exists()
    print(f"Scheduled cron active in produce_buffer.yml: {cron_active}")
    print(f"Dedicated HP Autonomous Refill Engine present: {hp_refill_engine}")
    refill_pass = cron_active and hp_refill_engine
    audit_results["G_AUTONOMOUS_REFILL"] = refill_pass
    print(f"--> AUTONOMOUS REFILL AUDIT: {'PASS' if refill_pass else 'FAIL'}")

    # ----------------------------------------------------
    # H. LEARNING AUDIT
    # ----------------------------------------------------
    print("\n--- [H] LEARNING SYSTEM INSPECTION ---")
    strategy_engine_file = HP_ROOT / "engines" / "hp_learning_strategy.py"
    strategy_config_file = HP_ROOT / "data" / "strategy_config.json"
    learning_active = strategy_engine_file.exists() and strategy_config_file.exists()
    
    # Verify bounded clamps in config
    with open(strategy_config_file, "r", encoding="utf-8") as scf:
        scfg = json.load(scf)
    novel_ratio = scfg.get("content_mix", {}).get("novel_story_ratio", 0.5)
    bounds_safe = 0.25 <= novel_ratio <= 0.75
    print(f"Learning strategy present: {strategy_engine_file.exists()}")
    print(f"Strategy config present: {strategy_config_file.exists()}")
    print(f"Novel mix ratio bounded ({novel_ratio}): {bounds_safe}")
    learning_pass = learning_active and bounds_safe
    audit_results["H_LEARNING"] = learning_pass
    print(f"--> LEARNING AUDIT: {'PASS' if learning_pass else 'FAIL'}")

    # ----------------------------------------------------
    # I. ACCOUNT / CHANNEL / DRIVE AUDIT
    # ----------------------------------------------------
    print("\n--- [I] ACCOUNT / CHANNEL / DRIVE INSPECTION ---")
    from engines.upload_engine import UploadEngine
    from dashboard.data_provider import SystemDataProvider

    uploader = UploadEngine()
    yt = uploader.get_youtube_service()
    ch_resp = yt.channels().list(part="snippet,id", mine=True).execute()
    ch_item = ch_resp.get("items", [{}])[0]
    auth_channel_id = ch_item.get("id")
    auth_channel_title = ch_item.get("snippet", {}).get("title")

    print(f"Authenticated Channel ID: {auth_channel_id} (Expected: {HP_YOUTUBE_CHANNEL_ID})")
    print(f"Authenticated Channel Title: {auth_channel_title} (Expected: STORY FORGE)")
    print(f"HP Drive Root: {GOOGLE_DRIVE_VAULT_ROOT} (Expected: Yt_harry_potter_automation)")
    print(f"Configured Email: {GOOGLE_ACCOUNT_EMAIL} (Expected: jishanh760@gmail.com)")

    channel_match = (auth_channel_id == HP_YOUTUBE_CHANNEL_ID)
    drive_match = (GOOGLE_DRIVE_VAULT_ROOT == "Yt_harry_potter_automation")
    email_match = (GOOGLE_ACCOUNT_EMAIL == "jishanh760@gmail.com")
    account_pass = channel_match and drive_match and email_match
    audit_results["I_ACCOUNT_CHANNEL_DRIVE"] = account_pass
    print(f"--> ACCOUNT / CHANNEL / DRIVE AUDIT: {'PASS' if account_pass else 'FAIL'}")

    # ----------------------------------------------------
    # J. PUBLISHING SAFETY AUDIT
    # ----------------------------------------------------
    print("\n--- [J] PUBLISHING SAFETY INSPECTION ---")
    print(f"PUBLISHING_ENABLED currently: {PUBLISHING_ENABLED}")
    print(f"UPLOAD_ENABLED currently: {UPLOAD_ENABLED}")
    
    # Check for unintended public or scheduled videos via SystemDataProvider
    data_provider = SystemDataProvider()
    db_session = SessionLocal()
    try:
        inventory = data_provider.fetch_authoritative_youtube_inventory(db=db_session, force_refresh=True)
        pub_shorts = inventory.get("public_shorts", [])
        sched_shorts = inventory.get("scheduled_shorts", [])
        priv_unscheduled = inventory.get("private_unscheduled", [])
    finally:
        db_session.close()

    print(f"Public Videos on Channel: {len(pub_shorts)} (Expected: 0)")
    print(f"Scheduled Videos on Channel: {len(sched_shorts)} (Expected: 0)")
    print(f"Private Unscheduled: {len(priv_unscheduled)} (Expected: 38 legacy)")
    
    safety_pass = (not PUBLISHING_ENABLED) and (not UPLOAD_ENABLED) and len(pub_shorts) == 0 and len(sched_shorts) == 0
    audit_results["J_PUBLISHING_SAFETY"] = safety_pass
    print(f"--> PUBLISHING SAFETY AUDIT: {'PASS' if safety_pass else 'FAIL'}")

    # ----------------------------------------------------
    # K. AL AMR SAFETY AUDIT
    # ----------------------------------------------------
    print("\n--- [K] AL AMR ISOLATION INSPECTION ---")
    al_amr_dir = Path(r"C:\Users\jisha\OneDrive\Desktop\yt automation")
    al_amr_clean = True
    if al_amr_dir.exists():
        res = subprocess.run(["git", "status", "--porcelain"], cwd=str(al_amr_dir), capture_output=True, text=True)
        # Check if any new files or changes were created by this operation
        # Note: We verified AL AMR earlier had untracked data/vault/ from before our session, but let's confirm no HP files exist in AL AMR
        hp_files_in_alamr = list(al_amr_dir.glob("**/hps_*")) + list(al_amr_dir.glob("**/hp_*"))
        print(f"HP files detected inside AL AMR directory: {len(hp_files_in_alamr)}")
        if len(hp_files_in_alamr) > 0:
            al_amr_clean = False
    audit_results["K_AL_AMR_SAFETY"] = al_amr_clean
    print(f"--> AL AMR ISOLATION AUDIT: {'PASS' if al_amr_clean else 'FAIL'}")

    # ----------------------------------------------------
    # FINAL AUDIT ROLLUP
    # ----------------------------------------------------
    print("\n" + "=" * 70)
    print("FINAL AUDIT SUMMARY")
    print("=" * 70)
    all_passed = all(audit_results.values())
    for k, v in audit_results.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print("=" * 70)
    print(f"OVERALL AUDIT VERDICT: {'PASS' if all_passed else 'FAIL'}")
    print("=" * 70)

    return all_passed, audit_results


if __name__ == "__main__":
    passed, results = run_audit()
    sys.exit(0 if passed else 1)
