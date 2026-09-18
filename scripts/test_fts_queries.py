import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.movie_asset_engine import MovieAssetEngine

engine = MovieAssetEngine()
queries = [
    ("Dumbledore", 1),
    ("Dobby", 2),
    ("Dementor", 3),
    ("Triwizard", 4),
    ("Prophecy", 5),
    ("Horcrux", 6),
    ("Bathilda", 7),
    ("Nagini", 8)
]

print("=" * 80)
print("TESTING SCENE MATCHING ACROSS ALL 8 MOVIES")
print("=" * 80)

for q, m_num in queries:
    res = engine.search_movie_scenes(q, movie_number=m_num, limit=1)
    if res:
        m = res[0]
        snippet = m["text"][:100].replace("\n", " ")
        print(f"Movie {m_num} [{q}]:")
        print(f"  Chunk:    {m['chunk_id']}")
        print(f"  Timeline: {m['start_timecode']} --> {m['end_timecode']} ({m['duration_seconds']}s)")
        print(f"  Dialogue: \"{snippet}\"")
        print(f"  Rank:     {m['relevance_rank']}\n")
    else:
        print(f"Movie {m_num} [{q}]: NO MATCH\n")
