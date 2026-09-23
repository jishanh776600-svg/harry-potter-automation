"""
STORY FORGE — BEAST Visual Retrieval Benchmark Suite
================================================================================
Evaluates the BEAST Visual Matching Engine across 5 canonical retrieval challenges:
  1. Neville + Sorting Hat (Pleading/arguing on stool in Great Hall)
  2. Harry + Mirror of Erised (Quiet observation in abandoned classroom)
  3. Snape + Potion / Riddle Chamber (Menacing presence in dungeon)
  4. Neville + Sword of Gryffindor (Year 7 Climax: Slaying Nagini in battle ruins)
  5. Hermione + Classroom Raising Hand (Answering question eagerly)

For each benchmark case, reports:
  - Selected Top Candidate
  - Exact Source Timestamps [Start, End]
  - Semantic Similarity Score
  - Character & Secondary Character Scores
  - Action Score
  - Object Score
  - Location Score
  - Temporal Coherence Score
  - VLM Verification Score
  - Final Composite Score
  - Disqualification / Rejection Reasons for rejected candidates
"""

import sys
import json
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.beast_visual_types import (
    BeastVisualRequirement,
    BeastCandidateShot,
    NarrativeEra,
)
from core.composition_models import ShotScale, NormalizedBBox, ShotCompositionAssessment
from core.storyboard_types import VisualRole
from engines.beast_visual_matching_engine import BeastVisualMatchingEngine

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def build_benchmark_candidate_pool() -> list[BeastCandidateShot]:
    """Constructs a comprehensive, diverse pool of candidate shots with hard negatives."""
    return [
        # Shot 1: Neville Year 1 Sorting Hat (Target for Case 1)
        BeastCandidateShot(
            shot_id="shot_01_neville_sorting_hat_stool",
            source_video="data/movies/Harry_Potter_1.mkv",
            movie_number=1,
            start_seconds=2568.5,
            end_seconds=2574.0,
            duration=5.5,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Neville Longbottom sits trembling on the wooden stool in the Great Hall, desperately arguing and begging the Sorting Hat on his head.",
            characters_present=["Neville Longbottom", "Sorting Hat"],
            detected_faces=1,
            primary_character_prominence=0.38,
            objects_present=["Sorting Hat", "Stool"],
            actions_depicted=["pleading", "sitting on stool", "arguing"],
            environment="Great Hall",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
        # Shot 2: Neville Year 7 Battle with Sword (Hard Negative for Case 1, Target for Case 4)
        BeastCandidateShot(
            shot_id="shot_02_neville_battle_sword_nagini",
            source_video="data/movies/Harry_Potter_8.mkv",
            movie_number=8,
            start_seconds=6168.0,
            end_seconds=6173.0,
            duration=5.0,
            narrative_era=NarrativeEra.YEAR_7,
            scene_description="Neville Longbottom, bloodied and standing in the ruined Hogwarts courtyard during the final battle, draws the Sword of Gryffindor to strike and slay Nagini.",
            characters_present=["Neville Longbottom", "Nagini", "Sorting Hat"],
            detected_faces=1,
            primary_character_prominence=0.45,
            objects_present=["Sword of Gryffindor", "Sorting Hat", "Horcrux"],
            actions_depicted=["drawing sword", "striking", "fighting", "slaying"],
            environment="Hogwarts Courtyard",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
        # Shot 3: Harry staring into Mirror of Erised (Target for Case 2)
        BeastCandidateShot(
            shot_id="shot_03_harry_mirror_of_erised",
            source_video="data/movies/Harry_Potter_1.mkv",
            movie_number=1,
            start_seconds=4200.0,
            end_seconds=4206.5,
            duration=6.5,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Harry Potter stands mesmerized before the ornate gold Mirror of Erised, staring at his parents' loving reflection.",
            characters_present=["Harry Potter"],
            detected_faces=1,
            primary_character_prominence=0.32,
            objects_present=["Mirror of Erised"],
            actions_depicted=["staring", "looking into mirror", "smiling"],
            environment="Abandoned Classroom",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
        # Shot 4: Harry running in corridor (Hard Negative for Case 2)
        BeastCandidateShot(
            shot_id="shot_04_harry_running_corridor",
            source_video="data/movies/Harry_Potter_1.mkv",
            movie_number=1,
            start_seconds=3100.0,
            end_seconds=3104.0,
            duration=4.0,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Harry Potter sprints through a dark stone hallway escaping Filch and Mrs Norris.",
            characters_present=["Harry Potter"],
            detected_faces=1,
            primary_character_prominence=0.22,
            objects_present=[],
            actions_depicted=["running", "fleeing"],
            environment="Hogwarts Corridor",
            shot_scale=ShotScale.MEDIUM_WIDE,
        ),
        # Shot 5: Snape in Potions Dungeon (Target for Case 3)
        BeastCandidateShot(
            shot_id="shot_05_snape_potions_dungeon",
            source_video="data/movies/Harry_Potter_1.mkv",
            movie_number=1,
            start_seconds=1800.0,
            end_seconds=1805.5,
            duration=5.5,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Severus Snape glares with dark eyes in the shadowy dungeon classroom, surrounded by steaming cauldrons, pickled specimens, and bubbling potions.",
            characters_present=["Severus Snape"],
            detected_faces=1,
            primary_character_prominence=0.48,
            objects_present=["Potion", "Cauldron"],
            actions_depicted=["standing", "glaring", "intimidating"],
            environment="Dungeons",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
        # Shot 6: Snape outdoors on Quidditch pitch (Hard Negative for Case 3)
        BeastCandidateShot(
            shot_id="shot_06_snape_quidditch_stands",
            source_video="data/movies/Harry_Potter_1.mkv",
            movie_number=1,
            start_seconds=5400.0,
            end_seconds=5403.5,
            duration=3.5,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Severus Snape mutters a counter-curse while sitting high in the open-air wooden Quidditch spectator towers during a match.",
            characters_present=["Severus Snape"],
            detected_faces=1,
            primary_character_prominence=0.35,
            objects_present=["Wand"],
            actions_depicted=["sitting", "whispering", "counter-curse"],
            environment="Quidditch Pitch",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
        # Shot 7: Hermione raising hand in classroom (Target for Case 5)
        BeastCandidateShot(
            shot_id="shot_07_hermione_raising_hand_charms",
            source_video="data/movies/Harry_Potter_1.mkv",
            movie_number=1,
            start_seconds=2910.0,
            end_seconds=2914.5,
            duration=4.5,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Hermione Granger eagerly shoots her hand straight into the air in Flitwick's charms class, desperate to recite the spell formula.",
            characters_present=["Hermione Granger"],
            detected_faces=1,
            primary_character_prominence=0.40,
            objects_present=["Wand", "Feather", "Book"],
            actions_depicted=["raising hand", "answering", "volunteer"],
            environment="Charms Classroom",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
        # Shot 8: Hermione crying in girls bathroom (Hard Negative for Case 5)
        BeastCandidateShot(
            shot_id="shot_08_hermione_bathroom_crying",
            source_video="data/movies/Harry_Potter_1.mkv",
            movie_number=1,
            start_seconds=4850.0,
            end_seconds=4854.0,
            duration=4.0,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Hermione Granger weeps in the cubicle of the stone girls bathroom before the mountain troll attacks.",
            characters_present=["Hermione Granger"],
            detected_faces=1,
            primary_character_prominence=0.30,
            objects_present=[],
            actions_depicted=["crying", "weeping", "hiding"],
            environment="Girls Bathroom",
            shot_scale=ShotScale.MEDIUM_SHOT,
        ),
        # Shot 9: Ron staring in disbelief (Target for Case 5 reaction)
        BeastCandidateShot(
            shot_id="shot_09_ron_bewildered_reaction",
            source_video="data/movies/Harry_Potter_1.mkv",
            movie_number=1,
            start_seconds=2920.0,
            end_seconds=2923.5,
            duration=3.5,
            narrative_era=NarrativeEra.YEAR_1,
            scene_description="Ron Weasley looks with utter disbelief and annoyance at Hermione's perfect spellwork, jaw slightly open.",
            characters_present=["Ron Weasley"],
            detected_faces=1,
            primary_character_prominence=0.45,
            objects_present=["Wand"],
            actions_depicted=["staring", "reacting", "annoyed"],
            environment="Charms Classroom",
            shot_scale=ShotScale.CLOSE_UP,
        ),
    ]


def run_benchmark():
    print("=" * 80)
    print("STORY FORGE — BEAST VISUAL RETRIEVAL BENCHMARK")
    print("=" * 80)

    pool = build_benchmark_candidate_pool()
    engine = BeastVisualMatchingEngine(min_confidence_threshold=65.0)

    benchmark_cases = [
        {
            "case_id": "CASE_1",
            "name": "Neville Begging the Sorting Hat (Year 1)",
            "narration": "Terrified by family expectations, eleven-year-old Neville begged the Sorting Hat on the stool to place him in Hufflepuff.",
            "expected_shot": "shot_01_neville_sorting_hat_stool",
            "unwanted_shot": "shot_02_neville_battle_sword_nagini",
            "role": VisualRole.DIRECT_EVIDENCE,
            "target_dur": 2.5,
        },
        {
            "case_id": "CASE_2",
            "name": "Harry Looking Into the Mirror of Erised (Year 1)",
            "narration": "Harry stood frozen in the abandoned chamber, gazing lovingly at his parents inside the Mirror of Erised.",
            "expected_shot": "shot_03_harry_mirror_of_erised",
            "unwanted_shot": "shot_04_harry_running_corridor",
            "role": VisualRole.DIRECT_EVIDENCE,
            "target_dur": 2.2,
        },
        {
            "case_id": "CASE_3",
            "name": "Snape in the Subterranean Potions Dungeon (Year 1)",
            "narration": "Severus Snape loomed silently among simmering cauldrons and dark potion vials in the Hogwarts dungeon.",
            "expected_shot": "shot_05_snape_potions_dungeon",
            "unwanted_shot": "shot_06_snape_quidditch_stands",
            "role": VisualRole.DIRECT_EVIDENCE,
            "target_dur": 2.0,
        },
        {
            "case_id": "CASE_4",
            "name": "Neville Slaying Nagini With Gryffindor's Sword (Year 7 Climax)",
            "narration": "Seven years later in the ruined battle courtyard, Neville drew Godric's silver sword from the Hat to strike Nagini down.",
            "expected_shot": "shot_02_neville_battle_sword_nagini",
            "unwanted_shot": "shot_01_neville_sorting_hat_stool",
            "role": VisualRole.DIRECT_EVIDENCE,
            "target_dur": 2.8,
        },
        {
            "case_id": "CASE_5",
            "name": "Hermione Eagerly Raising Her Hand in Charms (Year 1)",
            "narration": "Hermione Granger raised her hand with fierce urgency, desperate to answer Professor Flitwick's question.",
            "expected_shot": "shot_07_hermione_raising_hand_charms",
            "unwanted_shot": "shot_08_hermione_bathroom_crying",
            "role": VisualRole.DIRECT_EVIDENCE,
            "target_dur": 1.8,
        },
    ]

    all_passed = True
    results_summary = []

    for c in benchmark_cases:
        print(f"\n--- {c['case_id']}: {c['name']} ---")
        print(f"Narration: \"{c['narration']}\"")
        req = engine.parse_narration_beat(
            beat_id=c["case_id"].lower(),
            narration_text=c["narration"],
            visual_role=c["role"],
            target_duration=c["target_dur"],
        )

        match_res = engine.find_best_visual_match(
            requirement=req,
            candidate_pool=pool,
            target_duration=c["target_dur"],
            enable_vlm_gate=True,
        )

        if not match_res:
            print("  ❌ RESULT: NO_VALID_VISUAL returned (Fail closed)")
            all_passed = False
            continue

        best_shot, bd = match_res
        is_correct = (best_shot.shot_id == c["expected_shot"])
        status_sym = "[PASS]" if is_correct else "[FAIL]"
        if not is_correct:
            all_passed = False

        print(f"  {status_sym} Selected: {best_shot.shot_id} (Expected: {c['expected_shot']})")
        print(f"  Source Interval    : [{bd.extracted_interval[0]:.2f}s - {bd.extracted_interval[1]:.2f}s] ({c['target_dur']:.2f}s)")
        print(f"  Semantic Similarity: {bd.semantic_similarity:.1f}%")
        print(f"  Character Score    : Primary={bd.character_score:.1f}% | Secondary={bd.secondary_character_score:.1f}%")
        print(f"  Action Score       : {bd.action_score:.1f}%")
        print(f"  Object Score       : {bd.object_score:.1f}%")
        print(f"  Location Score     : {bd.location_score:.1f}%")
        print(f"  Temporal Coherence : {bd.temporal_coherence:.1f}%")
        print(f"  VLM Verification   : {bd.vlm_score:.1f}% (Verdict Match: {bd.vlm_verdict.match if bd.vlm_verdict else 'N/A'})")
        print(f"  Contradiction Pen. : {bd.contradiction_penalty:.1f}")
        print(f"  Final Score        : {bd.final_score:.1f}% (Acceptable: {bd.is_acceptable})")

        # Evaluate what happened to the unwanted hard negative
        unwanted_shot = next((s for s in pool if s.shot_id == c["unwanted_shot"]), None)
        if unwanted_shot:
            guard = engine.contradiction_guard
            has_contra, pen, reasons = guard.evaluate_contradiction(req, unwanted_shot)
            print(f"  Hard Negative Guard: '{c['unwanted_shot']}' Contradiction={has_contra} (Penalty={pen:.1f})")
            if reasons:
                print(f"    -> Rejection Reason: {'; '.join(reasons)}")

        results_summary.append({
            "case_id": c["case_id"],
            "name": c["name"],
            "selected_shot": best_shot.shot_id,
            "expected_shot": c["expected_shot"],
            "final_score": bd.final_score,
            "is_correct": is_correct,
        })

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    for r in results_summary:
        sym = "[PASS]" if r["is_correct"] else "[FAIL]"
        print(f"  {r['case_id']}: {sym:7s} | Selected: {r['selected_shot']:35s} | Score: {r['final_score']:.1f}%")

    print(f"\nOverall Benchmark Result: {'ALL 5 CASES PASSED' if all_passed else 'SOME CASES FAILED'}")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_benchmark())
