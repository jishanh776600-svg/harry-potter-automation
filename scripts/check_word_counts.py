import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_24_production_shorts import SHORTS_DATA

for d in SHORTS_DATA:
    txt = f"{d['hook']} {d['development']} {d['payoff']}"
    wc = len(txt.split())
    status = 'OK' if 55 <= wc <= 75 else f'BAD ({wc})'
    print(f"{d['part_marker']}: {wc} words -> {status}")
