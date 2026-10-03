"""
STORY FORGE — Phase 4: Deep Visual Search + Candidate Arbitration + Complete Visual EDL Benchmark
===================================================================================================
Executes comprehensive empirical benchmarking across multi-beat locked narrations and real HP movie indices:
  1. Complete Narration Beat Compilation & Contiguous Coverage
  2. 7-Level Deep Visual Search Hierarchy (L1-L7) & Candidate Pooling
  3. Phase 2 Perception & Phase 3 Physical Evidence Filtering (Physical Proof Strictly Dominates)
  4. 9:16 Crop Feasibility Pre-Arbitration Gate (SubjectAwareCompositionEngine)
  5. Multi-Beat Candidate Arbitration & Anti-Loop Enforcement (0 repeated footage, 0 stream loops)
  6. 4+ and 6+ Distinct Footage Segment Multi-Scene Timeline Verification
  7. Cryptographic End-to-End Lineage Integrity
"""

import sys
import time
import json
import psutil
import pathlib
import logging
from typing import Dict, List, Any

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from py_visual_evidence.schema import BoundingBox
from engines.retrieval.models import RetrievalCandidate
from engines.perception.models import (
    EntityTimeline,
    EntityTrack,
    IdentityMatchStatus,
    VisualObject,
)
from engines.action.models import (
    PhysicalActionType,
    ActionEvidenceVerdict,
    VisualActionAssertion,
)
from engines.visual_evidence.subject_aware_composition import SubjectAwareCompositionEngine
from engines.edl.models import (
    LockedNarrationInput,
    WordTimestamp,
    SentenceBoundary,
    VisualBeat,
    CoverageRequirement,
    CoverageState,
    CropFeasibility,
    EvaluatedCandidate,
    EDLEntry,
    VisualEDL,
)
from engines.edl.beat_compiler import VisualBeatCompiler
from engines.edl.concept_expansion import VisualConceptExpander
from engines.edl.deep_search import DeepMovieSearcher
from engines.edl.candidate_evaluator import CandidateEvidenceEvaluator
from engines.edl.arbitration import CandidateArbitrator
from engines.edl.timeline_generator import VisualEDLGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("Phase4EDLBenchmark")


