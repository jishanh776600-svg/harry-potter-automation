import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH
from core.models import HarryPotterScript
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(f"sqlite:///{DB_PATH}")
Session = sessionmaker(bind=engine)

with Session() as session:
    scripts = session.query(HarryPotterScript).all()
    for s in scripts:
        print("=" * 80)
        print(f"SCRIPT: {s.id} ({s.content_type})")
        print(f"Hook: {s.hook}")
        beats = json.loads(s.visual_beats_json)
        print(f"Total Beats: {len(beats)}")
        for b in beats:
            print(f"  Beat {b.get('beat_id')}:")
            print(f"    Narration:   {b.get('narration_text')}")
            print(f"    Requirement: {b.get('visual_requirement')}")
            print(f"    Characters:  {b.get('characters')}")
            print(f"    Location:    {b.get('location')}")
            print(f"    Action:      {b.get('action')}")
            print(f"    Movie Hint:  Movie {b.get('preferred_movie_number')}")
            print(f"    Retrieval:   {b.get('retrieval_hints')}")
