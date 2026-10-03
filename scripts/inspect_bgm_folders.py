import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent.parent
creds_file = PROJECT_ROOT / "credentials" / "hp_token.json"

creds = Credentials.from_authorized_user_file(str(creds_file))
drive = build("drive", "v3", credentials=creds)

query = "mimeType = 'application/vnd.google-apps.folder' and (name = 'Bgm' or name = 'bgm' or name = 'BGM' or name contains 'bgm' or name contains 'Bgm') and trashed = false"
res = drive.files().list(q=query, fields="files(id, name, mimeType, parents, modifiedTime)").execute()
folders = res.get("files", [])

print(f"Total folders matched: {len(folders)}")
for f in folders:
    fid = f["id"]
    f_res = drive.files().list(q=f"'{fid}' in parents and trashed = false", fields="files(id, name, mimeType, size, modifiedTime)").execute()
    items = f_res.get("files", [])
    print(f"\nFolder: '{f['name']}' (ID: {fid}, items: {len(items)}, parents: {f.get('parents')})")
    for it in items:
        print(f"   -> {it['name']} (ID: {it['id']}, size: {it.get('size')} bytes, modified: {it.get('modifiedTime')})")
