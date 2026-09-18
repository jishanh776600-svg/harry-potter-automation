import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

token_path = Path("credentials/hp_token.json")
creds = Credentials.from_authorized_user_file(str(token_path))
drive = build("drive", "v3", credentials=creds)

print("=== 1. SEARCHING FOR VAULT FOLDER ===")
res_folder = drive.files().list(
    q="trashed = false and mimeType = 'application/vnd.google-apps.folder' and (name contains 'Harry' or name contains 'Vault' or name contains 'vault')",
    fields="files(id, name, parents)"
).execute()
folders = res_folder.get("files", [])
print(f"Found {len(folders)} matching folders:")
for f in folders:
    print(f"  Folder: {f.get('name')} (ID: {f.get('id')})")

print("\n=== 2. SEARCHING FOR ALL PDF FILES ===")
res_pdf = drive.files().list(
    q="trashed = false and (mimeType = 'application/pdf' or name contains '.pdf' or name contains 'harry' or name contains 'Harry' or name contains 'potter' or name contains 'Potter')",
    pageSize=50,
    fields="files(id, name, mimeType, size, parents)"
).execute()
pdfs = res_pdf.get("files", [])
print(f"Found {len(pdfs)} matching PDF/Harry Potter files:")
for f in pdfs:
    print(f"  File: {f.get('name')} (ID: {f.get('id')}, Size: {f.get('size')} bytes, Parents: {f.get('parents')})")
