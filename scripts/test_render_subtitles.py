import subprocess
from pathlib import Path

BASE = Path("data/subtitles")
FONT_DIR = Path("data/fonts")

tests = [
    # (id, text, fontsize, outline, shadow, marginv)
    ("test_hogwarts", "Hogwarts kitchens", 96, 5.5, 0, 800),
    ("test_castle", "the castle", 96, 5.5, 0, 800),
    ("test_validation_sentence", "Harry Potter had no idea\nwhat was waiting for him.", 96, 5.5, 0, 800),
    ("test_validation_single_line", "Harry Potter had no idea what was waiting for him.", 84, 5.0, 0, 800),
]

for test_id, text, fs, out, sh, mv in tests:
    ass_path = BASE / f"{test_id}.ass"
    out_png = BASE / f"{test_id}_rendered.png"
    
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
Dialogue: 0,0:00:00.00,0:00:05.00,HP_Short,,0,0,0,,{text.replace('\n', '\\N')}
"""
    ass_path.write_text(ass_text, encoding="utf-8")
    
    # Use forward slashes for FFmpeg filter arguments
    ass_filter_path = str(ass_path).replace("\\", "/")
    fonts_filter_dir = str(FONT_DIR).replace("\\", "/")
    
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(BASE / "bg_test.png").replace("\\", "/"),
        "-vf", f"subtitles='{ass_filter_path}':fontsdir='{fonts_filter_dir}'",
        "-frames:v", "1", "-update", "1",
        str(out_png)
    ]
    subprocess.run(cmd, check=True)
    print(f"Generated: {out_png}")
