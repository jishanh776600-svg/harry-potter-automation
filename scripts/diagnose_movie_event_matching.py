"""
STORY FORGE — Movie Event Visual Matching Diagnostic CLI Tool (V2)
==================================================================
Runs offline diagnostic evaluations for visual queries without triggering any video rendering,
production builds, or YouTube uploads.

Benchmark Test Queries:
  1. "Snape questions Harry in Potions classroom."
  2. "Neville draws the Sword of Gryffindor."
  3. "Harry opens the Chamber of Secrets entrance."
  4. "Hermione punches Malfoy."
"""

import sys
import argparse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engines.movie_event import (
    MovieEventIndex,
    MovieEventRetrievalEngine,
    MovieEventVisualVerifier,
    VisualStoryboardGenerator,
    ClaimTransformer,
    MovieEventQuery,
    VerificationStatus,
)

BENCHMARK_QUERIES = [
    {
        "id": "QUERY_1",
        "query_text": "Snape questions Harry in Potions classroom.",
        "expected_movie": 1,
        "expected_action": "questions and confronts Harry directly",
    },
    {
        "id": "QUERY_2",
        "query_text": "Neville draws the Sword of Gryffindor.",
        "expected_movie": 8,
        "expected_action": "draws the Sword of Gryffindor from Sorting Hat",
    },
    {
        "id": "QUERY_3",
        "query_text": "Harry opens the Chamber of Secrets entrance.",
        "expected_movie": 2,
        "expected_action": "speaks Parseltongue and opens Chamber entrance",
    },
    {
        "id": "QUERY_4",
        "query_text": "Hermione punches Malfoy.",
        "expected_movie": 3,
        "expected_action": "punches Malfoy squarely in the face",
    },
]


def run_single_query_diagnostic(
    query_id: str,
    query_text: str,
    index: MovieEventIndex,
    retrieval_engine: MovieEventRetrievalEngine,
    verifier: MovieEventVisualVerifier,
    storyboard_gen: VisualStoryboardGenerator,
):
    print("=" * 80)
    print(f"[{query_id}] EVALUATING QUERY: \"{query_text}\"")
    print("=" * 80)

    # 1. Abstract vs Visualizable Analysis
    beat, classification = storyboard_gen.generate_beat_from_narration(
        beat_id=f"beat_{query_id.lower()}",
        narration_text=query_text,
        start_time=0.0,
        end_time=3.0,
    )
    print(f"-> Claim Type:        {classification.classification.value}")
    print(f"-> Is Visualizable:   {classification.is_directly_visualizable}")
    print(f"-> Required Action:   {beat.required_action}")
    print(f"-> Required Subjects: {beat.required_subjects}")
    print(f"-> Required Target:   {beat.required_target}")
    print(f"-> Required Location: {beat.required_location}")
    print(f"-> Forbidden Visuals: {beat.forbidden_visuals}")
    if classification.recommended_rewrite:
        print(f"-> Suggested Rewrite: {classification.recommended_rewrite}")

    # 2. Translate to Query and Search
    query = storyboard_gen.create_event_query(beat)
    ranked_candidates = retrieval_engine.retrieve_events(query, top_k=5, min_score=10.0)

    print(f"\nFound {len(ranked_candidates)} candidate events evaluated:")

    if not ranked_candidates:
        print("  [ERROR] Zero candidate events passed score threshold!")
        return None

    top_verified_event = None

    for rank, (event, score, breakdown) in enumerate(ranked_candidates, 1):
        # 3. Visual Verification Gate
        verification = verifier.verify_event(event, beat)

        verdict_str = "PASS (VERIFIED)" if verification.is_verified else f"FAIL ({verification.status.value})"
        star = " *** TOP VERIFIED MATCH ***" if (verification.is_verified and top_verified_event is None) else ""

        print(f"\n  Candidate #{rank} [Score: {score:.1f} pts] {star}")
        print(f"  - Event ID:      {event.event_id} (Movie {event.movie_number})")
        print(f"  - Timestamps:    {event.start_time:.1f}s - {event.end_time:.1f}s ({_format_tc(event.start_time)} - {_format_tc(event.end_time)})")
        print(f"  - Subject:       {event.primary_subject}")
        print(f"  - Depicted Act:  {event.action}")
        print(f"  - Target/Obj:    {event.target} | Objects: {event.visible_objects}")
        print(f"  - Location:      {event.location}")
        print(f"  - Visual Detail: {event.visual_description}")
        print(f"  - Verification:  {verdict_str}")
        print(f"  - Diagnostics:   {verification.explanation}")

        if verification.is_verified and top_verified_event is None:
            top_verified_event = (event, verification)

    # 4. Event Chain Inspection for Top Match
    if top_verified_event:
        ev, ver = top_verified_event
        print(f"\n  [EVENT CHAIN CONTINUITY for {ev.event_id}]")
        chain = retrieval_engine.retrieve_event_chain(ev.event_id)
        prec = chain.get("preceding")
        foll = chain.get("following")
        
        prec_desc = f"{prec.primary_subject} {prec.action} ({_format_tc(prec.start_time)})" if prec else "None (Scene Start)"
        foll_desc = f"{foll.primary_subject} {foll.action} ({_format_tc(foll.start_time)})" if foll else "None (Scene End)"
        
        print(f"  Preceding [Approach]: {prec_desc}")
        print(f"  Core Action:          {ev.primary_subject} {ev.action} ({_format_tc(ev.start_time)})")
        print(f"  Following [Reaction]: {foll_desc}")

    print("\n")
    return top_verified_event


def _format_tc(seconds: float) -> str:
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def main():
    parser = argparse.ArgumentParser(description="STORY FORGE Movie Event Visual Matching Diagnostic")
    parser.add_argument("--query", "-q", type=str, default=None, help="Custom visual query to evaluate")
    parser.add_argument("--all", "-a", action="store_true", help="Run all 4 canonical benchmark queries")

    args = parser.parse_args()

    index = MovieEventIndex()
    retrieval_engine = MovieEventRetrievalEngine(index)
    verifier = MovieEventVisualVerifier()
    storyboard_gen = VisualStoryboardGenerator()

    if args.query:
        run_single_query_diagnostic("CUSTOM", args.query, index, retrieval_engine, verifier, storyboard_gen)
    else:
        # Default or --all: Run all 4 benchmark queries
        for b in BENCHMARK_QUERIES:
            run_single_query_diagnostic(b["id"], b["query_text"], index, retrieval_engine, verifier, storyboard_gen)


if __name__ == "__main__":
    main()
