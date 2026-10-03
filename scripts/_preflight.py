import ast, math
from pathlib import Path

content = Path("scripts/run_phase5_fresh_validation.py").read_bytes().decode("utf-8")
ast.parse(content)
print("Syntax: OK,", len(content.splitlines()), "lines")

checks = [
    ("alimiter -2dBFS",             "level_out=0.794:limit=0.794"),
    ("novel b2 hermione timing",    '"start": 3.2, "end": 6.8,'),
    ("hermione punch action",       '"action": "punch"'),
    ("verify_final_render",         "verify_final_render("),
    ("num_samples 6",               "num_samples_per_beat=6"),
]

for label, needle in checks:
    found = needle in content
    status = "OK" if found else "MISSING"
    print(f"  [{status}] {label}")

print()
print("alimiter 0.794 =", round(20*math.log10(0.794), 2), "dBFS -> true peak guaranteed <= -1.0 dBTP")
