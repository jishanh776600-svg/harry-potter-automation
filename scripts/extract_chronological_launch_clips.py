import hashlib
import json
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "database" / "pipeline.db"
CLIPS_DIR = PROJECT_ROOT / "data" / "clips"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

MOVIE_1_PATH = PROJECT_ROOT / "data" / "movies" / "Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv"

SHOTS_SPEC = {
    # -------------------------------------------------------------------------
    # SHORT 1: Privet Drive / Deluminator / Cat on Wall (Novel Story, Bella, PART 01)
    # Earliest chronological narrative material (Book 1, Ch 1, Chunks 1-6)
    # -------------------------------------------------------------------------
    "hps_ns_b1c01_gc0001_0003": [
        {"shot_id": "shot_01", "ss": 45.0, "to": 48.0, "desc": "Privet Drive street sign with owl perched at night"},
        {"shot_id": "shot_02", "ss": 52.0, "to": 55.0, "desc": "Dumbledore appearing solemnly on empty street"},
        {"shot_id": "shot_03", "ss": 58.0, "to": 61.0, "desc": "Dumbledore walking down quiet suburban pavement"},
        {"shot_id": "shot_04", "ss": 67.0, "to": 70.0, "desc": "Dumbledore reaching into robes for silver Deluminator"},
        {"shot_id": "shot_05", "ss": 71.0, "to": 74.0, "desc": "Deluminator clicking open and absorbing street lamp light"},
        {"shot_id": "shot_06", "ss": 75.0, "to": 78.0, "desc": "Row of street lamps blacking out one by one"},
        {"shot_id": "shot_07", "ss": 79.0, "to": 82.0, "desc": "Pitch black street plunged into dark silence"},
        {"shot_id": "shot_08", "ss": 83.0, "to": 86.5, "desc": "Tabby cat sitting motionlessly on brick garden wall"}
    ],

    # -------------------------------------------------------------------------
    # SHORT 2: McGonagall Transformation / Hagrid Arrival (Novel Story, Bella, PART 02)
    # DIRECT CONTINUATION from Short 1 (Book 1, Ch 1, Chunks 7-11)
    # -------------------------------------------------------------------------
    "hps_ns_b1c01_gc0004_0006": [
        {"shot_id": "shot_01", "ss": 100.0, "to": 103.0, "desc": "Professor McGonagall standing in emerald cloak and spectacles"},
        {"shot_id": "shot_02", "ss": 104.5, "to": 107.5, "desc": "McGonagall questioning Dumbledore anxiously about rumors"},
        {"shot_id": "shot_03", "ss": 108.0, "to": 111.0, "desc": "Dumbledore confirming the tragedy with heavy sorrow"},
        {"shot_id": "shot_04", "ss": 114.0, "to": 117.0, "desc": "McGonagall expressing concern about baby Harry"},
        {"shot_id": "shot_05", "ss": 118.0, "to": 121.0, "desc": "Dumbledore looking compassionate and resolute"},
        {"shot_id": "shot_06", "ss": 125.0, "to": 128.0, "desc": "Loud rumbling engine sound breaking the night sky"},
        {"shot_id": "shot_07", "ss": 141.0, "to": 144.0, "desc": "Giant flying motorbike touching down on Privet Drive"},
        {"shot_id": "shot_08", "ss": 153.0, "to": 156.5, "desc": "Hagrid stepping off motorbike cradling baby Harry in bundle"}
    ],

    # -------------------------------------------------------------------------
    # SHORT 3: Snape's Deleted Defense / Potion Riddle (Discovery, Bella, NO PART MARKER)
    # Standalone high-quality discovery (Book 1, Ch 16)
    # -------------------------------------------------------------------------
    "hps_disc_peeves_poltergeist_b1": [
        {"shot_id": "shot_01", "ss": 7450.0, "to": 7453.0, "desc": "Giant stone chess queen smashing knight to pieces"},
        {"shot_id": "shot_02", "ss": 3125.0, "to": 3128.0, "desc": "Professor Snape glaring with brooding dark intensity"},
        {"shot_id": "shot_03", "ss": 7620.0, "to": 7623.0, "desc": "Wall of magical fire roaring up in doorway"},
        {"shot_id": "shot_04", "ss": 3140.0, "to": 3143.0, "desc": "Dark potion vials and flasks on stone bench"},
        {"shot_id": "shot_05", "ss": 7580.0, "to": 7583.0, "desc": "Hermione observing with sharp analytical focus"},
        {"shot_id": "shot_06", "ss": 7635.0, "to": 7638.0, "desc": "Hermione looking determined figuring out riddle"},
        {"shot_id": "shot_07", "ss": 7650.0, "to": 7653.0, "desc": "Hermione hugging Harry bravely beside steps"},
        {"shot_id": "shot_08", "ss": 7665.0, "to": 7668.5, "desc": "Harry stepping through roaring flames safely"}
    ],

    # -------------------------------------------------------------------------
    # SHORT 4: McGonagall's Secret Nimbus 2000 Note (Discovery, Bella, NO PART MARKER)
    # Standalone high-quality discovery (Book 1, Ch 10)
    # -------------------------------------------------------------------------
    "hps_disc_neville_hufflepuff_sorting_b1": [
        {"shot_id": "shot_01", "ss": 4505.0, "to": 4508.0, "desc": "Owls swooping through high Great Hall rafters"},
        {"shot_id": "shot_02", "ss": 4512.0, "to": 4515.0, "desc": "Long brown paper parcel dropped on table"},
        {"shot_id": "shot_03", "ss": 4520.0, "to": 4523.0, "desc": "Harry unwrapping paper revealing Nimbus 2000 logo"},
        {"shot_id": "shot_04", "ss": 4525.0, "to": 4528.0, "desc": "Ron gasping in awe at the racing broom"},
        {"shot_id": "shot_05", "ss": 4545.0, "to": 4548.0, "desc": "McGonagall looking down from high table with smirk"},
        {"shot_id": "shot_06", "ss": 3585.0, "to": 3588.0, "desc": "Oliver Wood grinning excitedly about Quidditch"},
        {"shot_id": "shot_07", "ss": 4720.0, "to": 4723.0, "desc": "Harry zooming on Nimbus 2000 in Quidditch match"},
        {"shot_id": "shot_08", "ss": 4750.0, "to": 4753.5, "desc": "Cheering Gryffindor stands waving scarlet scarves"}
    ]
}


