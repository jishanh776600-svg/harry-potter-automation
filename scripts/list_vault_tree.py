from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials.from_authorized_user_file("credentials/hp_token.json")
drive = build("drive", "v3", credentials=creds)

root_id = "11K6v7PjLsnb8fVCsAm00YGmamvv4ygzC"

def list_folder(folder_id, indent=0):
    query = f"'{folder_id}' in parents and trashed = false"
    res = drive.files().list(q=query, fields="files(id, name, mimeType, size)").execute()
    for f in res.get("files", []):
        size = f.get("size", "folder")
        name = f.get("name", "").encode("ascii", "replace").decode("ascii")
        print("  " * indent + f"- {name} (size: {size}, id: {f['id']})")
        if f["mimeType"] == "application/vnd.google-apps.folder":
            list_folder(f["id"], indent + 1)

print("Listing all contents of Yt_harry_potter_automation vault:")
list_folder(root_id)
