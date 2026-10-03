import hashlib
import io
import json
import logging
from pathlib import Path
import subprocess
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

PROJECT_ROOT = Path(__file__).resolve().parent.parent
music_dir = PROJECT_ROOT / "assets" / "music"
music_dir.mkdir(parents=True, exist_ok=True)

creds_file = PROJECT_ROOT / "credentials" / "hp_token.json"
if not creds_file.exists():
    raise FileNotFoundError(f"Missing {creds_file}")

creds = Credentials.from_authorized_user_file(str(creds_file))
drive = build("drive", "v3", credentials=creds)

drive_file_id = "1Tv5mQ0hHQlgmmNhuzhQaGouUWgIkvVkA"
filename = "Exactly Who.mp3"
dest_mp3 = music_dir / filename

print(f"[DOWNLOAD] Downloading {filename} (id: {drive_file_id}) from Drive...")
request = drive.files().get_media(fileId=drive_file_id)
with open(dest_mp3, "wb") as f:
    downloader = MediaIoBaseDownload(f, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            print(f"Download progress: {int(status.progress() * 100)}%")

print(f"[DOWNLOAD] Downloaded MP3 to {dest_mp3} ({dest_mp3.stat().st_size} bytes)")

# Compute SHA-256 of MP3
hasher_mp3 = hashlib.sha256()
with open(dest_mp3, "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        hasher_mp3.update(chunk)
mp3_sha256 = hasher_mp3.hexdigest()
print(f"[SHA256] MP3 SHA-256: {mp3_sha256}")

# Convert to 44.1kHz 16-bit stereo WAV
dest_wav = music_dir / "Exactly Who.wav"
cmd = [
    "ffmpeg", "-y", "-loglevel", "error",
    "-i", str(dest_mp3),
    "-ar", "44100", "-ac", "2",
    str(dest_wav)
]
subprocess.run(cmd, check=True)
print(f"[CONVERT] Converted to WAV: {dest_wav} ({dest_wav.stat().st_size} bytes)")

hasher_wav = hashlib.sha256()
with open(dest_wav, "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        hasher_wav.update(chunk)
wav_sha256 = hasher_wav.hexdigest()
print(f"[SHA256] WAV SHA-256: {wav_sha256}")

# Probe audio metadata via ffprobe
cmd_probe = [
    "ffprobe", "-v", "error",
    "-show_entries", "stream=duration,sample_rate,channels,codec_name",
    "-show_entries", "format=duration,size,bit_rate",
    "-of", "json",
    str(dest_wav)
]
res = subprocess.run(cmd_probe, capture_output=True, text=True, check=True)
metadata = json.loads(res.stdout)
print("[METADATA] Audio properties:")
print(json.dumps(metadata, indent=2))
