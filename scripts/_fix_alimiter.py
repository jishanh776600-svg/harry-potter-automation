"""
Patch run_phase5_fresh_validation.py — Attempt 6 fixes:
1. True peak: lower alimiter limit from 0.891 to 0.794 (-2 dBFS)
   giving 1 dB of headroom for inter-sample peaks.
   0.794 linear = -2.0 dBFS. With narration at -14 LUFS,
   the composite true peak will be comfortably <= -1.0 dBTP.

2. Novel beat timeline alignment: FRV samples the final MP4 using
   narration_start/end as VIDEO timestamps. But the rendered video
   has shot1=3.5s, shot2=4.3s, shot3=3.9s, shot4=3.8s (approx).
   novel_b2_strike must have narration_start=3.5 (not 3.2) so FRV
   samples frames that are actually inside the Buckbeak clip.

   Correct video-timeline offsets:
     novel_b1_setup:    0.0 -> 3.5   (shot1: m3_camera_pan_hogwarts)
     novel_b2_strike:   3.5 -> 7.8   (shot2: m3_buckbeak_slash_malfoy)
     novel_b3_reaction: 7.8 -> 11.7  (shot3: m3_hermione_wand_standoff)
     novel_b4_aftermath:11.7 -> 15.5 (shot4: m3_lupin_chocolate_handover)

3. Buckbeak crop threshold: lower from 0.60 to 0.40 (Buckbeak bbox.w=0.498
   is still too large to crop well; use centre crop).
"""
from pathlib import Path
import re, ast

script = Path("scripts/run_phase5_fresh_validation.py")
content = script.read_bytes().decode("utf-8")

# ── Fix 1: True peak limiter ─────────────────────────────────────────────────
OLD_LIMIT = "alimiter=level_in=1:level_out=0.891:limit=0.891:attack=5:release=50:level=true[aout]"
NEW_LIMIT = "alimiter=level_in=1:level_out=0.794:limit=0.794:attack=5:release=50:level=false[aout]"
if OLD_LIMIT in content:
    content = content.replace(OLD_LIMIT, NEW_LIMIT)
    print("[1] alimiter limit: 0.891 -> 0.794 (-2 dBFS, inter-sample safe)")
else:
    print("[1] WARNING: old alimiter not found — checking what's there:")
    for i, ln in enumerate(content.splitlines(), 1):
        if "alimiter" in ln:
            print(f"  L{i}: {ln.strip()!r}")

# ── Fix 2: Novel beat timeline alignment ─────────────────────────────────────
# Replace the beats_data dict in render_novel() with correct video offsets
OLD_BEATS = (
    '        {\n'
    '            "beat_id": "novel_b1_setup",\n'
    '            "narration": "Draco Malfoy insulted Buckbeak, calling him a stupid creature.",\n'
    '            "start": 0.0, "end": 3.2,\n'
    '            "type": "VISUAL_OPTIONAL", "direct": False,\n'
    '        },\n'
    '        {\n'
    '            "beat_id": "novel_b2_strike",\n'
    '            "narration": "Buckbeak reared up and slashed Malfoy across the arm with his talons.",\n'
    '            "start": 3.2, "end": 7.5,\n'
    '            "type": "VERIFIED_DIRECT", "direct": True,\n'
    '            "subjects": ["Buckbeak", "Draco Malfoy"],\n'
    '            "action": "slash strike",\n'
    '        },\n'
    '        {\n'
    '            "beat_id": "novel_b3_reaction",\n'
    '            "narration": "Hermione and Harry watched in shock as Draco collapsed to the ground.",\n'
    '            "start": 7.5, "end": 11.4,\n'
    '            "type": "VISUAL_OPTIONAL", "direct": False,\n'
    '        },\n'
    '        {\n'
    '            "beat_id": "novel_b4_aftermath",\n'
    '            "narration": "Buckbeak\'s loyalty, like all magical creatures, demanded respect -- or faced the consequences.",\n'
    '            "start": 11.4, "end": 15.5,\n'
    '            "type": "VISUAL_OPTIONAL", "direct": False,\n'
    '        },\n'
)
NEW_BEATS = (
    '        {\n'
    '            "beat_id": "novel_b1_setup",\n'
    '            "narration": "Draco Malfoy insulted Buckbeak, calling him a stupid creature.",\n'
    '            # Video offset: shot1 plays 0.0 -> 3.5s in the rendered MP4\n'
    '            "start": 0.0, "end": 3.5,\n'
    '            "type": "VISUAL_OPTIONAL", "direct": False,\n'
    '        },\n'
    '        {\n'
    '            "beat_id": "novel_b2_strike",\n'
    '            "narration": "Buckbeak reared up and slashed Malfoy across the arm with his talons.",\n'
    '            # Video offset: shot2 plays 3.5 -> 7.8s -- FRV must sample here\n'
    '            "start": 3.5, "end": 7.8,\n'
    '            "type": "VERIFIED_DIRECT", "direct": True,\n'
    '            "subjects": ["Buckbeak", "Draco Malfoy"],\n'
    '            "action": "slash strike",\n'
    '        },\n'
    '        {\n'
    '            "beat_id": "novel_b3_reaction",\n'
    '            "narration": "Hermione and Harry watched in shock as Draco collapsed to the ground.",\n'
    '            # Video offset: shot3 plays 7.8 -> 11.7s\n'
    '            "start": 7.8, "end": 11.7,\n'
    '            "type": "VISUAL_OPTIONAL", "direct": False,\n'
    '        },\n'
    '        {\n'
    '            "beat_id": "novel_b4_aftermath",\n'
    '            "narration": "Buckbeak\'s loyalty, like all magical creatures, demanded respect -- or faced the consequences.",\n'
    '            # Video offset: shot4 plays 11.7 -> end\n'
    '            "start": 11.7, "end": 15.5,\n'
    '            "type": "VISUAL_OPTIONAL", "direct": False,\n'
    '        },\n'
)
if OLD_BEATS in content:
    content = content.replace(OLD_BEATS, NEW_BEATS)
    print("[2] Novel beat video offsets aligned: b2_strike now starts at 3.5s (after shot1 ends)")
else:
    print("[2] WARNING: beat data block not found at expected text — checking nearby lines:")
    for i, ln in enumerate(content.splitlines(), 1):
        if "novel_b2_strike" in ln or "3.2, \"end\": 7.5" in ln:
            print(f"  L{i}: {ln!r}")

# ── Fix 3: Buckbeak crop threshold 0.60 -> 0.40 ──────────────────────────────
OLD_THRESH = "        if bk.bbox.w > 0.60:"
NEW_THRESH = "        if bk.bbox.w > 0.40:  # Buckbeak bbox.w=0.498 triggers centre crop"
if OLD_THRESH in content:
    content = content.replace(OLD_THRESH, NEW_THRESH)
    print("[3] Buckbeak wide-entity threshold: 0.60 -> 0.40 (bbox.w=0.498 now triggers centre crop)")
else:
    print("[3] WARNING: threshold line not found")

# ── Write and validate ────────────────────────────────────────────────────────
script.write_bytes(content.encode("utf-8"))
try:
    ast.parse(content)
    print("Syntax: OK")
except SyntaxError as e:
    print(f"SYNTAX ERROR at L{e.lineno}: {e.msg}")
    lines = content.splitlines()
    for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
        mark = ">>>" if i+1 == e.lineno else "   "
        print(f"{mark} L{i+1}: {lines[i]!r}")
