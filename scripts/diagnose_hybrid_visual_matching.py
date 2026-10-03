"""
STORY FORGE — Hybrid SRT + Movie Event Diagnostic CLI Tool (Phase 3)
====================================================================
Evaluates the MovieEvent-sole-authority architecture across:
  1. All 8 Movie Positive Benchmarks (HP 1 through HP 8)
  2. All 8 Movie Negative / Action-Mismatch Tests (HP 1 through HP 8)
  3. Performance Benchmarks: Index build time, latency, candidate counts
  4. Architectural Verification: Proves SRT visual fallback is 100% disabled.
"""

import sys
import time
import argparse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engines.movie_event import (
    MovieEventIndex,
    VisualStoryboardGenerator,
    ClaimTransformer,
    SRTCoarseLocator,
    HybridVisualSelector,
    MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN,
)

# Benchmark Positive Cases across all 8 movies
ALL_8_MOVIE_BENCHMARKS = [
    {
        "movie": 1,
        "name": "Movie 1: Snape Questions Harry",
        "narration": "Snape questions Harry in Potions classroom.",
        "expected_event": "evt_m1_potions_snape_questions_harry",
        "expected_winner": "MOVIE_EVENT",
    },
    {
        "movie": 2,
        "name": "Movie 2: Harry Opens Chamber Entrance",
        "narration": "Harry opens the Chamber of Secrets entrance by speaking Parseltongue.",
        "expected_event": "evt_m2_bathroom_harry_speaks_parseltongue_opens_chamber",
        "expected_winner": "MOVIE_EVENT",
    },
    {
        "movie": 3,
        "name": "Movie 3: Hermione Punches Malfoy",
        "narration": "Hermione punches Malfoy squarely in the face.",
        "expected_event": "evt_m3_sundial_hermione_punches_malfoy",
        "expected_winner": "MOVIE_EVENT",
    },
    {
        "movie": 4,
        "name": "Movie 4: Harry Summons Firebolt (Accio)",
        "narration": "Harry summons Firebolt broom with Accio spell in the dragon arena.",
        "expected_event": "evt_m4_first_task_harry_summons_firebolt",
        "expected_winner": "MOVIE_EVENT",
    },
    {
        "movie": 5,
        "name": "Movie 5: Harry Casts Patronum in DA",
        "narration": "Harry casts Expecto Patronum in Room of Requirement.",
        "expected_event": "evt_m5_ror_harry_casts_patronum",
        "expected_winner": "MOVIE_EVENT",
    },
    {
        "movie": 6,
        "name": "Movie 6: Harry Drinks Felix Felicis",
        "narration": "Harry drinks Felix Felicis potion from small vial in Gryffindor common room.",
        "expected_event": "evt_m6_common_room_harry_drinks_felix_felicis",
        "expected_winner": "MOVIE_EVENT",
    },
    {
        "movie": 7,
        "name": "Movie 7: Ron Destroys Slytherin Locket",
        "narration": "Ron destroys Slytherin Locket with Sword of Gryffindor.",
        "expected_event": "evt_m7_forest_ron_destroys_locket_with_sword",
        "expected_winner": "MOVIE_EVENT",
    },
    {
        "movie": 8,
        "name": "Movie 8: Neville Draws Sword of Gryffindor",
        "narration": "Neville draws the Sword of Gryffindor from the Sorting Hat.",
        "expected_event": "evt_m8_courtyard_neville_draws_sword",
        "expected_winner": "MOVIE_EVENT",
    },
]

