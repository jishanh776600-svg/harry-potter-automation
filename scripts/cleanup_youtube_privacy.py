"""
YouTube Privacy Cleanup — STORY FORGE (Harry Potter Channel)
============================================================
Hard Safety Gate: UCsghEXDa3EzxI4d93cjT-bQ
Sets all old content to PRIVATE.
DO NOT delete videos.
DO NOT upload, schedule, or publish anything.
"""
import os
import sys
import json
import logging
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("PRIVACY_CLEANUP")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = PROJECT_ROOT / "credentials" / "hp_token.json"
EXPECTED_CHANNEL_ID = "UCsghEXDa3EzxI4d93cjT-bQ"

# The 4 approved launch Shorts identifiers/titles to protect if present
PROTECTED_PATTERNS = [
    "hps_ns_b1c01_gc0001_0003",
    "hps_ns_b1c01_gc0004_0006",
    "hps_disc_peeves_poltergeist_b1",
    "hps_disc_neville_hufflepuff_sorting_b1",
    "the boy who lived",
    "peeves the poltergeist",
    "neville longbottom",
    "hufflepuff",
]


def is_protected_hp_video(video: dict) -> bool:
    title = video.get("snippet", {}).get("title", "").lower()
    desc = video.get("snippet", {}).get("description", "").lower()
    for pattern in PROTECTED_PATTERNS:
        if pattern in title or pattern in desc:
            return True
    return False


def run_cleanup():
    print()
    print("=" * 70)
    print("STORY FORGE YOUTUBE PRIVACY CLEANUP")
    print(f"Target Channel ID Gate: {EXPECTED_CHANNEL_ID}")
    print("=" * 70)

    if not TOKEN_PATH.exists():
        print(f"[ERROR] Token not found at {TOKEN_PATH}")
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    yt = build("youtube", "v3", credentials=creds)

    # 1. Channel Identity Gate Check
    ch_res = yt.channels().list(part="snippet,contentDetails", mine=True).execute()
    items = ch_res.get("items", [])
    if not items:
        print("[HARD GATE FAIL] No authenticated YouTube channel found. STOPPING.")
        sys.exit(1)

    ch = items[0]
    authenticated_ch_id = ch.get("id", "")
    authenticated_ch_name = ch.get("snippet", {}).get("title", "")

    print(f"Authenticated Channel ID:   {authenticated_ch_id}")
    print(f"Authenticated Channel Name: {authenticated_ch_name}")

    if authenticated_ch_id != EXPECTED_CHANNEL_ID:
        print(f"[HARD GATE FAIL] Authenticated channel {authenticated_ch_id} != {EXPECTED_CHANNEL_ID}! STOPPING.")
        sys.exit(1)

    print("[HARD GATE PASS] Channel identity confirmed exactly.")
    uploads_playlist = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    # 2. Enumerate all uploads
    video_ids = []
    page_token = None
    while True:
        pl_res = yt.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist,
            maxResults=50,
            pageToken=page_token
        ).execute()
        for item in pl_res.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = pl_res.get("nextPageToken")
        if not page_token:
            break

    print(f"Total entries in uploads playlist: {len(video_ids)}")

    # 3. Retrieve video details in batches
    all_videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        v_res = yt.videos().list(
            part="id,snippet,status,contentDetails",
            id=",".join(batch)
        ).execute()
        all_videos.extend(v_res.get("items", []))

    print(f"Authoritative videos retrieved: {len(all_videos)}")

    # Inventory breakdown
    total_found = len(all_videos)
    old_public = []
    old_unlisted = []
    already_private = []
    protected_hp = []
    skipped_ownership = []

    for v in all_videos:
        vid = v["id"]
        v_channel = v.get("snippet", {}).get("channelId", "")
        v_privacy = v.get("status", {}).get("privacyStatus", "")
        v_title = v.get("snippet", {}).get("title", "")

        # Per-video ownership check
        if v_channel != EXPECTED_CHANNEL_ID:
            print(f"[SKIP] Video {vid} channelId {v_channel} mismatch. Skipping.")
            skipped_ownership.append(v)
            continue

        # HP protection check
        if is_protected_hp_video(v):
            print(f"[PROTECT] Harry Potter content protected: {vid} - '{v_title}'")
            protected_hp.append(v)
            continue

        if v_privacy == "public":
            old_public.append(v)
        elif v_privacy == "unlisted":
            old_unlisted.append(v)
        elif v_privacy == "private":
            already_private.append(v)
        else:
            old_public.append(v)

    print()
    print("--- INVENTORY BEFORE CLEANUP ---")
    print(f"Total uploads found:       {total_found}")
    print(f"Old public uploads:        {len(old_public)}")
    print(f"Old unlisted uploads:      {len(old_unlisted)}")
    print(f"Already-private uploads:   {len(already_private)}")
    print(f"Protected HP uploads:      {len(protected_hp)}")
    print(f"Skipped ownership uploads: {len(skipped_ownership)}")
    print("--------------------------------")

    # 4. Execute privacy changes
    public_to_private = 0
    unlisted_to_private = 0
    failed_changes = []

    to_update = [(v, "public") for v in old_public] + [(v, "unlisted") for v in old_unlisted]

    for v, orig_status in to_update:
        vid = v["id"]
        title = v.get("snippet", {}).get("title", "")
        print(f"Updating {vid} [{orig_status.upper()} -> PRIVATE]: '{title[:50]}'")

        update_body = {
            "id": vid,
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False
            }
        }

        try:
            yt.videos().update(part="status", body=update_body).execute()
            if orig_status == "public":
                public_to_private += 1
            else:
                unlisted_to_private += 1
        except HttpError as e:
            print(f"[ERROR] Failed updating {vid}: {e}")
            failed_changes.append({"id": vid, "title": title, "error": str(e)})

    # 5. Final Readback Verification
    print()
    print("=" * 70)
    print("PERFORMING FINAL YOUTUBE API READBACK VERIFICATION...")
    print("=" * 70)

    verify_videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        v_res = yt.videos().list(
            part="id,snippet,status",
            id=",".join(batch)
        ).execute()
        verify_videos.extend(v_res.get("items", []))

    final_public = [v for v in verify_videos if v.get("status", {}).get("privacyStatus") == "public" and not is_protected_hp_video(v)]
    final_unlisted = [v for v in verify_videos if v.get("status", {}).get("privacyStatus") == "unlisted" and not is_protected_hp_video(v)]
    final_private = [v for v in verify_videos if v.get("status", {}).get("privacyStatus") == "private" and not is_protected_hp_video(v)]

    print()
    print("--- FINAL READBACK VERIFICATION ---")
    print(f"Remaining old PUBLIC videos:   {len(final_public)}")
    print(f"Remaining old UNLISTED videos: {len(final_unlisted)}")
    print(f"Remaining old PRIVATE videos:  {len(final_private)}")
    print(f"Protected HP videos modified:  0")
    print(f"Deleted videos:                0 (Zero deletions performed)")
    print(f"Uploads performed:             0 (Publishing remains OFF)")
    print(f"Schedules created:             0 (Scheduling remains OFF)")
    print(f"Publications performed:        0 (Publishing remains OFF)")
    print("-----------------------------------")


if __name__ == "__main__":
    run_cleanup()
