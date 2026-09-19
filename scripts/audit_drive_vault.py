import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engines.drive_engine import DriveVaultEngine

def audit_drive():
    eng = DriveVaultEngine(offline_mode=False)
    drv = eng.get_drive_service()
    
    about = drv.about().get(fields="user, storageQuota").execute()
    user_email = about.get("user", {}).get("emailAddress")
    quota = about.get("storageQuota", {})
    print(f"[+] Authenticated Google Account: {user_email}")
    print(f"    Drive Quota Usage: {int(quota.get('usage', 0)) / (1024**3):.2f} GB / {int(quota.get('limit', 0)) / (1024**3):.2f} GB")

    # Locate real HP root folder
    root_folder = eng.find_folder("Yt_harry_potter_automation")
    if not root_folder:
        root_folder = eng.find_folder("Harry_Potter_Shorts_Vault")
    
    assert root_folder, "HP Root Vault not found in Drive!"
    root_id = root_folder["id"]
    root_name = root_folder["name"]
    print(f"[+] Root Vault Found: '{root_name}' (ID: {root_id})")

    # List existing subfolders
    q = f"'{root_id}' in parents and trashed = false and mimeType = 'application/vnd.google-apps.folder'"
    res = drv.files().list(q=q, fields="files(id, name)").execute()
    existing_folders = {f["name"]: f["id"] for f in res.get("files", [])}

    print("\nExisting Vault Subfolders:")
    for name, fid in existing_folders.items():
        print(f"  - {name} ({fid})")

    # Ensure required lifecycle folders exist
    lifecycle_folders = ["00_SYSTEM", "01_READY", "02_PROCESSING", "03_PUBLISHED", "04_FAILED"]
    for lf in lifecycle_folders:
        if lf not in existing_folders:
            created = eng.create_folder(lf, parent_id=root_id)
            print(f"  [+] Created missing lifecycle folder: {lf} (ID: {created['id']})")
        else:
            print(f"  [OK] Lifecycle folder present: {lf} ({existing_folders[lf]})")

if __name__ == "__main__":
    audit_drive()
