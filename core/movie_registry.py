"""
Harry Potter Movie & Subtitle Canonical Registry (Step 6A)
================================================================================
Deterministic pairing of existing Harry Potter movie assets and their
corresponding English SRT subtitle files.

Source Location: Google Drive Vault `Yt_harry_potter_automation` (jishanh760@gmail.com)
  - Movies folder: `Harry Potter movies ` (ID: 1pDm1lgoQzlLiABpL7buRUfv7NfWpFfy4)
  - Subtitles folder: `Subtitle srt` (ID: 1WUzEVy1kmUtQpdsIgvANkBlMxLufRERV)
  - Local Subtitles: `data/movie_subtitles/`
"""

CANONICAL_MOVIES = [
    {
        "movie_number": 1,
        "title": "Harry Potter and the Sorcerer's Stone",
        "alt_title": "Harry Potter and the Philosopher's Stone",
        "year": 2001,
        "video_filename": "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv",
        "video_drive_id": "1Ql83MMBIrk_nqYqfq06cmyCqmiRpYVgZ",
        "video_file_size_bytes": 3085723808,
        "video_duration_seconds": 9144.0,  # 152.4 min
        "width": 1920,
        "height": 800,
        "srt_filename": "harry-potter-and-the-sorcerers-stone-yify-english-en.srt",
        "srt_archive_name": "Harry_potter_srt.7z",
        "srt_archive_drive_id": "1uQ5T-BO-sW_ARYcqLL6QljeZidslwDGq",
    },
    {
        "movie_number": 2,
        "title": "Harry Potter and the Chamber of Secrets",
        "alt_title": "Harry Potter and the Chamber of Secrets",
        "year": 2002,
        "video_filename": "Harry Potter and the Chamber of Secrets (2002) Dual Audio {Hindi-English} 1080p.mkv",
        "video_drive_id": "1dBbUg32r5OZ7uSSuJv6UdelE3z7-mfwX",
        "video_file_size_bytes": 3374339035,
        "video_duration_seconds": 9660.0,  # 161.0 min
        "width": 1920,
        "height": 800,
        "srt_filename": "harry-potter-and-the-chamber-of-secrets-yify-english-en.srt",
        "srt_archive_name": "Harry_potter_srt.7z",
        "srt_archive_drive_id": "1uQ5T-BO-sW_ARYcqLL6QljeZidslwDGq",
    },
    {
        "movie_number": 3,
        "title": "Harry Potter and the Prisoner of Azkaban",
        "alt_title": "Harry Potter and the Prisoner of Azkaban",
        "year": 2004,
        "video_filename": "3. Harry Potter and the Prisoner of Azkaban 2004 BluRay x265 [Org DD Hindi + DD 5.1 Eng] ESubs 1080p.mkv",
        "video_drive_id": "16boYmZt0sfBvN3e9lSSuTz8Wd8Nia80_",
        "video_file_size_bytes": 3126061054,
        "video_duration_seconds": 8502.0,  # 141.7 min
        "width": 1920,
        "height": 800,
        "srt_filename": "Harry Potter and the Prisoner of Azkaban-en.srt",
        "srt_archive_name": "Harry_potter_srt.7z",
        "srt_archive_drive_id": "1uQ5T-BO-sW_ARYcqLL6QljeZidslwDGq",
    }
]


def get_movie_by_number(movie_num: int):
    """Retrieves canonical movie pairing metadata by 1-based movie number."""
    for m in CANONICAL_MOVIES:
        if m["movie_number"] == movie_num:
            return m
    return None