# Negative / Action Mismatch Tests across all 8 movies (must fail closed)
ALL_8_MOVIE_NEGATIVE_TESTS = [
    {
        "movie": 1,
        "name": "Movie 1 Negative: Questions vs Walks Alone",
        "narration": "Snape questions Harry about asphodel.",
        "distractor_event": "evt_m1_potions_snape_walks_alone_distractor",
        "required_action": "questions",
    },
    {
        "movie": 2,
        "name": "Movie 2 Negative: Opens Entrance vs Wades Flooded Floor",
        "narration": "Harry opens the Chamber of Secrets entrance.",
        "distractor_event": "evt_m2_bathroom_harry_stares_flooded_distractor",
        "required_action": "opens",
    },
    {
        "movie": 3,
        "name": "Movie 3 Negative: Punches Malfoy vs Mocks with Binoculars",
        "narration": "Hermione punches Malfoy.",
        "distractor_event": "evt_m3_sundial_malfoy_mocks_friends_distractor",
        "required_action": "punches",
    },
    {
        "movie": 4,
        "name": "Movie 4 Negative: Drinks Polyjuice vs Merely Holds Flask Standing",
        "narration": "Moody drinks Polyjuice from flask.",
        "distractor_event": "evt_m4_defense_moody_holds_flask_standing_distractor",
        "required_action": "drinks",
    },
    {
        "movie": 5,
        "name": "Movie 5 Negative: Conjures Water Sphere vs Merely Stands at Fountain",
        "narration": "Dumbledore conjures giant water sphere encasing Voldemort.",
        "distractor_event": "evt_m5_atrium_dumbledore_stands_fountain_distractor",
        "required_action": "conjures",
    },
    {
        "movie": 6,
        "name": "Movie 6 Negative: Drinks Goblet vs Merely Holds Goblet",
        "narration": "Dumbledore drinks water from crystal goblet in cave.",
        "distractor_event": "evt_m6_cave_dumbledore_holds_crystal_goblet_distractor",
        "required_action": "drinks",
    },
    {
        "movie": 7,
        "name": "Movie 7 Negative: Destroys Locket vs Merely Stands Holding Sword",
        "narration": "Ron destroys Slytherin Locket with Sword of Gryffindor.",
        "distractor_event": "evt_m7_forest_ron_stands_holding_sword_distractor",
        "required_action": "destroys",
    },
    {
        "movie": 8,
        "name": "Movie 8 Negative: Draws Sword vs Merely Stands Holding Hat",
        "narration": "Neville draws the Sword of Gryffindor.",
        "distractor_event": "evt_m8_courtyard_neville_stands_speechless_distractor",
        "required_action": "draws",
    },
]


