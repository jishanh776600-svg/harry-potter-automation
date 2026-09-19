"""
Inspect Google Drive 01_READY folder.
"""
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file("credentials/hp_token.json")
drive = build("drive", "v3", credentials=creds)

VAULT_ID = "11K6v7PjLsnb8fVCsAm00YGmamvv4ygzC"

res = drive.files().list(
    q=f"'{VAULT_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
    fields="files(id, name)"
).execute()
folders = res.get("files", [])
print("Vault folders:", {f["name"]: f["id"] for f in folders})

ready_folder = next((f for f in folders if "01_READY" in f["name"]), None)
if ready_folder:
    ready_id = ready_folder["id"]
    files_res = drive.files().list(
        q=f"'{ready_id}' in parents and trashed=false",
        fields="files(id, name, size, createdTime)"
    ).execute()
    files = files_res.get("files", [])
    print(f"\nTotal files in 01_READY ({ready_id}): {len(files)}")
    for f in files:
        sz_mb = int(f.get("size", 0)) / (1024 * 1024)
        print(f"  {f['name']} ({sz_mb:.2f} MB) - ID: {f['id']}")
