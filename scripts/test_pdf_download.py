import os
import io
import hashlib
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pypdf

BOOKS_DIR = Path("data/books")
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

token_path = Path("credentials/hp_token.json")
creds = Credentials.from_authorized_user_file(str(token_path))
drive = build("drive", "v3", credentials=creds)

# File ID for harry_potter_1_.pdf is 1k7o-LeiKaAwI0MOUWYmPFwQiOms2eZPw
file_id = "1k7o-LeiKaAwI0MOUWYmPFwQiOms2eZPw"
filename = "harry_potter_1_.pdf"
dest_path = BOOKS_DIR / filename

if not dest_path.exists():
    print(f"Downloading {filename} from Google Drive...")
    request = drive.files().get_media(fileId=file_id)
    with open(dest_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"  Download progress: {int(status.progress() * 100)}%")
    print(f"Downloaded {filename} ({dest_path.stat().st_size} bytes)")
else:
    print(f"{filename} already exists locally ({dest_path.stat().st_size} bytes)")

# Quick inspection with pypdf
reader = pypdf.PdfReader(str(dest_path))
print(f"Total pages in {filename}: {len(reader.pages)}")

# Print sample text from first 5 pages
for i in range(min(5, len(reader.pages))):
    text = reader.pages[i].extract_text() or ""
    print(f"\n--- PAGE {i+1} ({len(text)} chars) ---")
    print(text[:300].strip())
