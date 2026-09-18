import sys
import json
import logging
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from config.settings import PUBLISHING_ENABLED, UPLOAD_ENABLED, DB_PATH
from engines.hp_script_engine import HarryPotterScriptEngine
from core.models import NovStoryCandidate, DiscoveryCandidate, HarryPotterScript

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Batch2Runner")


def register_candidates(session):
    c5 = session.query(NovStoryCandidate).filter_by(id="ns_b1c02_gc0020_0022").first()
    if not c5:
        c5 = NovStoryCandidate(
            id="ns_b1c02_gc0020_0022",
            content_type="novel_story",
            book_number=1,
            book_title="Harry Potter and the Philosopher's Stone",
            chapter_number=2,
            chapter_title="The Vanishing Glass",
            chunk_id_start="hp_b1_c02_chk008",
            chunk_id_end="hp_b1_c02_chk010",
            global_chronology_start=20,
            global_chronology_end=22,
            source_location="Book 1, Chapter 2 (p. 23-26)",
            source_text_preview="After lunch they went to the reptile house. It was cool and dark in there...",
            story_event_summary="Harry visits the zoo reptile house, speaks to a boa constrictor, and the glass magically vanishes, allowing the snake to escape while Dudley is trapped inside.",
            narration_complexity="LOW",
            short_duration_feasibility="FEASIBLE",
            overall_visual_feasibility="CONFIRMED_HIGH",
            status="APPROVED",
            content_fingerprint="fp_ns_b1c02_gc0020_0022",
            is_launch_candidate=False,
            batch_slot=5,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(c5)
        logger.info("Registered candidate: ns_b1c02_gc0020_0022")

    c6 = session.query(NovStoryCandidate).filter_by(id="ns_b1c03_gc0029_0031").first()
    if not c6:
        c6 = NovStoryCandidate(
            id="ns_b1c03_gc0029_0031",
            content_type="novel_story",
            book_number=1,
            book_title="Harry Potter and the Philosopher's Stone",
            chapter_number=3,
            chapter_title="The Letters from No One",
            chunk_id_start="hp_b1_c03_chk007",
            chunk_id_end="hp_b1_c03_chk009",
            global_chronology_start=29,
            global_chronology_end=31,
            source_location="Book 1, Chapter 3 (p. 33-36)",
            source_text_preview="letters came pelting out of the fireplace like bullets...",
            story_event_summary="Uncle Vernon boards up the house to block Harry's letters, but on Sunday morning, hundreds of letters fly out of the fireplace, filling the living room.",
            narration_complexity="LOW",
            short_duration_feasibility="FEASIBLE",
            overall_visual_feasibility="CONFIRMED_HIGH",
            status="APPROVED",
            content_fingerprint="fp_ns_b1c03_gc0029_0031",
            is_launch_candidate=False,
            batch_slot=6,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(c6)
        logger.info("Registered candidate: ns_b1c03_gc0029_0031")

    c7 = session.query(DiscoveryCandidate).filter_by(id="disc_mirror_of_erised_inscription_b1").first()
    if c7:
        c7.batch_slot = 7
        c7.updated_at = datetime.utcnow()
        logger.info("Updated candidate: disc_mirror_of_erised_inscription_b1 (slot 7)")

    c8 = session.query(DiscoveryCandidate).filter_by(id="disc_neville_remembrall_cloak_b1").first()
    if not c8:
        c8 = DiscoveryCandidate(
            id="disc_neville_remembrall_cloak_b1",
            content_type="discovery",
            discovery_type="LORE_DETAIL",
            book_number=1,
            book_title="Harry Potter and the Philosopher's Stone",
            chapter_number=9,
            chapter_title="The Midnight Duel",
            chunk_id_primary="hp_b1_c11_chk056",
            novel_fact_summary="Neville Longbottom receives a Remembrall that turns red when you have forgotten something, but he cannot remember what he forgot. The movie visual reveals he forgot his school cloak.",
            novel_evidence_text="Gran knows I forget things -- this tells you if there's something you've forgotten to do. Look, you hold it tight like this and if it turns red -- oh... because he couldn't remember what he had forgotten.",
            corresponding_movie_number=1,
            corresponding_movie_title="Harry Potter and the Sorcerer's Stone",
            movie_chunk_id="hp_m1_sc_0222",
            movie_shows="Neville holds the Remembrall as red smoke fills it, saying he cannot remember what he forgot. In the shot, all surrounding students wear their black robes, while Neville is in his shirt and tie.",
            movie_omits_or_changes="The movie never verbally explains what Neville forgot, leaving the cloak detail as a subtle visual background clue.",
            why_interesting="The movie solves Neville's mystery in plain sight without ever drawing explicit attention to it.",
            hook_concept="Did you know Neville's magical glass ball revealed his secret right on screen?",
            short_duration_feasibility="FEASIBLE",
            overall_visual_feasibility="CONFIRMED_HIGH",
            status="APPROVED",
            content_fingerprint="fp_disc_neville_remembrall_cloak_b1",
            is_launch_candidate=False,
            batch_slot=8,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(c8)
        logger.info("Registered candidate: disc_neville_remembrall_cloak_b1")

    session.commit()
    return c5, c6, c7, c8


def main():
    print("=" * 80)
    print("   BATCH 2: GENERATING 4 NEW HARRY POTTER SHORTS (SHORTS 5, 6, 7, 8)   ")
    print("=" * 80)

    if PUBLISHING_ENABLED or UPLOAD_ENABLED:
        print("ERROR: Publishing gates must remain disabled!")
        sys.exit(1)

    engine = HarryPotterScriptEngine()

    with engine.Session() as session:
        c5, c6, c7, c8 = register_candidates(session)

        prev_ids = [
            "hps_ns_b1c01_gc0001_0003",
            "hps_ns_b1c01_gc0004_0006",
            "hps_disc_peeves_poltergeist_b1",
            "hps_disc_neville_hufflepuff_sorting_b1"
        ]
        existing_prev = session.query(HarryPotterScript).filter(HarryPotterScript.id.in_(prev_ids)).all()
        print(f"\n[CHECK] Verified {len(existing_prev)}/4 previous batch scripts exist safely in database.")

        candidates = [c5, c6, c7, c8]
        new_scripts = []

        for cand in candidates:
            script_rec = engine.generate_script_for_candidate(cand, session)
            new_scripts.append(script_rec)

        print("\n" + "=" * 80)
        print("   BATCH 2 SCRIPTS GENERATED & PERSISTED SUCCESSFULLY   ")
        print("=" * 80)

        for s in new_scripts:
            print(f"\n[{s.part_marker}] SCRIPT ID: {s.id}")
            print(f"Content Type: {s.content_type} | QA: {s.qa_status} ({s.qa_score}/100)")
            print(f"Word Count: {s.word_count} words | Est Duration: {s.estimated_duration_sec}s")
            print(f"Hook: \"{s.hook}\"")
            print(f"Full Narration:\n  \"{s.full_text}\"")
            beats = json.loads(s.visual_beats_json)
            print(f"Total Visual Beats: {len(beats)}")
            for b in beats:
                print(f"  - {b['beat_id']} (Movie {b['preferred_movie_number']}): {b['visual_requirement'][:80]}...")

    print("\n[COMPLETE] Batch 2 generation complete. Zero rendering, zero publishing.")


if __name__ == "__main__":
    main()
