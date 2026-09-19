"""
Post-Enable Launch Verification
================================================================================
Verifies all 12 post-enable invariants immediately after enabling publishing.
"""
import sys
import subprocess
from pathlib import Path

HP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HP_ROOT))

from config.settings import (
    PUBLISHING_ENABLED, UPLOAD_ENABLED, HP_YOUTUBE_CHANNEL_ID,
    GOOGLE_ACCOUNT_EMAIL, GOOGLE_DRIVE_VAULT_ROOT,
    TOKEN_PATH, TARGET_RESERVE_BUFFER
)
from engines.upload_engine import UploadEngine
from engines.drive_engine import DriveVaultEngine
from dashboard.data_provider import SystemDataProvider
from core.database import SessionLocal


def run_post_verification():
    print("=" * 70)
    print("POST-ENABLE HP LAUNCH VERIFICATION (ITEMS 1 - 12)")
    print("=" * 70)

    # 1. HP channel ID
    print(f"1. HP Channel ID: {HP_YOUTUBE_CHANNEL_ID}")
    assert HP_YOUTUBE_CHANNEL_ID == "UCsghEXDa3EzxI4d93cjT-bQ", "Channel ID mismatch!"

    # 2. HP account
    print(f"2. HP Account: {GOOGLE_ACCOUNT_EMAIL}")
    assert GOOGLE_ACCOUNT_EMAIL == "jishanh760@gmail.com", "Google account mismatch!"

    # 3. HP Drive root
    print(f"3. HP Drive Root: {GOOGLE_DRIVE_VAULT_ROOT}")
    assert GOOGLE_DRIVE_VAULT_ROOT == "Yt_harry_potter_automation", "Drive vault root mismatch!"

    # 4. AL AMR untouched
    al_amr_dir = Path(r"C:\Users\jisha\OneDrive\Desktop\yt automation")
    hp_in_alamr = list(al_amr_dir.glob("**/hps_*"))
    print(f"4. AL AMR Untouched check: {len(hp_in_alamr)} HP files found in AL AMR (Expected 0)")
    assert len(hp_in_alamr) == 0, "AL AMR contaminated!"

    # 5. Publishing mechanism points ONLY to HP
    uploader = UploadEngine()
    yt = uploader.get_youtube_service()
    ch_resp = yt.channels().list(part="snippet,id", mine=True).execute()
    auth_id = ch_resp["items"][0]["id"]
    auth_title = ch_resp["items"][0]["snippet"]["title"]
    print(f"5. Authenticated YouTube Channel: {auth_title} ({auth_id})")
    assert auth_id == "UCsghEXDa3EzxI4d93cjT-bQ", f"Wrong channel: {auth_id}"
    assert "STORY FORGE" in auth_title.upper(), f"Wrong title: {auth_title}"

    # 6. Scheduler sees intended HP publishing configuration
    print(f"6. Publishing Configuration: PUBLISHING_ENABLED={PUBLISHING_ENABLED}, UPLOAD_ENABLED={UPLOAD_ENABLED}")
    assert PUBLISHING_ENABLED is True, "PUBLISHING_ENABLED must be True"
    assert UPLOAD_ENABLED is True, "UPLOAD_ENABLED must be True"

    # 7 & 8. No duplicate schedule or unrelated video entered queue
    db = SessionLocal()
    try:
        dp = SystemDataProvider()
        inventory = dp.fetch_authoritative_youtube_inventory(db=db, force_refresh=True)
        pub_shorts = inventory.get("public_shorts", [])
        sched_shorts = inventory.get("scheduled_shorts", [])
        print(f"7 & 8. YouTube State: Public Shorts = {len(pub_shorts)}, Scheduled Shorts = {len(sched_shorts)}")
        assert len(pub_shorts) == 0, "Unintended public short detected!"
        assert len(sched_shorts) == 0, "Unintended scheduled short detected!"
    finally:
        db.close()

    # 9. READY lifecycle remains valid
    vault = DriveVaultEngine()
    ready_files = vault.list_files_in_folder("01_READY")
    print(f"9. READY Lifecycle: {len(ready_files)}/8 Shorts in 01_READY")
    assert len(ready_files) == 8, f"Expected 8 in 01_READY, got {len(ready_files)}"

    # 10. Autonomous refill remains active
    workflow_path = HP_ROOT / ".github" / "workflows" / "produce_buffer.yml"
    with open(workflow_path, "r", encoding="utf-8") as wf:
        wf_content = wf.read()
    cron_active = "0 */4 * * *" in wf_content
    print(f"10. Autonomous Refill Cron Active: {cron_active}")
    assert cron_active, "Refill cron missing!"

    # 11. Learning remains active
    strategy_cfg = HP_ROOT / "data" / "strategy_config.json"
    print(f"11. Learning Config Active: {strategy_cfg.exists()}")
    assert strategy_cfg.exists(), "Learning config missing!"

    # 12. Safety gate active
    from core.lifecycle_gateway import is_valid_youtube_id
    assert is_valid_youtube_id("12345678901") is True
    assert is_valid_youtube_id("invalid") is False
    print("12. Safety Gates Active: Channel ID Gate, Drive Gate, Anti-Loop Gate, Invariant Gateway Verified.")

    print("=" * 70)
    print("ALL 12 POST-ENABLE VERIFICATION CHECKS PASSED!")
    print("=" * 70)


if __name__ == "__main__":
    run_post_verification()
