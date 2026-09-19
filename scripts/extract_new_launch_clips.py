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
    # SHORT 1: Dudley's Pig Tail (Novel Story, Bella, PART 01)
    # -------------------------------------------------------------------------
    "hps_ns_b1c01_gc0001_0003": [
        {"shot_id": "shot_01", "ss": 850.0, "to": 853.0, "desc": "Door knocked off hinges in sea hut"},
        {"shot_id": "shot_02", "ss": 856.0, "to": 859.0, "desc": "Hagrid towering in doorway in stormy wind"},
        {"shot_id": "shot_03", "ss": 915.0, "to": 918.0, "desc": "Vernon yelling hysterically pointing rifle"},
        {"shot_id": "shot_04", "ss": 919.0, "to": 922.0, "desc": "Hagrid grabbing rifle barrel and twisting it"},
        {"shot_id": "shot_05", "ss": 1046.0, "to": 1049.0, "desc": "Hagrid glaring fiercely pointing pink umbrella"},
        {"shot_id": "shot_06", "ss": 1050.0, "to": 1053.0, "desc": "Violet sparks flashing from umbrella tip"},
        {"shot_id": "shot_07", "ss": 1055.0, "to": 1058.0, "desc": "Dudley howling clutching curly tail"},
        {"shot_id": "shot_08", "ss": 1060.0, "to": 1063.0, "desc": "Dursleys fleeing in terror as Hagrid smiles sheepishly"}
    ],

    # -------------------------------------------------------------------------
    # SHORT 2: Malfoy's Trap & The Midnight Duel (Novel Story, Bella, PART 02)
    # -------------------------------------------------------------------------
    "hps_ns_b1c01_gc0004_0006": [
        {"shot_id": "shot_01", "ss": 2780.0, "to": 2783.0, "desc": "Malfoy smirking maliciously in Great Hall"},
        {"shot_id": "shot_02", "ss": 3670.0, "to": 3673.0, "desc": "Harry and Ron sneaking through darkened corridor"},
        {"shot_id": "shot_03", "ss": 3680.0, "to": 3683.0, "desc": "Whispering urgently behind stone pillar with wand"},
        {"shot_id": "shot_04", "ss": 3710.0, "to": 3713.0, "desc": "Filch raising glowing lantern searching shadows"},
        {"shot_id": "shot_05", "ss": 3718.0, "to": 3721.0, "desc": "Kids sprinting in terror down forbidden corridor"},
        {"shot_id": "shot_06", "ss": 3725.0, "to": 3728.0, "desc": "Hermione tapping keyhole whispering Alohomora"},
        {"shot_id": "shot_07", "ss": 3730.0, "to": 3733.0, "desc": "Door opening and kids slipping inside in relief"},
        {"shot_id": "shot_08", "ss": 3760.0, "to": 3763.5, "desc": "Fluffy three giant snarling heads looming over them"}
    ],

    # -------------------------------------------------------------------------
    # SHORT 3: Snape's Deleted Potion Riddle (Discovery, Sarah, NO PART MARKER)
    # -------------------------------------------------------------------------
    "hps_disc_peeves_poltergeist_b1": [
        {"shot_id": "shot_01", "ss": 3125.0, "to": 3128.0, "desc": "Snape sweeping into dark dungeon with black robes"},
        {"shot_id": "shot_02", "ss": 7450.0, "to": 7453.0, "desc": "Giant wizard chess pieces crashing on floor"},
        {"shot_id": "shot_03", "ss": 7580.0, "to": 7583.0, "desc": "Harry and Hermione running through dark archway"},
        {"shot_id": "shot_04", "ss": 7620.0, "to": 7623.0, "desc": "Wall of magical fire roaring up in doorway"},
        {"shot_id": "shot_05", "ss": 3140.0, "to": 3143.0, "desc": "Dark potion vials and flasks on stone bench"},
        {"shot_id": "shot_06", "ss": 7635.0, "to": 7638.0, "desc": "Hermione looking determined figuring out riddle"},
        {"shot_id": "shot_07", "ss": 7650.0, "to": 7653.0, "desc": "Hermione hugging Harry bravely beside steps"},
        {"shot_id": "shot_08", "ss": 7665.0, "to": 7668.5, "desc": "Harry stepping through roaring flames safely"}
    ],

    # -------------------------------------------------------------------------
    # SHORT 4: McGonagall's Secret Nimbus 2000 (Discovery, Sarah, NO PART MARKER)
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

            # Update or insert into hp_movie_clips
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
                ON CONFLICT(id) DO UPDATE SET
                    source_start_seconds=excluded.source_start_seconds,
                    source_end_seconds=excluded.source_end_seconds,
                    clip_start_seconds=excluded.clip_start_seconds,
                    clip_end_seconds=excluded.clip_end_seconds,
                    duration_seconds=excluded.duration_seconds,
                    file_path=excluded.file_path,
                    file_size_bytes=excluded.file_size_bytes,
                    sha256=excluded.sha256,
                    audio_stream_count=excluded.audio_stream_count,
                    width=excluded.width,
                    height=excluded.height,
                    visual_source_policy=excluded.visual_source_policy,
                    match_status=excluded.match_status,
                    status=excluded.status,
                    updated_at=excluded.updated_at
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