def build_benchmark_narration_hp3() -> LockedNarrationInput:
    """Case 1: 4-segment sequence — The Malfoy Confrontation (HP3)."""
    words = [
        WordTimestamp(word="Hermione", start_sec=0.0, end_sec=0.8),
        WordTimestamp(word="confronted", start_sec=0.8, end_sec=1.5),
        WordTimestamp(word="Draco", start_sec=1.5, end_sec=2.2),
        WordTimestamp(word="near", start_sec=2.2, end_sec=2.6),
        WordTimestamp(word="the", start_sec=2.6, end_sec=2.9),
        WordTimestamp(word="sundial,", start_sec=2.9, end_sec=3.6),
        WordTimestamp(word="raising", start_sec=3.6, end_sec=4.2),
        WordTimestamp(word="her", start_sec=4.2, end_sec=4.5),
        WordTimestamp(word="fist", start_sec=4.5, end_sec=5.0),
        WordTimestamp(word="and", start_sec=5.0, end_sec=5.3),
        WordTimestamp(word="striking", start_sec=5.3, end_sec=6.0),
        WordTimestamp(word="him", start_sec=6.0, end_sec=6.4),
        WordTimestamp(word="across", start_sec=6.4, end_sec=6.9),
        WordTimestamp(word="the", start_sec=6.9, end_sec=7.2),
        WordTimestamp(word="face.", start_sec=7.2, end_sec=7.8),
        WordTimestamp(word="Malfoy", start_sec=7.8, end_sec=8.5),
        WordTimestamp(word="collapsed", start_sec=8.5, end_sec=9.3),
        WordTimestamp(word="backward,", start_sec=9.3, end_sec=10.0),
        WordTimestamp(word="scrambling", start_sec=10.0, end_sec=10.8),
        WordTimestamp(word="away", start_sec=10.8, end_sec=11.3),
        WordTimestamp(word="in", start_sec=11.3, end_sec=11.6),
        WordTimestamp(word="sheer", start_sec=11.6, end_sec=12.1),
        WordTimestamp(word="terror.", start_sec=12.1, end_sec=13.0),
        WordTimestamp(word="Ron", start_sec=13.0, end_sec=13.6),
        WordTimestamp(word="and", start_sec=13.6, end_sec=13.9),
        WordTimestamp(word="Harry", start_sec=13.9, end_sec=14.5),
        WordTimestamp(word="watched", start_sec=14.5, end_sec=15.1),
        WordTimestamp(word="in", start_sec=15.1, end_sec=15.4),
        WordTimestamp(word="absolute", start_sec=15.4, end_sec=16.0),
        WordTimestamp(word="astonishment.", start_sec=16.0, end_sec=17.0),
    ]
    sentences = [
        SentenceBoundary(
            sentence_index=0,
            text="Hermione confronted Draco near the sundial, raising her fist and striking him across the face.",
            start_sec=0.0,
            end_sec=7.8,
            word_start_idx=0,
            word_end_idx=14,
        ),
        SentenceBoundary(
            sentence_index=1,
            text="Malfoy collapsed backward, scrambling away in sheer terror.",
            start_sec=7.8,
            end_sec=13.0,
            word_start_idx=15,
            word_end_idx=22,
        ),
        SentenceBoundary(
            sentence_index=2,
            text="Ron and Harry watched in absolute astonishment.",
            start_sec=13.0,
            end_sec=17.0,
            word_start_idx=23,
            word_end_idx=29,
        ),
    ]
    editorial = [
        {"beat_id": "b1_standoff", "start_sec": 0.0, "end_sec": 3.6, "text": "Hermione confronted Draco near sundial", "coverage": "DIRECT", "required_entities": ["Hermione Granger", "Draco Malfoy"]},
        {"beat_id": "b2_punch", "start_sec": 3.6, "end_sec": 7.8, "text": "Hermione punches Draco Malfoy in face", "coverage": "DIRECT", "required_entities": ["Hermione Granger", "Draco Malfoy"], "required_action": "PUNCH"},
        {"beat_id": "b3_recoil", "start_sec": 7.8, "end_sec": 13.0, "text": "Draco Malfoy falls backward and runs", "coverage": "DIRECT", "required_entities": ["Draco Malfoy"], "required_action": "FALL"},
        {"beat_id": "b4_reaction", "start_sec": 13.0, "end_sec": 17.0, "text": "Harry Potter and Ron Weasley watch shocked", "coverage": "DIRECT", "required_entities": ["Harry Potter", "Ron Weasley"]},
    ]
    return LockedNarrationInput(
        content_id="bench_narration_hp3_punch",
        script_hash="h3_script_c7d91a",
        narration_hash="h3_audio_f82e04",
        exact_narration_duration=17.0,
        word_timestamps=words,
        sentence_boundaries=sentences,
        narration_text="Hermione confronted Draco near the sundial, raising her fist and striking him across the face. Malfoy collapsed backward, scrambling away in sheer terror. Ron and Harry watched in absolute astonishment.",
        editorial_beat_boundaries=editorial,
    )


