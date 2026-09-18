import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.movie_asset_engine import MovieAssetEngine

engine = MovieAssetEngine()

# Movie 8 Nagini scene: 01:09:14 (4154.567s), 4.0 seconds duration
mkv_path = Path("data/movies/Harry Potter and the Deathly Hallows Part 2 2011 Dual Audio Hindi 720p BluRay (1).mkv")
out_clip = Path("data/assets/test_m8_muted_nagini.mp4")

print(f"Testing audio-muted clip extraction from Movie 8...")
result_path = engine.extract_muted_clip(
    video_input_path=mkv_path,
    start_seconds=4154.5,
    duration_seconds=4.0,
    output_clip_path=out_clip,
    target_width=1080,
    target_height=1920
)

print(f"Extracted clip path: {result_path}")
print(f"Clip exists: {result_path.exists()}, size: {result_path.stat().st_size} bytes")

# Double-check probe directly
import subprocess
probe_cmd = [
    "ffprobe", "-v", "error",
    "-select_streams", "a",
    "-show_entries", "stream=codec_type",
    "-of", "csv=p=0",
    str(result_path)
]
probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
audio_found = probe_res.stdout.strip()
print(f"Audio streams found in output clip: '{audio_found}' (Empty string = ZERO audio streams confirmed)")
if not audio_found and result_path.stat().st_size > 0:
    print("AUDIO MUTING INVARIANT FULLY CONFIRMED IN REAL EXTRACTION!")
else:
    print("FAILURE: Audio streams found or file empty!")
