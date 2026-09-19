import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

def render_test(margin_v: int, name: str):
    ass_content = f"""[Script Info]
Title: Test Subtitle Position
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HP_Default,Harry P,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4.5,0,2,80,80,{margin_v},1
Style: HP_TwoLine,Harry P,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4.2,0,2,80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:05.00,HP_Default,,0,0,0,,Hogwarts kitchens
"""
    ass_path = Path(f"data/subtitles/test_{name}.ass")
    ass_path.write_text(ass_content, encoding="utf-8")

    out_png = Path(f"data/subtitles/test_{name}_frame.png")
    # Escape path for FFmpeg subtitles filter
    ass_filter = f"subtitles='{ass_path.as_posix()}':fontsdir='data/fonts'"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x181820:s=1080x1920:d=1",
        "-vf", ass_filter,
        "-vframes", "1",
        str(out_png)
    ]
    subprocess.run(cmd, check=True)
    print(f"Rendered {out_png} with MarginV={margin_v}")
    return out_png

if __name__ == "__main__":
    # Test MarginV = 790 (old center), 560 (lower-middle upper), 500 (lower-middle classic), 450 (lower)
    render_test(790, "old_790")
    render_test(540, "new_540")
    render_test(500, "new_500")
