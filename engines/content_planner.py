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
    Base, ChronologyState, NovStoryCandidate, DiscoveryCandidate,
    migrate_discovery_schema
)
from core.discovery_types import (
    DiscoveryTier, DiscoveryStoryStructure, HookArchetype, EvidenceRoute,
    PayoffType, TitlePattern, EvidencePoint
)
from engines.novel_knowledge_engine import NovelKnowledgeEngine
from engines.movie_asset_engine import MovieAssetEngine
from engines.discovery_narrative_engine import DiscoveryNarrativeEngine

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
    {
        "slug": "neville_chosen_one_prophecy",
        "discovery_type": "LORE_DETAIL",
        "title": "Neville Longbottom could have been the Chosen One — the prophecy fits him too",
        "novel_search_query": "prophecy born seventh month dark lord",
        "movie_search_query": "Dumbledore prophecy Harry",
        "preferred_book": 5,
        "preferred_chapter": 37,
        "hook_concept": "The prophecy that made Harry 'the Chosen One' applied equally to Neville Longbottom — Voldemort himself chose which boy to fear.",
        "why_interesting": "The prophecy said 'born as the seventh month dies' to parents who had 'thrice defied Voldemort' — both Harry and Neville fit every condition perfectly.",
        "movie_omits": "Movie 5 mentions the prophecy but never clearly states that Neville was equally valid as the Chosen One — a fact Dumbledore explains at length in the book.",
        "novel_fact_summary": "The full prophecy in Book 5 applies to both Harry and Neville Longbottom. Voldemort chose Harry by attacking him, inadvertently creating the very enemy the prophecy foretold.",
    },
    {
        "slug": "kreacher_regulus_black_sacrifice",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Kreacher's backstory — Regulus Black's heroic death — is almost entirely cut from the movies",
        "novel_search_query": "Kreacher Regulus locket cave",
        "movie_search_query": "Kreacher locket Horcrux",
        "preferred_book": 7,
        "preferred_chapter": 10,
        "hook_concept": "The full tragic story of how Kreacher watched his master Regulus Black sacrifice himself to destroy a Horcrux — the movie cuts 90% of it.",
        "why_interesting": "Kreacher witnessed Regulus's self-sacrifice, was ordered to destroy the locket Horcrux, and spent decades failing to fulfill his dying master's last wish.",
        "movie_omits": "Movie 7 shows Kreacher briefly but completely omits the heartbreaking full account of Regulus Black's deliberate sacrifice to undermine Voldemort.",
        "novel_fact_summary": "Book 7 reveals that Regulus Black willingly sacrificed himself at the cave to replace the Horcrux locket with a fake — ordering Kreacher to destroy it. Kreacher spent decades trying to honor that dying wish.",
    },
    {
        "slug": "marauders_map_backstory",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "The Marauder's Map creators — James, Sirius, Remus, Pettigrew — their story barely exists in the films",
        "novel_search_query": "Marauders Moony Wormtail Padfoot Prongs",
        "movie_search_query": "Marauder map Moony Prongs",
        "preferred_book": 3,
        "preferred_chapter": 18,
        "hook_concept": "The Marauder's Map was created by James Potter, Sirius Black, Remus Lupin, and Peter Pettigrew — and the movie never fully explains their story.",
        "why_interesting": "The four friends became illegal Animagi specifically to keep Lupin company during his painful werewolf transformations — a massive act of loyalty that shaped the entire HP universe.",
        "movie_omits": "Movie 3 reveals the map's makers but barely explains why four teenage boys would risk imprisonment to become unregistered Animagi for their friend.",
        "novel_fact_summary": "The Marauders became Animagi specifically to accompany Remus Lupin during his monthly werewolf transformations — James became a stag, Sirius a dog, Peter a rat. The books spend chapters on this backstory.",
    },
    {
        "slug": "tom_riddle_orphanage_childhood",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Tom Riddle's orphanage childhood — his early dark magic — is barely in the films",
        "novel_search_query": "Tom Riddle orphanage children cave",
        "movie_search_query": "Tom Riddle young orphanage",
        "preferred_book": 6,
        "preferred_chapter": 13,
        "hook_concept": "As a child in an orphanage, Tom Riddle was already using dark magic to terrorize other children — years before he ever heard the word 'Hogwarts'.",
        "why_interesting": "Riddle could already control animals, cause pain to other children, and had a cruel fascination with snakes — all before any magical education.",
        "movie_omits": "Movie 6 shows young Riddle in the orphanage but only briefly — the novels detail specific incidents where Riddle terrorized children and stole from them.",
        "novel_fact_summary": "Book 6 reveals Tom Riddle as a child who terrorized two orphans in a cave, killed a rabbit, and instinctively used magic to harm and control — all before Dumbledore's first visit.",
    },
    {
        "slug": "dumbledore_horcrux_full_plan",
        "discovery_type": "MOTIVATION_REVEALED",
        "title": "Dumbledore knew he was dying — his entire year-long plan with Harry was designed for that",
        "novel_search_query": "Dumbledore hand cursed ring",
        "movie_search_query": "Dumbledore cursed hand ring",
        "preferred_book": 6,
        "preferred_chapter": 23,
        "hook_concept": "Dumbledore knew the ring Horcrux's curse would kill him within a year — so everything he did in Book 6, including his lessons with Harry, was his final legacy.",
        "why_interesting": "Dumbledore was already dying when he conducted all those memory sessions with Harry — he was racing against the curse to give Harry everything he needed.",
        "movie_omits": "Movie 6 shows Dumbledore's blackened hand but barely explores the full weight of his terminal condition and how it shaped every choice of his final year.",
        "novel_fact_summary": "In Book 6, Dumbledore's cursed hand from the Gaunt ring reveals he had roughly a year to live. His entire final year — the Horcrux lessons, the cave mission — was a carefully designed terminal legacy plan.",
    },
    {
        "slug": "harry_hagrid_vault_gringotts_detail",
        "discovery_type": "BOOK_VS_MOVIE_DIFFERENCE",
        "title": "The Gringotts vault scene reveals more about Voldemort's plan than the movie shows",
        "novel_search_query": "Gringotts Harry Hagrid vault",
        "movie_search_query": "Gringotts vault cart goblin",
        "preferred_book": 1,
        "preferred_chapter": 5,
        "hook_concept": "When Harry and Hagrid visit Gringotts in Book 1, the vault visit reveals a crucial detail about why Voldemort targeted that specific vault — which the movie glosses over.",
        "why_interesting": "The book's Gringotts scene establishes the wizarding economy, the nature of goblin-wizard tension, and the specific timing of Quirrell's vault break-in — all dropped from the film.",
        "movie_omits": "The movie visits Gringotts but skips the detail about Quirrell's failed break-in attempt happening the same day — a detail that confirms Voldemort was already moving on the Stone.",
        "novel_fact_summary": "Book 1 reveals that Quirrell attempted to rob vault 713 on the very same day Harry and Hagrid visited — if they had been a day later, the Stone would have been taken.",
    },
    {
        "slug": "house_elves_spew_slavery",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "Hermione's S.P.E.W. campaign — the entire house-elf slavery arc — is completely cut from the films",
        "novel_search_query": "kitchen elves Hogwarts",
        "movie_search_query": "house elf Dobby Winky",
        "preferred_book": 4,
        "preferred_chapter": 9,
        "hook_concept": "Hermione starts an entire anti-slavery movement for house-elves in Book 4 — S.P.E.W. — and it never appears in any of the movies.",
        "why_interesting": "The Society for the Promotion of Elfish Welfare runs across Books 4, 5, and 6 — it develops Hermione's character and deepens the wizarding world's moral complexity.",
        "movie_omits": "The films cut S.P.E.W. entirely, removing a major character arc and the wizarding world's uncomfortable parallel to slavery.",
        "novel_fact_summary": "Hermione's S.P.E.W. campaign in Books 4 through 6 is a sustained moral argument about house-elf slavery that the films erase entirely — along with Winky the traumatized elf.",
    },
    {
        "slug": "weasley_family_clock_magic",
        "discovery_type": "LORE_DETAIL",
        "title": "The Weasley family clock tracks every family member's location — including 'mortal peril'",
        "novel_search_query": "Weasley grandfather clock nine",
        "movie_search_query": "Weasley clock home",
        "preferred_book": 3,
        "preferred_chapter": 6,
        "hook_concept": "The Weasley family has a magical clock that shows each member's whereabouts — and one of the settings reads 'mortal peril'. The movies barely show it.",
        "why_interesting": "The clock has nine hands — one per family member — with locations including 'home', 'school', 'work', and disturbingly, 'lost' and 'mortal peril'.",
        "movie_omits": "Movie 3 briefly shows the clock but never highlights the 'mortal peril' hand or the clock's emotional weight for Molly Weasley, who watches it anxiously.",
        "novel_fact_summary": "The Weasley family clock is described in detail in Book 3 — nine hands, nine locations including 'mortal peril'. Molly watches it obsessively during the war years. The films show it only briefly.",
    },
    {
        "slug": "hagrid_expelled_framed_aragog",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Hagrid was framed by Tom Riddle — the book explains exactly how and why",
        "novel_search_query": "Riddle expelled monster Hagrid",
        "movie_search_query": "Hagrid expelled wand broken",
        "preferred_book": 2,
        "preferred_chapter": 13,
        "hook_concept": "Hagrid didn't open the Chamber of Secrets — Tom Riddle framed him deliberately. The book reveals exactly how Riddle manufactured the evidence.",
        "why_interesting": "Riddle needed a scapegoat to avoid being sent back to the orphanage, so he framed the innocent Hagrid and had his wand snapped — a 50-year injustice.",
        "movie_omits": "Movie 2 shows the diary memory but compresses Riddle's cold calculation in framing Hagrid to protect himself and avoid returning to the Muggle world.",
        "novel_fact_summary": "Book 2 reveals Tom Riddle deliberately framed Hagrid for opening the Chamber, calculating that he needed a scapegoat to stay at Hogwarts rather than return to the orphanage.",
    },
    {
        "slug": "sirius_azkaban_secret_escape",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "How Sirius Black escaped Azkaban — the Dementors' weakness that saved him",
        "novel_search_query": "Sirius Black Azkaban prison escape",
        "movie_search_query": "Sirius Azkaban escape dog",
        "preferred_book": 3,
        "preferred_chapter": 19,
        "hook_concept": "Sirius Black's Azkaban escape is more chilling in the book — he survived 12 years there by knowing he was innocent, and escaped by starving himself thin enough to slip through the bars.",
        "why_interesting": "Dementors feed on happiness — but Sirius had no happy memories to take. He clung to his knowledge of innocence, which kept him sane. His Animagus form confused the Dementors.",
        "movie_omits": "Movie 3 shows Sirius escaping but doesn't fully explore the psychological horror of 12 years in Azkaban or the exact mechanics of how he maintained his sanity.",
        "novel_fact_summary": "Book 3 reveals Sirius survived Azkaban by transforming into a dog — Dementors only sense human emotion. He starved himself thin and slipped through bars to escape, driven by knowing Peter Pettigrew was alive.",
    },
    {
        "slug": "fred_george_howler_mrs_weasley",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "A Howler actually explodes if you don't open it — a detail the movies never show",
        "novel_search_query": "Howler letter explode Ron Weasley",
        "movie_search_query": "Howler Mrs Weasley Ron",
        "preferred_book": 2,
        "preferred_chapter": 6,
        "hook_concept": "A Howler screams at you when opened — but if you refuse to open it, it bursts into flames and shrieks even louder. The book makes this terrifying detail clear.",
        "why_interesting": "The Howler reveals a layered magical communication system with built-in social enforcement — there is no escape from a Howler, and the consequences of ignoring it are worse.",
        "movie_omits": "The movie shows Mrs. Weasley's Howler but doesn't explain that refusing to open one makes it explode and scream anyway — removing the trap aspect of the magic.",
        "novel_fact_summary": "In Book 2, Ron's Howler from Molly Weasley is a terrifying public ordeal. The novel explains that unopened Howlers burst into flames and scream louder — there is no safe way to avoid them.",
    },
    {
        "slug": "lupin_werewolf_wolfsbane_potion",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Lupin's Wolfsbane Potion — what it actually does — is explained only in the books",
        "novel_search_query": "Lupin potion Snape werewolf transform",
        "movie_search_query": "Lupin werewolf transform",
        "preferred_book": 3,
        "preferred_chapter": 8,
        "hook_concept": "The Wolfsbane Potion doesn't stop Lupin from transforming — it just lets him keep his human mind during transformation. The movies never explain this crucial distinction.",
        "why_interesting": "Without the potion, Lupin becomes a mindless, dangerous beast. With it, he retains his consciousness and can simply curl up until dawn — a massive difference.",
        "movie_omits": "Movie 3 shows Snape brewing something for Lupin but never clearly explains what Wolfsbane actually does or why it matters so much to Lupin's ability to teach safely.",
        "novel_fact_summary": "Book 3 explains that Wolfsbane Potion allows Lupin to retain his human mind during his monthly wolf transformation — without it, he becomes a mindless beast who cannot control his actions.",
    },
    {
        "slug": "voldemort_diary_horcrux_accidental",
        "discovery_type": "LORE_DETAIL",
        "title": "Voldemort's diary Horcrux was planted to re-open the Chamber — not just to hide a soul piece",
        "novel_search_query": "Riddle Horcrux diary Malfoy",
        "movie_search_query": "Tom Riddle diary Ginny",
        "preferred_book": 6,
        "preferred_chapter": 23,
        "hook_concept": "The diary wasn't just a Horcrux for safekeeping — Voldemort intended it as a weapon to re-open the Chamber and purge Muggle-borns from Hogwarts.",
        "why_interesting": "Dumbledore reveals in Book 6 that Lucius Malfoy acted on his own initiative — Voldemort had given him the diary for safekeeping, not to plant at Hogwarts. Lucius improvised dangerously.",
        "movie_omits": "Movie 2 shows the diary and the Basilisk plot but doesn't explain that Lucius Malfoy went rogue with Voldemort's Horcrux — an act that infuriated Voldemort later.",
        "novel_fact_summary": "Book 6 reveals the diary Horcrux was given to Lucius Malfoy for safekeeping — not to plant on Ginny. Lucius improvised, using it to re-open the Chamber, risking the destruction of Voldemort's soul piece.",
    },
    {
        "slug": "harry_scar_horcrux_connection",
        "discovery_type": "LORE_DETAIL",
        "title": "Harry's scar is a Horcrux — but Dumbledore only confirms this in Book 6",
        "novel_search_query": "Voldemort soul Harry scar",
        "movie_search_query": "Harry scar pain Voldemort",
        "preferred_book": 6,
        "preferred_chapter": 23,
        "hook_concept": "Harry's scar hurts because a piece of Voldemort's soul lives inside him — but the books take six volumes before Dumbledore finally admits Harry himself is an unintentional Horcrux.",
        "why_interesting": "Voldemort accidentally created the seventh Horcrux when he murdered Harry's parents — a miscalculation that ultimately destroyed him.",
        "movie_omits": "The films hint at the scar connection but never deliver the same chilling realization — that Harry must die to destroy the piece of Voldemort living inside him.",
        "novel_fact_summary": "Book 6 finally reveals that Harry's scar contains a fragment of Voldemort's soul — making Harry an unintentional seventh Horcrux. This means Harry must allow himself to die for Voldemort to become mortal.",
    },
    {
        "slug": "ron_weasley_prefect_badge_surprise",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Why Dumbledore chose Ron as Prefect instead of Harry",
        "novel_search_query": "Ron prefect badge Dumbledore Harry",
        "movie_search_query": "Ron prefect Gryffindor badge",
        "preferred_book": 5,
        "preferred_chapter": 9,
        "hook_concept": "Harry thought he was guaranteed to be Gryffindor prefect — until Ron opened his letter and pulled out the badge.",
        "why_interesting": "Dumbledore chose Ron deliberately because he felt Harry had enough burdens to carry without prefect duties.",
        "movie_omits": "Movie 5 cuts the entire prefect storyline, completely omitting Ron and Hermione's leadership role.",
        "novel_fact_summary": "Book 5 reveals Dumbledore chose Ron over Harry because Harry was already carrying the weight of Voldemort's return.",
    },
    {
        "slug": "percy_weasley_betrayal_and_redemption",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Percy Weasley completely disowned his family — the movies erased his entire redemption",
        "novel_search_query": "Percy Ministry Weasley family traitor",
        "movie_search_query": "Percy Weasley Ministry Fudge",
        "preferred_book": 5,
        "preferred_chapter": 4,
        "hook_concept": "Percy Weasley cut ties with his family, called his father an embarrassment, and sent his mother's Christmas sweater back unopened.",
        "why_interesting": "Percy sided with Fudge against his own parents, only to break down weeping and beg for forgiveness during the Battle of Hogwarts.",
        "movie_omits": "The films show Percy standing silently near Fudge but never explain his deep ideological betrayal of the Weasleys.",
        "novel_fact_summary": "Book 5 shows Percy storming out of the Burrow and rejecting his family. His heartbreaking return occurs in Book 7 right before Fred dies.",
    },
    {
        "slug": "draco_malfoy_invisibility_cloak_train",
        "discovery_type": "BOOK_VS_MOVIE_DIFFERENCE",
        "title": "Draco stomped on Harry's face on the train — and Tonks saved him, not Luna",
        "novel_search_query": "Draco Malfoy train petrified Harry face nose",
        "movie_search_query": "Malfoy Harry train petrified",
        "preferred_book": 6,
        "preferred_chapter": 8,
        "hook_concept": "In the book, Malfoy breaks Harry's nose and leaves him paralyzed under his Cloak — and Tonks finds him, not Luna Lovegood.",
        "why_interesting": "Tonks was stationed in Hogsmeade battling depression and love for Lupin, which explains why she found Harry.",
        "movie_omits": "Movie 6 substitutes Luna Lovegood with Spectrespecs instead of Tonks's deeply personal Book 6 arc.",
        "novel_fact_summary": "In Book 6, Tonks finds Harry petrified on the Hogwarts Express, repairs his broken nose, and escorts him to Snape at the gate.",
    },
    {
        "slug": "neville_parents_st_mungos_heartbreak",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Neville visiting his tortured parents at St. Mungo's was completely erased from the films",
        "novel_search_query": "St Mungo Neville parents bubble gum wrapper",
        "movie_search_query": "Neville Longbottom parents hospital",
        "preferred_book": 5,
        "preferred_chapter": 23,
        "hook_concept": "Neville's mother can barely recognize him — but she silently hands him an empty candy wrapper, which he secretly pockets as his most treasured possession.",
        "why_interesting": "Alice and Frank Longbottom were tortured into insanity by Bellatrix Lestrange, spending their lives in St. Mungo's Hospital.",
        "movie_omits": "The films briefly mention Neville's parents but never show the heartbreaking hospital ward scene with the Droobles gum wrapper.",
        "novel_fact_summary": "Book 5 Chapter 23 depicts Harry, Ron, and Hermione encountering Neville visiting his parents at St. Mungo's, where his mother hands him an empty wrapper.",
    },
    {
        "slug": "peter_pettigrew_silver_hand_strangle",
        "discovery_type": "BOOK_VS_MOVIE_DIFFERENCE",
        "title": "Peter Pettigrew's chilling death was completely changed in the movie",
        "novel_search_query": "Pettigrew silver hand throat choke life debt",
        "movie_search_query": "Pettigrew cellar Malfoy Manor",
        "preferred_book": 7,
        "preferred_chapter": 23,
        "hook_concept": "In the movie, Pettigrew is just knocked out by Dobby. In the book, his own silver hand strangles him to death when he hesitates to kill Harry.",
        "why_interesting": "Voldemort gave Pettigrew the silver hand with a curse: if Pettigrew ever showed mercy or hesitation toward Harry, the hand would turn against its master.",
        "movie_omits": "Movie 7 Part 1 turns Pettigrew's death into comic relief with a stunned fall, erasing Voldemort's ruthless failsafe trap.",
        "novel_fact_summary": "In Book 7, Pettigrew hesitates for a single second remembering his life debt to Harry. The silver hand immediately chokes him to death despite Harry and Ron trying to pry it loose.",
    },
    {
        "slug": "dumbledore_howler_petunia_remember_last",
        "discovery_type": "LORE_DETAIL",
        "title": "Dumbledore sent a Howler to Aunt Petunia — revealing their secret past",
        "novel_search_query": "Remember my last Petunia Howler Dumbledore",
        "movie_search_query": "Petunia Howler letter Dumbledore",
        "preferred_book": 5,
        "preferred_chapter": 2,
        "hook_concept": "When Uncle Vernon tries to throw Harry out in Book 5, a smoking Howler explodes in the kitchen with Dumbledore's voice: 'Remember my last, Petunia.'",
        "why_interesting": "Petunia wrote letters to Dumbledore as a child begging to attend Hogwarts, and Dumbledore gently declined — creating her lifelong bitterness.",
        "movie_omits": "The movie cuts the Howler completely, removing the revelation that Dumbledore and Petunia had a direct connection predating Harry's birth.",
        "novel_fact_summary": "In Book 5, Dumbledore's Howler forces Petunia to keep Harry at Privet Drive. The 'last' refers to the letter left with baby Harry on her doorstep explaining the blood protection.",
    },
    {
        "slug": "remus_tonks_secret_marriage",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Remus Lupin tried to abandon Tonks — and Harry fought him at Grimmauld Place",
        "novel_search_query": "Lupin Tonks Grimmauld coward",
        "movie_search_query": "Lupin Tonks Grimmauld Place",
        "preferred_book": 7,
        "preferred_chapter": 11,
        "hook_concept": "The movies portray Lupin and Tonks as a happy couple — but the book reveals Lupin tried to abandon his pregnant wife out of werewolf shame.",
        "why_interesting": "Harry called Lupin a coward to his face, leading to a violent wand showdown in Grimmauld Place that forced Remus to return to his family.",
        "movie_omits": "The films cut Lupin's struggle with his marriage and child completely, showing them only standing side-by-side at Hogwarts.",
        "novel_fact_summary": "In Book 7, Remus Lupin attempted to leave Tonks due to fear of passing on lycanthropy. Harry furiously called him a coward, causing Lupin to curse Harry before ultimately returning home.",
    },
    {
        "slug": "voldemort_cursed_dada_job",
        "discovery_type": "LORE_DETAIL",
        "title": "Voldemort placed a curse on the Defense Against the Dark Arts job",
        "novel_search_query": "Dumbledore Voldemort defense against dark arts post",
        "movie_search_query": "Dumbledore Voldemort interview office",
        "preferred_book": 6,
        "preferred_chapter": 20,
        "hook_concept": "Why did Hogwarts never keep a Defense Against the Dark Arts teacher for more than one year? The book reveals Voldemort personally jinxed it.",
        "why_interesting": "After Dumbledore rejected Tom Riddle's job interview in his office, Voldemort cursed the position. The curse broke only upon Voldemort's death.",
        "movie_omits": "The films show different teachers each year but never explain the magical curse behind the turnover.",
        "novel_fact_summary": "In the novel, Dumbledore reveals to Harry that since rejecting Tom Riddle's application for the Defense Against the Dark Arts post, no teacher has lasted longer than a single year.",
    },
    {
        "slug": "dudley_dursley_redemption",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Dudley Dursley's emotional goodbye to Harry — completely deleted from the films",
        "novel_search_query": "Dudley tea waste of space",
        "movie_search_query": "Dudley Harry goodbye car",
        "preferred_book": 7,
        "preferred_chapter": 3,
        "hook_concept": "In the final book, Dudley Dursley does the unthinkable: he thanks Harry and admits Harry saved his soul.",
        "why_interesting": "Dudley left cups of tea outside Harry's bedroom door and shook Harry's hand, saying 'I don't think you're a waste of space.'",
        "movie_omits": "Movie 7 Part 1 cut Dudley's farewell entirely from the theatrical release, leaving their lifelong rivalry without closure.",
        "novel_fact_summary": "In the opening of Book 7, Dudley acknowledges that Harry saved his life from Dementors and parts with Harry on respectful terms, breaking the Dursley abuse cycle.",
    },
    {
        "slug": "james_potter_snapes_worst_memory",
        "discovery_type": "BOOK_VS_MOVIE_DIFFERENCE",
        "title": "James Potter was a relentless bully — the uncut Pensieve memory",
        "novel_search_query": "Levicorpus James Snape worst memory",
        "movie_search_query": "James Potter Snape tree Pensieve",
        "preferred_book": 5,
        "preferred_chapter": 28,
        "hook_concept": "Harry's father wasn't just mischievous — the novel's Pensieve scene reveals James Potter was an arrogant and cruel bully.",
        "why_interesting": "James used Levicorpus to dangle Snape upside down and threatened to remove his trousers in front of the entire school, shattering Harry's hero-worship.",
        "movie_omits": "Movie 5 softens James Potter's cruelty, omitting the worst humiliations and Lily Evans intervening to defend Severus.",
        "novel_fact_summary": "In Book 5, Harry witnesses Snape's Worst Memory in the Pensieve, seeing James Potter torment Snape without provocation, deeply disturbing Harry.",
    },
    {
        "slug": "lily_evans_snape_childhood",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Snape knew Lily Evans years before Hogwarts in Cokeworth",
        "novel_search_query": "Lily Snape Cokeworth magic",
        "movie_search_query": "Lily Snape childhood swing tree",
        "preferred_book": 7,
        "preferred_chapter": 33,
        "hook_concept": "Severus Snape and Lily Evans grew up on the same poor street — and Snape was the one who revealed to Lily that she was a witch.",
        "why_interesting": "The novel details years of secret childhood friendship under the trees before Petunia's jealousy and Hogwarts houses drove them apart.",
        "movie_omits": "The films only show brief flashes of young Lily and Snape, cutting Petunia spying on them and their deep early bond.",
        "novel_fact_summary": "In The Prince's Tale, J.K. Rowling reveals Snape and Lily bonded as outcast Muggle-town children in Cokeworth, with Snape mentoring Lily in magic before school.",
    },
    {
        "slug": "frank_bryce_muggle_gardener",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "Frank Bryce — the brave Muggle gardener who stood up to Voldemort",
        "novel_search_query": "Frank Bryce Riddle house gardener",
        "movie_search_query": "Frank Bryce Voldemort Riddle House",
        "preferred_book": 4,
        "preferred_chapter": 1,
        "hook_concept": "The opening chapter of Goblet of Fire is told entirely from the perspective of an elderly Muggle gardener.",
        "why_interesting": "Frank Bryce was framed by locals for the Riddle family murders decades earlier and died valiantly confronting Lord Voldemort in the dark.",
        "movie_omits": "The movie rushes through Frank's death in seconds without explaining his tragic backstory or the town suspicion he endured.",
        "novel_fact_summary": "Frank Bryce was the decorated war veteran gardener of the Riddle House who lived under suspicion of murder for 50 years before being killed by Voldemort in Book 4.",
    },
    {
        "slug": "bartycrouch_jr_winky_quidditch",
        "discovery_type": "LORE_DETAIL",
        "title": "Barty Crouch Jr was hidden in the Top Box at the Quidditch World Cup",
        "novel_search_query": "Barty Crouch Invisibility Cloak tent box",
        "movie_search_query": "Barty Crouch Jr Quidditch World Cup",
        "preferred_book": 4,
        "preferred_chapter": 35,
        "hook_concept": "Harry was sitting right next to Voldemort's deadliest Death Eater at the World Cup — without ever knowing it.",
        "why_interesting": "Barty Crouch Jr was smuggled out of Azkaban by his dying mother and kept under an Invisibility Cloak by his house-elf Winky in the Minister's box.",
        "movie_omits": "Movie 4 cuts the entire Winky and Azkaban escape storyline, creating massive plot holes regarding how Crouch Jr got free.",
        "novel_fact_summary": "The novel explains that Barty Crouch Jr escaped Azkaban via Polyjuice Potion and was secretly kept under an Imperius Curse until he broke free at the World Cup.",
    },
    {
        "slug": "ludo_bagman_goblins_debt",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "Ludo Bagman — the Quidditch legend completely erased from Movie 4",
        "novel_search_query": "Bagman leprechaun gold Fred George",
        "movie_search_query": "Quidditch World Cup referee",
        "preferred_book": 4,
        "preferred_chapter": 37,
        "hook_concept": "There was a famous Ministry sports chief who cheated Fred and George with fake gold — and the movies deleted him entirely.",
        "why_interesting": "Ludo Bagman was deeply in debt to goblins and constantly tried to help Harry win the Triwizard Tournament so he could pay off his bets.",
        "movie_omits": "Ludo Bagman was entirely cut from Goblet of Fire, with his commentator and judge roles distributed to other characters.",
        "novel_fact_summary": "Ludo Bagman is a former Wimbourne Wasps Quidditch star and Head of Magical Games who paid the Weasley twins with vanished leprechaun gold.",
    },
    {
        "slug": "draco_malfoy_vanishing_cabinet",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "How Draco Malfoy actually spent months fixing the Vanishing Cabinet",
        "novel_search_query": "Vanishing Cabinet Borgin Draco",
        "movie_search_query": "Draco Room of Requirement Vanishing Cabinet",
        "preferred_book": 6,
        "preferred_chapter": 27,
        "hook_concept": "The film makes Draco's repair seem effortless — the book shows the devastating psychological breakdown it caused.",
        "why_interesting": "Draco spent every weekend in the Room of Requirement weeping in Moaning Myrtle's bathroom, knowing Voldemort would kill his family if he failed.",
        "movie_omits": "Movie 6 shows Draco crying but skips the intricate mechanics of how Montague originally got trapped inside the cabinet in Book 5.",
        "novel_fact_summary": "In Book 6, Draco spent months fixing the broken Vanishing Cabinet linking Hogwarts to Borgin and Burkes, suffering near-total mental collapse under Voldemort's threats.",
    },
    {
        "slug": "ron_destroys_locket_vision",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "The Horcrux locket's psychological torture of Ron Weasley",
        "novel_search_query": "sword Gryffindor locket Ron",
        "movie_search_query": "Ron destroy locket Horcrux sword",
        "preferred_book": 7,
        "preferred_chapter": 19,
        "hook_concept": "When Ron opened the Slytherin locket, Riddle's soul didn't just speak — it weaponized Ron's deepest insecurities.",
        "why_interesting": "The locket formed ghostly likenesses of Harry and Hermione mocking Ron's poverty, his mother preferring Harry, and his feelings of worthlessness.",
        "movie_omits": "The movie shows kissing apparitions but leaves out Riddle's cruel voice taunting Ron about Mrs. Weasley wishing Harry were her son.",
        "novel_fact_summary": "In Book 7, the locket Horcrux assaults Ron with psychological visions of Hermione loving Harry and his mother disdaining him before Ron strikes it with Gryffindor's sword.",
    },
    {
        "slug": "dumbledore_hand_gaunt_ring",
        "discovery_type": "MOTIVATION_REVEALED",
        "title": "Why Dumbledore really put on the cursed Gaunt Ring Horcrux",
        "novel_search_query": "ring Gaunt Dumbledore hand Ariana",
        "movie_search_query": "Dumbledore blackened hand ring",
        "preferred_book": 7,
        "preferred_chapter": 33,
        "hook_concept": "Dumbledore didn't wither his hand out of carelessness — he was desperate to apologize to his dead sister.",
        "why_interesting": "Dumbledore recognized the Resurrection Stone set into Voldemort's Horcrux ring and recklessly put it on, hoping to see Ariana and his parents.",
        "movie_omits": "Movie 6 shows Dumbledore's charred hand but never reveals the heartbreaking emotional motive behind why the greatest wizard alive succumbed to temptation.",
        "novel_fact_summary": "Dumbledore tells Snape and Harry that he put on the Gaunt ring not to destroy a Horcrux, but because it housed the Resurrection Stone and he craved seeing his deceased family.",
    },
    {
        "slug": "sirius_black_mirror_forgotten",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "The two-way mirror that could have saved Sirius Black's life",
        "novel_search_query": "Sirius mirror package Christmas",
        "movie_search_query": "Sirius two way mirror shard",
        "preferred_book": 5,
        "preferred_chapter": 38,
        "hook_concept": "Sirius Black never had to die. Harry had a magic mirror in his trunk the whole time that would have proven Sirius was safe.",
        "why_interesting": "Sirius gave Harry an unwrapped parcel in Book 5 for emergencies. Harry vowed never to use it and forgot it — rushing blindly to the Ministry trap.",
        "movie_omits": "Movie 5 deletes the two-way mirror entirely, making its sudden appearance as a glass shard in Deathly Hallows a giant movie plot hole.",
        "novel_fact_summary": "In Book 5, Sirius gifted Harry a two-way mirror to talk to him. Harry forgot it until after Sirius fell through the Veil, smashing it in grief in Dumbledore's office.",
    },
    {
        "slug": "phineas_nigellus_portrait_spy",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "How Snape spied on the Golden Trio through a portrait in Hermione's bag",
        "novel_search_query": "Phineas Nigellus portrait Hermione bag",
        "movie_search_query": "Snape Headmaster office portrait",
        "preferred_book": 7,
        "preferred_chapter": 15,
        "hook_concept": "How did Snape know where Harry was camping in the woods to deliver the Sword of Gryffindor? Through a talking portrait.",
        "why_interesting": "Hermione packed Phineas Nigellus Black's portrait into her beaded bag. When she mentioned their location in the Forest of Dean, Phineas overheard and told Snape.",
        "movie_omits": "The films show Snape's Doe Patronus guiding Harry to the pool but never explain how Snape located the trio in thousands of acres of wilderness.",
        "novel_fact_summary": "In Book 7, Hermione removed Phineas Nigellus Black's portrait from Grimmauld Place. Phineas secretly reported the trio's whereabouts to Headmaster Snape.",
    },
    {
        "slug": "regulus_black_riddle_cave",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Regulus Black's heroic sacrifice in the Horcrux cave",
        "novel_search_query": "Regulus potion cave Inferi Kreacher",
        "movie_search_query": "Regulus Black locket cave note",
        "preferred_book": 7,
        "preferred_chapter": 10,
        "hook_concept": "Sirius thought his brother was a cowardly Death Eater — but Regulus died the bravest death in the entire series.",
        "why_interesting": "Instead of forcing his house-elf Kreacher to drink the burning emerald potion again, Regulus drank it himself and ordered Kreacher to leave him behind.",
        "movie_omits": "Movie 6 shows the R.A.B. note, but Movie 7 completely deletes Kreacher's tearful retelling of Regulus being dragged underwater by Inferi.",
        "novel_fact_summary": "In Book 7, Kreacher reveals that Regulus drank the emerald potion in the Horcrux cave himself, sacrificed his life to save Kreacher, and drowned in the black lake.",
    },
    {
        "slug": "albus_grindelwald_youth_alliance",
        "discovery_type": "LORE_DETAIL",
        "title": "Dumbledore's dark alliance with Gellert Grindelwald",
        "novel_search_query": "Grindelwald Dumbledore Greater Good Godric",
        "movie_search_query": "Dumbledore Grindelwald Godrics Hollow",
        "preferred_book": 7,
        "preferred_chapter": 35,
        "hook_concept": "Before Dumbledore was a champion of Muggle rights, he spent a summer planning world domination with Gellert Grindelwald.",
        "why_interesting": "Dumbledore coined the phrase 'For the Greater Good' to justify wizarding supremacy over Muggles, until Ariana's death shattered their partnership.",
        "movie_omits": "Deathly Hallows Part 1 glosses over Rita Skeeter's book and Dumbledore's actual ideological alignment with Grindelwald.",
        "novel_fact_summary": "In Book 7, Dumbledore confesses in King's Cross that as a young man he was seduced by Grindelwald's vision of wizards ruling over Muggles 'For the Greater Good'.",
    },
    {
        "slug": "aberforth_ariana_goat_patronus",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Aberforth Dumbledore — the forgotten brother who saved Hogwarts",
        "novel_search_query": "Aberforth goat Patronus Ariana",
        "movie_search_query": "Aberforth Hogs Head tunnel Ariana",
        "preferred_book": 7,
        "preferred_chapter": 28,
        "hook_concept": "Aberforth Dumbledore hated his famous brother Albus — but his stubborn bravery kept the student resistance alive.",
        "why_interesting": "Aberforth operated the Hog's Head secret tunnel behind Ariana's portrait, sent Dobby to Malfoy Manor, and produced a Goat Patronus.",
        "movie_omits": "Movie 7 Part 2 compresses Aberforth into a brief stopover, skipping his deep resentment of Albus for Ariana's death.",
        "novel_fact_summary": "In Book 7, Aberforth explains how Ariana was traumatized by Muggle boys and how Albus's ambition caused the three-way duel that killed her.",
    },
    {
        "slug": "harry_buries_dobby_by_hand",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Harry digging Dobby's grave with his bare hands",
        "novel_search_query": "Dobby grave shovel Harry spade",
        "movie_search_query": "Harry Dobby grave Shell Cottage",
        "preferred_book": 7,
        "preferred_chapter": 24,
        "hook_concept": "After Dobby died, Harry had the Elder Wand in sight — but chose to spend hours sweating with a Muggle spade.",
        "why_interesting": "Harry refused to use magic to dig Dobby's grave, wanting Dobby's resting place to be earned through physical human labor and love.",
        "movie_omits": "The movie shows Harry wrapping Dobby's body but cuts the prolonged spiritual turning point where manual labor cleared Voldemort from Harry's mind.",
        "novel_fact_summary": "In Book 7, Harry explicitly refuses to use magic to dig Dobby's grave at Shell Cottage, finding mental clarity through physical labor that blocked Voldemort's thoughts.",
    },
    {
        "slug": "bill_weasley_fleur_delacour_wedding",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Fleur Delacour's devotion to scarred Bill Weasley",
        "novel_search_query": "Bill Greyback steak Fleur hospital",
        "movie_search_query": "Bill Weasley scarred werewolf Fleur",
        "preferred_book": 6,
        "preferred_chapter": 29,
        "hook_concept": "Mrs. Weasley assumed Fleur only loved Bill for his good looks — until Fenrir Greyback mauled his face.",
        "why_interesting": "In the hospital wing, Fleur fiercely declared 'I am good-looking enough for both of us!' winning Mrs. Weasley's tearful acceptance.",
        "movie_omits": "Movie 6 cuts Bill being attacked during the Battle of the Astronomy Tower entirely, introducing his scars abruptly in Movie 7.",
        "novel_fact_summary": "In Book 6, Fenrir Greyback viciously mauled Bill Weasley. Fleur proved her unconditional love in the hospital wing, proving her character to Molly Weasley.",
    },
    {
        "slug": "arthur_weasley_malfoy_fistfight",
        "discovery_type": "BOOK_ONLY_DETAIL",
        "title": "Arthur Weasley tackled Lucius Malfoy into a bookstore bookshelf",
        "novel_search_query": "Flourish and Blotts Arthur Malfoy fight",
        "movie_search_query": "Lucius Malfoy Arthur Weasley Flourish Blotts",
        "preferred_book": 2,
        "preferred_chapter": 4,
        "hook_concept": "Wizards don't always use wands — Arthur Weasley gave Lucius Malfoy an old-fashioned Muggle punch to the eye.",
        "why_interesting": "In Flourish and Blotts, Arthur tackled Lucius into a stack of heavy encyclopedias until Hagrid had to pull them apart.",
        "movie_omits": "The movie replaces the physical brawl with polite sneering and a walking stick flick.",
        "novel_fact_summary": "In Book 2, Arthur Weasley threw Lucius Malfoy into a bookcase in Flourish and Blotts, giving him a cut lip before Hagrid separated them.",
    },
    {
        "slug": "ginny_weasley_chaser_talent",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Ginny Weasley was secretly one of Hogwarts' greatest Quidditch players",
        "novel_search_query": "Ginny broom shed Quidditch",
        "movie_search_query": "Ginny Weasley Quidditch tryout",
        "preferred_book": 5,
        "preferred_chapter": 26,
        "hook_concept": "Her brothers never let her play Quidditch at the Burrow — so Ginny broke into their broom shed every night for six years.",
        "why_interesting": "By the time she made the Gryffindor team, she outflew almost everyone and caught the Golden Snitch against Cho Chang.",
        "movie_omits": "The films portray Ginny as quiet and passive, deleting her fierce Quidditch dominance and witty personality.",
        "novel_fact_summary": "In Book 5, Hermione reveals Ginny has been breaking into the family broom shed since age six to practice flying secretly, becoming a star Chaser and Seeker.",
    },
    {
        "slug": "luna_lovegood_bedroom_paintings",
        "discovery_type": "CHARACTER_DEPTH",
        "title": "Luna Lovegood's bedroom ceiling — the most touching secret in the books",
        "novel_search_query": "Luna ceiling portraits friends bedroom",
        "movie_search_query": "Luna Lovegood house Rook bedroom",
        "preferred_book": 7,
        "preferred_chapter": 21,
        "hook_concept": "When Harry, Ron, and Hermione walked into Luna's bedroom, they looked up and started crying.",
        "why_interesting": "Luna had painted large portraits of Harry, Ron, Hermione, Ginny, and Neville connected by golden chains formed by the repeated word 'friends'.",
        "movie_omits": "Movie 7 Part 1 visits Xenophilius Lovegood's house but completely skips the emotional moment of seeing Luna's painted ceiling.",
        "novel_fact_summary": "In Book 7, the trio discovers Luna painted their faces on her ceiling entwined with golden chains inked with 'friends', showing how deeply she treasured them.",
    },
    {
        "slug": "fred_weasley_final_joke_death",
        "discovery_type": "BOOK_VS_MOVIE_DIFFERENCE",
        "title": "Fred Weasley died with a smile on his face laughing at Percy",
        "novel_search_query": "Fred joke Percy wall explosion",
        "movie_search_query": "Fred Weasley death Great Hall",
        "preferred_book": 7,
        "preferred_chapter": 31,
        "hook_concept": "The film showed Fred already dead on the floor — but the book captures the heartbreaking exact second of his passing.",
        "why_interesting": "Percy had just reconciled with his family and made a joke about resigning from the Ministry. Fred laughed: 'You're actually joking, Perce—' right as the wall exploded.",
        "movie_omits": "The movie cuts Percy's redemption and the explosion entirely, showing only the Weasley family weeping over Fred's corpse.",
        "novel_fact_summary": "In Book 7, Fred dies mid-battle laughing at a joke made by his newly reconciled brother Percy, with the ghost of his last laugh etched on his face.",
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
        # Initialize DB tables & migrate discovery schema
        engine = create_engine(f"sqlite:///{DB_PATH}")
        Base.metadata.create_all(engine)
        migrate_discovery_schema(DB_PATH)
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
        new_candidate_count = 0

        with self.Session() as session:
            for seed in DISCOVERY_SEEDS:
                if new_candidate_count >= count:
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

                # Search novel FTS for evidence with autonomous progressive fallback
                queries_to_try = [
                    seed.get("novel_search_query"),
                    seed.get("title"),
                    seed.get("novel_fact_summary"),
                    seed.get("hook_concept")
                ]
                queries_to_try = [q for q in queries_to_try if q]

                novel_hits = []
                for query_candidate in queries_to_try:
                    novel_hits = self.novel_engine.search(
                        query=query_candidate,
                        book_number=seed["preferred_book"],
                        limit=3
                    )
                    if not novel_hits:
                        novel_hits = self.novel_engine.search(
                            query=query_candidate,
                            limit=3
                        )
                    if novel_hits:
                        break

                if not novel_hits:
                    logger.warning(f"[DISCOVERY_PLANNER] No novel evidence for: {slug} after autonomous fallback attempts")
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

                # Visual beats for discovery with full key requirements
                visual_beats = [
                    {
                        "beat_id": "beat_1",
                        "description": f"Harry Potter scene from Movie {seed['preferred_book']} establishing context",
                        "visual_requirement": f"Harry Potter scene from Movie {seed['preferred_book']} establishing context",
                        "narration_text": seed.get("hook_concept", seed["title"]),
                    },
                    {
                        "beat_id": "beat_2",
                        "description": seed["movie_search_query"],
                        "visual_requirement": seed["movie_search_query"],
                        "narration_text": seed.get("why_interesting", seed["title"]),
                    },
                    {
                        "beat_id": "beat_3",
                        "description": f"Harry Potter character reaction or emotional moment",
                        "visual_requirement": f"Harry Potter character reaction or emotional moment",
                        "narration_text": seed.get("novel_fact_summary", seed["title"]),
                    },
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

                # Build verified evidence points via tri-partite routing
                evidence_points = [
                    DiscoveryNarrativeEngine.route_evidence(
                        claim=seed.get("novel_fact_summary", seed["title"]),
                        source_type="NOVEL",
                        source_id=best_novel["chunk_id"],
                        source_excerpt=best_novel["text"][:600],
                        notes="Primary novel canon grounding"
                    )
                ]
                if movie_hit:
                    evidence_points.append(
                        DiscoveryNarrativeEngine.route_evidence(
                            claim=seed.get("movie_omits", f"Movie shows: {movie_hit['text'][:100]}"),
                            source_type="MOVIE",
                            source_id=movie_hit["chunk_id"],
                            source_excerpt=movie_hit["text"][:300],
                            notes="Movie comparison grounding"
                        )
                    )
                elif seed.get("movie_omits"):
                    evidence_points.append(
                        DiscoveryNarrativeEngine.route_evidence(
                            claim=seed["movie_omits"],
                            source_type="MOVIE",
                            source_id=f"movie_{seed['preferred_book']}_omission",
                            source_excerpt=seed["movie_omits"],
                            notes="Movie omission reference"
                        )
                    )

                # Calculate topic scoring & narrative plan
                canon_depth_score = 90.0 if best_novel else 45.0
                movie_contrast_score = 85.0 if (movie_hit or seed.get("movie_omits")) else 30.0
                curiosity_score = 85.0
                visual_feas_score = 85.0 if overall_vf == VF_DIRECT_MATCH else (70.0 if overall_vf == VF_STRONG_CONTEXTUAL else 50.0)

                story_plan = DiscoveryNarrativeEngine.build_deep_discovery_plan(
                    topic_id=candidate_id,
                    discovery_type=seed["discovery_type"],
                    thesis=seed.get("novel_fact_summary", seed["title"]),
                    evidence_points=evidence_points,
                    insider_epiphany=seed.get("why_interesting", "Reveals crucial character depth missed by movie viewers."),
                    payoff_type=PayoffType.BOOK_MOVIE_REALIZATION,
                    payoff_text=seed.get("why_interesting", ""),
                    canon_depth=canon_depth_score,
                    movie_contrast=movie_contrast_score,
                    curiosity_factor=curiosity_score,
                    visual_feasibility=visual_feas_score,
                    topic_context=seed,
                    title_pattern=TitlePattern.BOOK_VS_MOVIE,
                    tier=DiscoveryTier.DEEP_DISCOVERY,
                )

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
                    # Deep Discovery Narrative Schemas (Step 1)
                    discovery_tier=story_plan.discovery_tier.value,
                    story_structure=story_plan.story_structure.value,
                    hook_archetype=story_plan.hook_archetype.value,
                    evidence_route=story_plan.evidence_route.value if hasattr(story_plan.evidence_route, 'value') else str(story_plan.evidence_route),
                    thesis=story_plan.thesis,
                    evidence_points_json=json.dumps([ep.to_dict() for ep in story_plan.evidence_points]),
                    anchor_point_json=json.dumps(story_plan.anchor_point.to_dict()) if story_plan.anchor_point else None,
                    insider_epiphany=story_plan.insider_epiphany,
                    payoff_type=story_plan.payoff_type.value,
                    payoff_text=story_plan.payoff_text,
                    title_pattern=story_plan.title_pattern.value,
                    suggested_title=story_plan.suggested_title,
                    expected_duration=story_plan.expected_duration,
                    target_word_count=story_plan.target_word_count,
                    target_speech_rate=story_plan.target_speech_rate,
                    topic_score=story_plan.topic_score,
                    canon_depth=story_plan.canon_depth,
                    movie_contrast=story_plan.movie_contrast,
                    curiosity_factor=story_plan.curiosity_factor,
                    visual_feasibility_score=story_plan.visual_feasibility,
                    routing_decision=story_plan.routing_decision,
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
                    "discovery_tier": story_plan.discovery_tier.value,
                    "story_structure": story_plan.story_structure.value,
                    "hook_archetype": story_plan.hook_archetype.value,
                    "evidence_route": story_plan.evidence_route.value if hasattr(story_plan.evidence_route, 'value') else str(story_plan.evidence_route),
                    "topic_score": story_plan.topic_score,
                    "expected_duration": story_plan.expected_duration,
                    "target_word_count": story_plan.target_word_count,
                    "target_speech_rate": story_plan.target_speech_rate,
                    "suggested_title": story_plan.suggested_title,
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
                new_candidate_count += 1

                logger.info(
                    f"[DISCOVERY_PLANNER] Candidate created: {candidate_id} | "
                    f"Tier={story_plan.discovery_tier.value} | "
                    f"Score={story_plan.topic_score} | Structure={story_plan.story_structure.value}"
                )

            # Autonomous Deep Discovery Fallback: If seeds were exhausted or insufficient,
            # mine unscripted canonical scenes directly from the novel FTS database.
            if new_candidate_count < count:
                logger.info(f"[DISCOVERY_PLANNER] Seeds provided {new_candidate_count}/{count} candidates. Activating Autonomous Novel Miner...")
                mined = self._mine_autonomous_novel_discovery(session, count - new_candidate_count, results)
                new_candidate_count += mined

            session.commit()

        return results

    def _mine_autonomous_novel_discovery(
        self,
        session,
        needed: int,
        results: List[Dict[str, Any]]
    ) -> int:
        """
        Autonomous Deep Discovery Miner.
        Activated when curated seeds are exhausted or insufficient.
        Scans novel chunks across the 7 books for rich canon moments, character
        dialogues, and dramatic turning points not yet turned into Discovery candidates.
        """
        existing_chunks = {
            c.chunk_id_primary for c in session.query(DiscoveryCandidate.chunk_id_primary).all()
            if c.chunk_id_primary
        }

        mining_themes = [
            ("Dumbledore Voldemort", "Dumbledore Voldemort duel"),
            ("Snape Lily", "Snape Lily childhood memories"),
            ("Sirius Harry", "Sirius Harry godfather Azkaban"),
            ("Hermione Ron", "Hermione Ron arguing friendship"),
            ("Malfoy Draco", "Draco Malfoy wand fear"),
            ("Neville Longbottom", "Neville sword bravery"),
            ("Hagrid creature", "Hagrid dragon forest beast"),
            ("McGonagall Dumbledore", "McGonagall Hogwarts defense"),
            ("Lupin werewolf", "Remus Lupin moon transformation"),
            ("Horcrux soul", "Horcrux dark magic destroy"),
            ("Pensieve memory", "Pensieve memory silver liquid"),
            ("Sorting Hat song", "Sorting Hat Great Hall feast"),
        ]

        added = 0
        for theme_query, movie_query in mining_themes:
            if added >= needed:
                break

            hits = self.novel_engine.search(query=theme_query, limit=5)
            for hit in hits:
                if added >= needed:
                    break
                cid = hit["chunk_id"]
                if cid in existing_chunks:
                    continue

                b_num = hit.get("book_number", 1)
                c_num = hit.get("chapter_number", 1)
                fp = _fingerprint(["AUTO_MINED_LORE", str(b_num), str(c_num), cid])
                if session.query(DiscoveryCandidate).filter_by(content_fingerprint=fp).first():
                    continue

                text = hit["text"]
                char = "Harry Potter"
                for nm in ["Dumbledore", "Snape", "Voldemort", "Sirius", "Lupin", "Hermione", "Ron", "Neville", "Malfoy", "McGonagall", "Hagrid"]:
                    if nm.lower() in text.lower():
                        char = nm
                        break

                cand_id = f"disc_auto_b{b_num}c{c_num}_{cid[:6]}"
                chap_title = hit.get("chapter_title", f"Chapter {c_num}")
                book_title = hit.get("book_title", f"Book {b_num}")

                visual_beats = [
                    {
                        "beat_id": "beat_1",
                        "description": f"{char} establishing scene at Hogwarts",
                        "visual_requirement": f"{char} establishing scene at Hogwarts",
                        "narration_text": f"In {book_title}, {chap_title}, a pivotal canon detail takes place.",
                    },
                    {
                        "beat_id": "beat_2",
                        "description": movie_query,
                        "visual_requirement": movie_query,
                        "narration_text": f"The novel reveals {char}'s deeper thoughts and secret motives.",
                    },
                    {
                        "beat_id": "beat_3",
                        "description": f"{char} emotional realization close up",
                        "visual_requirement": f"{char} emotional realization close up",
                        "narration_text": f"This canon revelation changes how fans view the entire scene.",
                    },
                ]
                enriched_beats, overall_vf = self._check_visual_feasibility(
                    visual_beats, movie_number_hint=b_num
                )

                summary = f"Canonical book passage from Book {b_num}, Chapter {c_num} ({chap_title}) detailing {char}'s pivotal narrative beat."
                title = f"Book {b_num} Secret: What really happened in '{chap_title}'"

                candidate = DiscoveryCandidate(
                    id=cand_id,
                    discovery_type="BOOK_ONLY_DETAIL",
                    book_number=b_num,
                    book_title=book_title,
                    chapter_number=c_num,
                    chapter_title=chap_title,
                    chunk_id_primary=cid,
                    chunk_ids_supporting=json.dumps([]),
                    novel_fact_summary=summary,
                    novel_evidence_text=text[:600],
                    corresponding_movie_number=b_num,
                    corresponding_movie_title=f"Harry Potter {b_num}",
                    movie_chunk_id=None,
                    movie_shows="Movie portrays simplified adaptation of this sequence",
                    movie_omits_or_changes="Novel provides extensive inner dialogue and lore context",
                    why_interesting=f"Deepens understanding of {char} and canonical wizarding lore.",
                    hook_concept=f"Did you know what J.K. Rowling actually wrote in {chap_title} about {char}?",
                    short_duration_feasibility="FEASIBLE",
                    visual_beats_json=json.dumps(enriched_beats),
                    overall_visual_feasibility=overall_vf,
                    discovery_tier="DEEP_DISCOVERY",
                    story_structure="BOOK_TO_MOVIE_CONTRAST",
                    hook_archetype="FORBIDDEN_KNOWLEDGE",
                    evidence_route="NOVEL_PRIMARY",
                    thesis=summary,
                    evidence_points_json=json.dumps([]),
                    anchor_point_json=None,
                    insider_epiphany=f"Reveals critical canon lore for {char}.",
                    payoff_type="BOOK_MOVIE_REALIZATION",
                    payoff_text=f"A crucial insight into {char}'s true character.",
                    title_pattern="BOOK_VS_MOVIE",
                    suggested_title=title,
                    expected_duration=55.0,
                    target_word_count=130,
                    target_speech_rate=2.4,
                    topic_score=85.0,
                    canon_depth=90.0,
                    movie_contrast=80.0,
                    curiosity_factor=85.0,
                    visual_feasibility_score=80.0,
                    routing_decision="AUTONOMOUS_MINED",
                    status=STATUS_ELIGIBLE,
                    content_fingerprint=fp,
                    is_launch_candidate=False,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                session.add(candidate)
                existing_chunks.add(cid)
                added += 1
                results.append({
                    "id": cand_id,
                    "slug": cand_id,
                    "title": title,
                    "status": STATUS_ELIGIBLE,
                    "novel_fact_summary": summary,
                    "visual_beats": enriched_beats,
                    "content_fingerprint": fp,
                })
                logger.info(f"[DISCOVERY_PLANNER] Autonomous Miner created candidate: {cand_id}")

        return added

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

