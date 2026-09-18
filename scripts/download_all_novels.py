import os
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

files = [
    (1, "harry_potter_1_.pdf", "1k7o-LeiKaAwI0MOUWYmPFwQiOms2eZPw"),
    (2, "Harry_potter_2_.pdf", "1UEfgC_HtW_IAqv_m0QA1XSXVmYWnzERr"),
    (3, "Harry_potter_3_.pdf", "1f79QJljQOFpDtNsdsekE2KyeN0QmgL5Y"),
    (4, "Harry_potter_4_.pdf", "1DT5Bs1j2OWvyfyYSP1Kk_9g0sqwxx2EQ"),
    (5, "Harry_potter_5_.pdf", "1KfGjRU7Waz_K4ZFE__eOJkPfA43zZZ5J"),
    (6, "Harry_potter_6_.pdf", "1z8eeqDgSls5oqJ1oeEFadjK58lbPFzS0"),
    (7, "Harry_potter_7_.pdf", "1akXrnNhmDTxQSHPk4cgytox-LUqYSUvA"),
]

for b_num, fname, fid in files:
    dest = BOOKS_DIR / fname
    if not dest.exists():
        print(f"Downloading Book {b_num}: {fname}...")
        request = drive.files().get_media(fileId=fid)
        with open(dest, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        print(f"  Downloaded: {dest.stat().st_size} bytes")
    else:
        print(f"Book {b_num} cached locally: {dest.stat().st_size} bytes")
    
    reader = pypdf.PdfReader(str(dest))
    print(f"  Pages: {len(reader.pages)}")
    # Find first chapter heading in first 10 pages
    for p_idx in range(min(10, len(reader.pages))):
        t = reader.pages[p_idx].extract_text() or ""
        if "CHAPTER" in t.upper():
            lines = [line.strip() for line in t.split("\n") if line.strip()]
            for l_idx, line in enumerate(lines[:10]):
                if "CHAPTER" in line.upper():
                    header_lines = lines[max(0, l_idx-1):min(len(lines), l_idx+3)]
                    print(f"  First chapter detected on page {p_idx+1}: {' / '.join(header_lines)}")
                    break
            break
print("\nAll 7 books downloaded and verified successfully!")
