import os
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

token_path = Path("credentials/hp_token.json")
creds = Credentials.from_authorized_user_file(str(token_path))
drive = build("drive", "v3", credentials=creds)

print("=== INSPECTING FOLDER 'Subtitle srt' (1WUzEVy1kmUtQpdsIgvANkBlMxLufRERV) ===")
res = drive.files().list(
    q="'1WUzEVy1kmUtQpdsIgvANkBlMxLufRERV' in parents and trashed = false",
    fields="files(id, name, mimeType, size)"
).execute()
files = res.get("files", [])
for f in files:
    print(f"  - {f.get('name')} (ID: {f.get('id')}, Size: {f.get('size')} bytes)")

# Download Harry_potter_srt.7z
srt_archive_id = "1uQ5T-BO-sW_ARYcqLL6QljeZidslwDGq"
dest_archive = Path("data/movie_subtitles/Harry_potter_srt.7z")
dest_archive.parent.mkdir(parents=True, exist_ok=True)

if not dest_archive.exists():
    print(f"\nDownloading Harry_potter_srt.7z...")
    request = drive.files().get_media(fileId=srt_archive_id)
    with open(dest_archive, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
    print(f"Downloaded to {dest_archive} ({dest_archive.stat().st_size} bytes)")
else:
    print(f"\nArchive already exists locally: {dest_archive} ({dest_archive.stat().st_size} bytes)")