def build_benchmark_narration_hp8() -> LockedNarrationInput:
    """Case 2: 6-segment sequence — The Fate of the Elder Wand (HP8)."""
    words = [
        WordTimestamp(word="Standing", start_sec=0.0, end_sec=0.7),
        WordTimestamp(word="upon", start_sec=0.7, end_sec=1.1),
        WordTimestamp(word="the", start_sec=1.1, end_sec=1.3),
        WordTimestamp(word="shattered", start_sec=1.3, end_sec=1.9),
        WordTimestamp(word="viaduct,", start_sec=1.9, end_sec=2.6),
        WordTimestamp(word="Harry", start_sec=2.6, end_sec=3.2),
        WordTimestamp(word="held", start_sec=3.2, end_sec=3.7),
        WordTimestamp(word="the", start_sec=3.7, end_sec=3.9),
        WordTimestamp(word="legendary", start_sec=3.9, end_sec=4.6),
        WordTimestamp(word="Elder", start_sec=4.6, end_sec=5.0),
        WordTimestamp(word="Wand.", start_sec=5.0, end_sec=5.6),
        WordTimestamp(word="Beside", start_sec=5.6, end_sec=6.1),
        WordTimestamp(word="him,", start_sec=6.1, end_sec=6.5),
        WordTimestamp(word="Ron", start_sec=6.5, end_sec=7.0),
        WordTimestamp(word="and", start_sec=7.0, end_sec=7.3),
        WordTimestamp(word="Hermione", start_sec=7.3, end_sec=8.0),
        WordTimestamp(word="waited", start_sec=8.0, end_sec=8.6),
        WordTimestamp(word="in", start_sec=8.6, end_sec=8.9),
        WordTimestamp(word="reverent", start_sec=8.9, end_sec=9.5),
        WordTimestamp(word="silence.", start_sec=9.5, end_sec=10.2),
        WordTimestamp(word="With", start_sec=10.2, end_sec=10.6),
        WordTimestamp(word="both", start_sec=10.6, end_sec=11.0),
        WordTimestamp(word="hands,", start_sec=11.0, end_sec=11.6),
        WordTimestamp(word="he", start_sec=11.6, end_sec=11.9),
        WordTimestamp(word="gripped", start_sec=11.9, end_sec=12.5),
        WordTimestamp(word="the", start_sec=12.5, end_sec=12.8),
        WordTimestamp(word="unbeatable", start_sec=12.8, end_sec=13.6),
        WordTimestamp(word="relic.", start_sec=13.6, end_sec=14.3),
        WordTimestamp(word="Suddenly,", start_sec=14.3, end_sec=15.0),
        WordTimestamp(word="he", start_sec=15.0, end_sec=15.3),
        WordTimestamp(word="snapped", start_sec=15.3, end_sec=16.0),
        WordTimestamp(word="it", start_sec=16.0, end_sec=16.3),
        WordTimestamp(word="cleanly", start_sec=16.3, end_sec=16.9),
        WordTimestamp(word="in", start_sec=16.9, end_sec=17.2),
        WordTimestamp(word="two.", start_sec=17.2, end_sec=17.8),
        WordTimestamp(word="He", start_sec=17.8, end_sec=18.1),
        WordTimestamp(word="cast", start_sec=18.1, end_sec=18.6),
        WordTimestamp(word="the", start_sec=18.6, end_sec=18.9),
        WordTimestamp(word="broken", start_sec=18.9, end_sec=19.5),
        WordTimestamp(word="halves", start_sec=19.5, end_sec=20.1),
        WordTimestamp(word="into", start_sec=20.1, end_sec=20.5),
        WordTimestamp(word="the", start_sec=20.5, end_sec=20.8),
        WordTimestamp(word="abyss,", start_sec=20.8, end_sec=21.5),
        WordTimestamp(word="watching", start_sec=21.5, end_sec=22.2),
        WordTimestamp(word="them", start_sec=22.2, end_sec=22.6),
        WordTimestamp(word="plummet", start_sec=22.6, end_sec=23.3),
        WordTimestamp(word="into", start_sec=23.3, end_sec=23.7),
        WordTimestamp(word="the", start_sec=23.7, end_sec=24.0),
        WordTimestamp(word="mist", start_sec=24.0, end_sec=24.5),
        WordTimestamp(word="below.", start_sec=24.5, end_sec=25.2),
    ]
    sentences = [
        SentenceBoundary(sentence_index=0, text="Standing upon the shattered viaduct, Harry held the legendary Elder Wand.", start_sec=0.0, end_sec=5.6, word_start_idx=0, word_end_idx=10),
        SentenceBoundary(sentence_index=1, text="Beside him, Ron and Hermione waited in reverent silence.", start_sec=5.6, end_sec=10.2, word_start_idx=11, word_end_idx=19),
        SentenceBoundary(sentence_index=2, text="With both hands, he gripped the unbeatable relic.", start_sec=10.2, end_sec=14.3, word_start_idx=20, word_end_idx=27),
        SentenceBoundary(sentence_index=3, text="Suddenly, he snapped it cleanly in two.", start_sec=14.3, end_sec=17.8, word_start_idx=28, word_end_idx=34),
        SentenceBoundary(sentence_index=4, text="He cast the broken halves into the abyss,", start_sec=17.8, end_sec=21.5, word_start_idx=35, word_end_idx=42),
        SentenceBoundary(sentence_index=5, text="watching them plummet into the mist below.", start_sec=21.5, end_sec=25.2, word_start_idx=43, word_end_idx=49),
    ]
    editorial = [
        {"beat_id": "b1_bridge", "start_sec": 0.0, "end_sec": 5.6, "text": "Harry Potter holds Elder Wand on bridge", "coverage": "DIRECT", "required_entities": ["Harry Potter"], "required_objects": ["elder_wand"]},
        {"beat_id": "b2_friends", "start_sec": 5.6, "end_sec": 10.2, "text": "Ron Weasley and Hermione Granger stand watching", "coverage": "DIRECT", "required_entities": ["Ron Weasley", "Hermione Granger"]},
        {"beat_id": "b3_grip", "start_sec": 10.2, "end_sec": 14.3, "text": "Harry Potter grips wand with both hands", "coverage": "DIRECT", "required_entities": ["Harry Potter"], "required_objects": ["elder_wand"], "required_action": "HOLD"},
        {"beat_id": "b4_snap", "start_sec": 14.3, "end_sec": 17.8, "text": "Harry Potter snaps elder wand in two", "coverage": "DIRECT", "required_entities": ["Harry Potter"], "required_objects": ["elder_wand"], "required_action": "BREAK"},
        {"beat_id": "b5_throw", "start_sec": 17.8, "end_sec": 21.5, "text": "Harry Potter throws broken wand halves", "coverage": "DIRECT", "required_entities": ["Harry Potter"], "required_objects": ["elder_wand"], "required_action": "THROW"},
        {"beat_id": "b6_fall", "start_sec": 21.5, "end_sec": 25.2, "text": "Wand pieces fall down into gorge", "coverage": "DIRECT", "required_objects": ["wand"], "required_action": "FALL"},
    ]
    return LockedNarrationInput(
        content_id="bench_narration_hp8_wand",
        script_hash="h8_script_7e1c8b",
        narration_hash="h8_audio_9a3d42",
        exact_narration_duration=25.2,
        word_timestamps=words,
        sentence_boundaries=sentences,
        narration_text="Standing upon the shattered viaduct, Harry held the legendary Elder Wand. Beside him, Ron and Hermione waited in reverent silence. With both hands, he gripped the unbeatable relic. Suddenly, he snapped it cleanly in two. He cast the broken halves into the abyss, watching them plummet into the mist below.",
        editorial_beat_boundaries=editorial,
    )


