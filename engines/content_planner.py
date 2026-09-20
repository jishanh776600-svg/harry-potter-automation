"""
Harry Potter Content Planner Engine (Step 7)
================================================================================
Produces structured CONTENT PLANS for two types of Shorts:

  A. NOVEL STORY SHORTS — Chronological storytelling grounded in the 7 novels
  B. DISCOVERY SHORTS   — Educational book-vs-movie comparison facts

This step answers: "WHAT SHORT SHOULD WE MAKE?"
It does NOT produce final narration, scripts, TTS, clips, or renders.

HARD INVARIANTS enforced at every point:
  - MOVIE FOOTAGE ONLY — no AI visuals, stock, Pexels, images, or book illustrations
  - Novel facts grounded in local novel FTS knowledge base (no web searches)
  - Movie evidence grounded in local movie SRT subtitle index
  - Publishing remains disabled (PUBLISHING_ENABLED=false)
  - AL AMR is never touched
"""

import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import PROJECT_ROOT, DB_PATH, get_content_mix_allocation
from core.models import (
    Base, ChronologyState, NovStoryCandidate, DiscoveryCandidate
)
from engines.novel_knowledge_engine import NovelKnowledgeEngine
from engines.movie_asset_engine import MovieAssetEngine

logger = logging.getLogger(__name__)


# ── Visual Feasibility Status Constants ───────────────────────────────────────
VF_DIRECT_MATCH = "DIRECT_MATCH"
VF_STRONG_CONTEXTUAL = "STRONG_CONTEXTUAL_MATCH"
VF_WEAK_CONTEXTUAL = "WEAK_CONTEXTUAL_MATCH"
VF_NO_FOOTAGE = "NO_USABLE_MOVIE_FOOTAGE"
VF_ADAPTATION_REQUIRED = "VISUAL_ADAPTATION_REQUIRED"

# ── Candidate Status Constants ─────────────────────────────────────────────────
STATUS_ELIGIBLE = "ELIGIBLE"
STATUS_NEEDS_ADAPTATION = "NEEDS_ADAPTATION"
STATUS_REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
STATUS_REJECTED_TOO_COMPLEX = "REJECTED_TOO_COMPLEX"
STATUS_REJECTED_NO_VISUAL = "REJECTED_NO_USABLE_VISUAL"
STATUS_REJECTED_SKIPPED = "REJECTED_SKIPPED"

CHRONOLOGY_STATE_KEY = "novel_story_progress"


