import io
import sys
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parent.parent
creds_file = PROJECT_ROOT / "credentials" / "hp_token.json"
music_dir = PROJECT_ROOT / "assets" / "music"
music_dir.mkdir(parents=True, exist_ok=True)

creds = Credentials.from_authorized_user_file(str(creds_file))
drive = build("drive", "v3", credentials=creds)

file_id = "1Ec4XKRvjYgIOZuYJ2GdFZMimIq5yZUnE"
filename = "HARRY POTTER _ ULTIMATE BGM _ NO COPYRIGHT [kVmIrNDYPIk].mp3"
dest_mp3 = music_dir / filename

print(f"Downloading {filename} (id: {file_id}) from Harry Potter Google Drive...")
request = drive.files().get_media(fileId=file_id)
with open(dest_mp3, "wb") as f:
    downloader = MediaIoBaseDownload(f, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            print(f"Download progress: {int(status.progress() * 100)}%")

print(f"Downloaded MP3: {dest_mp3} ({dest_mp3.stat().st_size} bytes)")

# Convert to 44.1kHz 16-bit stereo WAV for pristine mixing
dest_wav = music_dir / (dest_mp3.stem + ".wav")
cmd = [
    "ffmpeg", "-y", "-loglevel", "error",
    "-i", str(dest_mp3),
    "-ar", "44100", "-ac", "2",
    str(dest_wav)
]
subprocess.run(cmd, check=True)
print(f"Converted WAV: {dest_wav} ({dest_wav.stat().st_size} bytes)")
