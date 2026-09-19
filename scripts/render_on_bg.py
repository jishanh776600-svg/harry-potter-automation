import subprocess
from pathlib import Path

BASE = Path("data/subtitles")
FONT_DIR = Path("data/fonts")

for test_name in ["precise_hogwarts", "precise_castle", "precise_validation_2lines"]:
    ass_path = BASE / f"{test_name}.ass"
    out_png = BASE / f"{test_name}_on_bg.png"
    
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(BASE / "bg_test.png").replace("\\", "/"),
        "-vf", f"subtitles='{str(ass_path).replace('\\', '/')}':fontsdir='{str(FONT_DIR).replace('\\', '/')}'",
        "-frames:v", "1", "-update", "1",
        str(out_png)
    ]
    subprocess.run(cmd, check=True)
    print(f"Rendered {out_png}")
