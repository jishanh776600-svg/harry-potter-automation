import cv2
import numpy as np
import os
import subprocess

params = [
    # (name, fontsize, outline, shadow, spacing, marginv)
    ('size88_out5', 88, 5, 0, 0, 800),
    ('size96_out5', 96, 5, 0, 0, 800),
    ('size96_out6', 96, 6, 0, 0, 800),
    ('size104_out5', 104, 5, 0, 0, 800),
    ('size104_out6', 104, 6, 1, 0, 800),
    ('size104_out7', 104, 7, 0, 0, 800),
]

for name, fs, out, sh, sp, mv in params:
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HP,Harry P,{fs},&H00FFFFFF,&H00000000,&H00000000,&H80000000,-1,0,0,0,100,100,{sp},0,1,{out},{sh},2,80,80,{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,HP,,0,0,0,,Hogwarts kitchens
"""
    ass_path = f"data/subtitles/test_{name}.ass"
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    
    out_png = f"data/subtitles/frame_{name}.png"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=1",
        "-vf", f"subtitles={ass_path}:fontsdir=data/fonts",
        "-frames:v", "1", "-update", "1",
        out_png
    ]
    subprocess.run(cmd, check=True)
    print(f"Rendered {name}")
