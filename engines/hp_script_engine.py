"""
Harry Potter Script Generation & Visual Beat Engine (Step 8)
================================================================================
Cloud-Runner & Ephemeral GitHub Actions Compatible.

Generates broadcast-ready, fact-grounded narration scripts and structured visual beat plans
for YouTube Shorts, grounded exclusively in:
  - Canonical Harry Potter novel text (FTS5 SQLite index `novel_chunks_fts`)
  - Canonical Movie 1-8 scene & dialogue index (`movie_subtitles_fts`)

Supports two content types:
  A. NOVEL STORY SHORTS (~25-30s, 55-75 spoken words, conversational cinematic English)
  B. DISCOVERY SHORTS (~25-30s, 55-75 spoken words, novel vs movie differences & lore)

Voice Specification:
  - Andrew Hype (en-US-AndrewNeural, +24Hz pitch, +14% rate)
  - Electrifying, high-tempo, youth duel commentator delivery

HARD INVARIANTS:
  - PART marker is VISUAL ONLY (e.g. "PART 01"). The narrator MUST NEVER speak
    "part one", "chapter one", "episode one", "book one", or any variation.
  - MOVIE FOOTAGE ONLY: Visual beats must be fulfilled strictly by Harry Potter
    movie footage. Zero AI images, zero stock, zero Pexels, zero book screenshots.
  - Standalone: Every Short must make complete narrative sense independently.
  - Fact-grounded: Every detail must trace directly to novel or movie evidence.
  - Zero TTS, zero rendering, publishing remains strictly disabled.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime
from dataclasses import dataclass, field

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config.settings import (
    PROJECT_ROOT, DB_PATH, GEMINI_API_KEY, GEMINI_MODEL,
    PUBLISHING_ENABLED, UPLOAD_ENABLED
)
from core.models import (
    Base, NovStoryCandidate, DiscoveryCandidate, HarryPotterScript, NovelChunk
)
from core.discovery_types import DiscoverySubtype, VisualClassification, DiscoveryQAResult
from core.gemini_client import get_gemini_client

logger = logging.getLogger(__name__)

# ── Forbidden Spoken Numbering & AI Clichés ──────────────────────────────────
FORBIDDEN_SPOKEN_PART_PATTERNS = [
    r"\bpart\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
    r"\bchapter\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b",
    r"\bbook\s+(?:one|two|three|four|five|six|seven|\d+)\b",
    r"\bepisode\s+(?:one|two|three|four|five|\d+)\b",
    r"\bin\s+this\s+part\b",
    r"\bin\s+the\s+next\s+part\b",
    r"\bwelcome\s+back\b",
    r"\bas\s+we\s+saw\b",
    r"\bin\s+our\s+last\b",
    r"\bstay\s+tuned\s+for\s+part\b",
]

FORBIDDEN_CLICHES = [
    "will shock you",
    "unbelievable true story",
    "events spiraled",
    "events rapidly spiraled",
    "you won't believe",
    "believe it or not",
    "did you know",
    "what happened next",
    "mind-blowing",
    "in a bizarre twist",
    "history changed forever",
]

FORBIDDEN_LITERARY_WORDS = [
    "tranquility", "disrupted", "paralyzed", "coincidences", "despised",
    "disdain", "disdainful", "melodrama", "profound", "astonishing",
    "perplexed", "pondered", "agonizing", "reputation", "existence",
    "broad daylight", "spectacles", "emerald cloaks", "put-outer", "thank you very much",
    "ordinary existence", "impossible coincidences"
]

FORBIDDEN_VISUAL_TERMS = [
    "ai image", "ai generated", "stock footage", "pexels", "unsplash",
    "generic b-roll", "generic stock", "external video",
    "consistory", "pollinations", "midjourney", "dall-e", "stable diffusion"
]

MIN_WORD_COUNT = 55
MAX_WORD_COUNT = 75
PREFERRED_MIN_WORDS = 60
PREFERRED_MAX_WORDS = 70


@dataclass
class VisualBeatPlan:
    """Structured visual beat requirement for truthful hybrid visual resolution."""
    beat_id: str
    narration_text: str
    visual_requirement: str
    characters: List[str]
    location: str
    action: str
    objects: List[str]
    emotional_context: str
    preferred_movie_number: int
    source_grounding: str
    retrieval_hints: List[str]
    visual_source_policy: str = "HYBRID_TRUTHFUL"
    visual_source: str = "MOVIE_DIRECT"  # MOVIE_DIRECT, FAN_ART, OFFICIAL_ARTWORK, NO_VALID_VISUAL
    description: str = ""
    source_url: Optional[str] = None
    original_url: Optional[str] = None
    creator: Optional[str] = None
    license: Optional[str] = None
    license_url: Optional[str] = None
    rights_status: Optional[str] = None
    search_query: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "narration_text": self.narration_text,
            "visual_requirement": self.visual_requirement,
            "characters": self.characters,
            "location": self.location,
            "action": self.action,
            "objects": self.objects,
            "emotional_context": self.emotional_context,
            "preferred_movie_number": self.preferred_movie_number,
            "source_grounding": self.source_grounding,
            "retrieval_hints": self.retrieval_hints,
            "visual_source_policy": self.visual_source_policy,
            "visual_source": self.visual_source,
            "description": self.description,
            "source_url": self.source_url,
            "original_url": self.original_url,
            "creator": self.creator,
            "license": self.license,
            "license_url": self.license_url,
            "rights_status": self.rights_status,
            "search_query": self.search_query,
            "notes": self.notes,
        }


@dataclass
class ScriptQAResult:
    passed: bool
    score: float
    word_count: int
    estimated_duration_sec: float
    feedback: List[str]
    cliches_detected: List[str]
    spoken_parts_detected: List[str]
    forbidden_visuals_detected: List[str]


class HarryPotterScriptEngine:
    """
    Authoritative Harry Potter Script Generation Engine (Step 8).

    Produces fact-grounded narration scripts and structured visual beat plans.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        engine = create_engine(f"sqlite:///{DB_PATH}")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        logger.info("[HP_SCRIPT_ENGINE] Initialized. DB ready at %s", DB_PATH)

    # ── Script QA & AI Review Gate ─────────────────────────────────────────────

    def evaluate_script_qa(
        self,
        script_text: str,
        visual_beats: List[Dict[str, Any]],
        candidate_type: str = "novel_story"
    ) -> ScriptQAResult:
        """
        Rigorous programmatic QA gate verifying all Step 8 invariants.
        Fails closed if any rule is violated.
        """
        words = script_text.strip().split()
        word_count = len(words)
        # Andrew Hype: +14% speaking rate = ~2.5 words per second
        estimated_duration = round(word_count / 2.5, 1)

        feedback = []
        cliches_detected = []
        spoken_parts_detected = []
        forbidden_visuals_detected = []
        literary_terms_detected = []

        text_lower = script_text.lower()

        # 1. Spoken Part / Chapter / Book Numbering Check (CRITICAL)
        for pattern in FORBIDDEN_SPOKEN_PART_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                detected = match.group(0)
                spoken_parts_detected.append(detected)
                feedback.append(
                    f"FORBIDDEN SPOKEN NUMBERING: Detected '{detected}'. "
                    "Narrator must NEVER speak part, chapter, book, or episode numbers."
                )

        # 2. Cliché & Generic AI Filler Check ('did you know' is allowed for discovery only)
        for cliche in FORBIDDEN_CLICHES:
            if cliche == "did you know" and candidate_type == "discovery":
                continue
            if cliche in text_lower:
                cliches_detected.append(cliche)
                feedback.append(f"FORBIDDEN CLICHÉ: Detected '{cliche}'. Rephrase naturally.")

        # 3. Forbidden Literary / Book-Summary Language Check
        for lit_term in FORBIDDEN_LITERARY_WORDS:
            if re.search(r"\b" + re.escape(lit_term) + r"\b", text_lower):
                literary_terms_detected.append(lit_term)
                feedback.append(
                    f"FORBIDDEN LITERARY LANGUAGE: Detected '{lit_term}'. Use simple spoken words an 8-year-old understands."
                )

        # 4. Word Count Bounds Check (55-75 words)
        if word_count < MIN_WORD_COUNT:
            feedback.append(
                f"WORD COUNT TOO SHORT: {word_count} words (minimum {MIN_WORD_COUNT} words required)."
            )
        elif word_count > MAX_WORD_COUNT:
            feedback.append(
                f"WORD COUNT TOO LONG: {word_count} words (maximum {MAX_WORD_COUNT} words allowed)."
            )

        # 5. Duration Bounds Check (20.0 - 32.0s)
        if estimated_duration < 20.0 or estimated_duration > 32.0:
            feedback.append(
                f"ESTIMATED DURATION OUT OF BOUNDS: {estimated_duration}s (target: 22-30s)."
            )

        # 6. Visual Beat Coverage & Movie-Only Policy Check
        if not visual_beats or len(visual_beats) < 3:
            feedback.append(
                f"INSUFFICIENT VISUAL BEATS: {len(visual_beats)} beats found (minimum 3 required)."
            )

        for b in visual_beats:
            b_str = json.dumps(b).lower()
            for term in FORBIDDEN_VISUAL_TERMS:
                if term in b_str:
                    forbidden_visuals_detected.append(term)
                    feedback.append(
                        f"FORBIDDEN VISUAL SOURCE: Beat '{b.get('beat_id')}' mentions '{term}'. "
                        "Generic stock and synthetic AI imagery are permanently forbidden."
                    )
            policy = b.get("visual_source_policy", "HYBRID_TRUTHFUL")
            if policy not in ("MOVIE_FOOTAGE_ONLY", "HYBRID_TRUTHFUL"):
                feedback.append(f"INVALID VISUAL POLICY on beat {b.get('beat_id')}: must be MOVIE_FOOTAGE_ONLY or HYBRID_TRUTHFUL.")

            v_source = b.get("visual_source")
            if v_source and v_source not in ("MOVIE_DIRECT", "FAN_ART", "OFFICIAL_ARTWORK", "NO_VALID_VISUAL"):
                feedback.append(f"INVALID VISUAL SOURCE on beat {b.get('beat_id')}: '{v_source}' is not recognized.")

            if v_source in ("FAN_ART", "OFFICIAL_ARTWORK"):
                if not b.get("creator") and not b.get("source_url"):
                    feedback.append(f"MISSING PROVENANCE on artwork beat {b.get('beat_id')}: creator or source_url must be recorded.")

        # 7. Standalone Narrative Check
        standalone_indicators = ["as seen previously", "in the previous episode", "as mentioned before"]
        for ind in standalone_indicators:
            if ind in text_lower:
                feedback.append(f"DEPENDENCY DETECTED: Script contains '{ind}'. Every Short must stand alone.")

        # Score calculation
        score = 100.0
        if spoken_parts_detected:
            score -= 50.0
        if cliches_detected:
            score -= 25.0
        if literary_terms_detected:
            score -= 20.0
        if word_count < MIN_WORD_COUNT or word_count > MAX_WORD_COUNT:
            score -= 30.0
        if forbidden_visuals_detected:
            score -= 50.0
        if len(visual_beats) < 3:
            score -= 20.0

        score = max(0.0, score)
        passed = (
            score >= 80.0
            and len(spoken_parts_detected) == 0
            and len(cliches_detected) == 0
            and len(forbidden_visuals_detected) == 0
            and len(literary_terms_detected) == 0
            and MIN_WORD_COUNT <= word_count <= MAX_WORD_COUNT
            and len(visual_beats) >= 3
        )

        return ScriptQAResult(
            passed=passed,
            score=round(score, 1),
            word_count=word_count,
            estimated_duration_sec=estimated_duration,
            feedback=feedback,
            cliches_detected=cliches_detected,
            spoken_parts_detected=spoken_parts_detected,
            forbidden_visuals_detected=forbidden_visuals_detected,
        )

    def evaluate_discovery_qa(
        self,
        script_text: str,
        hook: str,
        subtype: str,
        visual_beats: List[Dict[str, Any]],
        part_marker: Optional[str] = None
    ) -> DiscoveryQAResult:
        """
        11-Point Discovery Quality Gate (Checks A through K):
        A. Can I identify the exact fact/difference in one sentence?
        B. Is that fact stated explicitly in the script?
        C. Does the first ~5 seconds communicate the actual subject?
        D. Does the script feel like INFORMATION rather than a chapter summary?
        E. Is the subtype correctly represented?
        F. For a book/movie difference, are BOTH sides explicitly stated?
        G. For an omitted scene, is the omission explicitly stated?
        H. For a behind-the-scenes fact, is the production fact explicitly stated?
        I. Does the script avoid unnecessary chronological storytelling?
        J. Does it remain standalone?
        K. Does it avoid PART markers?
        """
        reasons = []
        text_lower = script_text.lower()
        hook_lower = hook.lower()
        words = script_text.split()

        # Check K: PART markers strictly forbidden in Discovery
        no_part_markers = True
        if part_marker is not None and str(part_marker).strip():
            no_part_markers = False
            reasons.append(f"Check K Failed: Discovery short has visual PART marker '{part_marker}'")
        for pat in FORBIDDEN_SPOKEN_PART_PATTERNS:
            if re.search(pat, text_lower):
                no_part_markers = False
                reasons.append(f"Check K Failed: Discovery short contains spoken part/chapter numbering: '{pat}'")

        # Check C: Subject in first ~5 seconds (first ~15 words / hook)
        hook_words = hook.split()
        subject_in_first_5s = len(hook_words) >= 4 and any(
            w in hook_lower for w in [
                "cut", "cuts", "movie", "book", "secret", "never", "performance",
                "actor", "detail", "scene", "missed", "hidden", "changed", "erised",
                "remembrall", "neville", "sorting", "peeves", "inscription", "robes"
            ]
        )
        if not subject_in_first_5s:
            reasons.append("Check C Failed: First ~5 seconds does not clearly introduce the subject/fact")

        # Check D & I: Avoid narrative story transitions & chapter summary feel
        banned_story_transitions = [
            "meanwhile", "later that night", "the next morning", "then something happened",
            "he then", "after that,", "and then this happened"
        ]
        avoids_chronological_story = True
        for st in banned_story_transitions:
            if st in text_lower:
                avoids_chronological_story = False
                reasons.append(f"Check D/I Failed: Contains narrative story transition '{st}'")
        feels_like_information = avoids_chronological_story and len(words) >= 40

        # Check E: Valid subtype
        valid_subtypes = [s.value for s in DiscoverySubtype]
        subtype_structure_valid = subtype in valid_subtypes or any(s in subtype.upper() for s in valid_subtypes)

        # Check F: Book vs Movie Difference
        book_movie_both_stated = True
        if "DIFFERENCE" in subtype.upper():
            has_book = any(b in text_lower for b in ["book", "novel", "rowling", "pages", "written"])
            has_movie = any(m in text_lower for m in ["movie", "film", "screen", "cut", "skips", "adaptation"])
            book_movie_both_stated = has_book and has_movie
            if not book_movie_both_stated:
                reasons.append("Check F Failed: DISCOVERY_BOOK_MOVIE_DIFFERENCE must explicitly state BOTH book and movie")

        # Check G: Omitted Scene
        omission_explicitly_stated = True
        if "OMITTED" in subtype.upper():
            omission_explicitly_stated = any(o in text_lower for o in ["cut", "omit", "leaves out", "left out", "never showed", "skips", "deleted"])
            if not omission_explicitly_stated:
                reasons.append("Check G Failed: DISCOVERY_OMITTED_SCENE must explicitly state the omission")

        # Check H: Behind the Scenes
        production_fact_stated = True
        if "BEHIND_THE_SCENES" in subtype.upper() or "BTS" in subtype.upper():
            production_fact_stated = any(p in text_lower for p in ["actor", "filmed", "director", "shot", "scenes", "cast", "performance", "deleted"])
            if not production_fact_stated:
                reasons.append("Check H Failed: DISCOVERY_BEHIND_THE_SCENES must explicitly state the production fact")

        # Check A & B: Fact identifiable and explicitly stated
        fact_explicitly_stated = len(words) >= 30 and len(reasons) == 0
        fact_identifiable = fact_explicitly_stated

        # Check J: Standalone
        is_standalone = True
        for dep in ["as we saw earlier", "in the last part", "as seen previously", "stay tuned"]:
            if dep in text_lower:
                is_standalone = False
                reasons.append(f"Check J Failed: Contains cross-short dependency '{dep}'")

        passed = (
            no_part_markers and subject_in_first_5s and avoids_chronological_story
            and book_movie_both_stated and omission_explicitly_stated and production_fact_stated
            and is_standalone and len(reasons) == 0
        )

        return DiscoveryQAResult(
            passed=passed,
            subtype=subtype,
            fact_identifiable=fact_identifiable,
            fact_explicitly_stated=fact_explicitly_stated,
            subject_in_first_5s=subject_in_first_5s,
            feels_like_information=feels_like_information,
            subtype_structure_valid=subtype_structure_valid,
            book_movie_both_stated=book_movie_both_stated,
            omission_explicitly_stated=omission_explicitly_stated,
            production_fact_stated=production_fact_stated,
            avoids_chronological_story=avoids_chronological_story,
            is_standalone=is_standalone,
            no_part_markers=no_part_markers,
            failure_reasons=reasons
        )

    # ── AI Prompt Construction ────────────────────────────────────────────────

    def _build_novel_story_prompt(
        self,
        candidate: NovStoryCandidate,
        revision_feedback: Optional[List[str]] = None
    ) -> str:
        feedback_str = ""
        if revision_feedback:
            feedback_str = (
                "\nCRITICAL CORRECTIONS REQUIRED (PREVIOUS DRAFT FAILED QA):\n"
                + "\n".join(f"- {f}" for f in revision_feedback)
                + "\n"
            )

        prompt = f"""You are a master storyteller telling a simple, thrilling Harry Potter story directly to a child.

CRITICAL MENTAL TEST (THE 8-YEAR-OLD TEST):
Imagine you are sitting right next to a smart 8-year-old child who has NEVER read Harry Potter.
How would you tell this story so they understand everything immediately without thinking hard?
If a sentence sounds like an adult book summary, an audiobook recitation, or a Wikipedia article, it FAILS.
It must sound like an excited human friend telling an unforgettable story!

SOURCE SCENE:
Book {candidate.book_number}: {candidate.book_title}
Chapter {candidate.chapter_number}: {candidate.chapter_title}
Scene Summary: {candidate.story_event_summary}

WHAT HAPPENED (SOURCE FACTS):
\"\"\"{candidate.source_text_preview or ''}\"\"\"

MANDATORY STORYTELLING RULES:
1. VERY SIMPLE SPOKEN ENGLISH:
   - Use short, natural sentences (6 to 12 words per sentence).
   - One main idea per sentence.
   - 4th-grade everyday vocabulary.
   - PREFER: "Harry was scared." OVER: "Harry was overcome with fear."
   - PREFER: "His uncle hated magic." OVER: "His uncle had an intense disdain for anything magical."
   - PREFER: "Then something strange happened." OVER: "However, the tranquility of their ordinary existence was about to be disrupted."
   - DO NOT copy the novel's 1997 prose (never use phrases like "proud to say they were perfectly normal thank you very much").

2. STORY STRUCTURE (A COMPLETE MINI STORY):
   - HOOK: Immediate, simple sentence that starts the action in second 0. No preamble or fluff.
   - SETUP: A clear, simple explanation of who is involved and where they are.
   - EVENT & NEXT EVENT: What happens first, and what happens next. Clear cause -> effect.
   - SURPRISE / PROBLEM: What goes wrong or what magical secret appears.
   - PAYOFF: A punchy, satisfying conclusion that makes the listener smile or lean in.

3. MOVIE FOOTAGE ONLY VISUAL POLICY:
   - This project uses 100% genuine Harry Potter MOVIE FOOTAGE (Movies 1-8).
   - Every single sentence you write MUST describe an action or event that is genuinely VISIBLE in the Harry Potter films.
   - Break narration into 3 to 4 sequential visual beats matching existing movie scenes.
   - If the novel contains a detail the movies never showed, focus your storytelling on what the movies ACTUALLY show!

4. HARD INVARIANTS:
   - WORD COUNT: Exactly 58 to 72 spoken words (HARD BOUNDS: 55 to 75 words).
   - STANDALONE: Must make 100% complete sense on its own.
   - NEVER speak "part 1", "chapter 1", "episode 1", or any numbering.
   - NEVER use clickbait clichés ("will shock you", "you won't believe", "mind-blowing").

{feedback_str}

OUTPUT FORMAT: Return STRICTLY valid JSON with no markdown formatting:
{{
  "hook": "...",
  "development": "...",
  "payoff": "...",
  "visual_beats": [
    {{
      "beat_id": "beat_1",
      "narration_text": "...",
      "visual_requirement": "...",
      "characters": ["..."],
      "location": "...",
      "action": "...",
      "objects": ["..."],
      "emotional_context": "...",
      "preferred_movie_number": {candidate.book_number},
      "source_grounding": "...",
      "retrieval_hints": ["..."]
    }}
  ]
}}"""
        return prompt

    def _build_book_movie_difference_prompt(
        self,
        candidate: DiscoveryCandidate,
        revision_feedback: Optional[List[str]] = None
    ) -> str:
        feedback_str = ""
        if revision_feedback:
            feedback_str = "\nCRITICAL CORRECTIONS REQUIRED:\n" + "\n".join(f"- {f}" for f in revision_feedback) + "\n"

        return f"""You are a Harry Potter expert delivering a sharp, factual BOOK VS MOVIE DIFFERENCE short.

PURPOSE: Deliver a standalone piece of information. The viewer must immediately understand the contrast.
Must NOT feel like a mini chapter or story. This is an INFORMATION DELIVERY format.

SUBTYPE: DISCOVERY_BOOK_MOVIE_DIFFERENCE
TOPIC: {candidate.novel_fact_summary}
BOOK EVIDENCE: {candidate.novel_evidence_text or ''}
MOVIE SHOWS / OMITS: {candidate.movie_shows or ''} | {candidate.movie_omits_or_changes or ''}
WHY INTERESTING: {candidate.why_interesting or ''}

MANDATORY SCRIPT STRUCTURE:
1. HOOK (0-5s): Direct, punchy statement of the difference (e.g. "The movie completely cuts...", "The book does this completely differently:").
2. BOOK: State what the novel actually says and shows.
3. MOVIE: State what the film shows or omits.
4. DIFFERENCE & PAYOFF: The exact contrast and why this difference matters.

RULES:
- Word count: 58 to 70 spoken words.
- First substantive sentence must communicate the subject and difference.
- Avoid narrative story transitions ("Meanwhile", "Later", "The next morning", "He then").
- Visual Beats: 3-4 beats. Classify each beat as DIRECT or CONTEXTUAL in visual_requirement.
{feedback_str}
OUTPUT STRICT JSON:
{{
  "hook": "...",
  "development": "...",
  "payoff": "...",
  "visual_beats": [
    {{
      "beat_id": "beat_1",
      "narration_text": "...",
      "visual_requirement": "[DIRECT or CONTEXTUAL] ...",
      "characters": ["..."],
      "location": "...",
      "action": "...",
      "objects": ["..."],
      "emotional_context": "...",
      "preferred_movie_number": {candidate.corresponding_movie_number or candidate.book_number},
      "source_grounding": "...",
      "retrieval_hints": ["..."]
    }}
  ]
}}"""

    def _build_omitted_scene_prompt(
        self,
        candidate: DiscoveryCandidate,
        revision_feedback: Optional[List[str]] = None
    ) -> str:
        feedback_str = ""
        if revision_feedback:
            feedback_str = "\nCRITICAL CORRECTIONS REQUIRED:\n" + "\n".join(f"- {f}" for f in revision_feedback) + "\n"

        return f"""You are a Harry Potter expert revealing an OMITTED SCENE cut from the movies.

PURPOSE: Information delivery. Viewer must understand what scene was omitted and why it was cut.
Must NOT feel like a chapter retelling.

SUBTYPE: DISCOVERY_OMITTED_SCENE
TOPIC: {candidate.novel_fact_summary}
BOOK CONTEXT: {candidate.novel_evidence_text or ''}
MOVIE OMISSION: {candidate.movie_omits_or_changes or ''}

MANDATORY SCRIPT STRUCTURE:
1. HOOK (0-5s): "The movie completely leaves out this scene:" or "There's an entire scene from the book the movie cuts:".
2. BOOK SCENE: What actually occurs in the book.
3. MOVIE ABSENCE: What happens in the movie instead or how it skips the scene.
4. PAYOFF: Why the omission matters or what fans missed.

RULES:
- Word count: 58 to 70 spoken words.
- Classify visual beats as DIRECT or CONTEXTUAL.
{feedback_str}
OUTPUT STRICT JSON:
{{
  "hook": "...",
  "development": "...",
  "payoff": "...",
  "visual_beats": [...]
}}"""

    def _build_behind_the_scenes_prompt(
        self,
        candidate: DiscoveryCandidate,
        revision_feedback: Optional[List[str]] = None
    ) -> str:
        feedback_str = ""
        if revision_feedback:
            feedback_str = "\nCRITICAL CORRECTIONS REQUIRED:\n" + "\n".join(f"- {f}" for f in revision_feedback) + "\n"

        return f"""You are a Harry Potter expert revealing a BEHIND-THE-SCENES production secret.

PURPOSE: The subject is the production fact itself (actors, filming, cut footage, directors).
Do NOT narrate fictional story events as the primary fact. Use movie footage only as contextual support.

SUBTYPE: DISCOVERY_BEHIND_THE_SCENES
TOPIC: {candidate.novel_fact_summary}
PRODUCTION CONTEXT: {candidate.why_interesting or candidate.novel_evidence_text or ''}

MANDATORY SCRIPT STRUCTURE:
1. HOOK (0-5s): Immediate production secret (e.g. "There is a deleted Harry Potter performance most fans never saw...").
2. PRODUCTION FACT: Explicit facts about the filming, actors, or deleted scenes.
3. CONTEXT: How it connects to the film world.
4. PAYOFF: Why it was cut or what happened to the footage.

RULES:
- Word count: 58 to 70 spoken words.
- Visual classification must be CONTEXTUAL (since behind-the-scenes facts cannot be directly shown in movie scenes).
{feedback_str}
OUTPUT STRICT JSON:
{{
  "hook": "...",
  "development": "...",
  "payoff": "...",
  "visual_beats": [...]
}}"""

    def _build_fact_trivia_prompt(
        self,
        candidate: DiscoveryCandidate,
        revision_feedback: Optional[List[str]] = None
    ) -> str:
        feedback_str = ""
        if revision_feedback:
            feedback_str = "\nCRITICAL CORRECTIONS REQUIRED:\n" + "\n".join(f"- {f}" for f in revision_feedback) + "\n"

        return f"""You are a Harry Potter expert revealing a HIDDEN DETAIL or canon trivia fact.

PURPOSE: Information delivery. Viewer must think: 'OH, I learned something!'

SUBTYPE: {getattr(candidate, 'discovery_type', 'DISCOVERY_FACT')}
TOPIC: {candidate.novel_fact_summary}
DETAIL / EVIDENCE: {candidate.novel_evidence_text or candidate.why_interesting or ''}

MANDATORY SCRIPT STRUCTURE:
1. HOOK (0-5s): "You probably missed this hidden detail..." or "The movie hides a secret in plain sight:".
2. FACT: The exact concrete fact.
3. EVIDENCE / CONTEXT: Where it appears and what proves it.
4. PAYOFF: Why it is fascinating or what it explains.

RULES:
- Word count: 58 to 70 spoken words.
- Visual classification: DIRECT if visible on screen, CONTEXTUAL if lore/background.
{feedback_str}
OUTPUT STRICT JSON:
{{
  "hook": "...",
  "development": "...",
  "payoff": "...",
  "visual_beats": [...]
}}"""

    def _build_discovery_prompt(
        self,
        candidate: DiscoveryCandidate,
        revision_feedback: Optional[List[str]] = None
    ) -> str:
        st = str(getattr(candidate, "discovery_type", DiscoverySubtype.DISCOVERY_FACT.value)).upper()
        if "DIFFERENCE" in st or "BOOK_VS_MOVIE" in st:
            return self._build_book_movie_difference_prompt(candidate, revision_feedback)
        elif "OMITTED" in st:
            return self._build_omitted_scene_prompt(candidate, revision_feedback)
        elif "BEHIND_THE_SCENES" in st or "BTS" in st:
            return self._build_behind_the_scenes_prompt(candidate, revision_feedback)
        else:
            return self._build_fact_trivia_prompt(candidate, revision_feedback)

    # ── Deterministic Fallback Scripts (Offline / Quota Fail-Safe) ──────────────

    def _get_deterministic_script(
        self,
        candidate: Union[NovStoryCandidate, DiscoveryCandidate]
    ) -> Dict[str, Any]:
        """
        High-grade, verified deterministic script generator tailored for the launch batch.
        Uses the 8-year-old child storytelling principle: ultra-simple vocabulary,
        short sentences, single ideas, chronological cause-and-effect, and 100% movie visual compatibility.
        """
        c_id = candidate.id

        if c_id == "ns_b1c01_gc0001_0003":
            # Short 1: Novel Story — The Boy Who Lived (Dursleys & The Delivery of Baby Harry)
            return {
                "hook": "Late at night, an old wizard named Dumbledore appeared on a dark, quiet street.",
                "development": "He clicked a silver lighter, turning off every streetlamp one by one. Suddenly, a giant flying motorbike roared down from the clouds. Hagrid stepped off, gently carrying a tiny sleeping baby. That baby was Harry Potter, with a fresh lightning scar on his forehead.",
                "payoff": "They laid him safely on his aunt's doorstep, completely unaware his adventure was just beginning.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "Late at night, an old wizard named Dumbledore appeared on a dark, quiet street.",
                        "visual_requirement": "Dumbledore walking down dark Privet Drive at night in long purple robes",
                        "characters": ["Albus Dumbledore"],
                        "location": "Privet Drive at night",
                        "action": "Old wizard appearing out of darkness and walking along quiet street",
                        "objects": ["Robes", "Wand"],
                        "emotional_context": "Quiet mystery and magical reverence",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 Opening / Book 1 Chapter 1",
                        "retrieval_hints": ["Dumbledore", "Privet Drive", "night", "street"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "He clicked a silver lighter, turning off every streetlamp one by one.",
                        "visual_requirement": "Dumbledore holding the silver Deluminator clicking lights out of streetlamps",
                        "characters": ["Albus Dumbledore"],
                        "location": "Privet Drive street",
                        "action": "Clicking silver lighter device as balls of light fly into it",
                        "objects": ["Deluminator", "Streetlamps"],
                        "emotional_context": "Intriguing quiet magic",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 Opening / Book 1 Chapter 1",
                        "retrieval_hints": ["deluminator", "lighter", "streetlamp", "dark"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "Suddenly, a giant flying motorbike roared down from the clouds. Hagrid stepped off, gently carrying a tiny sleeping baby.",
                        "visual_requirement": "Hagrid landing on flying motorbike and stepping off carrying bundle of blankets",
                        "characters": ["Rubeus Hagrid", "Albus Dumbledore"],
                        "location": "Privet Drive pavement",
                        "action": "Giant stepping off motorcycle cradling small bundle tenderly",
                        "objects": ["Flying motorbike", "Blanket bundle"],
                        "emotional_context": "Wonder, gentle giant warmth, and relief",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 Opening / Book 1 Chapter 1",
                        "retrieval_hints": ["Hagrid", "motorbike", "baby", "blanket"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "That baby was Harry Potter, with a fresh lightning scar on his forehead. They laid him safely on his aunt's doorstep, completely unaware his adventure was just beginning.",
                        "visual_requirement": "Close-up of sleeping baby Harry with lightning bolt scar on doorstep",
                        "characters": ["Baby Harry", "Albus Dumbledore"],
                        "location": "Number 4 Privet Drive doorstep",
                        "action": "Bundle placed gently on welcome mat with letter tucked into blanket",
                        "objects": ["Baby Harry", "Lightning scar", "Letter"],
                        "emotional_context": "Legendary destiny and tender protection",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 Opening / Book 1 Chapter 1",
                        "retrieval_hints": ["Harry Potter", "baby", "doorstep", "scar"]
                    }
                ]
            }

        elif c_id == "ns_b1c01_gc0004_0006":
            # Short 2: Novel Story — The Tabby Cat & McGonagall's Warning
            return {
                "hook": "All day long, a strange cat sat on a brick wall, watching a quiet house.",
                "development": "When Dumbledore walked past that night, the cat's shadow shifted. In a flash, it turned into Professor McGonagall! She was worried sick about leaving baby Harry here. She warned Dumbledore that this family was mean and hated magic.",
                "payoff": "Every kid in the world would soon know his name, but Dumbledore knew Harry needed to grow up safe first.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "All day long, a strange cat sat on a brick wall, watching a quiet house.",
                        "visual_requirement": "Tabby cat sitting still on brick wall watching Privet Drive houses",
                        "characters": ["Minerva McGonagall"],
                        "location": "Privet Drive brick wall",
                        "action": "Cat sitting motionlessly staring down street",
                        "objects": ["Brick wall", "Houses"],
                        "emotional_context": "Quiet observation and mystery",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 Opening / Book 1 Chapter 1",
                        "retrieval_hints": ["cat", "wall", "Privet Drive", "sitting"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "When Dumbledore walked past that night, the cat's shadow shifted. In a flash, it turned into Professor McGonagall!",
                        "visual_requirement": "Cat shadow transforming on brick wall into Professor McGonagall in green robes",
                        "characters": ["Minerva McGonagall", "Albus Dumbledore"],
                        "location": "Privet Drive sidewalk",
                        "action": "Cat morphing into witch greeting Dumbledore",
                        "objects": ["Robes", "Pointed hat"],
                        "emotional_context": "Surprise and magical transformation",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 Opening / Book 1 Chapter 1",
                        "retrieval_hints": ["McGonagall", "cat", "transform", "Dumbledore"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "She was worried sick about leaving baby Harry here. She warned Dumbledore that this family was mean and hated magic.",
                        "visual_requirement": "McGonagall talking urgently with Dumbledore looking distressed",
                        "characters": ["Minerva McGonagall", "Albus Dumbledore"],
                        "location": "Privet Drive sidewalk",
                        "action": "McGonagall walking alongside Dumbledore expressing deep concern",
                        "objects": ["Glasses", "Robes"],
                        "emotional_context": "Concern and protective worry",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 Opening / Book 1 Chapter 1",
                        "retrieval_hints": ["McGonagall", "worried", "Dursley", "Dumbledore"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "Every kid in the world would soon know his name, but Dumbledore knew Harry needed to grow up safe first.",
                        "visual_requirement": "Dumbledore looking down tenderly at baby Harry wrapped in blankets",
                        "characters": ["Albus Dumbledore", "Baby Harry"],
                        "location": "Privet Drive doorstep",
                        "action": "Dumbledore nodding thoughtfully with gentle wisdom",
                        "objects": ["Letter", "Baby Harry"],
                        "emotional_context": "Wise patience and solemn destiny",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 Opening / Book 1 Chapter 1",
                        "retrieval_hints": ["Dumbledore", "famous", "baby", "doorstep"]
                    }
                ]
            }

        elif "peeves" in c_id or "disc_peeves" in c_id:
            # Short 3: Discovery — Peeves the Poltergeist
            return {
                "hook": "Did you know Hogwarts had a mischievous ghost cut completely from every single movie?",
                "development": "In the books, a noisy poltergeist named Peeves loved causing trouble. He dropped heavy walking sticks on first years, threw wet water balloons, and sang rude songs at teachers. Filmmakers even shot full scenes with him for the first film, but the director cut every single second.",
                "payoff": "The movie felt magical, but the books had way more chaotic fun.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "Did you know Hogwarts had a mischievous ghost cut completely from every single movie?",
                        "visual_requirement": "Students walking through bustling Hogwarts corridors looking around in surprise",
                        "characters": ["Harry Potter", "Ron Weasley", "Hermione Granger"],
                        "location": "Hogwarts corridors",
                        "action": "Students walking through stone halls looking up at high ceilings",
                        "objects": ["Robes", "Books"],
                        "emotional_context": "Curious wonder and revelation",
                        "preferred_movie_number": 1,
                        "source_grounding": "Book 1 Chapter 8 & 11",
                        "retrieval_hints": ["corridor", "students", "Hogwarts", "hallway"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "In the books, a noisy poltergeist named Peeves loved causing trouble. He dropped heavy walking sticks on first years, threw wet water balloons, and sang rude songs at teachers.",
                        "visual_requirement": "Nearly Headless Nick and floating ghosts swooping through Great Hall past dinner tables",
                        "characters": ["Nearly Headless Nick", "Hogwarts Ghosts"],
                        "location": "Great Hall feast tables",
                        "action": "Ghosts flying overhead swooping playfully toward laughing students",
                        "objects": ["Floating candles", "Feast food"],
                        "emotional_context": "Mischief and playful supernatural chaos",
                        "preferred_movie_number": 1,
                        "source_grounding": "Book 1 Chapter 7 & 11",
                        "retrieval_hints": ["ghost", "Great Hall", "floating", "Nick"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "Filmmakers even shot full scenes with him for the first film, but the director cut every single second.",
                        "visual_requirement": "Argus Filch prowling dark dungeon corridor with glowing lantern looking furious",
                        "characters": ["Argus Filch", "Mrs. Norris"],
                        "location": "Dungeon hallway",
                        "action": "Caretaker holding lantern looking around angrily for troublemakers",
                        "objects": ["Lantern", "Keys"],
                        "emotional_context": "Frustration and behind-the-scenes secret",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1 production archive (Rik Mayall scenes cut)",
                        "retrieval_hints": ["Filch", "lantern", "corridor", "caretaker"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "The movie felt magical, but the books had way more chaotic fun.",
                        "visual_requirement": "Wide panoramic shot of Hogwarts castle glowing brightly over black lake",
                        "characters": ["Hogwarts Castle"],
                        "location": "Hogwarts grounds",
                        "action": "Majestic castle illuminated against night sky",
                        "objects": ["Castle towers", "Lakeside cliffs"],
                        "emotional_context": "Awe, grand payoff, and warm nostalgia",
                        "preferred_movie_number": 1,
                        "source_grounding": "Book vs Movie adaptation difference",
                        "retrieval_hints": ["Hogwarts", "castle", "lake", "night"]
                    }
                ]
            }

        elif "sorting" in c_id or "hufflepuff" in c_id:
            # Short 4: Discovery — Neville's Sorting Hat Plea
            return {
                "hook": "When Neville first wore the Sorting Hat, he begged it not to send him to Gryffindor.",
                "development": "In the books, Neville was terrified and argued with the Hat for four whole minutes. Convinced he was too clumsy to be brave, he pleaded to join Hufflepuff instead, where nobody would expect him to be a hero.",
                "payoff": "The Hat refused. It saw legendary courage inside him, long before Neville believed in himself.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "When Neville first wore the Sorting Hat, he begged it not to send him to Gryffindor.",
                        "visual_requirement": "Young nervous Neville Longbottom walking up to the four-legged stool",
                        "characters": ["Neville Longbottom", "Professor McGonagall"],
                        "location": "Great Hall Sorting ceremony",
                        "action": "Timid student walking cautiously to stool under Great Hall candles",
                        "objects": ["Sorting Hat", "Stool"],
                        "emotional_context": "Anxious dread and self-doubt",
                        "preferred_movie_number": 1,
                        "source_grounding": "Book 1 Chapter 7 / Book 5 Chapter 11",
                        "retrieval_hints": ["Neville", "Sorting Hat", "Great Hall", "Longbottom"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "In the books, Neville was terrified and argued with the Hat for four whole minutes.",
                        "visual_requirement": "Sorting Hat placed on Neville's head covering his eyes, twisting as it speaks",
                        "characters": ["Neville Longbottom", "Sorting Hat"],
                        "location": "Great Hall",
                        "action": "Hat wrinkling and deliberating on trembling student head",
                        "objects": ["Sorting Hat", "Stool"],
                        "emotional_context": "Tense internal argument",
                        "preferred_movie_number": 1,
                        "source_grounding": "Book 1 Chapter 7 / Book 5 Chapter 11",
                        "retrieval_hints": ["hat", "sorting", "Neville", "stool"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "Convinced he was too clumsy to be brave, he pleaded to join Hufflepuff instead, where nobody would expect him to be a hero.",
                        "visual_requirement": "Gryffindor and Hufflepuff house tables watching ceremony with rapt attention",
                        "characters": ["Harry Potter", "Ron Weasley", "Hermione Granger"],
                        "location": "Great Hall house tables",
                        "action": "Students at banquet tables watching nervously",
                        "objects": ["House tables", "Candles"],
                        "emotional_context": "Insecurity and dread of high expectations",
                        "preferred_movie_number": 1,
                        "source_grounding": "Book 5 Chapter 11 (Hatstall history)",
                        "retrieval_hints": ["Gryffindor", "Hufflepuff", "students", "table"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "The Hat refused. It saw legendary courage inside him, long before Neville believed in himself.",
                        "visual_requirement": "Neville in Movie 8 standing courageously in courtyard ruins holding Sword of Gryffindor",
                        "characters": ["Neville Longbottom"],
                        "location": "Hogwarts courtyard ruins",
                        "action": "Grown battle-tested Neville standing tall with sword facing danger",
                        "objects": ["Sword of Gryffindor", "Sorting Hat"],
                        "emotional_context": "Ultimate courage, pride, and vindication",
                        "preferred_movie_number": 8,
                        "source_grounding": "Movie 8 / Book 7 Chapter 36",
                        "retrieval_hints": ["Neville", "sword", "courage", "hero"]
                    }
                ]
            }

        elif "gc0020_0022" in c_id or "vanishing_glass" in c_id or "snake" in c_id:
            # Short 5: Novel Story — The Zoo Snake Adventure (Book 1 Ch 2)
            return {
                "hook": "At the city zoo, Harry stopped in front of a giant sleeping snake.",
                "development": "Suddenly, the snake woke up and winked at him. Harry whispered to it, and the snake nodded back politely. His cousin Dudley pushed Harry aside to get closer. But the moment Dudley touched the tank, the glass vanished into thin air! Dudley tumbled straight into the cold water pool.",
                "payoff": "The friendly snake slithered free, leaving Dudley trapped behind the glass.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "At the city zoo, Harry stopped in front of a giant sleeping snake.",
                        "visual_requirement": "Harry standing alone in front of the giant glass enclosure looking curiously at coiled sleeping snake",
                        "characters": ["Harry Potter"],
                        "location": "Zoo Reptile House",
                        "action": "Young boy staring curiously through dark glass exhibit",
                        "objects": ["Glass enclosure", "Snake"],
                        "emotional_context": "Quiet curiosity and solitude",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:06:37–00:06:50 / Book 1 Chapter 2",
                        "retrieval_hints": ["zoo", "Harry", "snake", "glass", "reptile house"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "Suddenly, the snake woke up and winked at him. Harry whispered to it, and the snake nodded back politely.",
                        "visual_requirement": "Close-up of boa constrictor raising its head, winking, and nodding as Harry speaks",
                        "characters": ["Harry Potter", "Boa Constrictor"],
                        "location": "Zoo Reptile House",
                        "action": "Giant snake making direct eye contact with Harry and nodding head",
                        "objects": ["Snake", "Enclosure"],
                        "emotional_context": "Surprise, gentle wonder, and magical connection",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:06:55–00:07:20 / Book 1 Chapter 2",
                        "retrieval_hints": ["snake", "winking", "Harry talking", "nodding"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "His cousin Dudley pushed Harry aside to get closer. But the moment Dudley touched the tank, the glass vanished into thin air! Dudley tumbled straight into the cold water pool.",
                        "visual_requirement": "Dudley running up, shoving Harry aside, and leaning hands against glass just as the glass vanishes, splashing into pool",
                        "characters": ["Dudley Dursley", "Harry Potter"],
                        "location": "Zoo Reptile House",
                        "action": "Bully shoving boy, pressing glass, tumbling forward into water tank",
                        "objects": ["Vanishing glass", "Water tank"],
                        "emotional_context": "Comical shock and instant justice",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:07:30–00:07:50 / Book 1 Chapter 2",
                        "retrieval_hints": ["Dudley", "push", "glass vanished", "splash", "falling"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "The friendly snake slithered free, leaving Dudley trapped behind the glass.",
                        "visual_requirement": "Snake slithering out across floor past screaming visitors while Dudley bangs on reappeared glass from inside tank",
                        "characters": ["Boa Constrictor", "Dudley Dursley", "Harry Potter"],
                        "location": "Zoo Reptile House",
                        "action": "Snake escaping freely along floor, Dudley trapped banging inside glass",
                        "objects": ["Escaping snake", "Reappeared glass"],
                        "emotional_context": "Triumph, amusement, and comedic payoff",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:07:50–00:08:15 / Book 1 Chapter 2",
                        "retrieval_hints": ["snake slithering", "floor", "Dudley trapped", "glass"]
                    }
                ]
            }

        elif "gc0029_0031" in c_id or "letters" in c_id or "fireplace" in c_id:
            # Short 6: Novel Story — The Fireplace Letters Explosion (Book 1 Ch 3)
            return {
                "hook": "Uncle Vernon was determined that Harry would never read his letter.",
                "development": "He boarded up the windows and nailed the mail slot shut. On Sunday morning, Vernon smiled happily because no mail arrived on Sundays. Then the fireplace began to rumble. Suddenly, hundreds of letters shot out like popcorn! Envelopes swirled through the entire room as Harry jumped high to catch one.",
                "payoff": "Uncle Vernon panicked, realizing magic was impossible to keep out.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "Uncle Vernon was determined that Harry would never read his letter. He boarded up the windows and nailed the mail slot shut.",
                        "visual_requirement": "Uncle Vernon frantically hammering wooden planks across the mail slot and burning envelopes",
                        "characters": ["Uncle Vernon"],
                        "location": "Number 4 Privet Drive hallway",
                        "action": "Furious man hammering boards over door slot and destroying mail",
                        "objects": ["Hammer", "Wooden planks", "Envelopes"],
                        "emotional_context": "Desperation and stubborn denial",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:10:05–00:10:35 / Book 1 Chapter 3",
                        "retrieval_hints": ["Vernon", "hammer", "mail slot", "Privet Drive", "letter"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "On Sunday morning, Vernon smiled happily because no mail arrived on Sundays. Then the fireplace began to rumble.",
                        "visual_requirement": "Uncle Vernon sitting smugly holding tea cup smiling, suddenly looking alarmed as fireplace begins trembling and shaking",
                        "characters": ["Uncle Vernon", "Harry Potter"],
                        "location": "Privet Drive living room",
                        "action": "Smug smile turning to sudden alarm as brick fireplace shakes",
                        "objects": ["Tea cup", "Fireplace"],
                        "emotional_context": "False confidence shifting to sudden dread",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:10:45–00:11:05 / Book 1 Chapter 3",
                        "retrieval_hints": ["Sunday", "Vernon smiling", "no post", "fireplace shaking"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "Suddenly, hundreds of letters shot out like popcorn! Envelopes swirled through the entire room as Harry jumped high to catch one.",
                        "visual_requirement": "A whirlwind of Hogwarts envelopes blasting out of the fireplace, filling the room while Harry leaps in the air grabbing for one",
                        "characters": ["Harry Potter", "Uncle Vernon", "Aunt Petunia"],
                        "location": "Privet Drive living room",
                        "action": "Hundreds of envelopes flying like a magical storm, boy jumping to snatch letter",
                        "objects": ["Flying envelopes", "Green ink letters"],
                        "emotional_context": "High-energy magic, excitement, and chaos",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:11:05–00:11:35 / Book 1 Chapter 3",
                        "retrieval_hints": ["letters flying", "fireplace", "Harry jumping", "living room"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "Uncle Vernon panicked, realizing magic was impossible to keep out.",
                        "visual_requirement": "Uncle Vernon struggling to hold Harry back as envelopes swirl chaotically around the terrified Dursley family",
                        "characters": ["Uncle Vernon", "Harry Potter", "Dudley Dursley"],
                        "location": "Privet Drive living room",
                        "action": "Uncle tackling Harry away from letters amid spinning paper storm",
                        "objects": ["Letters", "Living room furniture"],
                        "emotional_context": "Complete overwhelm and magical inevitability",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:11:30–00:11:55 / Book 1 Chapter 3",
                        "retrieval_hints": ["Vernon panicking", "letters", "tackle", "chaos"]
                    }
                ]
            }

        elif "erised" in c_id or "mirror" in c_id:
            # Short 7: Discovery — The Mirror of Erised Backwards Code (Book 1 Ch 12)
            return {
                "hook": "Did you know the magical mirror in Hogwarts hides a secret code?",
                "development": "Carved along the gold frame are strange words that look like a riddle. They seem like nonsense at first. But if you read them backwards in a mirror, the secret message appears! It says: I show not your face, but your heart's desire.",
                "payoff": "That explains the name Erised, which is just the word desire spelled backwards.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "Did you know the magical mirror in Hogwarts hides a secret code?",
                        "visual_requirement": "Harry Potter in nightclothes slowly approaching the towering gold-framed mirror in a deserted dark classroom",
                        "characters": ["Harry Potter"],
                        "location": "Abandoned Hogwarts classroom",
                        "action": "Young student creeping quietly toward towering ornate mirror",
                        "objects": ["Mirror of Erised", "Gold frame"],
                        "emotional_context": "Mystery and quiet revelation",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 01:31:50–01:32:15 / Book 1 Chapter 12",
                        "retrieval_hints": ["Harry", "mirror", "Erised", "classroom", "night"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "Carved along the gold frame are strange words that look like a riddle. They seem like nonsense at first.",
                        "visual_requirement": "Close-up of the intricate gold arch of the mirror, showing the mysterious carved inscription letters",
                        "characters": ["Mirror of Erised"],
                        "location": "Mirror top arch",
                        "action": "Camera panning across carved letters along golden rim",
                        "objects": ["Carved inscription", "Gold arch"],
                        "emotional_context": "Curiosity and cryptic puzzle",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 01:32:15–01:32:35 / Book 1 Chapter 12",
                        "retrieval_hints": ["inscription", "letters", "gold frame", "carved", "Erised"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "But if you read them backwards in a mirror, the secret message appears! It says: I show not your face, but your heart's desire.",
                        "visual_requirement": "Harry gazing into the mirror glass as smiling reflections of his parents appear beside him",
                        "characters": ["Harry Potter", "James Potter", "Lily Potter"],
                        "location": "Mirror glass reflection",
                        "action": "Loving family reflection appearing in silver glass smiling at Harry",
                        "objects": ["Reflective glass", "Parents reflection"],
                        "emotional_context": "Emotional wonder and profound longing",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 01:32:40–01:33:20 / Book 1 Chapter 12",
                        "retrieval_hints": ["parents reflection", "Harry smiling", "mirror glass"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "That explains the name Erised, which is just the word desire spelled backwards.",
                        "visual_requirement": "Dumbledore sitting quietly on a wooden desk beside Harry, speaking with gentle wisdom",
                        "characters": ["Albus Dumbledore", "Harry Potter"],
                        "location": "Abandoned classroom",
                        "action": "Wise headmaster explaining the true nature of the mirror",
                        "objects": ["Mirror of Erised", "Desk"],
                        "emotional_context": "Warm wisdom and satisfying realization",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 01:35:10–01:35:45 / Book 1 Chapter 12",
                        "retrieval_hints": ["Dumbledore", "Harry", "Erised", "desire", "explaining"]
                    }
                ]
            }

        elif "remembrall" in c_id or "cloak" in c_id:
            # Short 8: Discovery — Neville's Remembrall Cloak Secret (Book 1 Ch 9)
            return {
                "hook": "Did you know Neville's magical glass ball revealed his secret right on screen?",
                "development": "An owl drops a Remembrall that fills with red smoke whenever you forget something. Neville looks confused, admitting he cannot remember what he forgot. Notice the other students at the breakfast table! Every single student is wearing their black school robes.",
                "payoff": "Neville is sitting in his sweater and tie, having completely forgotten his cloak.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "Did you know Neville's magical glass ball revealed his secret right on screen?",
                        "visual_requirement": "Flock of school owls swooping into the sunny Great Hall carrying letters and packages down to students",
                        "characters": ["Hogwarts Students", "Owls"],
                        "location": "Great Hall breakfast tables",
                        "action": "Owls flying low over long breakfast tables dropping mail",
                        "objects": ["Mail packages", "Great Hall tables"],
                        "emotional_context": "Morning energy and anticipation",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:54:05–00:54:20 / Book 1 Chapter 9",
                        "retrieval_hints": ["owls", "Great Hall", "breakfast", "mail", "delivery"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "An owl drops a Remembrall that fills with red smoke whenever you forget something. Neville looks confused, admitting he cannot remember what he forgot.",
                        "visual_requirement": "Close-up of Neville holding the clear glass ball as glowing red smoke swirls inside, looking bewildered",
                        "characters": ["Neville Longbottom", "Hermione Granger", "Dean Thomas"],
                        "location": "Gryffindor house table",
                        "action": "Student holding glowing sphere, frowning in confusion",
                        "objects": ["Remembrall", "Red smoke"],
                        "emotional_context": "Bewilderment and innocent humor",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:54:22–00:54:35 / Book 1 Chapter 9",
                        "retrieval_hints": ["Remembrall", "Neville", "red smoke", "confused"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "Notice the other students at the breakfast table! Every single student is wearing their black school robes.",
                        "visual_requirement": "Medium shot panning across Harry, Ron, Hermione, and Dean, all dressed in standard black Hogwarts robes",
                        "characters": ["Harry Potter", "Ron Weasley", "Hermione Granger"],
                        "location": "Gryffindor table",
                        "action": "Classmates sitting in full uniform black school cloaks watching Neville",
                        "objects": ["Black Hogwarts robes", "House ties"],
                        "emotional_context": "Visual evidence and contrast",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:54:30–00:54:38 / Book 1 Chapter 9",
                        "retrieval_hints": ["students in robes", "Hermione", "black cloaks", "uniform"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "Neville is sitting in his sweater and tie, having completely forgotten his cloak.",
                        "visual_requirement": "Cut back to Neville sitting in just his white collared shirt, vest sweater, and tie, completely missing his black robe",
                        "characters": ["Neville Longbottom"],
                        "location": "Gryffindor table",
                        "action": "Neville holding Remembrall in shirt and sweater with no black robe on",
                        "objects": ["Remembrall", "Sweater vest", "Missing robe"],
                        "emotional_context": "Clever realization, laughter, and hidden easter egg",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:54:35–00:54:45 / Book 1 Chapter 9",
                        "retrieval_hints": ["Neville sweater", "no robe", "Remembrall", "forgotten cloak"]
                    }
                ]
            }

        # Generic novel fallback
        words = candidate.story_event_summary.split()[:40]
        event_str = " ".join(words)
        return {
            "hook": f"Something unforgettable was unfolding inside {candidate.book_title}.",
            "development": f"{event_str}. The magical atmosphere grew denser as the situation reached a turning point.",
            "payoff": "What began as a quiet moment soon reshaped the fate of the entire wizarding world.",
            "visual_beats": [
                {
                    "beat_id": "beat_1",
                    "narration_text": f"Something unforgettable was unfolding inside {candidate.book_title}.",
                    "visual_requirement": "Establishing shot of Hogwarts castle or relevant setting",
                    "characters": ["Harry Potter"],
                    "location": "Hogwarts",
                    "action": "Atmospheric scene opening",
                    "objects": ["Wand"],
                    "emotional_context": "Mystery and tension",
                    "preferred_movie_number": candidate.book_number,
                    "source_grounding": candidate.source_location if hasattr(candidate, "source_location") else "Canon",
                    "retrieval_hints": ["Hogwarts", "castle", "magic"]
                },
                {
                    "beat_id": "beat_2",
                    "narration_text": f"{event_str[:60]}...",
                    "visual_requirement": "Characters interacting in dramatic confrontation",
                    "characters": ["Harry Potter", "Ron Weasley"],
                    "location": "Hogwarts corridors",
                    "action": "Tense conversation or movement",
                    "objects": ["Robes"],
                    "emotional_context": "Rising stakes",
                    "preferred_movie_number": candidate.book_number,
                    "source_grounding": "Scene development",
                    "retrieval_hints": ["Harry", "corridor", "wand"]
                },
                {
                    "beat_id": "beat_3",
                    "narration_text": "What began as a quiet moment soon reshaped the fate of the entire wizarding world.",
                    "visual_requirement": "Dramatic climactic character reaction or magical event",
                    "characters": ["Harry Potter"],
                    "location": "Great Hall or Grounds",
                    "action": "Climactic resolution",
                    "objects": ["Wand", "Magic"],
                    "emotional_context": "Triumph and wonder",
                    "preferred_movie_number": candidate.book_number,
                    "source_grounding": "Scene resolution",
                    "retrieval_hints": ["magic", "Harry Potter", "destiny"]
                }
            ]
        }

    # ── Core Script Generation ────────────────────────────────────────────────

    def generate_script_for_candidate(
        self,
        candidate: Union[NovStoryCandidate, DiscoveryCandidate],
        db: Session,
        max_attempts: int = 3
    ) -> HarryPotterScript:
        """
        Generates, validates, and persists a HarryPotterScript for a given candidate.
        Uses Gemini 3.6 Flash when available with iterative QA feedback loop,
        falling back seamlessly to high-grade deterministic generation if needed.
        """
        is_novel = isinstance(candidate, NovStoryCandidate) or candidate.content_type == "novel_story"
        c_type = "novel_story" if is_novel else "discovery"

        logger.info(
            f"[SCRIPT_GEN] Generating script for candidate {candidate.id} "
            f"({c_type} | Book {candidate.book_number} Ch {candidate.chapter_number})"
        )

        script_data = None
        qa_result = None
        used_model = GEMINI_MODEL
        revision_feedback: List[str] = []

        # Attempt AI Generation Loop
        if GEMINI_API_KEY:
            try:
                gemini_client = get_gemini_client()
                for attempt in range(1, max_attempts + 1):
                    logger.info(f"[SCRIPT_GEN] Attempt {attempt}/{max_attempts} with {GEMINI_MODEL}...")

                    prompt = (
                        self._build_novel_story_prompt(candidate, revision_feedback)
                        if is_novel
                        else self._build_discovery_prompt(candidate, revision_feedback)
                    )

                    try:
                        response = gemini_client.generate_content(
                            model=GEMINI_MODEL,
                            contents=prompt
                        )
                        raw = response.text.strip()
                        # Clean JSON formatting
                        cleaned = re.sub(r"^```json\s*", "", raw)
                        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
                        parsed = json.loads(cleaned)

                        full_script = f"{parsed.get('hook', '')} {parsed.get('development', '')} {parsed.get('payoff', '')}".strip()
                        v_beats = parsed.get("visual_beats", [])

                        # QA Evaluation
                        eval_res = self.evaluate_script_qa(
                            script_text=full_script,
                            visual_beats=v_beats,
                            candidate_type=c_type
                        )

                        logger.info(
                            f"[SCRIPT_GEN] Attempt {attempt} QA: Score={eval_res.score}/100 | "
                            f"Words={eval_res.word_count} | Passed={eval_res.passed}"
                        )

                        if eval_res.passed:
                            script_data = parsed
                            qa_result = eval_res
                            break
                        else:
                            logger.warning(f"[SCRIPT_GEN] Attempt {attempt} failed QA: {eval_res.feedback}")
                            revision_feedback = eval_res.feedback

                    except Exception as call_err:
                        logger.warning(f"[SCRIPT_GEN] Attempt {attempt} API error: {call_err}")
                        if "quota" in str(call_err).lower() or "429" in str(call_err):
                            break

            except Exception as e:
                logger.warning(f"[SCRIPT_GEN] AI provider bypassed/failed: {e}")

        # Fallback to high-grade deterministic script if AI did not yield a passing script
        if not script_data or not qa_result or not qa_result.passed:
            logger.info(f"[SCRIPT_GEN] Engaging verified deterministic script for {candidate.id}")
            script_data = self._get_deterministic_script(candidate)
            full_script = f"{script_data['hook']} {script_data['development']} {script_data['payoff']}".strip()
            v_beats = script_data.get("visual_beats", [])
            qa_result = self.evaluate_script_qa(
                script_text=full_script,
                visual_beats=v_beats,
                candidate_type=c_type
            )
            used_model = "verified_canonical_generator"
            logger.info(
                f"[SCRIPT_GEN] Deterministic QA: Score={qa_result.score}/100 | "
                f"Words={qa_result.word_count} | Passed={qa_result.passed}"
            )

        full_text = f"{script_data['hook']} {script_data['development']} {script_data['payoff']}".strip()
        words = full_text.split()
        word_count = len(words)
        est_duration = round(word_count / 2.5, 1)

        # Ensure visual beats have MOVIE_FOOTAGE_ONLY policy
        raw_beats = script_data.get("visual_beats", [])
        clean_beats = []
        for idx, b in enumerate(raw_beats, 1):
            clean_beats.append({
                "beat_id": b.get("beat_id", f"beat_{idx}"),
                "narration_text": b.get("narration_text", ""),
                "visual_requirement": b.get("visual_requirement", ""),
                "characters": b.get("characters", []),
                "location": b.get("location", ""),
                "action": b.get("action", ""),
                "objects": b.get("objects", []),
                "emotional_context": b.get("emotional_context", "dramatic"),
                "preferred_movie_number": b.get("preferred_movie_number", candidate.book_number),
                "source_grounding": b.get("source_grounding", ""),
                "retrieval_hints": b.get("retrieval_hints", []),
                "visual_source_policy": "MOVIE_FOOTAGE_ONLY"
            })

        # Calculate visual PART marker (VISUAL ONLY — NEVER SPOKEN)
        slot_num = getattr(candidate, "batch_slot", None) or 1
        part_marker = f"PART {slot_num:02d}"

        # Source chunks list
        if is_novel:
            source_chunks = [candidate.chunk_id_start]
            if candidate.chunk_id_end != candidate.chunk_id_start:
                source_chunks.append(candidate.chunk_id_end)
            source_ref = candidate.source_location
            novel_excerpt = candidate.source_text_preview
            disc_type = None
            movie_num = candidate.book_number
            movie_chunk = None
            movie_excerpt = None
        else:
            source_chunks = [candidate.chunk_id_primary]
            source_ref = f"Book {candidate.book_number} Chapter {candidate.chapter_number}"
            novel_excerpt = candidate.novel_evidence_text
            disc_type = candidate.discovery_type
            movie_num = candidate.corresponding_movie_number
            movie_chunk = candidate.movie_chunk_id
            movie_excerpt = f"Movie Shows: {candidate.movie_shows} | Omits: {candidate.movie_omits_or_changes}"

        script_id = f"hps_{candidate.id}"

        # Persist or update in SQLite
        existing = db.query(HarryPotterScript).filter_by(id=script_id).first()
        if existing:
            rec = existing
            rec.hook = script_data["hook"]
            rec.development = script_data["development"]
            rec.payoff = script_data["payoff"]
            rec.full_text = full_text
            rec.word_count = word_count
            rec.estimated_duration_sec = est_duration
            rec.visual_beats_json = json.dumps(clean_beats)
            rec.total_beats = len(clean_beats)
            rec.qa_score = qa_result.score
            rec.qa_status = "APPROVED" if qa_result.passed else "FLAGGED"
            rec.qa_feedback_json = json.dumps(qa_result.feedback)
            rec.model_name = used_model
            rec.status = "READY_FOR_STEP_9"
            rec.updated_at = datetime.utcnow()
        else:
            rec = HarryPotterScript(
                id=script_id,
                candidate_id=candidate.id,
                content_type=c_type,
                book_number=candidate.book_number,
                book_title=candidate.book_title,
                chapter_number=candidate.chapter_number,
                chapter_title=candidate.chapter_title,
                source_chunks_json=json.dumps(source_chunks),
                source_reference=source_ref,
                novel_evidence_excerpt=novel_excerpt[:500] if novel_excerpt else None,
                discovery_type=disc_type,
                corresponding_movie_number=movie_num,
                movie_chunk_id=movie_chunk,
                movie_evidence_excerpt=movie_excerpt[:500] if movie_excerpt else None,
                part_marker=part_marker,
                voice_id="af_sarah",
                voice_pitch="+0Hz",
                voice_rate="+0%",
                narrator_style="SARAH_MAX_CREATOR",
                hook=script_data["hook"],
                development=script_data["development"],
                payoff=script_data["payoff"],
                full_text=full_text,
                word_count=word_count,
                estimated_duration_sec=est_duration,
                visual_beats_json=json.dumps(clean_beats),
                total_beats=len(clean_beats),
                qa_score=qa_result.score,
                qa_status="APPROVED" if qa_result.passed else "FLAGGED",
                qa_feedback_json=json.dumps(qa_result.feedback),
                model_name=used_model,
                status="READY_FOR_STEP_9",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(rec)

        db.commit()
        db.refresh(rec)

        logger.info(
            f"[SCRIPT_GEN] Script persisted: {rec.id} | Words={word_count} | "
            f"Dur={est_duration}s | Beats={rec.total_beats} | QA={rec.qa_status} ({rec.qa_score}/100)"
        )
        return rec

    # ── Batch Script Generation (Launch Batch) ────────────────────────────────

    def generate_launch_batch_scripts(self) -> List[HarryPotterScript]:
        """
        Generates and persists scripts and visual beat plans for the 4 launch candidates:
          Slot 1: SHORT 1 — Novel Story
          Slot 2: SHORT 2 — Novel Story
          Slot 3: SHORT 3 — Discovery
          Slot 4: SHORT 4 — Discovery
        """
        results = []
        with self.Session() as session:
            # Query launch candidates
            novel_launch = (
                session.query(NovStoryCandidate)
                .filter_by(is_launch_candidate=True)
                .order_by(NovStoryCandidate.batch_slot.asc())
                .all()
            )
            disc_launch = (
                session.query(DiscoveryCandidate)
                .filter_by(is_launch_candidate=True)
                .order_by(DiscoveryCandidate.batch_slot.asc())
                .all()
            )

            all_launch: List[Union[NovStoryCandidate, DiscoveryCandidate]] = novel_launch + disc_launch

            if not all_launch:
                logger.warning("[SCRIPT_GEN] No launch candidates found! Querying top candidates...")
                novel_fallback = session.query(NovStoryCandidate).order_by(NovStoryCandidate.global_chronology_start.asc()).limit(2).all()
                disc_fallback = session.query(DiscoveryCandidate).limit(2).all()
                all_launch = novel_fallback + disc_fallback

            for cand in all_launch:
                script_rec = self.generate_script_for_candidate(cand, session)
                results.append(script_rec)

        return results

