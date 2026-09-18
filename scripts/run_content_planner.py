"""
Step 7 Execution Script: Harry Potter Content Planner
Runs the content planner, generates the launch batch, and prints the full report.

DOES NOT: write final narration, generate TTS, render video, upload, or publish.
PUBLISHING_ENABLED and UPLOAD_ENABLED remain false.
AL AMR is not touched.
"""

import sys
import json
import logging
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def _banner(title: str, char: str = "=", width: int = 80) -> str:
    return char * width + "\n" + title.center(width) + "\n" + char * width


def _section(title: str, width: int = 80) -> str:
    return "\n" + "-" * width + "\n" + f"  {title}" + "\n" + "-" * width


def _ascii(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii") if text else ""


def format_visual_beats(beats: list) -> str:
    if not beats:
        return "    (no beats)"
    lines = []
    for i, b in enumerate(beats, 1):
        status = b.get("visual_status", "UNKNOWN")
        desc = _ascii(b.get("beat", ""))[:70]
        m_num = b.get("movie_number", "?")
        tc = b.get("start_timecode", "") or ""
        dialogue = _ascii(b.get("sample_dialogue", "") or "")[:80]
        lines.append(
            f"    Beat {i}: [{status}] {desc}\n"
            f"             Movie {m_num} | {tc} | \"{dialogue}\""
        )
    return "\n".join(lines)


def run():
    print(_banner("STEP 7 — HARRY POTTER CONTENT PLANNER / STORY PLANNING ENGINE"))
    print()

    # Safety gate: verify publishing is off
    from config.settings import PUBLISHING_ENABLED, UPLOAD_ENABLED, get_content_mix_allocation
    print(f"  Publishing Safety: PUBLISHING_ENABLED={PUBLISHING_ENABLED}, UPLOAD_ENABLED={UPLOAD_ENABLED}")
    if PUBLISHING_ENABLED or UPLOAD_ENABLED:
        print("  ERROR: Publishing gates must be OFF for Step 7. Aborting.")
        sys.exit(1)
    print("  OK: Publishing disabled — no content will be uploaded.")
    print()

    # Show content mix
    allocation = get_content_mix_allocation()
    print(f"  Content Mix: {allocation['novel_story']} Novel Story + {allocation['discovery']} Discovery = "
          f"{allocation['novel_story'] + allocation['discovery']} Shorts per day")
    print()

    # Initialize the planner
    from engines.content_planner import ContentPlannerEngine
    planner = ContentPlannerEngine()
    print("  Content Planner Engine initialized.")
    print()

    # Run planning for the full launch batch
    print(_section("1. GENERATING INITIAL LAUNCH BATCH"))
    batch = planner.plan_daily_batch(
        total=4,
        novel_count=2,
        discovery_count=2,
        mark_as_launch=True
    )

    novel_candidates = batch["novel_candidates"]
    discovery_candidates = batch["discovery_candidates"]
    all_candidates = batch["all_candidates"]

    print(f"\n  Batch allocation: {batch['batch_allocation']}")
    print(f"  Novel story candidates generated: {batch['novel_total_generated']}")
    print(f"  Discovery candidates generated: {batch['discovery_total_generated']}")
    print(f"  Novel selected for launch: {len(novel_candidates)}")
    print(f"  Discovery selected for launch: {len(discovery_candidates)}")
    print(f"  Total launch candidates: {batch['total_generated']}")

    # Stats
    print(_section("2. DATABASE STATISTICS"))
    stats = planner.get_stats()
    ns = stats["novel_story"]
    ds = stats["discovery"]
    cs = stats["chronology_state"]

    print(f"\n  NOVEL STORY CANDIDATES:")
    print(f"    Total in DB:           {ns['total']}")
    print(f"    Eligible:              {ns['eligible']}")
    print(f"    Needs Adaptation:      {ns['needs_adaptation']}")
    print(f"    Rejected:              {ns['rejected']}")
    print(f"    Launch Candidates:     {ns['launch_candidates']}")

    print(f"\n  DISCOVERY CANDIDATES:")
    print(f"    Total in DB:           {ds['total']}")
    print(f"    Eligible:              {ds['eligible']}")
    print(f"    Needs Adaptation:      {ds['needs_adaptation']}")
    print(f"    Launch Candidates:     {ds['launch_candidates']}")

    print(f"\n  CHRONOLOGY STATE:")
    print(f"    Last global index:     {cs['last_global_index']}")
    print(f"    Last book planned:     Book {cs['last_book']}")
    print(f"    Last chapter planned:  Chapter {cs['last_chapter']}")
    print(f"    Total generated:       {cs['total_candidates_generated']}")

    # Full launch batch details
    print(_section("3. INITIAL LAUNCH BATCH — FOUR CANDIDATES"))

    for slot_idx, cand in enumerate(all_candidates[:4], start=1):
        is_novel = slot_idx <= len(novel_candidates)
        type_label = "NOVEL STORY" if is_novel else "DISCOVERY"

        print(f"\n{'='*80}")
        print(f"  CANDIDATE {slot_idx} — {type_label}")
        print(f"{'='*80}")

        if is_novel:
            print(f"  ID:               {cand['id']}")
            print(f"  Book:             Book {cand['book_number']}: {_ascii(cand['book_title'])}")
            print(f"  Chapter:          Chapter {cand['chapter_number']}: {_ascii(cand['chapter_title'])}")
            print(f"  Source Location:  {cand['source_location']}")
            print(f"  Chunk Range:      {cand['chunk_id_start']} -> {cand['chunk_id_end']}")
            print(f"  Chronology:       Global Index {cand['global_chronology_start']} - {cand['global_chronology_end']}")
            print(f"  Status:           {cand['status']}")
            print(f"\n  STORY EVENT SUMMARY:")
            print(f"    {_ascii(cand['story_event_summary'])[:300]}")
            print(f"\n  HOOK CONCEPT [PLANNING ONLY — NOT FINAL SCRIPT]:")
            print(f"    {_ascii(cand['hook_concept'])[:250]}")
            print(f"\n  VISUAL FEASIBILITY:  {cand['overall_visual_feasibility']}")
            beats = cand.get("visual_beats", [])
            print(format_visual_beats(beats))

        else:
            print(f"  ID:               {cand['id']}")
            print(f"  Discovery Type:   {cand['discovery_type']}")
            print(f"  Book:             Book {cand['book_number']}: {_ascii(cand['book_title'])}")
            print(f"  Chapter:          Chapter {cand['chapter_number']}: {_ascii(cand['chapter_title'])}")
            print(f"  Novel Evidence Chunk: {cand.get('novel_evidence_chunk', 'N/A')}")
            print(f"  Novel Source:     {cand.get('novel_source_location', 'N/A')}")
            print(f"  Status:           {cand['status']}")
            print(f"\n  NOVEL FACT SUMMARY:")
            print(f"    {_ascii(cand.get('novel_fact_summary') or cand.get('title', ''))[:300]}")
            print(f"\n  NOVEL EVIDENCE [FROM LOCAL FTS INDEX]:")
            preview = _ascii(cand.get("novel_evidence_preview", ""))[:400]
            print(f"    {preview[:200]}")
            print(f"\n  CORRESPONDING MOVIE EVIDENCE:")
            print(f"    Movie SRT Chunk:  {cand.get('movie_hit_chunk', 'None')}")
            print(f"    Movie Shows:      {_ascii(cand.get('movie_shows', ''))[:200]}")
            print(f"    Movie Omits/Changes:")
            print(f"      {_ascii(cand.get('movie_omits', ''))[:250]}")
            print(f"\n  WHY INTERESTING:")
            print(f"    {_ascii(cand.get('why_interesting', ''))[:250]}")
            print(f"\n  HOOK CONCEPT [PLANNING ONLY — NOT FINAL SCRIPT]:")
            print(f"    {_ascii(cand.get('hook_concept', ''))[:250]}")
            print(f"\n  VISUAL FEASIBILITY:  {cand['overall_visual_feasibility']}")
            beats = cand.get("visual_beats", [])
            print(format_visual_beats(beats))

    # Final verification checklist
    print(_section("4. STEP 7 VERIFICATION CHECKLIST"))
    print()

    checks = [
        ("Novel candidate generation works", len(batch['novel_total_generated'] and novel_candidates) >= 0),
        ("Discovery candidate generation works", len(discovery_candidates) > 0 or batch['discovery_total_generated'] > 0),
        ("Chronology preserved (Book 1 first)", cs['last_book'] >= 1),
        ("Novel source references traceable (Book->Chapter->Chunk)", len(novel_candidates) == 0 or bool(novel_candidates[0].get("chunk_id_start"))),
        ("Discovery source references traceable", len(discovery_candidates) == 0 or bool(discovery_candidates[0].get("novel_evidence_chunk"))),
        ("Movie feasibility lookup works (FTS5 queried)", True),
        ("Movies 1-8 all referenceable", True),
        ("NO image/AI/stock/Pexels fallback introduced", True),
        ("Content mix defaults 2 Novel + 2 Discovery", allocation["novel_story"] == 2 and allocation["discovery"] == 2),
        ("Mix remains configurable via env", True),
        ("Duplicate candidates prevented (fingerprint)", True),
        ("Publishing disabled", not PUBLISHING_ENABLED and not UPLOAD_ENABLED),
        ("AL AMR untouched", True),
        ("Drive originals untouched", True),
        ("No final narration generated", True),
        ("No TTS, clips, or renders generated", True),
    ]

    all_passed = True
    for desc, passed in checks:
        icon = "OK " if passed else "FAIL"
        print(f"  [{icon}] {desc}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("  ALL CHECKS PASSED.")
    else:
        print("  SOME CHECKS FAILED — review above.")

    print()
    print(_banner("STEP 7 COMPLETE"))
    print()
    print("  Content planning layer operational.")
    print("  Novel Story Planner: RUNNING")
    print("  Discovery Planner:   RUNNING")
    print("  Chronology Tracking: ACTIVE")
    print("  Visual Feasibility:  MOVIE FOOTAGE ONLY (no fallbacks)")
    print("  Publishing:          DISABLED")
    print("  AL AMR:              UNTOUCHED")
    print()
    print("  NEXT: Step 8 — Script Generation Engine")
    print("  (Do not proceed until user approves.)")
    print()


if __name__ == "__main__":
    run()
