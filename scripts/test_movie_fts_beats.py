"""Debug movie FTS to check why Hogwarts search returns nothing."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.movie_asset_engine import MovieAssetEngine

eng = MovieAssetEngine()

queries = [
    "Hogwarts castle",
    "Privet Drive Dursley",
    "Harry Potter",
    "owl letter",
    "wizarding world",
    "Hogwarts",
    "Diagon Alley",
    "Sorting Hat",
    "Harry",
    "wand",
]

print("=" * 80)
print("MOVIE SRT FTS DIAGNOSTIC")
print("=" * 80)
for q in queries:
    try:
        results = eng.search_movie_scenes(q, limit=1)
        if results:
            r = results[0]
            tc = r["start_timecode"]
            txt = r["text"][:100].encode("ascii", "replace").decode("ascii")
            rank = r.get("relevance_rank", "?")
            print(f"FOUND   [{q}]: M{r['movie_number']} @{tc} rank={rank}")
            print(f"         Text: {txt}")
        else:
            print(f"NONE    [{q}]")
    except Exception as e:
        print(f"ERROR   [{q}]: {e}")
    print()
