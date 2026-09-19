import subprocess
from pathlib import Path

movie_path = Path("data/movies/Harry Potter and the Sorcerers Stone (2001) Dual Audio {Hindi-English} 1080p BluRay 2.8GB ESub.mkv")
out_dir = Path("data/clips/test_rebuild")
out_dir.mkdir(parents=True, exist_ok=True)

# Test extract 1 shot from Hagrid pig tail scene: 1045s to 1048s (3 seconds)
test_clip = out_dir / "shot_hagrid_pig_test.mp4"

# 1080x1920 9:16 vertical crop with muted audio
vf = "scale=-1:1920,crop=1080:1920"
cmd = [
    "ffmpeg", "-y", "-loglevel", "error",
    "-ss", "1045.0",
    "-to", "1048.0",
    "-i", str(movie_path),
    "-an",  # ZERO MOVIE AUDIO
    "-vf", vf,
    "-r", "30",
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
    str(test_clip)
]
subprocess.run(cmd, check=True)
print(f"Extracted test clip: {test_clip} ({test_clip.stat().st_size} bytes)")
