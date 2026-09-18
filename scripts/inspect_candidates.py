import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import DB_PATH
from core.models import NovStoryCandidate, DiscoveryCandidate, ChronologyState
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine(f"sqlite:///{DB_PATH}")
Session = sessionmaker(bind=engine)

with Session() as session:
    print("=== Chronology State ===")
    cs = session.query(ChronologyState).all()
    for s in cs:
        print(f"ID={s.id}, last_global={s.last_planned_global_index}, book={s.last_planned_book_number}, ch={s.last_planned_chapter_number}, total={s.total_candidates_generated}")

    print("\n=== Novel Story Candidates ===")
    novs = session.query(NovStoryCandidate).all()
    for n in novs:
        print(f"ID={n.id} | Launch={n.is_launch_candidate} | Slot={n.batch_slot} | B{n.book_number}C{n.chapter_number} | GC={n.global_chronology_start}-{n.global_chronology_end} | Status={n.status}")
        print(f"  Summary: {n.story_event_summary[:120]}")
        print(f"  Hook: {n.hook_concept[:120]}")

    print("\n=== Discovery Candidates ===")
    discs = session.query(DiscoveryCandidate).all()
    for d in discs:
        print(f"ID={d.id} | Launch={d.is_launch_candidate} | Slot={d.batch_slot} | Type={d.discovery_type} | B{d.book_number}C{d.chapter_number} | Status={d.status}")
        print(f"  Fact: {d.novel_fact_summary[:120]}")
        print(f"  Hook: {d.hook_concept[:120]}")
