"""
Harry Potter Movie & Subtitle Canonical Registry (Step 6B)
================================================================================
Deterministic pairing of existing Harry Potter movie assets (Movies 1–8) and their
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
        "srt_source_type": "7z_archive",
        "srt_source_container": "Harry_potter_srt.7z",
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
        "srt_source_type": "7z_archive",
        "srt_source_container": "Harry_potter_srt.7z",
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
        "srt_source_type": "7z_archive",
        "srt_source_container": "Harry_potter_srt.7z",
    },
    {
        "movie_number": 4,
        "title": "Harry Potter and the Goblet of Fire",
        "alt_title": "Harry Potter and the Goblet of Fire",
        "year": 2005,
        "video_filename": "Harry Potter And The Goblet Of Fire 2005 BluRay 720p Dual Audio Hindi.mkv",
        "video_drive_id": "1EmxX84TQW6CpxIdXtgTTe9u7Cc7HkDoQ",
        "video_file_size_bytes": 1230299496,
        "video_duration_seconds": 9426.0,  # 157.1 min
        "width": 1280,
        "height": 534,
        "srt_filename": "Harry Potter and the Goblet of Fire 2005 720p BrRip x264 YIFY-English.srt",
        "srt_source_type": "zip_archive",
        "srt_source_container": "harry-potter-and-the-goblet-of-fire-2005-english-yify-106488.zip",
    },
    {
        "movie_number": 5,
        "title": "Harry Potter and the Order of the Phoenix",
        "alt_title": "Harry Potter and the Order of the Phoenix",
        "year": 2007,
        "video_filename": "Harry Potter And The Order Of The Phoenix 2007 Dual Audio Hindi 720p BluRay.mkv",
        "video_drive_id": "1pB-V9DdpiF6a1LwC23svVpg_D7esAKwA",
        "video_file_size_bytes": 1062728845,
        "video_duration_seconds": 7800.0,  # 130.0 min
        "width": 1280,
        "height": 528,
        "srt_filename": "Harry.Potter.and.the.Order.of.the.Phoenix.2007.1080p.BrRip.x264.YIFY-en.srt",
        "srt_source_type": "plain_srt",
        "srt_source_container": None,
    },
    {
        "movie_number": 6,
        "title": "Harry Potter and the Half-Blood Prince",
        "alt_title": "Harry Potter and the Half-Blood Prince",
        "year": 2009,
        "video_filename": "Harry Potter And The Half Blood Prince 2009 BluRay 720p Dual Audio Hindi.mkv",
        "video_drive_id": "12034RFo4SR-x1qIwNNw2S-EUEL4rL7jk",
        "video_file_size_bytes": 1337612655,
        "video_duration_seconds": 9210.0,  # 153.5 min
        "width": 1280,
        "height": 542,
        "srt_filename": "Harry Potter 6 and the Half-Blood Prince-en.srt",
        "srt_source_type": "plain_srt",
        "srt_source_container": None,
    },
    {
        "movie_number": 7,
        "title": "Harry Potter and the Deathly Hallows - Part 1",
        "alt_title": "Harry Potter and the Deathly Hallows Part 1",
        "year": 2010,
        "video_filename": "Harry Potter And The Deathly Hallows Part 1 2010 Dual Audio Hindi 720p BluRay.mkv",
        "video_drive_id": "1V8UTs2fnFZBI-ToDpQQfeKZhveRHRXE-",
        "video_file_size_bytes": 1092871009,
        "video_duration_seconds": 8286.0,  # 138.1 min
        "width": 1280,
        "height": 528,
        "srt_filename": "Harry.Potter.and.the.Deathly.Hallows-.Part.1.2010.1080p.720p.BluRay.x264.[YTS.MX]-English-en.srt",
        "srt_source_type": "plain_srt",
        "srt_source_container": None,
    },
    {
        "movie_number": 8,
        "title": "Harry Potter and the Deathly Hallows - Part 2",
        "alt_title": "Harry Potter and the Deathly Hallows Part 2",
        "year": 2011,
        "video_filename": "Harry Potter and the Deathly Hallows Part 2 2011 Dual Audio Hindi 720p BluRay (1).mkv",
        "video_drive_id": "1GHpEuPlHh8wFdXOKPYoWnyFx6d2dSOff",
        "video_file_size_bytes": 1070982599,
        "video_duration_seconds": 7818.0,  # 130.3 min
        "width": 1280,
        "height": 528,
        "srt_filename": "Harry Potter and the Deathly Hallows Part 2-en.srt",
        "srt_source_type": "embedded_mkv_stream",
        "srt_source_container": "Harry Potter and the Deathly Hallows Part 2 2011 Dual Audio Hindi 720p BluRay (1).mkv",
    },
]


def get_movie_by_number(movie_num: int):
    """Retrieves canonical movie pairing metadata by 1-based movie number."""
    for m in CANONICAL_MOVIES:
        if m["movie_number"] == movie_num:
            return m
    return None