def run_benchmarks() -> Dict[str, Any]:
    process = psutil.Process()
    mem_before = process.memory_info().rss / (1024 * 1024)
    start_total_time = time.perf_counter()

    generator = VisualEDLGenerator()
    results = {}

    # Benchmark 1: HP3 Malfoy Confrontation (4+ Segments)
    logger.info("Executing Benchmark 1: HP3 Malfoy Confrontation...")
    narr_hp3 = build_benchmark_narration_hp3()
    t0 = time.perf_counter()
    edl_hp3 = generator.generate_edl(narr_hp3, target_movie_id=3)
    t_hp3 = time.perf_counter() - t0

    unique_intervals_hp3 = len({(e.source_movie_id, e.source_clip_start, e.source_clip_end) for e in edl_hp3.entries if e.coverage_state != CoverageState.UNFULFILLED})

    results["benchmark_1_hp3_punch"] = {
        "content_id": edl_hp3.content_id,
        "edl_id": edl_hp3.edl_id,
        "total_narration_duration": edl_hp3.total_narration_duration,
        "total_beats": len(edl_hp3.entries),
        "directly_covered_duration": edl_hp3.directly_covered_duration,
        "optional_duration": edl_hp3.optional_duration,
        "unfulfilled_duration": edl_hp3.unfulfilled_duration,
        "coverage_percentage": edl_hp3.coverage_percentage,
        "unique_footage_intervals": unique_intervals_hp3,
        "stream_loops_detected": edl_hp3.anti_loop_audit.stream_loops_detected,
        "repeated_source_count": edl_hp3.anti_loop_audit.repeated_source_count,
        "anti_loop_passed": edl_hp3.anti_loop_audit.passed,
        "is_complete": edl_hp3.is_complete,
        "lineage_valid": edl_hp3.lineage.is_valid(),
        "edl_hash": edl_hp3.lineage.edl_hash,
        "latency_sec": round(t_hp3, 3),
        "entries": [e.model_dump(mode="json") for e in edl_hp3.entries],
    }

    # Benchmark 2: HP8 Elder Wand Snap & Throw (6+ Segments)
    logger.info("Executing Benchmark 2: HP8 Elder Wand Snap (6+ Segments)...")
    narr_hp8 = build_benchmark_narration_hp8()
    t0 = time.perf_counter()
    edl_hp8 = generator.generate_edl(narr_hp8, target_movie_id=8)
    t_hp8 = time.perf_counter() - t0

    unique_intervals_hp8 = len({(e.source_movie_id, e.source_clip_start, e.source_clip_end) for e in edl_hp8.entries if e.coverage_state != CoverageState.UNFULFILLED})

    results["benchmark_2_hp8_wand"] = {
        "content_id": edl_hp8.content_id,
        "edl_id": edl_hp8.edl_id,
        "total_narration_duration": edl_hp8.total_narration_duration,
        "total_beats": len(edl_hp8.entries),
        "directly_covered_duration": edl_hp8.directly_covered_duration,
        "optional_duration": edl_hp8.optional_duration,
        "unfulfilled_duration": edl_hp8.unfulfilled_duration,
        "coverage_percentage": edl_hp8.coverage_percentage,
        "unique_footage_intervals": unique_intervals_hp8,
        "stream_loops_detected": edl_hp8.anti_loop_audit.stream_loops_detected,
        "repeated_source_count": edl_hp8.anti_loop_audit.repeated_source_count,
        "anti_loop_passed": edl_hp8.anti_loop_audit.passed,
        "is_complete": edl_hp8.is_complete,
        "lineage_valid": edl_hp8.lineage.is_valid(),
        "edl_hash": edl_hp8.lineage.edl_hash,
        "latency_sec": round(t_hp8, 3),
        "entries": [e.model_dump(mode="json") for e in edl_hp8.entries],
    }

    # Benchmark 3: Adversarial Loop Attempt
    logger.info("Executing Benchmark 3: Adversarial Loop Injection Test...")
    arbitrator = CandidateArbitrator()
    b1 = VisualBeat(beat_id="b1", narration_start=0.0, narration_end=3.0, text_span="Action 1", visual_assertion="Action 1", required_entities=["Harry Potter"])
    b2 = VisualBeat(beat_id="b2", narration_start=3.0, narration_end=6.0, text_span="Action 2", visual_assertion="Action 2", required_entities=["Ron Weasley"])
    b3 = VisualBeat(beat_id="b3", narration_start=6.0, narration_end=9.0, text_span="Action 3", visual_assertion="Action 3", required_entities=["Hermione Granger"])

    cand_duplicate = EvaluatedCandidate(
        candidate_id="c_dupe",
        beat_id="b1",
        source_movie_id=3,
        source_video="m3.mp4",
        source_interval=(50.0, 55.0),
        verified_sub_interval=(50.0, 55.0),
        overall_arbitration_score=0.95,
        is_physical_verified=True,
        evidence_hash="hash_dupe_123",
    )
    cand_alt_2 = EvaluatedCandidate(
        candidate_id="c_alt_2",
        beat_id="b2",
        source_movie_id=3,
        source_video="m3.mp4",
        source_interval=(120.0, 125.0),
        verified_sub_interval=(120.0, 125.0),
        overall_arbitration_score=0.88,
        is_physical_verified=True,
        evidence_hash="hash_alt_2",
    )
    cand_alt_3 = EvaluatedCandidate(
        candidate_id="c_alt_3",
        beat_id="b3",
        source_movie_id=3,
        source_video="m3.mp4",
        source_interval=(240.0, 245.0),
        verified_sub_interval=(240.0, 245.0),
        overall_arbitration_score=0.85,
        is_physical_verified=True,
        evidence_hash="hash_alt_3",
    )

    # Offer candidate c_dupe to all three beats to tempt a loop
    eval_cands = {
        "b1": [cand_duplicate],
        "b2": [cand_duplicate, cand_alt_2],
        "b3": [cand_duplicate, cand_alt_3],
    }
    entries_loop, audit_loop = arbitrator.arbitrate_timeline([b1, b2, b3], eval_cands)

    results["benchmark_3_anti_loop_adversarial"] = {
        "loop_injection_attempted": True,
        "audit_passed": audit_loop.passed,
        "stream_loops_detected": audit_loop.stream_loops_detected,
        "repeated_source_count": audit_loop.repeated_source_count,
        "total_entries": len(entries_loop),
        "selected_candidate_ids": [e.evidence_id for e in entries_loop],
        "loop_defeated": (entries_loop[1].evidence_id == "c_alt_2" and entries_loop[2].evidence_id == "c_alt_3"),
    }

    # Benchmark 4: 9:16 Crop Feasibility Stress Gate
    logger.info("Executing Benchmark 4: 9:16 Crop Feasibility Stress Gate...")
    evaluator = CandidateEvidenceEvaluator()
    cand_wide = RetrievalCandidate(candidate_id="c_wide", movie_id="3", start=10.0, end=15.0, source="TEST", retrieval_score=0.90)
    beat_standoff = VisualBeat(beat_id="b_wide", narration_start=0.0, narration_end=3.0, text_span="Wide confrontation", visual_assertion="Hermione and Draco standoff", required_entities=["Hermione Granger", "Draco Malfoy"])

    # Impossible wide separation: x=0.05 and x=0.92
    box_far_l = BoundingBox(x=0.05, y=0.3, w=0.1, h=0.4)
    box_far_r = BoundingBox(x=0.92, y=0.3, w=0.1, h=0.4)
    res_impossible = evaluator.evaluate_candidate(cand_wide, beat_standoff, subject_bboxes=[box_far_l, box_far_r], is_two_shot=True)

    # Feasible two-shot: x=0.35 and x=0.55
    box_close_l = BoundingBox(x=0.35, y=0.3, w=0.1, h=0.4)
    box_close_r = BoundingBox(x=0.55, y=0.3, w=0.1, h=0.4)
    res_feasible = evaluator.evaluate_candidate(cand_wide, beat_standoff, subject_bboxes=[box_close_l, box_close_r], is_two_shot=True)

    results["benchmark_4_crop_feasibility_gate"] = {
        "impossible_wide_case": {
            "crop_feasibility": res_impossible.crop_feasibility.value,
            "is_rejected": res_impossible.is_rejected,
            "rejection_reason": res_impossible.rejection_reason,
        },
        "feasible_compact_case": {
            "crop_feasibility": res_feasible.crop_feasibility.value,
            "is_rejected": res_feasible.is_rejected,
            "crop_window": res_feasible.crop_window,
            "overall_score": res_feasible.overall_arbitration_score,
        },
    }

    # Summary Statistics
    total_time = time.perf_counter() - start_total_time
    mem_after = process.memory_info().rss / (1024 * 1024)

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_benchmark_time_sec": round(total_time, 3),
        "peak_ram_mb": round(mem_after, 2),
        "ram_delta_mb": round(mem_after - mem_before, 2),
        "benchmarks_executed": len(results),
        "all_anti_loop_verified": all([
            results["benchmark_1_hp3_punch"]["anti_loop_passed"],
            results["benchmark_2_hp8_wand"]["anti_loop_passed"],
            results["benchmark_3_anti_loop_adversarial"]["audit_passed"],
        ]),
        "total_edl_entries_generated": len(edl_hp3.entries) + len(edl_hp8.entries),
        "detailed_results": results,
    }

    # Save benchmark report to reports/phase4_visual_search_timeline_benchmark.json
    out_path = PROJECT_ROOT / "reports" / "phase4_visual_search_timeline_benchmark.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Phase 4 benchmark successfully written to %s", out_path)
    return summary


if __name__ == "__main__":
    summary = run_benchmarks()
    print("\n================ PHASE 4 BENCHMARK SUMMARY ================")
    print(f"Total Time: {summary['total_benchmark_time_sec']}s")
    print(f"Memory: {summary['peak_ram_mb']} MB (delta: {summary['ram_delta_mb']} MB)")
    print(f"Anti-Loop Audit: {'ALL PASSED (0 Loops)' if summary['all_anti_loop_verified'] else 'FAILED'}")
    print(f"Entries Generated: {summary['total_edl_entries_generated']}")
    print("===========================================================")
