"""
Discovery Content Format Separation & Quality Gate Test Suite
=============================================================
Verifies:
1. Canonical Discovery Subtypes Enum (8 explicit subtypes)
2. Subtype-Specific Script Prompts & Architecture
3. 11-Point Discovery Quality Gate (Checks A through K)
4. Visual-to-Script Classifications (DIRECT vs CONTEXTUAL)
5. Strict Non-Interference: Novel Story intact, Discovery has NO PART markers
"""
import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.discovery_types import DiscoverySubtype, VisualClassification, DiscoveryQAResult
from engines.hp_script_engine import HarryPotterScriptEngine
from core.event_semantic_engine import EventSemanticVisualEngine


def test_discovery_format_separation():
    print("=" * 80)
    print("TESTING HARRY POTTER DISCOVERY CONTENT-FORMAT SEPARATION")
    print("=" * 80)

    # 1. Verify 8 canonical subtypes
    print("\n[TEST 1] Verifying 8 Canonical Discovery Subtypes...")
    expected_subtypes = {
        "DISCOVERY_FACT",
        "DISCOVERY_BOOK_MOVIE_DIFFERENCE",
        "DISCOVERY_OMITTED_SCENE",
        "DISCOVERY_NOVEL_ONLY_DETAIL",
        "DISCOVERY_CHARACTER_DETAIL",
        "DISCOVERY_BEHIND_THE_SCENES",
        "DISCOVERY_MOVIE_DETAIL",
        "DISCOVERY_TRIVIA",
    }
    actual_subtypes = {s.value for s in DiscoverySubtype}
    assert expected_subtypes == actual_subtypes, f"Subtype mismatch! Expected {expected_subtypes}, got {actual_subtypes}"
    print("  --> [TEST 1 PASSED]: All 8 canonical Discovery subtypes registered.")

    # 2. Query DB and run 11-point Discovery Quality Gate on all 4 Discovery scripts
    print("\n[TEST 2] Running 11-Point Discovery Quality Gate on Active Discovery Scripts...")
    engine = HarryPotterScriptEngine()
    conn = sqlite3.connect(PROJECT_ROOT / "data/database/pipeline.db")
    c = conn.cursor()

    discovery_ids = [
        "hps_disc_peeves_poltergeist_b1",
        "hps_disc_neville_hufflepuff_sorting_b1",
        "hps_disc_mirror_of_erised_inscription_b1",
        "hps_disc_neville_remembrall_cloak_b1",
    ]

    for s_id in discovery_ids:
        c.execute("SELECT id, content_type, discovery_type, hook, development, payoff, full_text, part_marker FROM hp_scripts WHERE id = ?", (s_id,))
        row = c.fetchone()
        assert row is not None, f"Script {s_id} missing from database!"
        s_id, c_type, stype, hook, dev, payoff, full_text, p_marker = row

        print(f"\n  Evaluating {s_id}:")
        print(f"    Subtype:     {stype}")
        print(f"    Hook:        {hook[:60]}...")
        print(f"    Part Marker: {p_marker}")

        # Run 11-Point Quality Gate
        qa_res = engine.evaluate_discovery_qa(
            script_text=full_text,
            hook=hook,
            subtype=stype,
            visual_beats=[],
            part_marker=p_marker
        )

        print(f"    Passed: {qa_res.passed} | Reasons: {qa_res.failure_reasons}")
        assert qa_res.passed, f"Discovery QA failed for {s_id}: {qa_res.failure_reasons}"
        assert qa_res.no_part_markers, f"PART marker detected in Discovery Short {s_id}!"
        assert qa_res.subject_in_first_5s, f"Subject not in first 5s for {s_id}!"
        assert qa_res.avoids_chronological_story, f"Chronological story transitions detected in {s_id}!"

    print("\n  --> [TEST 2 PASSED]: All 4 Discovery scripts passed 11-Point Quality Gate (Checks A through K).")

    # 3. Verify Visual Classifications in Event Semantic Engine
    print("\n[TEST 3] Verifying Visual Classifications (DIRECT vs CONTEXTUAL)...")
    event_engine = EventSemanticVisualEngine()
    
    # Short 5: Rik Mayall Peeves (Contextual)
    e5 = event_engine.get_canonical_events_for_short("hps_disc_peeves_poltergeist_b1")
    assert all(b.visual_classification == "CONTEXTUAL" for b in e5), "Short 5 visual classification must be CONTEXTUAL"
    print("  Short 5 (Peeves BTS): All beats correctly classified as CONTEXTUAL.")

    # Short 6: Neville Sorting Book/Movie Difference (Contextual)
    e6 = event_engine.get_canonical_events_for_short("hps_disc_neville_hufflepuff_sorting_b1")
    assert all(b.visual_classification == "CONTEXTUAL" for b in e6), "Short 6 visual classification must be CONTEXTUAL"
    print("  Short 6 (Neville Sorting): All beats correctly classified as CONTEXTUAL.")

    # Short 7: Mirror of Erised Inscription (Direct)
    e7 = event_engine.get_canonical_events_for_short("hps_disc_mirror_of_erised_inscription_b1")
    assert all(b.visual_classification == "DIRECT" for b in e7), "Short 7 visual classification must be DIRECT"
    print("  Short 7 (Mirror Inscription): All beats correctly classified as DIRECT.")

    # Short 8: Neville Remembrall Robes (Direct)
    e8 = event_engine.get_canonical_events_for_short("hps_disc_neville_remembrall_cloak_b1")
    assert all(b.visual_classification == "DIRECT" for b in e8), "Short 8 visual classification must be DIRECT"
    print("  Short 8 (Neville Robes): All beats correctly classified as DIRECT.")

    print("  --> [TEST 3 PASSED]: Visual classifications strictly aligned with information nature.")

    # 4. Confirm Novel Story Shorts Remain Completely Intact
    print("\n[TEST 4] Confirming Novel Story Shorts Remain Completely Intact...")
    novel_ids = [
        ("hps_ns_b1c01_gc0001_0003", "PART 01"),
        ("hps_ns_b1c01_gc0004_0006", "PART 02"),
        ("hps_ns_b1c01_gc0007_0009", "PART 03"),
        ("hps_ns_b1c01_gc0010_0012", "PART 04"),
    ]
    for n_id, expected_part in novel_ids:
        c.execute("SELECT content_type, part_marker FROM hp_scripts WHERE id = ?", (n_id,))
        row = c.fetchone()
        assert row is not None, f"Novel Short {n_id} missing!"
        assert row[0] == "novel_story", f"Content type modified for {n_id}!"
        assert row[1] == expected_part, f"Part marker modified for {n_id}! Expected {expected_part}, got {row[1]}"
        print(f"  Novel Short {n_id}: Intact with {expected_part}.")

    print("  --> [TEST 4 PASSED]: Approved Novel Story architecture 100% untouched.")

    conn.close()
    print("\n" + "=" * 80)
    print("ALL DISCOVERY CONTENT FORMAT SEPARATION TESTS PASSED PERFECTLY!")
    print("=" * 80)


if __name__ == "__main__":
    test_discovery_format_separation()
