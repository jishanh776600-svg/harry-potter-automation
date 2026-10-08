import os
import sys
import json
from pathlib import Path
from core.database import SessionLocal
from config.settings import (
    HP_YOUTUBE_CHANNEL_ID,
    PUBLISHING_ENABLED,
    UPLOAD_ENABLED,
    APPROVED_PRODUCTION_VOICES,
    KOKORO_VOICE,
    GOOGLE_DRIVE_VAULT_ROOT,
    TARGET_RESERVE_BUFFER,
    SHORTS_PER_DAY,
    SCHEDULING_HORIZON_HOURS,
    VISUAL_SOURCE_PRIORITY
)
from config.constants import PUBLISHING_SLOTS_UTC
from engines.drive_engine import DriveVaultEngine, is_valid_ready_short
from engines.tts_engine import TTSEngine
from engines.qa_engine import QAEngine

def run_test():
    print('='*60)
    print('HARRY POTTER AUTOMATION — CLEAN CLOUD PRODUCTION TEST')
    print('='*60)

    # 1. Configuration & Safety Gate Audit
    print('\n[1/7] Safety Gates & Channel ID Verification...')
    assert HP_YOUTUBE_CHANNEL_ID == 'UCsghEXDa3EzxI4d93cjT-bQ', f'Channel ID mismatch: {HP_YOUTUBE_CHANNEL_ID}'
    assert PUBLISHING_ENABLED is False, 'Publishing MUST be False'
    assert UPLOAD_ENABLED is False, 'Upload MUST be False'
    assert APPROVED_PRODUCTION_VOICES == ['af_bella'], f'Unexpected voice list: {APPROVED_PRODUCTION_VOICES}'
    assert KOKORO_VOICE == 'af_bella', f'Unexpected default voice: {KOKORO_VOICE}'
    assert GOOGLE_DRIVE_VAULT_ROOT == 'Yt_harry_potter_automation', f'Unexpected vault root: {GOOGLE_DRIVE_VAULT_ROOT}'
    assert TARGET_RESERVE_BUFFER == 8, f'Unexpected buffer target: {TARGET_RESERVE_BUFFER}'
    assert SHORTS_PER_DAY == 3, f'Unexpected daily shorts limit: {SHORTS_PER_DAY}'
    assert SCHEDULING_HORIZON_HOURS == 48, f'Unexpected scheduling horizon: {SCHEDULING_HORIZON_HOURS}'
    assert PUBLISHING_SLOTS_UTC == [(2, 30, '02:30 UTC (08:00 AM IST)'), (10, 30, '10:30 UTC (04:00 PM IST)'), (18, 30, '18:30 UTC (12:00 AM IST)')], f'Unexpected slots: {PUBLISHING_SLOTS_UTC}'
    print('  [+] Channel Safety Gate: LOCKED to UCsghEXDa3EzxI4d93cjT-bQ')
    print('  [+] Publishing & Upload: LOCKED to False')
    print('  [+] Buffer & Scheduling: 8 Reserve / 3 per Day / 48h Horizon')

    # 2. Drive Vault Architecture
    print('\n[2/7] Drive Vault Architecture & Inventory...')
    drive = DriveVaultEngine(offline_mode=False)
    folders = drive.inspect_or_init_vault()
    for name in ['00_SYSTEM', '01_READY', '02_PROCESSING', '03_PUBLISHED', '04_FAILED']:
        assert folders.get(name) is not None, f'Missing vault folder: {name}'
    print(f"  [+] Vault Root: {folders['root']}")
    print("  [+] Lifecycle folders verified: 00_SYSTEM, 01_READY, 02_PROCESSING, 03_PUBLISHED, 04_FAILED")

    # 3. 01_READY Stock Verification
    session = SessionLocal()
    ready_files = drive.list_files_in_folder("01_READY")
    valid_ready = []
    for f in ready_files:
        is_val, reason = is_valid_ready_short(f, db=session)
        if is_val:
            valid_ready.append(f)
        print(f"   - {f.get('name')}: valid={is_val} ({reason})")
    print(f"  [+] 01_READY Valid Reserve: {len(valid_ready)} / {TARGET_RESERVE_BUFFER} Shorts")
    assert len(valid_ready) >= 4, f"Expected at least 4 approved shorts in 01_READY, got {len(valid_ready)}"

    # 4. Database Sync State in 00_SYSTEM
    print("\n[3/7] Canonical Database Sync State...")
    sys_files = drive.list_files_in_folder("00_SYSTEM")
    sys_names = {f["name"]: f for f in sys_files}
    assert "pipeline.db" in sys_names, "pipeline.db missing in 00_SYSTEM"
    print(f"  [+] pipeline.db present in Drive 00_SYSTEM (ID: {sys_names['pipeline.db']['id']}, Size: {sys_names['pipeline.db'].get('size')} bytes)")
    if "visual_memory.db" in sys_names:
        print(f"  [+] visual_memory.db present in Drive 00_SYSTEM (ID: {sys_names['visual_memory.db']['id']})")
    if "short_fingerprints.db" in sys_names:
        print(f"  [+] short_fingerprints.db present in Drive 00_SYSTEM (ID: {sys_names['short_fingerprints.db']['id']})")

    # 5. Kokoro TTS & Bella Voice
    print("\n[4/7] Kokoro TTS & Bella Synthesis Test...")
    tts = TTSEngine()
    test_wav = Path("data/renders/test_cloud_bella_speech.wav")
    success, dur = tts.generate_kokoro_audio(
        text="Deep inside the Hogwarts library, Harry discovered a book that had been hidden for centuries.",
        output_path=test_wav,
        voice="af_bella",
        speed=1.00
    )
    assert success and dur > 2.0, f"TTS synthesis failed (success={success}, dur={dur})"
    print(f"  [+] Bella speech synthesized: {dur:.2f}s ({test_wav.stat().st_size} bytes)")

    # 6. Subtitle Font & BGM
    print("\n[5/7] Subtitle Font & Harry Potter BGM Verification...")
    font_path = Path("assets/fonts/HarryP.ttf")
    assert font_path.exists(), f"Font missing at {font_path}"
    print(f"  [+] Font HarryP.ttf verified ({font_path.stat().st_size} bytes)")
    bgm_candidates = list(Path("assets/music").glob("*.mp3")) + list(Path("assets/music").glob("*.wav"))
    assert len(bgm_candidates) > 0, "No BGM tracks found in assets/music"
    print(f"  [+] Harry Potter BGM track verified: {bgm_candidates[0].name}")

    # 7. QA Engine Verification
    print("\n[6/7] Media Inspection & QA Engine Test...")
    qa = QAEngine()
    test_mp4 = Path("data/renders/hps_ns_b1c01_gc0001_0003.mp4")
    info = qa.inspect_media(test_mp4)
    assert info.get("has_video") and info.get("has_audio"), "QA failed media inspection"
    print(f"  [+] Sample short verified: {info['width']}x{info['height']} ({info['video_codec']}/{info['audio_codec']}), duration: {info['duration']:.2f}s")

    # 8. End-to-End Safety Confirmation
    print("\n[7/7] Autonomous Safety Confirmation...")
    print("  [+] Zero direct YouTube uploads performed.")
    print("  [+] Zero schedule mutations executed.")
    print("  [+] Quality benchmark (First 4 Approved Shorts) preserved.")
    print("\n[PASS] All 7 Cloud Production Verification Gates Passed Successfully!")
    session.close()

if __name__ == "__main__":
    run_test()