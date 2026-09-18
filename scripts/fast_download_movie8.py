import os
import sys
import subprocess
from pathlib import Path
import requests
from google.oauth2.credentials import Credentials

MOVIES_DIR = Path("data/movies")
MOVIES_DIR.mkdir(parents=True, exist_ok=True)
SUBTITLES_DIR = Path("data/movie_subtitles")
SUBTITLES_DIR.mkdir(parents=True, exist_ok=True)

token_path = Path("credentials/hp_token.json")
creds = Credentials.from_authorized_user_file(str(token_path))
if not creds.valid and creds.refresh_token:
    from google.auth.transport.requests import Request
    creds.refresh(Request())

file_id = "1GHpEuPlHh8wFdXOKPYoWnyFx6d2dSOff"
dest_mkv = MOVIES_DIR / "Harry Potter and the Deathly Hallows Part 2 2011 Dual Audio Hindi 720p BluRay (1).mkv"
total_size = 1070982599

current_size = dest_mkv.stat().st_size if dest_mkv.exists() else 0
print(f"Initial file size: {current_size} / {total_size} bytes")

if current_size < total_size:
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {creds.token}"}
    mode = "wb"
    if current_size > 0:
        headers["Range"] = f"bytes={current_size}-"
        mode = "ab"
        print(f"Resuming download from byte {current_size}...")
    else:
        print("Starting new download...")

    resp = requests.get(url, headers=headers, stream=True, timeout=60)
    print(f"HTTP Status: {resp.status_code}")
    if resp.status_code in (200, 206):
        with open(dest_mkv, mode) as f:
            downloaded = current_size
            for chunk in resp.iter_content(chunk_size=4 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    pct = int(downloaded / total_size * 100)
                    sys.stdout.write(f"\rProgress: {downloaded}/{total_size} bytes ({pct}%)")
                    sys.stdout.flush()
        print("\nDownload complete!")
    else:
        print(f"Error downloading: HTTP {resp.status_code}: {resp.text}")

print(f"Final MKV size: {dest_mkv.stat().st_size} bytes")

# Extract English subtitle stream (0:s:0)
output_srt = SUBTITLES_DIR / "Harry Potter and the Deathly Hallows Part 2-en.srt"
print(f"Extracting English subtitle track 0:s:0 to {output_srt}...")

cmd = [
    "ffmpeg", "-y",
    "-i", str(dest_mkv),
    "-map", "0:s:0",
    "-c:s", "text",
    str(output_srt)
]

res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0 and output_srt.exists():
    print(f"SUCCESS: Extracted Movie 8 SRT ({output_srt.stat().st_size} bytes)")
    with open(output_srt, "r", encoding="utf-8", errors="replace") as f:
        sample = [f.readline().strip() for _ in range(12)]
    print("Sample lines:")
    for l in sample:
        print(" ", l)
else:
    print(f"Extraction failed: {res.stderr[-300:]}")
