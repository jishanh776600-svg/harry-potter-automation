import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

token_path = Path("credentials/hp_token.json")
creds = Credentials.from_authorized_user_file(str(token_path))
drive = build("drive", "v3", credentials=creds)

print("=== INSPECTING MOVIE FOLDER (1pDm1lgoQzlLiABpL7buRUfv7NfWpFfy4) ===")
res_movies = drive.files().list(
    q="'1pDm1lgoQzlLiABpL7buRUfv7NfWpFfy4' in parents and trashed = false",
    fields="files(id, name, mimeType, size, videoMediaMetadata)"
).execute()
for f in res_movies.get("files", []):
    v_meta = f.get("videoMediaMetadata", {})
    dur_ms = v_meta.get("durationMillis")
    dur_min = round(int(dur_ms) / 60000, 1) if dur_ms else "N/A"
    size_gb = round(int(f.get("size", 0)) / (1024**3), 2)
    print(f"  - {f.get('name')}")
    print(f"    ID: {f.get('id')} | Size: {size_gb} GB | Duration: {dur_min} min | Width: {v_meta.get('width')}x{v_meta.get('height')}")

print("\n=== INSPECTING SRT FOLDER / FILES ===")
res_srt = drive.files().list(
    q="(name contains '.srt' or name contains 'srt' or name contains 'Subtitles' or name contains 'subtitles') and trashed = false",
    fields="files(id, name, mimeType, size, parents)"
).execute()
for f in res_srt.get("files", []):
    print(f"  - {f.get('name')} (ID: {f.get('id')}, Size: {f.get('size')} bytes, Parents: {f.get('parents')})")