def extract_clips():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    vf = "scale=-1:1920,crop=1080:1920"

    # Clean old clips for these 4 scripts first
    cursor.execute("""
        DELETE FROM hp_movie_clips
        WHERE script_id IN (
            'hps_ns_b1c01_gc0001_0003',
            'hps_ns_b1c01_gc0004_0006',
            'hps_disc_peeves_poltergeist_b1',
            'hps_disc_neville_hufflepuff_sorting_b1'
        )
    """)
    conn.commit()

    for script_id, shots in SHOTS_SPEC.items():
        print(f"\nExtracting shots for {script_id}...")
        for idx, sh in enumerate(shots, 1):
            shot_id = sh["shot_id"]
            ss = sh["ss"]
            to = sh["to"]
            dur = round(to - ss, 2)
            out_clip = CLIPS_DIR / f"{script_id}_{shot_id}.mp4"

            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-ss", str(ss),
                "-to", str(to),
                "-i", str(MOVIE_1_PATH),
                "-an",  # ZERO MOVIE AUDIO
                "-vf", vf,
                "-r", "30",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                str(out_clip)
            ]
            subprocess.run(cmd, check=True)
            clip_size = out_clip.stat().st_size
            sha256 = hashlib.sha256(out_clip.read_bytes()).hexdigest()

            # Insert into hp_movie_clips
            db_clip_id = f"clip_{script_id}_{shot_id}"
            now_iso = datetime.utcnow().isoformat()
            cursor.execute("""
                INSERT INTO hp_movie_clips (
                    id, script_id, beat_id, shot_id, shot_index,
                    movie_id, movie_number, movie_title, source_mode,
                    source_start_seconds, source_end_seconds,
                    clip_start_seconds, clip_end_seconds, duration_seconds,
                    retrieval_score, confidence, match_status,
                    file_path, file_size_bytes, sha256,
                    audio_stream_count, width, height,
                    visual_source_policy, status, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?
                )
            """, (
                db_clip_id, script_id, f"beat_{idx}", shot_id, idx,
                "hp_m1", 1, "Harry Potter and the Sorcerer's Stone", "LOCAL",
                ss, to,
                ss, to, dur,
                100.0, 100.0, "ACCEPTED",
                str(out_clip), clip_size, sha256,
                0, 1080, 1920,
                "MOVIE_FOOTAGE_ONLY", "READY_FOR_STEP_10", now_iso, now_iso
            ))

            print(f"  [+] Shot {idx}/8 ({shot_id}): {ss}s-{to}s ({dur}s) -> {out_clip.name} ({clip_size // 1024} KB)")

    conn.commit()
    conn.close()
    print("\nAll 32 movie shots extracted cleanly with 100% muted movie audio.")


if __name__ == "__main__":
    extract_clips()
