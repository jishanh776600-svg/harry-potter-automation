import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parent.parent
creds_file = PROJECT_ROOT / "credentials" / "hp_token.json"

if not creds_file.exists():
    raise FileNotFoundError(f"Missing {creds_file}")

creds = Credentials.from_authorized_user_file(str(creds_file))
drive = build("drive", "v3", credentials=creds)

folder_id = "1kf4KrH2Nqebtx3Suz5izLb3PtRNyu7b6"
res = drive.files().list(
    q=f"'{folder_id}' in parents",
    fields="files(id, name, mimeType, size, createdTime, modifiedTime, md5Checksum, trashed, webContentLink)"
).execute()

items = res.get("files", [])
print(f"Total files in folder {folder_id}: {len(items)}")
for item in items:
    print(json.dumps(item, indent=2))