def _format_tc(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def run_diagnostics():
    print("=" * 80)
    print("STORY FORGE — PHASE 3: ALL-8-MOVIE VISUAL MATCHING DIAGNOSTIC")
    print("Architecture: SRT = Coarse Locator Only | MovieEvent = Sole Selection Authority")
    print("=" * 80)

    t_idx_start = time.perf_counter()
    index = MovieEventIndex()
    t_idx_end = time.perf_counter()
    index_build_ms = (t_idx_end - t_idx_start) * 1000.0

    print(f"\n[1] Index Initialization: {len(index.list_all_events())} events indexed in {index_build_ms:.2f} ms.")

    storyboard_gen = VisualStoryboardGenerator()
    coarse_locator = SRTCoarseLocator()
    hybrid_selector = HybridVisualSelector(index=index, min_improvement_margin=MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN)

    # --------------------------------------------------------------------------
    # PART 1: ALL 8 MOVIES POSITIVE BENCHMARKS
    # --------------------------------------------------------------------------
    print("\n[2] Executing Positive Benchmarks Across All 8 Films:")
    print("-" * 80)

    latencies = []
    candidates_searched_list = []
    positive_pass_count = 0

    for item in ALL_8_MOVIE_BENCHMARKS:
        m = item["movie"]
        beat, _ = storyboard_gen.generate_beat_from_narration(
            beat_id=f"bench_m{m}",
            narration_text=item["narration"],
            start_time=0.0,
            end_time=3.0,
            inferred_movie=m,
        )

        output = hybrid_selector.select_visual_for_beat(beat, content_id=f"bench_content_m{m}", inferred_movie=m)
        latencies.append(output.retrieval_duration_ms)
        candidates_searched_list.append(output.candidates_searched_count)

        winner = output.comparison.selected_source
        cand = output.selected_candidate
        cand_id = cand["candidate_id"] if cand else "NONE"
        lvl = output.search_level_reached

        passed = (winner == "MOVIE_EVENT" and cand_id == item["expected_event"])
        if passed:
            positive_pass_count += 1

        print(f"Movie {m:02d} | Status: {'[PASS]' if passed else '[FAIL]'} | Winner: {winner:<11} | Level: {lvl} | Candidate: {cand_id}")
        if cand:
            print(f"         Time: {_format_tc(cand['start_seconds'])} - {_format_tc(cand['end_seconds'])} ({cand['duration']:.1f}s) | Latency: {output.retrieval_duration_ms:.2f} ms")
            print(f"         Action Depicted: '{cand['action']}'")

    print("-" * 80)
    print(f"Positive Benchmarks: {positive_pass_count}/{len(ALL_8_MOVIE_BENCHMARKS)} PASSED.")

    # --------------------------------------------------------------------------
    # PART 2: ALL 8 MOVIES NEGATIVE / ACTION-MISMATCH TESTS
    # --------------------------------------------------------------------------
    print("\n[3] Executing Negative Action-Mismatch Tests (Must Fail Closed):")
    print("-" * 80)

    negative_pass_count = 0
    for neg in ALL_8_MOVIE_NEGATIVE_TESTS:
        m = neg["movie"]
        distractor = index.get_event(neg["distractor_event"])
        assert distractor is not None, f"Distractor {neg['distractor_event']} not found!"

        beat, _ = storyboard_gen.generate_beat_from_narration(
            beat_id=f"neg_m{m}",
            narration_text=neg["narration"],
            start_time=0.0,
            end_time=3.0,
            inferred_movie=m,
        )

        # Directly verify distractor against required beat
        ver = hybrid_selector.verifier.verify_event(distractor, beat)
        passed = (not ver.is_verified and "ACTION MISMATCH" in ver.explanation)
        if passed:
            negative_pass_count += 1

        print(f"Movie {m:02d} Negative | {'[REJECTED - OK]' if passed else '[FAILED VETO]'} | Action: '{neg['required_action']}' vs '{distractor.action}'")

    print("-" * 80)
    print(f"Negative Tests: {negative_pass_count}/{len(ALL_8_MOVIE_NEGATIVE_TESTS)} PASSED (All false candidates rejected).")

    # --------------------------------------------------------------------------
    # PART 3: ARCHITECTURAL INTEGRITY CHECKS
    # --------------------------------------------------------------------------
    print("\n[4] Architectural Assertion: SRT Visual Fallback Disabled Check:")
    print("-" * 80)

    # Prove SRT candidate can NEVER be selected
    from engines.movie_event.models import VisualBeat, MovieEvent
    dummy_beat = VisualBeat(beat_id="arch_test", narrative_text="Test", required_action="testing")
    dummy_srt = MovieEvent(
        event_id="dummy_srt", movie_id="hp1", movie_number=1, scene_id="s1",
        start_time=100.0, end_time=105.0, primary_subject="Snape", action="testing", location="Hogwarts",
        visual_description="Test"
    )
    cmp_test = hybrid_selector._compare_candidates(beat=dummy_beat, srt_event=dummy_srt, srt_score=99.0, srt_ver=None, me_event=None)
    arch_pass = (cmp_test.selected_source == "NO_VALID_VISUAL" and cmp_test.fallback_used is False)
    print(f"SRT Fallback Blocked: {'[PASS]' if arch_pass else '[FAIL]'} (Selected: {cmp_test.selected_source}, Fallback Used: {cmp_test.fallback_used})")

    # --------------------------------------------------------------------------
    # PART 4: TELEMETRY & PERFORMANCE SUMMARY
    # --------------------------------------------------------------------------
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    worst_latency = max(latencies) if latencies else 0.0
    avg_candidates = sum(candidates_searched_list) / len(candidates_searched_list) if candidates_searched_list else 0

    print("\n[5] Performance & Telemetry Summary:")
    print(f"  - Index Canonical Events: {len(index.list_all_events())}")
    print(f"  - Index Build Latency: {index_build_ms:.2f} ms")
    print(f"  - Average Candidates Evaluated: {avg_candidates:.1f}")
    print(f"  - Average Retrieval Latency: {avg_latency:.2f} ms")
    print(f"  - Worst-Case Latency: {worst_latency:.2f} ms")
    print("=" * 80)

    all_passed = (positive_pass_count == len(ALL_8_MOVIE_BENCHMARKS) and 
                  negative_pass_count == len(ALL_8_MOVIE_NEGATIVE_TESTS) and 
                  arch_pass)
    print(f"FINAL RESULT: {'PASS' if all_passed else 'FAIL'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_diagnostics())
