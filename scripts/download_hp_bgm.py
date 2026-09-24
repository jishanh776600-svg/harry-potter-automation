import io
import sys
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parent.parent
music_dir = PROJECT_ROOT / "assets" / "music"
music_dir.mkdir(parents=True, exist_ok=True)

token_candidates = [
    PROJECT_ROOT / "credentials" / "hp_token.json",
    PROJECT_ROOT / "token.json",
    Path("credentials/hp_token.json"),
    Path("token.json")
]
creds_file = next((p for p in token_candidates if p.exists()), None)
if not creds_file:
    raise FileNotFoundError("Could not find hp_token.json or token.json in project credentials.")

creds = Credentials.from_authorized_user_file(str(creds_file))
drive = build("drive", "v3", credentials=creds)

file_id = "1KExAdFU1tI7Ht_j0AxTqzIqgV3HtHkIe"
filename = "Barty Crouch Junior! - Harry Potter and the Goblet of Fire Complete Score (Film Mix).mp3"
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

# Generate 1.2x speed WAV
dest_12x_wav = music_dir / (dest_mp3.stem + "_1.2x.wav")
cmd_12x = [
    "ffmpeg", "-y", "-loglevel", "error",
    "-i", str(dest_wav),
    "-filter:a", "atempo=1.2",
    "-ar", "44100", "-ac", "2",
    str(dest_12x_wav)
]
subprocess.run(cmd_12x, check=True)
print(f"Generated 1.2x WAV: {dest_12x_wav} ({dest_12x_wav.stat().st_size} bytes)")
