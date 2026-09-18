import os
import sys
import time
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def parallel_download_drive_file(
    file_id: str,
    dest_path: Path,
    token_path: Path,
    num_workers: int = 8,
    chunk_size_mb: int = 16
):
    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    drive = build("drive", "v3", credentials=creds)
    meta = drive.files().get(fileId=file_id, fields="id, name, size").execute()
    total_size = int(meta["size"])
    chunk_bytes = chunk_size_mb * 1024 * 1024

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size == total_size:
        print(f"File already complete: {dest_path.name} ({total_size} bytes)")
        return dest_path

    print(f"Target file: {meta['name']} ({total_size / (1024**3):.2f} GB)")
    print(f"Starting parallel download with {num_workers} threads ({chunk_size_mb} MB chunks)...")

    # Pre-allocate sparse or zero-filled file
    with open(dest_path, "wb") as f:
        f.seek(total_size - 1)
        f.write(b"\0")

    # Generate chunk byte ranges: (start, end)
    ranges = []
    offset = 0
    while offset < total_size:
        end = min(offset + chunk_bytes - 1, total_size - 1)
        ranges.append((offset, end))
        offset = end + 1

    total_chunks = len(ranges)
    completed_chunks = 0
    completed_bytes = 0
    t0 = time.time()

    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    def download_range(start_byte, end_byte):
        nonlocal creds
        # Refresh token if within 5 mins of expiry
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {creds.token}",
            "Range": f"bytes={start_byte}-{end_byte}"
        })
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()

        with open(dest_path, "r+b") as out_f:
            out_f.seek(start_byte)
            out_f.write(data)

        return len(data)

    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        future_to_range = {pool.submit(download_range, r[0], r[1]): r for r in ranges}
        for future in as_completed(future_to_range):
            try:
                n_bytes = future.result()
                completed_chunks += 1
                completed_bytes += n_bytes
                elapsed = time.time() - t0
                speed_mb = (completed_bytes / (1024 * 1024)) / max(elapsed, 0.1)
                percent = (completed_bytes / total_size) * 100
                if completed_chunks % 5 == 0 or completed_chunks == total_chunks:
                    print(
                        f"[{percent:5.1f}%] {completed_bytes / (1024**2):.1f} / {total_size / (1024**2):.1f} MB "
                        f"({completed_chunks}/{total_chunks} chunks) @ {speed_mb:.1f} MB/s | Elapsed: {elapsed:.0f}s",
                        flush=True
                    )
            except Exception as e:
                r = future_to_range[future]
                print(f"Error downloading chunk {r}: {e}, retrying...", flush=True)
                # Retry once
                time.sleep(1)
                download_range(r[0], r[1])

    print(f"Download complete: {dest_path.name} in {time.time() - t0:.1f}s")
    return dest_path

if __name__ == "__main__":
    t_path = Path("credentials/hp_token.json")
    f_id = "1Ql83MMBIrk_nqYqfq06cmyCqmiRpYVgZ"
    d_path = Path("data/movies/Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv")
    parallel_download_drive_file(f_id, d_path, t_path, num_workers=8, chunk_size_mb=16)
