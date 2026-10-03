import subprocess
from pathlib import Path

vault = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\harry_potter_automation\data\vault\phase5_validation_1790448318")
novel_mp4 = vault / "final_novel_buckbeak_malfoy_1790448318.mp4"
brain = Path(r"C:\Users\jisha\.gemini\antigravity\brain\eaa301ad-f26a-485c-9af7-0c985361de36")

print("Novel MP4 exists:", novel_mp4.exists())

timestamps = [(4.275, "b2_sample1"), (6.425, "b2_sample2"), (3.2, "b2_start")]
for ts, label in timestamps:
    out = brain / f"novel_probe_{label}.jpg"
    r = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", str(ts), "-i", str(novel_mp4),
        "-frames:v", "1", "-q:v", "2", str(out)
    ], capture_output=True)
    if out.exists():
        print(f"t={ts}s ({label}): {out.stat().st_size} bytes")
    else:
        err = r.stderr.decode("utf-8", errors="replace")
        print(f"t={ts}s ({label}): FAILED - {err[:80]}")
