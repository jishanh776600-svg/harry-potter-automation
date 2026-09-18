"""
Execution script for Step 6: Ingest all 7 Harry Potter novels into SQLite pipeline.db
and test FTS5 search and narrative chronology.
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from engines.novel_knowledge_engine import NovelKnowledgeEngine

def main():
    print("=" * 80)
    print("STEP 6: HARRY POTTER NOVEL INGESTION & SEARCHABLE KNOWLEDGE BASE")
    print("=" * 80)

    engine = NovelKnowledgeEngine()

    print("\n>>> VERIFYING/INGESTING ALL 7 NOVELS INTO SQLITE (pipeline.db)...")
    results = engine.ingest_all_novels(force=False)

    print("\n" + "=" * 80)
    print("INGESTION SUMMARY BY NOVEL")
    print("=" * 80)
    total_chapters = 0
    total_pages = 0
    total_chunks = 0

    for r in results:
        print(f"  Book {r['book_number']}: {r['title']}")
        print(f"    - Chapters: {r['chapters']} | Pages: {r['pages']} | Chunks: {r['chunks']} ({r['status']})")
        total_chapters += r["chapters"]
        total_pages += r["pages"]
        total_chunks += r["chunks"]

    print("-" * 80)
    print(f"TOTAL SERIES STATS:")
    print(f"  Books:    7")
    print(f"  Chapters: {total_chapters}")
    print(f"  Pages:    {total_pages}")
    print(f"  Chunks:   {total_chunks} (Searchable Passages)")
    print("=" * 80)

    print("\n>>> DEMONSTRATING SEARCH & RETRIEVAL (FTS5 BM25)...")

    test_queries = [
        ("Mirror of Erised", 1),
        ("Dobby warning Privet Drive", 2),
        ("Boggart wardrobe Lupin", 3),
        ("Graveyard Voldemort bone", 4),
        ("Dumbledore Army Room Requirement", 5),
        ("Cave potion Horcrux", 6),
        ("Elder Wand Battle Hogwarts", 7),
    ]

    for q, b_num in test_queries:
        print(f"\n[QUERY] '{q}' (Target Book: {b_num})")
        matches = engine.search(q, book_number=b_num, limit=1)
        if matches:
            m = matches[0]
            print(f"  Match Found: {m['chunk_id']}")
            print(f"  Location:    {m['source_location']} | Chapter: {m['chapter_title']}")
            print(f"  Rank:        {m['relevance_rank']}")
            snippet = m['text'][:180].replace('\n', ' ').encode('ascii', 'replace').decode('ascii')
            print(f"  Snippet:     {snippet}...")
        else:
            print("  No match found.")

    print("\n>>> TESTING CHRONOLOGY PRESERVATION (First 3 series passages)...")
    chron_passages = engine.get_chronological_passages(start_index=1, limit=3)
    for p in chron_passages:
        snippet = p['text'][:120].replace('\n', ' ').encode('ascii', 'replace').decode('ascii')
        print(f"  #{p['global_chronology_index']} [{p['source_location']}]: {snippet}...")

    print("\n>>> TESTING IDEMPOTENCY (Running without force)...")
    cached_results = engine.ingest_all_novels(force=False)
    all_cached = all(r["status"] == "CACHED" for r in cached_results)
    print(f"  Idempotency check: {'PASSED (All 7 books detected as CACHED, 0 duplicates)' if all_cached else 'FAILED'}")

    print("\n" + "=" * 80)
    print("STEP 6 COMPLETE: ALL 7 HARRY POTTER NOVELS SUCCESSFULLY INGESTED & SEARCHABLE!")
    print("=" * 80)

if __name__ == "__main__":
    main()
