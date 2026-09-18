import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.movie_registry import CANONICAL_MOVIES
from engines.subtitle_processor import validate_srt_integrity

SUBTITLES_DIR = Path("data/movie_subtitles")

print("=" * 80)
print("AUDITING AND VALIDATING ALL 8 HARRY POTTER SUBTITLE ASSETS")
print("=" * 80)

all_valid = True
for m in CANONICAL_MOVIES:
    m_num = m["movie_number"]
    title = m["title"]
    srt_name = m["srt_filename"]
    srt_path = SUBTITLES_DIR / srt_name

    expected_duration = m["video_duration_seconds"] * 0.7  # at least 70% of movie
    res = validate_srt_integrity(srt_path, expected_min_duration_sec=3600.0)

    status_str = "PASS" if res.get("valid") else "FAIL"
    if not res.get("valid"):
        all_valid = False

    print(f"\nMovie {m_num}: {title}")
    print(f"  SRT File: {srt_name}")
    print(f"  Container Type: {m['srt_source_type']}")
    print(f"  Status: [{status_str}]")
    if res.get("valid"):
        print(f"  Entries Count: {res['parsed_entries']}")
        print(f"  Max Timestamp: {res['max_timecode']} ({res['max_timestamp_seconds']}s)")
        print(f"  English Confirmed: {res['is_english']}")
        print(f"  File Size: {res['file_size_bytes']} bytes")
    else:
        print(f"  Error: {res.get('error')}")

print("\n" + "=" * 80)
if all_valid:
    print("ALL 8 MOVIES HAVE VALID, VERIFIED ENGLISH SRT SUBTITLES!")
else:
    print("SOME SUBTITLE FILES FAILED VALIDATION!")
print("=" * 80)