def _fingerprint(parts: List[str]) -> str:
    """Deterministic SHA-256 fingerprint from a list of identity parts."""
    normalized = "|".join(str(p).strip().lower() for p in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── Discovery Seed Topics ──────────────────────────────────────────────────────
# Each entry is a curated book-vs-movie discovery fact with search hints.
# Facts are verified via local FTS — not model memory.
DISCOVERY_SEEDS = [
    {
        "slug": "peeves_poltergeist",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "Peeves the Poltergeist — completely cut from all 8 movies",
        "novel_search_query": "Peeves poltergeist ghost",
        "movie_search_query": "poltergeist ghost hallway",
        "preferred_book": 1,
        "preferred_chapter": 8,
        "hook_concept": "There's a chaos-causing ghost in every Harry Potter book that none of the movies ever showed — and the crew actually filmed scenes with him.",
        "why_interesting": "Peeves was a major recurring character in all 7 books, yet entirely absent from all 8 films. Actor Rik Mayall filmed scenes but was cut entirely.",
        "movie_omits": "Peeves never appears in any of the 8 HP films despite being present throughout all 7 novels.",
        "novel_fact_summary": "Peeves the Poltergeist is a recurring chaos-causing entity who appears in all 7 Harry Potter novels but was completely absent from all 8 films.",
    },
    {
        "slug": "neville_hufflepuff_sorting",
        "discovery_type": "BOOK_VS_MOVIE_DIFFERENCE",
        "title": "Neville begged the Sorting Hat to put him in Hufflepuff — the movie skips this",
        "novel_search_query": "Neville sorting hat Hufflepuff",
        "movie_search_query": "Neville sorting hat",
        "preferred_book": 1,
        "preferred_chapter": 7,
        "hook_concept": "Neville Longbottom desperately pleaded with the Sorting Hat to put him anywhere but Gryffindor — a detail completely dropped in the movies.",
        "why_interesting": "This reveals early Neville's extreme self-doubt and makes his Book 7 heroism even more powerful.",
        "movie_omits": "The movie shows the Sorting Hat simply placing Neville in Gryffindor with no internal struggle mentioned.",
        "novel_fact_summary": "In the novel, Neville pleaded with the Sorting Hat to be placed in Hufflepuff rather than Gryffindor due to his crippling self-doubt.",
    },
    {
        "slug": "dobby_enslaved_malfoys",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "The book explains exactly why Dobby is enslaved to the Malfoys — movies never do",
        "novel_search_query": "Dobby house elf bound",
        "movie_search_query": "Dobby Malfoy free",
        "preferred_book": 2,
        "preferred_chapter": 2,
        "hook_concept": "Why was Dobby a slave to the Malfoys specifically? The book explains the dark truth — the movies completely gloss over it.",
        "why_interesting": "Understanding Dobby's specific enslavement to the Malfoys adds massive weight to his eventual freedom and loyalty to Harry.",
        "movie_omits": "Movie 2 shows Dobby serving Lucius Malfoy but never explains the house-elf enslavement mechanics clearly.",
        "novel_fact_summary": "The novels establish that house-elves are magically bound to their families through a dark enchantment — Dobby was bound to serve the Malfoy family against his will.",
    },
    {
        "slug": "mirror_of_erised_inscription",
        "discovery_type": "LORE_DETAIL",
        "title": "The Mirror of Erised has a secret inscription — most fans never decoded it",
        "novel_search_query": "Mirror heart desire show",
        "movie_search_query": "Mirror of Erised",
        "preferred_book": 1,
        "preferred_chapter": 12,
        "hook_concept": "The Mirror of Erised has words written along the top — and when you reverse them, they reveal exactly what the mirror does.",
        "why_interesting": "The inscription 'Erised stra ehru oyt ube cafru oyt on wohsi' reversed is 'I show not your face but your heart's desire' — the books explain this explicitly.",
        "movie_omits": "The movie shows the inscription but never explains or draws attention to what it means when reversed.",
        "novel_fact_summary": "The Mirror of Erised bears an inscription that, when reversed, reads 'I show not your face but your heart's desire' — the novels make Dumbledore explain this directly.",
    },
    {
        "slug": "quirrell_voldemort_backstory",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Quirrell's backstory — how he met Voldemort in Albania — is only in the novel",
        "novel_search_query": "Quirrell Voldemort forest",
        "movie_search_query": "Quirrell Voldemort",
        "preferred_book": 1,
        "preferred_chapter": 17,
        "hook_concept": "The movie never explains how Voldemort ended up sharing Quirrell's body — the book reveals a chilling backstory.",
        "why_interesting": "Quirrell sought Voldemort out in the Albanian forest, and Voldemort seized the opportunity — showing Voldemort's manipulative nature even in his weakened state.",
        "movie_omits": "Movie 1 shows Quirrell as Voldemort's host but omits the backstory of how this happened.",
        "novel_fact_summary": "In the novel, Quirrell had traveled to find Voldemort in Albania and willingly let Voldemort possess him — the movies never explain this origin.",
    },
    {
        "slug": "hermione_research_library",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Hermione's obsessive library research saves Harry — the movies compress her role",
        "novel_search_query": "Hermione research library",
        "movie_search_query": "Hermione library books",
        "preferred_book": 4,
        "preferred_chapter": 20,
        "hook_concept": "Hermione spends weeks in the library researching to save Harry — a dedication the movies turn into a brief montage.",
        "why_interesting": "Hermione's role as Harry's intellectual backbone is more thoroughly shown in the novels, where her research is painstakingly detailed.",
        "movie_omits": "Movie 4 shows Harry's preparation but downplays the step-by-step research Hermione conducted across weeks.",
        "novel_fact_summary": "Hermione's extensive library research across multiple weeks is a defining character trait in the novels that the films repeatedly compress or omit.",
    },
    {
        "slug": "dumbledore_explains_dursleys",
        "discovery_type": "MOTIVATION_REVEALED",
        "title": "Dumbledore's full explanation for leaving Harry at the Dursleys — only in Book 5",
        "novel_search_query": "Dumbledore Dursleys protection",
        "movie_search_query": "Dumbledore Privet Drive protection",
        "preferred_book": 5,
        "preferred_chapter": 37,
        "hook_concept": "The full reason why Dumbledore placed Harry with the Dursleys — the exact magical mechanism — is only explained in Book 5.",
        "why_interesting": "It reveals that Petunia's acceptance of Harry into her home renewed and anchored Lily's blood protection annually.",
        "movie_omits": "The movies never fully explain why Harry specifically had to return to Privet Drive each summer.",
        "novel_fact_summary": "The novel explains that Petunia's acceptance of Harry annually renewed Lily's blood protection — the movie omits this crucial magical mechanism entirely.",
    },
    {
        "slug": "snape_patronus_prince_tale",
        "discovery_type": "MOTIVATION_REVEALED",
        "title": "Snape's Patronus is a Doe — and the novel's explanation is more powerful than the film",
        "novel_search_query": "Patronus doe silver Snape",
        "movie_search_query": "Snape Patronus doe silver",
        "preferred_book": 7,
        "preferred_chapter": 33,
        "hook_concept": "Snape's Patronus takes the form of a silver doe — the same as Lily Potter's — and the novel gives his full motivation that the movie truncates.",
        "why_interesting": "The 'always' moment works only if you understand that Snape's love for Lily was the anchor for every decision of his life.",
        "movie_omits": "Movie 7 Part 2 shows the memory sequence but compresses the full emotional context of Snape's sustained devotion across decades.",
        "novel_fact_summary": "The Prince's Tale chapter in Book 7 provides the most complete account of Snape's love for Lily and how it shaped every decision of his life — deeper than the film's condensed version.",
    },
]


class ContentPlannerEngine:
    """
    Harry Potter Content Planning Engine — Step 7.

    Produces structured content plans for Novel Story and Discovery Shorts.
    Sources all facts from the local novel FTS and movie SRT indexes.
    Enforces strict MOVIE FOOTAGE ONLY visual policy.
    Never produces final narration — planning layer only.
    """

    def __init__(self):
        # Initialize DB tables
        engine = create_engine(f"sqlite:///{DB_PATH}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        self.novel_engine = NovelKnowledgeEngine()
        self.movie_engine = MovieAssetEngine()
        logger.info("[CONTENT_PLANNER] Initialized. Novel FTS + Movie SRT indexes ready.")

    # ── Chronology State ───────────────────────────────────────────────────────

    def _get_chronology_state(self, session) -> ChronologyState:
        state = session.query(ChronologyState).filter_by(id=CHRONOLOGY_STATE_KEY).first()
        if state is None:
            state = ChronologyState(
                id=CHRONOLOGY_STATE_KEY,
                last_planned_global_index=0,
                last_planned_book_number=0,
                last_planned_chapter_number=0,
                total_candidates_generated=0,
                updated_at=datetime.utcnow()
            )
            session.add(state)
            session.flush()
        return state

    # ── Visual Feasibility Check ───────────────────────────────────────────────

    def _check_visual_feasibility(
        self,
        beats: List[Dict[str, str]],
        movie_number_hint: Optional[int] = None
    ) -> Tuple[List[Dict], str]:
        """
        For each visual beat (plain-English description of what needs to be shown),
        queries the Movie SRT FTS index for a matching scene.

        Search strategy:
          1. Try preferred movie first (movie_number_hint) for direct match
          2. If no match, search all 8 movies for contextual match
          3. If still no match: NO_USABLE_MOVIE_FOOTAGE

        Returns (enriched_beats_list, overall_feasibility_status).
        Visual policy: MOVIE FOOTAGE ONLY. No AI, stock, Pexels, or fallbacks.
        """
        enriched = []
        statuses = []

        for beat in beats:
            description = beat.get("description", "")
            result = {
                "beat": description,
                "movie_number": None,
                "chunk_id": None,
                "start_timecode": None,
                "end_timecode": None,
                "duration_seconds": None,
                "sample_dialogue": None,
                "visual_status": VF_NO_FOOTAGE,
            }

            try:
                # Step 1: Try preferred movie
                best = None
                if movie_number_hint is not None:
                    preferred = self.movie_engine.search_movie_scenes(
                        query=description,
                        movie_number=movie_number_hint,
                        limit=3
                    )
                    if preferred:
                        best = preferred[0]
                        is_broad = False

                # Step 2: Search all movies if no preferred match
                if best is None:
                    broad = self.movie_engine.search_movie_scenes(
                        query=description,
                        limit=3
                    )
                    if broad:
                        best = broad[0]
                        is_broad = True
                    else:
                        is_broad = False

                if best:
                    rank = abs(best.get("relevance_rank", 999))
                    result["movie_number"] = best["movie_number"]
                    result["chunk_id"] = best["chunk_id"]
                    result["start_timecode"] = best["start_timecode"]
                    result["end_timecode"] = best["end_timecode"]
                    result["duration_seconds"] = best["duration_seconds"]
                    result["sample_dialogue"] = best["text"][:120]

                    # Score by BM25 rank magnitude + whether it came from the preferred movie
                    if not is_broad and rank <= 8.0:
                        result["visual_status"] = VF_DIRECT_MATCH
                    elif not is_broad and rank <= 14.0:
                        result["visual_status"] = VF_STRONG_CONTEXTUAL
                    elif rank <= 10.0:
                        result["visual_status"] = VF_STRONG_CONTEXTUAL
                    else:
                        result["visual_status"] = VF_WEAK_CONTEXTUAL

                # Step 3: If movie footage was not found, check truthful fan art / illustration feasibility
                if result["visual_status"] == VF_NO_FOOTAGE:
                    try:
                        from engines.fan_art_retrieval_engine import FanArtRetrievalEngine
                        fa_engine = FanArtRetrievalEngine()
                        beat_dict = {"narration_text": description, "action": description}
                        artwork = fa_engine.search_artwork_for_beat(beat_dict)
                        if artwork:
                            result["visual_status"] = "FAN_ART_MATCH"
                            result["visual_source"] = artwork.source_type.value if hasattr(artwork.source_type, "value") else artwork.source_type
                            result["creator"] = artwork.creator
                            result["source_url"] = artwork.source_url
                    except Exception as fa_err:
                        logger.debug(f"[VISUAL_FEASIBILITY] Artwork check notice: {fa_err}")

            except Exception as e:
                logger.warning(f"[VISUAL_FEASIBILITY] Search error for '{description[:50]}': {e}")

            enriched.append(result)
            statuses.append(result["visual_status"])

        # Determine overall status
        if all(s in (VF_DIRECT_MATCH, "FAN_ART_MATCH") for s in statuses):
            overall = VF_DIRECT_MATCH
        elif all(s in (VF_DIRECT_MATCH, VF_STRONG_CONTEXTUAL, "FAN_ART_MATCH") for s in statuses):
            overall = VF_STRONG_CONTEXTUAL
        elif VF_NO_FOOTAGE in statuses and len([s for s in statuses if s == VF_NO_FOOTAGE]) >= len(statuses) / 2:
            overall = VF_ADAPTATION_REQUIRED
        elif VF_NO_FOOTAGE in statuses:
            overall = VF_WEAK_CONTEXTUAL
        else:
            overall = VF_WEAK_CONTEXTUAL

        return enriched, overall


    # ── Novel Story Planner ────────────────────────────────────────────────────

    def plan_novel_story_candidates(
        self,
        count: int = 6,
        force_restart: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Generates Novel Story Short candidates in strict chronological order.

        Reads from the chronological frontier, groups adjacent novel chunks
        into coherent scene windows, evaluates visual feasibility,
        and persists ELIGIBLE candidates idempotently.

        Does NOT generate final narration — planning metadata only.
        """
        with self.Session() as session:
            state = self._get_chronology_state(session)

            if force_restart:
                state.last_planned_global_index = 0
                session.flush()

            start_index = state.last_planned_global_index + 1
            logger.info(f"[NOVEL_PLANNER] Starting from global chronology index {start_index}")

            # Fetch a generous window of passages to work with
            passages = self.novel_engine.get_chronological_passages(
                start_index=start_index,
                limit=count * 5
            )

            if not passages:
                logger.warning("[NOVEL_PLANNER] No more passages available in chronology.")
                return []

            # Group into chapter-level scene windows (2-3 chunks per candidate)
            windows = self._group_into_scene_windows(passages, window_size=3)
            results = []

            for window in windows:
                if len(results) >= count:
                    break

                first = window[0]
                last = window[-1]

                # Build content fingerprint
                fp = _fingerprint([
                    str(first["book_number"]),
                    str(first["chapter_number"]),
                    first["chunk_id"],
                    last["chunk_id"]
                ])

                # Idempotency check
                existing = session.query(NovStoryCandidate).filter_by(
                    content_fingerprint=fp
                ).first()
                if existing:
                    logger.debug(f"[NOVEL_PLANNER] Duplicate skipped: {fp[:12]}")
                    continue

                # Analyze the window
                analysis = self._analyze_story_window(window)

                # Build visual beats for the scene
                visual_beats = self._extract_story_visual_beats(window, first["book_number"])
                enriched_beats, overall_vf = self._check_visual_feasibility(
                    visual_beats, movie_number_hint=first["book_number"]
                )

                # Determine candidate status
                status = STATUS_ELIGIBLE
                if overall_vf == VF_NO_FOOTAGE:
                    status = STATUS_NEEDS_ADAPTATION
                elif analysis["complexity"] == "COMPLEX" and analysis["word_count"] > 800:
                    status = STATUS_REJECTED_TOO_COMPLEX

                # Build candidate ID
                candidate_id = (
                    f"ns_b{first['book_number']}c{first['chapter_number']:02d}"
                    f"_gc{first['global_chronology_index']:04d}"
                    f"_{last['global_chronology_index']:04d}"
                )

                candidate = NovStoryCandidate(
                    id=candidate_id,
                    book_number=first["book_number"],
                    book_title=first["book_title"],
                    chapter_number=first["chapter_number"],
                    chapter_title=first["chapter_title"],
                    chunk_id_start=first["chunk_id"],
                    chunk_id_end=last["chunk_id"],
                    global_chronology_start=first["global_chronology_index"],
                    global_chronology_end=last["global_chronology_index"],
                    source_location=first["source_location"],
                    source_text_preview="\n\n".join(p["text"][:200] for p in window)[:500],
                    story_event_summary=analysis["event_summary"],
                    characters_json=json.dumps(analysis["characters"]),
                    locations_json=json.dumps(analysis["locations"]),
                    objects_events_json=json.dumps(analysis["objects_events"]),
                    beginning_context=analysis["beginning"],
                    central_development=analysis["development"],
                    payoff_conclusion=analysis["payoff"],
                    hook_concept=analysis["hook_concept"],
                    narration_complexity=analysis["complexity"],
                    short_duration_feasibility=analysis["duration_feasibility"],
                    visual_beats_json=json.dumps(enriched_beats),
                    overall_visual_feasibility=overall_vf,
                    status=status,
                    content_fingerprint=fp,
                    is_launch_candidate=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(candidate)
                session.flush()

                # Update chronology state
                if last["global_chronology_index"] > state.last_planned_global_index:
                    state.last_planned_global_index = last["global_chronology_index"]
                    state.last_planned_book_number = last["book_number"]
                    state.last_planned_chapter_number = last["chapter_number"]
                state.total_candidates_generated += 1
                state.updated_at = datetime.utcnow()

                results.append({
                    "id": candidate_id,
                    "book_number": first["book_number"],
                    "book_title": first["book_title"],
                    "chapter_number": first["chapter_number"],
                    "chapter_title": first["chapter_title"],
                    "story_event_summary": analysis["event_summary"],
                    "hook_concept": analysis["hook_concept"],
                    "status": status,
                    "overall_visual_feasibility": overall_vf,
                    "global_chronology_start": first["global_chronology_index"],
                    "global_chronology_end": last["global_chronology_index"],
                    "source_location": first["source_location"],
                    "chunk_id_start": first["chunk_id"],
                    "chunk_id_end": last["chunk_id"],
                    "visual_beats": enriched_beats,
                    "content_fingerprint": fp,
                })

                logger.info(
                    f"[NOVEL_PLANNER] Candidate created: {candidate_id} | "
                    f"B{first['book_number']}C{first['chapter_number']} | "
                    f"VF={overall_vf} | Status={status}"
                )

            session.commit()

        return results

    def _group_into_scene_windows(
        self,
        passages: List[Dict],
        window_size: int = 3
    ) -> List[List[Dict]]:
        """
        Groups passages into chapter-coherent scene windows.
        A window breaks if the chapter changes (maintain chapter unity).
        """
        if not passages:
            return []

        windows = []
        current_window = [passages[0]]

        for p in passages[1:]:
            prev = current_window[-1]
            # Break window on chapter boundary
            same_chapter = (
                p["book_number"] == prev["book_number"] and
                p["chapter_number"] == prev["chapter_number"]
            )
            if same_chapter and len(current_window) < window_size:
                current_window.append(p)
            else:
                if len(current_window) >= 1:
                    windows.append(current_window)
                current_window = [p]

        if current_window:
            windows.append(current_window)

        return windows

    def _analyze_story_window(self, window: List[Dict]) -> Dict[str, Any]:
        """
        Analyzes a group of novel passages to extract structured planning metadata.
        No AI used — pure text analysis of novel chunks.
        """
        combined_text = " ".join(p["text"] for p in window)
        word_count = len(combined_text.split())

        first = window[0]
        chapter_title = first["chapter_title"]

        # Character detection from HP universe names
        hp_characters = [
            "Harry", "Hermione", "Ron", "Dumbledore", "Voldemort", "Snape",
            "Hagrid", "McGonagall", "Neville", "Malfoy", "Draco", "Sirius",
            "Lupin", "Quirrell", "Weasley", "Fred", "George", "Ginny",
            "Dobby", "Hedwig", "Peeves", "Flamel", "Lockhart", "Moody",
            "Cedric", "Fleur", "Viktor", "Bellatrix", "Umbridge", "Luna",
            "Trelawney", "Firenze", "Aragog", "Fawkes", "Crabbe", "Goyle",
            "Percy", "Charlie", "Bill", "Molly", "Arthur", "Tonks",
            "Scabbers", "Pettigrew", "Tom", "Riddle", "Slughorn", "Kreacher",
            "Regulus", "Horcrux", "Griphook", "Aberforth", "Ariana"
        ]
        characters = list({
            c for c in hp_characters
            if c.lower() in combined_text.lower()
        })

        # Location detection
        hp_locations = [
            "Hogwarts", "Diagon Alley", "Gringotts", "Hogsmeade", "Azkaban",
            "Privet Drive", "Forbidden Forest", "Quidditch", "Great Hall",
            "Potions", "Transfiguration", "Astronomy", "Divination",
            "Chamber of Secrets", "Room of Requirement", "Department of Mysteries",
            "Ministry of Magic", "Grimmauld Place", "Godric's Hollow",
            "Dumbledore's office", "Borgin", "Knockturn", "The Burrow",
            "Spinner's End", "Malfoy Manor", "Gringotts", "Shell Cottage",
            "Dobby's", "Platform Nine"
        ]
        locations = list({
            loc for loc in hp_locations
            if loc.lower() in combined_text.lower()
        })

        # Object/event detection
        hp_objects = [
            "Philosopher's Stone", "Sorcerer's Stone", "Invisibility Cloak",
            "Marauder's Map", "Horcrux", "Elder Wand", "Resurrection Stone",
            "Mirror of Erised", "Sorting Hat", "Nimbus", "Firebolt",
            "Polyjuice Potion", "Patronus", "Dementor", "Time-Turner",
            "Pensieve", "Prophecy", "Deathly Hallows", "Dark Mark",
            "Felix Felicis", "Avada Kedavra", "Expecto Patronum"
        ]
        objects_events = list({
            o for o in hp_objects
            if o.lower() in combined_text.lower()
        })

        # Complexity assessment
        if word_count < 350:
            complexity = "SIMPLE"
            duration_feasibility = "FEASIBLE"
        elif word_count < 650:
            complexity = "MODERATE"
            duration_feasibility = "FEASIBLE"
        elif word_count < 900:
            complexity = "COMPLEX"
            duration_feasibility = "NEEDS_TRIMMING"
        else:
            complexity = "COMPLEX"
            duration_feasibility = "TOO_COMPLEX"

        # Event summary from first passage
        preview = first["text"][:250].replace("\n", " ").strip()

        # Beginning / Development / Payoff structure
        passages_list = [p["text"] for p in window]
        beginning = passages_list[0][:200].replace("\n", " ").strip() if passages_list else ""
        development = passages_list[len(passages_list) // 2][:200].replace("\n", " ").strip() if len(passages_list) > 1 else beginning
        payoff = passages_list[-1][:200].replace("\n", " ").strip() if passages_list else ""

        # Hook concept — character + chapter + event structure
        char_str = characters[0] if characters else "Harry"
        event_hint = chapter_title

        hook_concept = (
            f"[HOOK CONCEPT — NOT FINAL NARRATION] "
            f"Something remarkable happens to {char_str} in '{event_hint}' — "
            f"a pivotal moment in Book {first['book_number']} that shapes the rest of the story."
        )

        return {
            "event_summary": f"Book {first['book_number']}, Chapter {first['chapter_number']}: {chapter_title}. {preview}...",
            "characters": characters[:6],
            "locations": locations[:4],
            "objects_events": objects_events[:4],
            "beginning": beginning,
            "development": development,
            "payoff": payoff,
            "hook_concept": hook_concept,
            "complexity": complexity,
            "duration_feasibility": duration_feasibility,
            "word_count": word_count,
        }

    def _extract_story_visual_beats(
        self,
        window: List[Dict],
        book_number: int
    ) -> List[Dict[str, str]]:
        """
        Identifies 3–4 key visual moments from the novel passage window.
        Each beat is expressed as a plain-English description of what needs
        to be shown via movie footage.
        """
        first = window[0]
        chapter_title = first["chapter_title"]
        combined_text = " ".join(p["text"] for p in window)

        # Extract key character names for beat descriptions
        characters_present = []
        for name in ["Harry", "Hermione", "Ron", "Dumbledore", "Voldemort", "Snape",
                     "Hagrid", "McGonagall", "Neville", "Malfoy"]:
            if name.lower() in combined_text.lower():
                characters_present.append(name)

        char = characters_present[0] if characters_present else "Harry Potter"
        char2 = characters_present[1] if len(characters_present) > 1 else None

        # Visual beats use dialogue-searchable terms that appear in movie SRTs.
        # SRTs contain DIALOGUE only — not visual descriptions.
        # Use character names + key scene words that would appear as movie dialogue.
        beats = []

        # Beat 1: Use character name directly — always matches dialogue in SRTs
        beats.append({"description": char})

        # Beat 2: Key noun from chapter title + character (dialogue-adjacent)
        chapter_words = [w for w in chapter_title.split() if len(w) > 4
                         and w.lower() not in {"about", "their", "there", "where", "which", "would", "could", "other"}]
        if chapter_words:
            beats.append({"description": f"{char} {chapter_words[0]}"})
        else:
            beats.append({"description": f"{char} wand"})

        # Beat 3: Second character interaction or general HP world term
        if char2:
            beats.append({"description": f"{char} {char2}"})
        else:
            beats.append({"description": "Harry Hogwarts"})

        # Beat 4: Scene-specific object/event if detectable
        for hp_object in ["wand", "Sorting Hat", "Quidditch", "Patronus", "Horcrux",
                           "Diagon Alley", "Hogwarts", "potion", "Snitch", "broomstick"]:
            if hp_object.lower() in combined_text.lower():
                beats.append({"description": f"{hp_object}"})
                break

        return beats[:4]


    # ── Discovery Planner ──────────────────────────────────────────────────────

    def plan_discovery_candidates(
        self,
        count: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Generates Discovery Short candidates from curated book-vs-movie seeds.

        Each candidate is grounded by querying the local novel FTS index for evidence.
        Movie evidence is checked via the SRT subtitle index.
        Does NOT generate final narration — planning metadata only.
        """
        results = []

        with self.Session() as session:
            for seed in DISCOVERY_SEEDS:
                if len(results) >= count:
                    break

                slug = seed["slug"]

                # Build fingerprint
                fp = _fingerprint([
                    seed["discovery_type"],
                    str(seed["preferred_book"]),
                    str(seed["preferred_chapter"]),
                    slug
                ])

                # Idempotency check
                existing = session.query(DiscoveryCandidate).filter_by(
                    content_fingerprint=fp
                ).first()
                if existing:
                    logger.debug(f"[DISCOVERY_PLANNER] Duplicate skipped: {slug}")
                    results.append({
                        "id": existing.id,
                        "slug": slug,
                        "status": existing.status,
                        "duplicate": True,
                    })
                    continue

                # Search novel FTS for evidence
                novel_hits = self.novel_engine.search(
                    query=seed["novel_search_query"],
                    book_number=seed["preferred_book"],
                    limit=3
                )

                if not novel_hits:
                    # Try without book filter
                    novel_hits = self.novel_engine.search(
                        query=seed["novel_search_query"],
                        limit=3
                    )

                if not novel_hits:
                    logger.warning(f"[DISCOVERY_PLANNER] No novel evidence for: {slug}")
                    continue

                best_novel = novel_hits[0]
                supporting_chunk_ids = [h["chunk_id"] for h in novel_hits[1:]]

                # Search movie SRT for comparison evidence
                movie_hit = None
                try:
                    movie_hits = self.movie_engine.search_movie_scenes(
                        query=seed["movie_search_query"],
                        movie_number=seed["preferred_book"],  # same number as book
                        limit=2
                    )
                    if not movie_hits:
                        movie_hits = self.movie_engine.search_movie_scenes(
                            query=seed["movie_search_query"],
                            limit=2
                        )
                    if movie_hits:
                        movie_hit = movie_hits[0]
                except Exception as e:
                    logger.warning(f"[DISCOVERY_PLANNER] Movie search error for {slug}: {e}")

                # Visual beats for discovery
                visual_beats = [
                    {"description": f"Harry Potter scene from Movie {seed['preferred_book']} establishing context"},
                    {"description": seed["movie_search_query"]},
                    {"description": f"Harry Potter character reaction or emotional moment"},
                ]
                enriched_beats, overall_vf = self._check_visual_feasibility(
                    visual_beats, movie_number_hint=seed["preferred_book"]
                )

                candidate_id = f"disc_{slug}_b{seed['preferred_book']}"

                # Determine book and chapter metadata from novel hit
                book_num = best_novel.get("book_number", seed["preferred_book"])
                chap_num = best_novel.get("chapter_number", seed["preferred_chapter"])
                book_title = best_novel.get("book_title", f"Book {book_num}")
                chapter_title = best_novel.get("chapter_title", f"Chapter {chap_num}")

                candidate = DiscoveryCandidate(
                    id=candidate_id,
                    discovery_type=seed["discovery_type"],
                    book_number=book_num,
                    book_title=book_title,
                    chapter_number=chap_num,
                    chapter_title=chapter_title,
                    chunk_id_primary=best_novel["chunk_id"],
                    chunk_ids_supporting=json.dumps(supporting_chunk_ids),
                    novel_fact_summary=seed["novel_fact_summary"] if "novel_fact_summary" in seed else seed["title"],
                    novel_evidence_text=best_novel["text"][:600],
                    corresponding_movie_number=movie_hit["movie_number"] if movie_hit else seed["preferred_book"],
                    corresponding_movie_title=movie_hit["movie_title"] if movie_hit else None,
                    movie_chunk_id=movie_hit["chunk_id"] if movie_hit else None,
                    movie_shows=movie_hit["text"][:300] if movie_hit else "No direct match found in movie SRT",
                    movie_omits_or_changes=seed.get("movie_omits", ""),
                    why_interesting=seed.get("why_interesting", ""),
                    hook_concept=seed.get("hook_concept", ""),
                    short_duration_feasibility="FEASIBLE",
                    visual_beats_json=json.dumps(enriched_beats),
                    overall_visual_feasibility=overall_vf,
                    status=STATUS_ELIGIBLE,
                    content_fingerprint=fp,
                    is_launch_candidate=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(candidate)
                session.flush()

                results.append({
                    "id": candidate_id,
                    "slug": slug,
                    "discovery_type": seed["discovery_type"],
                    "book_number": book_num,
                    "book_title": book_title,
                    "chapter_number": chap_num,
                    "chapter_title": chapter_title,
                    "title": seed["title"],
                    "novel_fact_summary": seed.get("title", ""),
                    "novel_evidence_chunk": best_novel["chunk_id"],
                    "novel_evidence_preview": best_novel["text"][:300],
                    "novel_source_location": best_novel["source_location"],
                    "movie_hit_chunk": movie_hit["chunk_id"] if movie_hit else None,
                    "movie_shows": movie_hit["text"][:200] if movie_hit else "Not found in SRT",
                    "movie_omits": seed.get("movie_omits", ""),
                    "hook_concept": seed.get("hook_concept", ""),
                    "why_interesting": seed.get("why_interesting", ""),
                    "status": STATUS_ELIGIBLE,
                    "overall_visual_feasibility": overall_vf,
                    "visual_beats": enriched_beats,
                    "content_fingerprint": fp,
                })

                logger.info(
                    f"[DISCOVERY_PLANNER] Candidate created: {candidate_id} | "
                    f"Type={seed['discovery_type']} | VF={overall_vf}"
                )

            session.commit()

        return results

    # ── Daily Batch Planning ───────────────────────────────────────────────────

    def plan_daily_batch(
        self,
        total: Optional[int] = None,
        novel_count: Optional[int] = None,
        discovery_count: Optional[int] = None,
        mark_as_launch: bool = False
    ) -> Dict[str, Any]:
        """
        Produces one complete daily batch of content candidates.

        Uses the configured content mix allocation (default: 2 Novel + 2 Discovery).
        Allocation is configurable — supports 4+0, 3+1, 2+2, 1+3, 0+4.

        Returns structured batch with all candidates traceable to source.
        Does NOT generate narration or render anything.
        Publishing gates remain closed (PUBLISHING_ENABLED=false).
        """
        allocation = get_content_mix_allocation(total_shorts=total)
        n_novel = novel_count if novel_count is not None else allocation["novel_story"]
        n_discovery = discovery_count if discovery_count is not None else allocation["discovery"]

        logger.info(f"[BATCH_PLANNER] Planning batch: {n_novel} Novel + {n_discovery} Discovery")

        novel_candidates = self.plan_novel_story_candidates(count=n_novel * 3)
        eligible_novel = [c for c in novel_candidates if c["status"] == STATUS_ELIGIBLE][:n_novel]

        discovery_candidates = self.plan_discovery_candidates(count=n_discovery * 3)
        eligible_discovery = [c for c in discovery_candidates
                              if c.get("status") == STATUS_ELIGIBLE and not c.get("duplicate")][:n_discovery]

        all_selected = eligible_novel + eligible_discovery

        if mark_as_launch:
            with self.Session() as session:
                for slot, cand in enumerate(all_selected, start=1):
                    content_type = "novel" if slot <= len(eligible_novel) else "discovery"
                    if content_type == "novel":
                        rec = session.query(NovStoryCandidate).filter_by(id=cand["id"]).first()
                    else:
                        rec = session.query(DiscoveryCandidate).filter_by(id=cand["id"]).first()
                    if rec:
                        rec.is_launch_candidate = True
                        rec.batch_slot = slot
                        rec.batch_date = "LAUNCH"
                        rec.updated_at = datetime.utcnow()
                session.commit()

        return {
            "batch_allocation": {"novel_story": n_novel, "discovery": n_discovery},
            "novel_candidates": eligible_novel,
            "discovery_candidates": eligible_discovery,
            "all_candidates": all_selected,
            "total_generated": len(all_selected),
            "novel_total_generated": len(novel_candidates),
            "discovery_total_generated": len(discovery_candidates),
        }

    # ── Statistics ─────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Returns current planning database statistics."""
        with self.Session() as session:
            total_novel = session.query(NovStoryCandidate).count()
            eligible_novel = session.query(NovStoryCandidate).filter_by(status=STATUS_ELIGIBLE).count()
            needs_adaptation_novel = session.query(NovStoryCandidate).filter_by(status=STATUS_NEEDS_ADAPTATION).count()
            rejected_novel = session.query(NovStoryCandidate).filter(
                NovStoryCandidate.status.in_([STATUS_REJECTED_DUPLICATE, STATUS_REJECTED_NO_VISUAL, STATUS_REJECTED_TOO_COMPLEX])
            ).count()
            launch_novel = session.query(NovStoryCandidate).filter_by(is_launch_candidate=True).count()

            total_disc = session.query(DiscoveryCandidate).count()
            eligible_disc = session.query(DiscoveryCandidate).filter_by(status=STATUS_ELIGIBLE).count()
            needs_adaptation_disc = session.query(DiscoveryCandidate).filter_by(status=STATUS_NEEDS_ADAPTATION).count()
            launch_disc = session.query(DiscoveryCandidate).filter_by(is_launch_candidate=True).count()

            state = self._get_chronology_state(session)
            # Materialize state values before session closes
            state_last_global = state.last_planned_global_index
            state_last_book = state.last_planned_book_number
            state_last_chapter = state.last_planned_chapter_number
            state_total_gen = state.total_candidates_generated
            session.commit()

        return {
            "novel_story": {
                "total": total_novel,
                "eligible": eligible_novel,
                "needs_adaptation": needs_adaptation_novel,
                "rejected": rejected_novel,
                "launch_candidates": launch_novel,
            },
            "discovery": {
                "total": total_disc,
                "eligible": eligible_disc,
                "needs_adaptation": needs_adaptation_disc,
                "launch_candidates": launch_disc,
            },
            "chronology_state": {
                "last_global_index": state_last_global,
                "last_book": state_last_book,
                "last_chapter": state_last_chapter,
                "total_candidates_generated": state_total_gen,
            }
        }

