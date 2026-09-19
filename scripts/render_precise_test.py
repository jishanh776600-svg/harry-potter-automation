import subprocess
from pathlib import Path

BASE = Path("data/subtitles")
FONT_DIR = Path("data/fonts")

tests = [
    ("precise_hogwarts", "Hogwarts kitchens", 84, 4.5, 0, 790),
    ("precise_castle", "the castle", 84, 4.5, 0, 790),
    ("precise_validation_2lines", "Harry Potter had no idea\\Nwhat was waiting for him.", 84, 4.5, 0, 790),
    ("precise_validation_1line", "Harry Potter had no idea what was waiting for him.", 76, 4.2, 0, 790),
]

for test_id, text, fs, out, sh, mv in tests:
    ass_path = BASE / f"{test_id}.ass"
    out_png = BASE / f"{test_id}.png"
    
    ass_text = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HP_Short,Harry P,{fs},&H00FFFFFF,&H00000000,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{out},{sh},2,80,80,{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,HP_Short,,0,0,0,,{text}
"""
    ass_path.write_text(ass_text, encoding="utf-8")
    
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=1",
        "-vf", f"subtitles='{str(ass_path).replace('\\', '/')}':fontsdir='{str(FONT_DIR).replace('\\', '/')}'",
        "-frames:v", "1", "-update", "1",
        str(out_png)
    ]
    subprocess.run(cmd, check=True)
    print(f"Generated {out_png}")
