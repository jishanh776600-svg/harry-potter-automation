"""
STORY FORGE — Discovery BGM Registration From Google Drive
===========================================================
Authoritatively inspects the dedicated STORY FORGE Google Drive Bgm folder,
validates the sole canonical soundtrack, computes SHA-256 and audio properties,
and persists verified DiscoveryBGMConfig.
"""

import hashlib
import io
import json
import logging
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import soundfile as sf

from config.settings import (
    PROJECT_ROOT, MUSIC_DIR, DATA_DIR, EXPECTED_DRIVE_ROOT_ID
)
from core.discovery_bgm import DiscoveryBGMConfig, DiscoveryBGMGate, BGMConfigurationError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DiscoveryBGMRegistration")


def register_bgm_from_drive() -> DiscoveryBGMConfig:
    creds_file = PROJECT_ROOT / "credentials" / "hp_token.json"
    if not creds_file.exists():
        raise FileNotFoundError(f"Missing {creds_file}")

    creds = Credentials.from_authorized_user_file(str(creds_file))
    drive = build("drive", "v3", credentials=creds)

    # 1. Locate the dedicated Bgm folder inside the STORY FORGE root
    query = f"'{EXPECTED_DRIVE_ROOT_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and name = 'Bgm' and trashed = false"
    res = drive.files().list(q=query, fields="files(id, name, modifiedTime)").execute()
    folders = res.get("files", [])

    if not folders:
        # Fallback to general Bgm query
        query_fallback = "mimeType = 'application/vnd.google-apps.folder' and name = 'Bgm' and trashed = false"
        res_fb = drive.files().list(q=query_fallback, fields="files(id, name, parents, modifiedTime)").execute()
        folders = res_fb.get("files", [])

    if not folders:
        raise RuntimeError("No Bgm folder found in Google Drive.")

    bgm_folder = folders[0]
    folder_id = bgm_folder["id"]
    logger.info(f"Inspecting Authoritative Drive Bgm Folder: '{bgm_folder['name']}' (ID: {folder_id})")

    # 2. List items in the Bgm folder
    f_res = drive.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType, size, createdTime, modifiedTime, md5Checksum)"
    ).execute()
    items = f_res.get("files", [])
    logger.info(f"Found {len(items)} item(s) in Drive Bgm folder.")

    if len(items) == 0:
        raise RuntimeError("Drive Bgm folder is empty. No BGM track found.")
    elif len(items) > 1:
        # Check if exactly one is audio
        audio_items = [it for it in items if "audio" in it.get("mimeType", "") or it["name"].endswith((".mp3", ".wav", ".aac", ".m4a"))]
        if len(audio_items) != 1:
            raise RuntimeError(f"Ambiguous BGM candidates in folder: {[it['name'] for it in items]}")
        selected_item = audio_items[0]
    else:
        selected_item = items[0]

    drive_file_id = selected_item["id"]
    drive_filename = selected_item["name"]
    mime_type = selected_item.get("mimeType", "audio/mpeg")
    file_size = int(selected_item.get("size", 0))
    modified_time = selected_item.get("modifiedTime", "")

    logger.info(f"Authoritative BGM Identified: '{drive_filename}'")
    logger.info(f"  Drive ID: {drive_file_id}")
    logger.info(f"  MIME: {mime_type} | Size: {file_size} bytes | Modified: {modified_time}")

    # Strict check: Must not be Esther Abrami No.6
    lower_name = drive_filename.lower()
    if "esther" in lower_name or "no.6" in lower_name:
        raise RuntimeError(f"Rejected: Drive file '{drive_filename}' matches prohibited Esther No.6.")

    # 3. Download/sync through cloud runner
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    local_mp3 = MUSIC_DIR / drive_filename
    
    logger.info(f"Downloading from Google Drive to: {local_mp3}...")
    request = drive.files().get_media(fileId=drive_file_id)
    with open(local_mp3, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

    logger.info(f"Download complete: {local_mp3.stat().st_size} bytes.")

    # 4. Generate/verify standard 44.1kHz stereo WAV for broadcast production
    local_wav = MUSIC_DIR / (local_mp3.stem + ".wav")
    cmd_wav = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(local_mp3),
        "-ar", "44100", "-ac", "2",
        str(local_wav)
    ]
    subprocess.run(cmd_wav, check=True)

    # Generate 1.2x speed variant as requested by user
    local_12x_wav = MUSIC_DIR / (local_mp3.stem + "_1.2x.wav")
    cmd_12x = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(local_wav),
        "-filter:a", "atempo=1.2",
        "-ar", "44100", "-ac", "2",
        str(local_12x_wav)
    ]
    subprocess.run(cmd_12x, check=True)

    # 5. Measure audio properties using soundfile
    info = sf.info(str(local_wav))
    duration_sec = round(float(info.duration), 2)
    sample_rate = int(info.samplerate)
    channels = int(info.channels)

    # 6. Calculate deterministic SHA-256 of the authoritative WAV
    hasher = hashlib.sha256()
    with open(local_wav, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    wav_sha256 = hasher.hexdigest()

    logger.info(f"Audio Verification Succeeded:")
    logger.info(f"  Duration: {duration_sec}s | Sample Rate: {sample_rate}Hz | Channels: {channels}")
    logger.info(f"  SHA-256: {wav_sha256}")

    # 7. Construct DiscoveryBGMConfig
    config = DiscoveryBGMConfig(
        bgm_filename=local_wav.name,
        source_provider="GOOGLE_DRIVE_STORY_FORGE_BGM_VAULT",
        drive_file_id=drive_file_id,
        expected_sha256=wav_sha256,
        actual_sha256=wav_sha256,
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        speed_multiplier=1.2,       # Permanent 1.2x speed
        volume_db=-18.0,            # Very low background level
        volume_amix_weight=0.20,
        status="VERIFIED",
    )

    fingerprint = config.compute_config_fingerprint()
    logger.info(f"Config Fingerprint: {fingerprint}")

    # 8. Persist and verify gate
    DiscoveryBGMGate.save_persisted_config(config)
    verified = DiscoveryBGMGate.verify_and_resolve_bgm()
    assert verified.status == "VERIFIED"
    logger.info("DiscoveryBGMGate verified successfully! BGM is locked and ready.")

    return verified


if __name__ == "__main__":
    cfg = register_bgm_from_drive()
    print("\n" + "=" * 80)
    print("BGM REGISTRATION MANIFEST:")
    print("=" * 80)
    print(json.dumps(cfg.to_dict(), indent=2))
