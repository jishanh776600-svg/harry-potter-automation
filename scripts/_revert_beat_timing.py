"""
Revert fix 2 (wrong beat timing): restore original beat timings (3.2 / 7.5 / 11.4 / 15.5)
since the rendered video timeline DOES follow narration durations, not raw clip durations.
"""
from pathlib import Path
import ast

script = Path("scripts/run_phase5_fresh_validation.py")
content = script.read_bytes().decode("utf-8")

# Current (wrong) block after fix 2
OLD_BEATS = (
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

# Correct block — narration-duration-based timeline
NEW_BEATS = (
    '        {\n'
    '            "beat_id": "novel_b1_setup",\n'
    '            "narration": "Draco Malfoy insulted Buckbeak, calling him a stupid creature.",\n'
    '            # Narration window (= video offset since renderer trims clips to narration)\n'
    '            "start": 0.0, "end": 3.2,\n'
    '            "type": "VISUAL_OPTIONAL", "direct": False,\n'
    '        },\n'
    '        {\n'
    '            "beat_id": "novel_b2_strike",\n'
    '            "narration": "Buckbeak reared up and slashed Malfoy across the arm with his talons.",\n'
    '            # Narration window 3.2->7.5 = video window for Buckbeak clip in final MP4\n'
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

if OLD_BEATS in content:
    content = content.replace(OLD_BEATS, NEW_BEATS)
    print("[REVERT] Restored original narration-based beat timings (3.2/7.5/11.4/15.5)")
else:
    print("[REVERT] ERROR: wrong-timing block not found")
    for i, ln in enumerate(content.splitlines(), 1):
        if '"start": 3.5' in ln and i > 660 and i < 720:
            print(f"  L{i}: {ln!r}")

script.write_bytes(content.encode("utf-8"))
ast.parse(content)
print("Syntax OK")
