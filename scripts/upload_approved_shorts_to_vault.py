from pathlib import Path
from engines.drive_engine import DriveVaultEngine, is_valid_ready_short
from core.database import SessionLocal

APPROVED_FILES = [
    'hps_ns_b1c01_gc0001_0003.mp4',
    'hps_ns_b1c01_gc0004_0006.mp4',
    'hps_disc_peeves_poltergeist_b1.mp4',
    'hps_disc_neville_hufflepuff_sorting_b1.mp4'
]

def main():
    renders_dir = Path('data/renders')
    engine = DriveVaultEngine(offline_mode=False)
    session = SessionLocal()

    print('[*] Inspecting Google Drive 01_READY folder...')
    existing_files = engine.list_files_in_folder('01_READY')
    existing_names = {f['name']: f for f in existing_files}
    print('Existing in 01_READY:', list(existing_names.keys()))

    for filename in APPROVED_FILES:
        local_path = renders_dir / filename
        if not local_path.exists():
            print(f'[-] ERROR: Local file not found: {local_path}')
            continue

        if filename in existing_names:
            file_id = existing_names[filename].get("id")
            print(f"[=] Already exists in 01_READY: {filename} (ID: {file_id})")
            continue

        print(f"[+] Uploading {filename} to Drive 01_READY...")
        meta = {
            "voice": "af_bella",
            "voice_id": "af_bella",
            "niche": "Harry Potter",
            "qa_status": "PASSED"
        }
        res = engine.upload_video_to_vault(
            local_path=local_path,
            target_folder="01_READY",
            metadata_properties=meta
        )
        print(f"    Uploaded: ID={res.get('id')}")

    print("\n[*] Auditing 01_READY stock in Drive:")
    ready_files = engine.list_files_in_folder("01_READY")
    valid_count = 0
    for f in ready_files:
        is_val, reason = is_valid_ready_short(f, db=session)
        print(f" - {f.get('name')}: valid={is_val} ({reason})")
        if is_val:
            valid_count += 1

    print(f"\n[SUMMARY] Total Valid 01_READY Stock in Drive: {valid_count} / 8")
    session.close()

if __name__ == "__main__":
    main()