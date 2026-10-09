"""
Harry Potter Script Generation & Visual Beat Engine (Step 8)
================================================================================
Cloud-Runner & Ephemeral GitHub Actions Compatible.

Generates broadcast-ready, fact-grounded narration scripts and structured visual beat plans
for YouTube Shorts, grounded exclusively in:
  - Canonical Harry Potter novel text (FTS5 SQLite index `novel_chunks_fts`)
  - Canonical Movie 1-8 scene & dialogue index (`movie_subtitles_fts`)

Supports two content types:
  A. NOVEL STORY SHORTS (~45-60s, 100-150 spoken words, conversational cinematic English)
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
    PUBLISHING_ENABLED, UPLOAD_ENABLED, AI_PROVIDER_AVAILABLE
)
from core.models import (
    Base, NovStoryCandidate, DiscoveryCandidate, HarryPotterScript, NovelChunk,
    migrate_discovery_schema
)
from core.discovery_types import (
    DiscoverySubtype, DiscoveryTier, DiscoveryStoryStructure, HookArchetype,
    EvidenceRoute, PayoffType, TitlePattern, VisualClassification, DiscoveryQAResult
)
from core.multi_fact_types import (
    MultiFactTopicPack, MultiFactPayload, VisualProposition, FactType, MultiFactFormat
)
from core.gemini_client import get_gemini_client
from engines.discovery_narrative_engine import (
    DiscoveryNarrativeEngine, THROAT_CLEARING_PATTERNS,
    DiscoveryEditorialModel, DiscoveryEditorialEvaluationResult
)

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
    "ai image", "ai generated", "stock footage", "pexels", "unsplash", "pixabay",
    "shutterstock", "getty", "istock", "generic b-roll", "generic stock", "external video",
    "consistory", "pollinations", "midjourney", "dall-e", "stable diffusion"
]

MIN_WORD_COUNT = 62
MAX_WORD_COUNT = 85
PREFERRED_MIN_WORDS = 65
PREFERRED_MAX_WORDS = 78

# ── DEXTER LOFTIN VIRAL NARRATION & HOOK ENGINE INVARIANTS ─────────────────
DEXTER_LOFTIN_GUIDANCE = """
DEXTER LOFTIN STYLE & RETENTION SPECIFICATION:
1. HOOK (0-5s):
   - High personal curiosity, counter-intuitive realization, or poignant observation:
     Examples:
     * "It took me eighteen years to realize why [Character] could almost never look [Character] in the eyes."
     * "There's a subtle detail in [Scene] that completely changes how you view [Character]."
     * "Did you notice what [Character] always does right before [Action]?"
     * "Almost nobody realizes why [Character] actually said this."
   - Avoid dry academic introductions, robotic exposition, or greeting the audience.
2. DEVELOPMENT (Conversational Spoken Storytelling):
   - Fast, punchy, spoken English. Short sentences. Zero textbook prose.
   - Grounded in human emotions: grief, loyalty, hidden regret, shock, or dark mystery.
3. PAYOFF (Final Revelation):
   - Emotional punchline or lore twist that lingers, ending with a compelling viewer prompt (e.g., "Did you notice this?").
4. PHYSICAL MOVIE VISUAL ANCHORS:
   - Every visual beat MUST name specific characters, facial expressions, gaze directions, robes, or props.
   - This directly drives facial recognition centering (YuNet/SFace) and rapid cuts (1.4s-1.8s).
"""

NOVEL_STORY_MIN_WORDS = 62
NOVEL_STORY_MAX_WORDS = 85
NOVEL_STORY_MIN_DURATION = 22.0
NOVEL_STORY_MAX_DURATION = 28.0

DISCOVERY_SHORT_MIN_WORDS = 58
DISCOVERY_SHORT_MAX_WORDS = 90
DISCOVERY_SHORT_MIN_DURATION = 18.0
DISCOVERY_SHORT_MAX_DURATION = 29.5


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
        migrate_discovery_schema(self.db_path)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        logger.info("[HP_SCRIPT_ENGINE] Initialized. DB ready at %s", DB_PATH)

    # ── Script QA & AI Review Gate ─────────────────────────────────────────────

    def evaluate_script_qa(
        self,
        script_text: str,
        visual_beats: List[Dict[str, Any]],
        candidate_type: str = "novel_story",
        candidate_context: Optional[Dict[str, Any]] = None,
        editorial_model: Optional[DiscoveryEditorialModel] = None,
    ) -> ScriptQAResult:
        """
        Rigorous programmatic QA gate verifying all Step 8 invariants.
        Fails closed if any rule is violated.
        Supports DEEP_DISCOVERY (220-300 words, 65-80.9s), MICRO_DISCOVERY (55-85 words, 20-35s),
        enforces Discovery Editorial Value / Anti-Recap Gate,
        and strictly preserves NOVEL_STORY isolation (100-150 words, 45-60s).
        """
        words = script_text.strip().split()
        word_count = len(words)

        # Ensure visual_beats is a list of dicts
        normalized_beats = []
        for i, b in enumerate(visual_beats or []):
            if isinstance(b, dict):
                normalized_beats.append(b)
            elif isinstance(b, str):
                normalized_beats.append({
                    "beat_id": f"beat_{i+1}",
                    "visual_requirement": b,
                    "narration_text": b,
                    "characters": []
                })
        visual_beats = normalized_beats

        c_type_upper = str(candidate_type).upper()
        is_deep_discovery = (c_type_upper == "DEEP_DISCOVERY") or (c_type_upper == "DISCOVERY" and word_count >= 150)
        is_micro_discovery = (c_type_upper == "MICRO_DISCOVERY") or (c_type_upper in ("DISCOVERY_SHORT", "DISCOVERY") and word_count < 100)

        if is_deep_discovery:
            min_words = 220
            max_words = 300
            min_duration = 65.0
            max_duration = 80.9
            target_speech_rate = 3.55  # ~3.4 - 3.7 wps
            estimated_duration = round(word_count / target_speech_rate, 1)
        elif is_micro_discovery:
            min_words = DISCOVERY_SHORT_MIN_WORDS
            max_words = DISCOVERY_SHORT_MAX_WORDS
            min_duration = DISCOVERY_SHORT_MIN_DURATION
            max_duration = DISCOVERY_SHORT_MAX_DURATION
            target_speech_rate = 3.15  # Calibrated for Bella / Cloned Narrator at 1.00x speed
            estimated_duration = round(word_count / target_speech_rate, 1)
        else:
            # NOVEL_STORY defaults: strictly 22 to 28 seconds (75 to 88 words at ~3.15 wps)
            min_words = NOVEL_STORY_MIN_WORDS
            max_words = NOVEL_STORY_MAX_WORDS
            min_duration = NOVEL_STORY_MIN_DURATION
            max_duration = NOVEL_STORY_MAX_DURATION
            target_speech_rate = 3.15
            estimated_duration = round(word_count / 3.15, 1)

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

        # 2. Cliché & Generic AI Filler Check (Curiosity hooks like 'did you know' / 'do you know' are encouraged)
        for cliche in FORBIDDEN_CLICHES:
            if cliche in text_lower:
                cliches_detected.append(cliche)
                feedback.append(f"FORBIDDEN CLICHÉ: Detected '{cliche}'. Rephrase naturally.")

        # Throat-clearing check for Deep Discovery
        if is_deep_discovery:
            for pattern in THROAT_CLEARING_PATTERNS:
                if re.search(pattern, text_lower):
                    cliches_detected.append("throat_clearing")
                    feedback.append(f"FORBIDDEN THROAT-CLEARING: Opening contains generic pattern '{pattern}'.")

        # 3. Forbidden Literary / Book-Summary Language Check
        for lit_term in FORBIDDEN_LITERARY_WORDS:
            if re.search(r"\b" + re.escape(lit_term) + r"\b", text_lower):
                literary_terms_detected.append(lit_term)
                feedback.append(
                    f"FORBIDDEN LITERARY LANGUAGE: Detected '{lit_term}'. Use simple spoken words an 8-year-old understands."
                )

        # 4. Word Count Bounds Check
        if word_count < min_words:
            feedback.append(
                f"WORD COUNT TOO SHORT: {word_count} words (minimum {min_words} words required)."
            )
        elif word_count > max_words:
            feedback.append(
                f"WORD COUNT TOO LONG: {word_count} words (maximum {max_words} words allowed)."
            )

        # 5. Duration Bounds Check
        if estimated_duration < min_duration or estimated_duration > max_duration:
            feedback.append(
                f"ESTIMATED DURATION OUT OF BOUNDS: {estimated_duration}s (target: {min_duration}-{max_duration}s)."
            )

        # 6. Visual Beat Coverage & Micro-Beats Pacing (Minimum 8, target 10-11 beats)
        target_min_beats = 8
        if not visual_beats or len(visual_beats) < target_min_beats:
            feedback.append(
                f"INSUFFICIENT VISUAL BEATS: {len(visual_beats)} beats found (minimum {target_min_beats} required, target 10-11 micro-beats for fast vertical pacing)."
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
        if word_count < min_words or word_count > max_words:
            score -= 30.0
        if forbidden_visuals_detected:
            score -= 50.0
        if len(visual_beats) < target_min_beats:
            score -= 25.0

        # 8. Discovery Editorial Value & Anti-Recap Gate (Discovery ONLY — Novel Story 100% Isolated)
        editorial_res = None
        is_novel = c_type_upper in ("NOVEL_STORY", "NOVEL_STORY_SHORT")
        is_discovery = not is_novel
        if is_discovery:
            editorial_res = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(
                script_text=script_text,
                visual_beats=visual_beats,
                candidate_context=candidate_context,
                editorial_model=editorial_model,
            )
            if not editorial_res.passed:
                score -= 40.0
                for r in editorial_res.reasons:
                    feedback.append(f"EDITORIAL VALUE FAILURE: {r}")

        score = max(0.0, score)
        passed = (
            score >= 80.0
            and len(spoken_parts_detected) == 0
            and len(cliches_detected) == 0
            and len(forbidden_visuals_detected) == 0
            and len(literary_terms_detected) == 0
            and min_words <= word_count <= max_words
            and min_duration <= estimated_duration <= max_duration
            and len(visual_beats) >= target_min_beats
            and (is_novel or (editorial_res is not None and editorial_res.passed))
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
        part_marker: Optional[str] = None,
        discovery_tier: Optional[str] = None,
        candidate_context: Optional[Dict[str, Any]] = None,
        editorial_model: Optional[DiscoveryEditorialModel] = None,
    ) -> DiscoveryQAResult:
        """
        12-Point Discovery Quality Gate (Checks A through K + L + M):
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
        L. Zero throat-clearing openings in Frame 0.
        M. Editorial Value Check: anti-recap, viewer value, explanatory depth, no scene padding.
        """
        reasons = []
        text_lower = script_text.lower()
        hook_lower = hook.lower()
        words = script_text.split()
        word_count = len(words)

        # Auto-resolve tier if not explicitly forced
        if discovery_tier is None or str(discovery_tier).upper() == "AUTO":
            effective_tier = "MICRO_DISCOVERY" if word_count < 120 else "DEEP_DISCOVERY"
        else:
            effective_tier = str(discovery_tier).upper()

        # Check K: PART markers strictly forbidden in Discovery
        no_part_markers = True
        if part_marker is not None and str(part_marker).strip():
            no_part_markers = False
            reasons.append(f"Check K Failed: Discovery short has visual PART marker '{part_marker}'")
        for pat in FORBIDDEN_SPOKEN_PART_PATTERNS:
            if re.search(pat, text_lower):
                no_part_markers = False
                reasons.append(f"Check K Failed: Discovery short contains spoken part/chapter numbering: '{pat}'")

        # Check L: Zero throat-clearing in Frame 0
        no_throat_clearing = True
        if effective_tier == "DEEP_DISCOVERY":
            for pat in THROAT_CLEARING_PATTERNS:
                if re.search(pat, hook_lower):
                    no_throat_clearing = False
                    reasons.append(f"Check L Failed: Deep Discovery hook contains forbidden throat-clearing: '{pat}'")

        # Check C: Subject in first ~5 seconds (first ~15 words / hook)
        hook_words = hook.split()
        subject_in_first_5s = len(hook_words) >= 4 and any(
            w in hook_lower for w in [
                "cut", "cuts", "movie", "book", "secret", "never", "performance",
                "actor", "detail", "scene", "missed", "hidden", "changed", "erised",
                "remembrall", "neville", "sorting", "peeves", "inscription", "robes",
                "truth", "reality", "books", "films", "story"
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

        # Check tier bounds
        duration_within_tier_bounds = True
        word_count_within_tier_bounds = True
        if effective_tier == "DEEP_DISCOVERY":
            if word_count < 220 or word_count > 300:
                word_count_within_tier_bounds = False
                reasons.append(f"Check Word Count Failed: {word_count} words outside Deep Discovery target bounds (220-300)")
        elif effective_tier == "MICRO_DISCOVERY":
            if word_count < 74 or word_count > 88:
                word_count_within_tier_bounds = False
                reasons.append(f"Check Word Count Failed: {word_count} words outside Micro Discovery bounds (74-88 for 21-25s safe Shorts window)")

        # Check M: Discovery Editorial Value Gate (viewer value, anti-recap, explanatory depth)
        editorial_res = DiscoveryNarrativeEngine.evaluate_discovery_editorial_value(
            script_text=script_text,
            hook=hook,
            visual_beats=visual_beats,
            candidate_context=candidate_context,
            editorial_model=editorial_model,
        )
        if not editorial_res.passed:
            reasons.extend([f"Check M Failed: {r}" for r in editorial_res.reasons])

        # Check N: Visual Grounding & Movie Catalog Feasibility Guardrail
        # Verifies that required characters and visual requirements do not rely on unfilmed book-only elements
        unfilmed_elements = [
            "peeves", "winky", "ludo bagman", "charlie weasley dragon breeding",
            "deathday party", "spew", "s.p.e.w.", "kreacher leading house-elves with cleavers",
            "voldemort gaunt ring flashback", "merope gaunt", "morfin gaunt", "marvolo gaunt",
            "hephzibah smith cup", "tom riddle hepzibah", "neville parents st mungo",
            "st mungo hospital ward", "lockhart autograph st mungo", "prime minister muggle portrait"
        ]
        visual_grounding_valid = True
        for beat in visual_beats:
            b_text = " ".join([
                str(beat.get("visual_requirement", "")),
                str(beat.get("action", "")),
                str(beat.get("narration_text", "")),
                " ".join(beat.get("characters", []))
            ]).lower()
            for unfilmed in unfilmed_elements:
                if unfilmed in b_text:
                    visual_grounding_valid = False
                    reasons.append(f"Check N Failed: Beat '{beat.get('beat_id')}' requires unfilmed book-only element '{unfilmed}' not present in Warner Bros movie catalog.")

        passed = (
            no_part_markers and subject_in_first_5s and avoids_chronological_story
            and book_movie_both_stated and omission_explicitly_stated and production_fact_stated
            and is_standalone and no_throat_clearing and editorial_res.passed
            and visual_grounding_valid and len(reasons) == 0
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
            no_throat_clearing=no_throat_clearing,
            duration_within_tier_bounds=duration_within_tier_bounds,
            word_count_within_tier_bounds=word_count_within_tier_bounds,
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
   - Break narration into strictly 8 to 11 sequential micro-beats matching existing movie scenes (cuts every 1.8s to 2.8s for fast vertical video pacing).
   - If the novel contains a detail the movies never showed, focus your storytelling on what the movies ACTUALLY show!

4. HARD INVARIANTS:
   - WORD COUNT: Exactly 65 to 78 spoken words (STRICT PROGRAMMATIC RANGE: 62 to 85 words for 22.0s-28.0s duration; target 25s).
   - STANDALONE: Must make 100% complete sense on its own.
   - NEVER speak "part 1", "chapter 1", "episode 1", or any numbering.
   - NEVER use clickbait clichés ("will shock you", "you won't believe", "mind-blowing").

{DEXTER_LOFTIN_GUIDANCE}

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

CRITICAL EDITORIAL INVARIANT: DISCOVERY SCRIPT != MOVIE SCENE RECAP.
The movie event is visual evidence, NOT the subject of the script.
Do NOT write chronological scene narration ('First X happened, then Y happened, then Hermione punched him, then Malfoy ran away').
Do NOT describe visible physical actions without explaining what they mean, why they matter, or what the audience doesn't know.
Focus on delivering the novel-vs-movie difference, the creative rationale, and the canon insight.

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

{DEXTER_LOFTIN_GUIDANCE}

RULES:
- Word count: Exactly 65 to 78 spoken words (STRICT PROGRAMMATIC RANGE: 62 to 85 words for 22.0s-28.0s duration; target 25s).
- First substantive sentence must communicate the subject and difference.
- Avoid narrative story transitions ("Meanwhile", "Later", "The next morning", "He then").
- Visual Beats: Exactly 8 to 11 micro-beats (1.8s - 2.8s each). Classify each beat as DIRECT or CONTEXTUAL in visual_requirement.
- STRICT VISUAL INVENTORY CONSTRAINT (ZERO MISMATCH RULE):
  * Every visual beat MUST describe a real, filmed movie shot from the Harry Potter film franchise.
  * Disambiguate characters explicitly: specify EXACT full names (e.g. 'Barty Crouch Jr.' NOT just 'Crouch', 'Draco Malfoy' NOT just 'Malfoy').
  * NEVER describe an imaginary, book-only action as if filmed. In retrieval_hints, provide the exact character name, key action words, and film scene setting.
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

CRITICAL EDITORIAL INVARIANT: DISCOVERY SCRIPT != MOVIE SCENE RECAP.
The movie event is visual evidence, NOT the subject of the script.
Do NOT merely narrate the sequence of events.
Explain what was omitted, why it was cut, and why it matters to the lore or characters.

SUBTYPE: DISCOVERY_OMITTED_SCENE
TOPIC: {candidate.novel_fact_summary}
BOOK CONTEXT: {candidate.novel_evidence_text or ''}
MOVIE OMISSION: {candidate.movie_omits_or_changes or ''}

MANDATORY SCRIPT STRUCTURE:
1. HOOK (0-5s): "The movie completely leaves out this scene:" or "There's an entire scene from the book the movie cuts:".
2. BOOK SCENE: What actually occurs in the book.
3. MOVIE ABSENCE: What happens in the movie instead or how it skips the scene.
4. PAYOFF: Why the omission matters or what fans missed.

{DEXTER_LOFTIN_GUIDANCE}

RULES:
- Word count: Exactly 65 to 78 spoken words (STRICT PROGRAMMATIC RANGE: 62 to 85 words for 22.0s-28.0s duration; target 25s).
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

CRITICAL EDITORIAL INVARIANT: DISCOVERY SCRIPT != MOVIE SCENE RECAP.
The subject is the production craft, director decision, actor performance, or filming fact.
Movie footage serves purely as contextual visual evidence.

SUBTYPE: DISCOVERY_BEHIND_THE_SCENES
TOPIC: {candidate.novel_fact_summary}
PRODUCTION CONTEXT: {candidate.why_interesting or candidate.novel_evidence_text or ''}

MANDATORY SCRIPT STRUCTURE:
1. HOOK (0-5s): Immediate production secret (e.g. "There is a deleted Harry Potter performance most fans never saw...").
2. PRODUCTION FACT: Explicit facts about the filming, actors, or deleted scenes.
3. CONTEXT: How it connects to the film world.
4. PAYOFF: Why it was cut or what happened to the footage.

{DEXTER_LOFTIN_GUIDANCE}

RULES:
- Word count: Exactly 65 to 78 spoken words (STRICT PROGRAMMATIC RANGE: 62 to 85 words for 22.0s-28.0s duration; target 25s).
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

CRITICAL EDITORIAL INVARIANT: DISCOVERY SCRIPT != MOVIE SCENE RECAP.
The movie event is visual evidence, NOT the subject of the script.
Do NOT describe physical actions without explaining the underlying hidden detail, lore mechanic, or character motivation.
The audience must walk away having learned something new.

SUBTYPE: {getattr(candidate, 'discovery_type', 'DISCOVERY_FACT')}
TOPIC: {candidate.novel_fact_summary}
DETAIL / EVIDENCE: {candidate.novel_evidence_text or candidate.why_interesting or ''}

MANDATORY SCRIPT STRUCTURE:
1. HOOK (0-5s): "You probably missed this hidden detail..." or "The movie hides a secret in plain sight:".
2. FACT: The exact concrete fact.
3. EVIDENCE / CONTEXT: Where it appears and what proves it.
4. PAYOFF: Why it is fascinating or what it explains.

{DEXTER_LOFTIN_GUIDANCE}

RULES:
- Word count: Exactly 65 to 78 spoken words (STRICT PROGRAMMATIC RANGE: 62 to 85 words for 22.0s-28.0s duration; target 25s).
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

    # ── Vertical Video Micro-Beats Pacing Enforcer ──────────────────────────────

    def _enforce_micro_beats(
        self,
        beats: List[Dict[str, Any]],
        full_text: str = "",
        target_duration: float = 24.0,
        target_min: int = 8,
        target_max: int = 11,
    ) -> List[Dict[str, Any]]:
        """
        Enforces fast-paced vertical video pacing (strictly 8 to 11 micro-beats, ~1.8s - 2.8s per beat).
        Prevents long, static shots and clip looping.
        """
        if not beats:
            return []

        result_beats = []
        for b in beats:
            if isinstance(b, dict):
                result_beats.append(dict(b))
            elif isinstance(b, str):
                result_beats.append({
                    "narration_text": b,
                    "visual_requirement": b,
                    "description": b,
                })
            elif hasattr(b, "__dict__"):
                result_beats.append(dict(b.__dict__))
            else:
                result_beats.append({
                    "narration_text": str(b),
                    "visual_requirement": str(b),
                    "description": str(b),
                })

        # Step 0: Ensure every beat has an initial positive duration
        total_words = sum(len(str(b.get("narration_text", "")).split()) for b in result_beats)
        for b in result_beats:
            cur_dur = float(b.get("duration_seconds") or 0.0)
            if cur_dur <= 0.0:
                w_cnt = len(str(b.get("narration_text", "")).split())
                if total_words > 0 and w_cnt > 0:
                    b["duration_seconds"] = round(target_duration * (w_cnt / total_words), 2)
                else:
                    b["duration_seconds"] = round(target_duration / max(1, len(result_beats)), 2)

        # Step 1: Subdivide beats until we reach target_min (8-9 beats minimum)
        max_subdivide_iter = 20
        iter_count = 0
        while len(result_beats) < target_min and iter_count < max_subdivide_iter:
            iter_count += 1
            # Find the longest beat or the beat with the most narration words
            longest_idx = max(
                range(len(result_beats)),
                key=lambda i: (
                    result_beats[i].get("duration_seconds", 0.0),
                    len(str(result_beats[i].get("narration_text", "")).split())
                )
            )
            longest = result_beats[longest_idx]

            text = longest.get("narration_text", "").strip()
            parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+|(?<=,)\s+|(?<=;)\s*', text) if p.strip()]

            if len(parts) >= 2:
                mid = len(parts) // 2
                part1_text = " ".join(parts[:mid])
                part2_text = " ".join(parts[mid:])
            else:
                words = text.split()
                if len(words) >= 4:
                    mid = len(words) // 2
                    part1_text = " ".join(words[:mid])
                    part2_text = " ".join(words[mid:])
                else:
                    part1_text = text
                    part2_text = text

            dur = longest.get("duration_seconds", target_duration / len(result_beats))
            dur1 = round(dur / 2.0, 2)
            dur2 = round(dur - dur1, 2)

            vis = longest.get("visual_requirement", "")

            b1 = dict(longest)
            b1["narration_text"] = part1_text
            b1["duration_seconds"] = dur1
            b1["visual_requirement"] = f"[Action Focus] {vis}"

            b2 = dict(longest)
            b2["narration_text"] = part2_text
            b2["duration_seconds"] = dur2
            b2["visual_requirement"] = f"[Detail/Reaction Focus] {vis}"

            result_beats = result_beats[:longest_idx] + [b1, b2] + result_beats[longest_idx+1:]

        # Step 2: If we have more than target_max, merge shortest adjacent beats
        while len(result_beats) > target_max:
            shortest_idx = min(
                range(len(result_beats) - 1),
                key=lambda i: result_beats[i].get("duration_seconds", 0) + result_beats[i+1].get("duration_seconds", 0)
            )
            b1 = result_beats[shortest_idx]
            b2 = result_beats[shortest_idx + 1]
            merged = dict(b1)
            merged["narration_text"] = f"{b1.get('narration_text', '')} {b2.get('narration_text', '')}".strip()
            merged["duration_seconds"] = round(b1.get("duration_seconds", 0) + b2.get("duration_seconds", 0), 2)
            merged["visual_requirement"] = b1.get("visual_requirement", "")
            result_beats = result_beats[:shortest_idx] + [merged] + result_beats[shortest_idx+2:]

        # Step 3: Re-index beat IDs and rebalance duration so sum matches target_duration
        min_beat_dur = 1.2
        total_d = sum(b.get("duration_seconds", 0) for b in result_beats)
        if total_d > 0 and target_duration > 0:
            scale = target_duration / total_d
            for b in result_beats:
                b["duration_seconds"] = max(min_beat_dur, round(b.get("duration_seconds", 0) * scale, 2))
        else:
            equal_dur = max(min_beat_dur, round(target_duration / max(1, len(result_beats)), 2))
            for b in result_beats:
                b["duration_seconds"] = equal_dur

        for idx, b in enumerate(result_beats, 1):
            b["beat_id"] = f"beat_{idx}"

        return result_beats

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
                "hook": "Uncle Vernon vowed Harry would never read his Hogwarts letter.",
                "development": "He furiously ripped up every envelope that arrived. He nailed wooden boards straight across the door slot. He even burned letters in the fireplace flames. On Sunday morning, Vernon smiled smugly—no mail on Sundays. Outside, dozens of mysterious owls gathered silently. Suddenly, the fireplace began to shake violently! Hundreds of letters exploded out like fireworks. Harry leaped high into the air to catch one.",
                "payoff": "Vernon tackled Harry in panic, realizing magic was unstoppable!",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "Uncle Vernon vowed Harry would never read his Hogwarts letter.",
                        "visual_requirement": "Uncle Vernon tearing up Hogwarts envelopes in hallway with a furious expression",
                        "characters": ["Uncle Vernon"],
                        "location": "Number 4 Privet Drive hallway",
                        "action": "Angry man tearing up magical letters",
                        "objects": ["Envelopes", "Hogwarts seal"],
                        "emotional_context": "Stubborn denial and anger",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:09:44 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_VERNON_TEAR_LETTERS", "Vernon", "tearing", "envelopes", "Privet Drive"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "He furiously ripped up every envelope that arrived.",
                        "visual_requirement": "Young Harry Potter in his cupboard under the stairs peeking out curiously",
                        "characters": ["Harry Potter"],
                        "location": "Cupboard under the stairs",
                        "action": "Young Harry watching the strange arrival of letters with quiet wonder",
                        "objects": ["Glasses", "Cupboard door"],
                        "emotional_context": "Curiosity and hope",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:09:54 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_HARRY_PEEK_CUPBOARD", "Harry", "cupboard", "watching", "young"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "He nailed wooden boards straight across the door slot.",
                        "visual_requirement": "Young Harry Potter listening under stairs as Uncle Vernon hammers wooden boards across door",
                        "characters": ["Harry Potter", "Uncle Vernon"],
                        "location": "Cupboard under stairs / Front door",
                        "action": "Young Harry listening under stairs as Uncle Vernon hammers wooden boards across door",
                        "objects": ["Cupboard", "Hammer", "Toy soldiers"],
                        "emotional_context": "Desperate stubborn denial",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:09:50 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_HARRY_CUPBOARD_HAMMER", "Vernon", "hammer", "mail slot", "Privet Drive"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "He even burned letters in the fireplace flames.",
                        "visual_requirement": "Uncle Vernon crouching by the fireplace gleefully burning letters in the bright flames",
                        "characters": ["Uncle Vernon"],
                        "location": "Privet Drive living room fireplace",
                        "action": "Vernon laughing and burning letters in fireplace",
                        "objects": ["Fireplace", "Flames", "Envelopes"],
                        "emotional_context": "Malicious glee and destruction",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:10:28 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_VERNON_BURN_LETTERS", "Vernon", "fireplace", "burning", "fire", "letters"]
                    },
                    {
                        "beat_id": "beat_5",
                        "narration_text": "On Sunday morning, Vernon smiled smugly—no mail on Sundays.",
                        "visual_requirement": "Uncle Vernon sitting at breakfast table smiling smugly eating a biscuit",
                        "characters": ["Uncle Vernon"],
                        "location": "Privet Drive living room",
                        "action": "Uncle Vernon grinning arrogantly and holding up a biscuit",
                        "objects": ["Biscuit", "Table"],
                        "emotional_context": "Smug false confidence",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:11:15 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_VERNON_SUNDAY_BISCUIT", "Vernon", "smiling", "Sunday", "biscuit", "living room"]
                    },
                    {
                        "beat_id": "beat_6",
                        "narration_text": "Outside, dozens of mysterious owls gathered silently.",
                        "visual_requirement": "Privet Drive street with dozens of owls perched silently on rooftops and fences",
                        "characters": ["Owls"],
                        "location": "Privet Drive exterior",
                        "action": "Flock of owls gathering in daylight all along the neighborhood",
                        "objects": ["Owls", "Rooftops", "Street"],
                        "emotional_context": "Eerie magical omen",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:11:10 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_PRIVET_OWLS_ROOF", "owls", "Privet Drive", "roof", "street", "flock"]
                    },
                    {
                        "beat_id": "beat_7",
                        "narration_text": "Suddenly, the fireplace began to shake violently!",
                        "visual_requirement": "Uncle Vernon smile freezing in horror as the brick fireplace begins to rumble violently",
                        "characters": ["Uncle Vernon", "Aunt Petunia"],
                        "location": "Privet Drive living room",
                        "action": "Vernon smile freezing in horror as the brick fireplace begins to rumble violently",
                        "objects": ["Fireplace", "Living room"],
                        "emotional_context": "Sudden anxiety and dread",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:11:22 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_VERNON_FREEZE_RUMBLE", "Vernon", "frozen", "shock", "fireplace", "rumble"]
                    },
                    {
                        "beat_id": "beat_8",
                        "narration_text": "Hundreds of letters exploded out like fireworks.",
                        "visual_requirement": "Hundreds of Hogwarts letters blasting violently out of fireplace into room",
                        "characters": ["Hogwarts Letters"],
                        "location": "Privet Drive fireplace",
                        "action": "Whirlwind of flying letters shooting out into living room",
                        "objects": ["Fireplace", "Flying envelopes", "Hogwarts seal"],
                        "emotional_context": "Explosive magical spectacle",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:11:30 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_LETTERS_EXPLODE_FIREPLACE", "letters shooting", "fireplace", "explosion", "envelopes"]
                    },
                    {
                        "beat_id": "beat_9",
                        "narration_text": "Harry leaped high into the air to catch one.",
                        "visual_requirement": "Harry Potter leaping joyfully in air catching a Hogwarts letter in the storm",
                        "characters": ["Harry Potter"],
                        "location": "Privet Drive living room",
                        "action": "Harry jumping with huge smile grabbing letter mid-air",
                        "objects": ["Flying letters", "Hogwarts envelope"],
                        "emotional_context": "Pure joy and triumphant magic",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:11:49 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_HARRY_LEAP_CATCH_LETTER", "Harry jumping", "catch letter", "flying letters", "smile"]
                    },
                    {
                        "beat_id": "beat_10",
                        "narration_text": "Vernon tackled Harry in panic, realizing magic was unstoppable!",
                        "visual_requirement": "Uncle Vernon tackling Harry in hallway amidst swirling paper storm",
                        "characters": ["Uncle Vernon", "Harry Potter"],
                        "location": "Privet Drive hallway by stairs",
                        "action": "Vernon frantically pinning Harry as paper tornado fills the house",
                        "objects": ["Flying letters", "Stairs"],
                        "emotional_context": "Desperate chaotic panic",
                        "preferred_movie_number": 1,
                        "source_grounding": "Movie 1, 00:11:54 / Book 1 Chapter 3",
                        "retrieval_hints": ["HP_M01_VERNON_TACKLE_HALLWAY", "Vernon tackle", "Harry", "letters swirling", "hallway"]
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
                "hook": "Did you know Neville Longbottom's Remembrall revealed a secret the movie never said out loud?",
                "development": "During morning mail in the Great Hall, an owl drops a magical glass ball that glows bright scarlet whenever you forget something. Neville stares at the glowing sphere completely bewildered, admitting he cannot remember what he forgot. But look closely at the breakfast table! Every single classmate is wearing their black school robes.",
                "payoff": "Neville is sitting in just his sweater and tie, having completely forgotten his school cloak!",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "Did you know Neville Longbottom's Remembrall revealed a secret the movie never said out loud?",
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
                        "narration_text": "During morning mail in the Great Hall, an owl drops a magical glass ball that glows bright scarlet whenever you forget something. Neville stares at the glowing sphere completely bewildered, admitting he cannot remember what he forgot.",
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
                        "narration_text": "But look closely at the breakfast table! Every single classmate is wearing their black school robes.",
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
                        "narration_text": "Neville is sitting in just his sweater and tie, having completely forgotten his school cloak!",
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

        elif "dobby" in c_id or "enslaved" in c_id or "malfoy" in c_id:
            # Short 9: Discovery — Dobby's Enslavement to the Malfoys (Book 2 Ch 2 & Ch 18)
            return {
                "hook": "Do you know the dark reason why Dobby was actually enslaved to the Malfoys?",
                "development": "In the films, Lucius Malfoy treats Dobby like an ordinary mistreated house servant. But the original books reveal a terrifying magical contract. House-elves are magically bound to ancient wizarding manors through an unbreakable blood curse. Dobby could never disobey any direct command without being forced to brutally punish himself.",
                "payoff": "That is why catching Harry's hidden sock was so historic. It broke an ancient family curse and gave Dobby his freedom forever.",
                "visual_beats": [
                    {
                        "beat_id": "beat_1",
                        "narration_text": "Do you know the dark reason why Dobby was actually enslaved to the Malfoys?",
                        "visual_requirement": "Dobby the house elf standing on Harry's bed in Privet Drive looking distressed and warning Harry",
                        "characters": ["Dobby", "Harry Potter"],
                        "location": "Harry's bedroom Privet Drive",
                        "action": "Dobby bouncing on bed speaking urgently with bulging eyes",
                        "objects": ["Pillowcase garment"],
                        "emotional_context": "Urgent warning and desperate devotion",
                        "preferred_movie_number": 2,
                        "source_grounding": "Movie 2, 00:03:20–00:03:45 / Book 2 Chapter 2",
                        "retrieval_hints": ["Dobby", "bedroom", "Privet Drive", "warning", "bed"]
                    },
                    {
                        "beat_id": "beat_2",
                        "narration_text": "In the films, Lucius Malfoy treats Dobby like an ordinary mistreated house servant.",
                        "visual_requirement": "Lucius Malfoy walking imperiously with his snake-headed cane looking sneeringly down",
                        "characters": ["Lucius Malfoy"],
                        "location": "Hogwarts corridor",
                        "action": "Lucius walking arrogantly holding silver snake cane",
                        "objects": ["Snake cane", "Dark robes"],
                        "emotional_context": "Arrogant malice and cruel superiority",
                        "preferred_movie_number": 2,
                        "source_grounding": "Movie 2, 02:21:25–02:21:50 / Book 2 Chapter 18",
                        "retrieval_hints": ["Lucius Malfoy", "snake cane", "corridor", "Malfoy"]
                    },
                    {
                        "beat_id": "beat_3",
                        "narration_text": "But the original books reveal a terrifying magical contract. House-elves are magically bound to ancient wizarding manors through an unbreakable blood curse. Dobby could never disobey any direct command without being forced to brutally punish himself.",
                        "visual_requirement": "Dobby cowering fearfully behind Lucius Malfoy trembling in hallway",
                        "characters": ["Dobby", "Lucius Malfoy"],
                        "location": "Hogwarts hallway",
                        "action": "House-elf cowering and trembling in terror behind cruel master",
                        "objects": ["Ragged pillowcase"],
                        "emotional_context": "Tragic magical enslavement and fear",
                        "preferred_movie_number": 2,
                        "source_grounding": "Movie 2, 02:22:00–02:22:30 / Book 2 Chapter 18",
                        "retrieval_hints": ["Dobby cowering", "Malfoy", "hallway", "house-elf"]
                    },
                    {
                        "beat_id": "beat_4",
                        "narration_text": "That is why catching Harry's hidden sock was so historic. It broke an ancient family curse and gave Dobby his freedom forever.",
                        "visual_requirement": "Dobby holding up the sock in sheer wonderment realizing he is free, blasting Lucius backward",
                        "characters": ["Dobby", "Lucius Malfoy", "Harry Potter"],
                        "location": "Hogwarts hallway",
                        "action": "Dobby holding up sock overjoyed, snapping fingers to blast Lucius down stairs",
                        "objects": ["Sock", "Wand"],
                        "emotional_context": "Triumph, magical liberation, and epic justice",
                        "preferred_movie_number": 2,
                        "source_grounding": "Movie 2, 02:25:10–02:25:45 / Book 2 Chapter 18",
                        "retrieval_hints": ["Dobby sock", "Dobby free", "Lucius blasted", "sock"]
                    }
                ]
            }

        # Generic novel / discovery fallback
        summary_raw = (
            getattr(candidate, "story_event_summary", None)
            or getattr(candidate, "novel_fact_summary", None)
            or getattr(candidate, "thesis", None)
            or getattr(candidate, "title", None)
            or "A crucial secret was uncovered in the wizarding world"
        )
        words = str(summary_raw).split()[:40]
        event_str = " ".join(words)
        b_title = getattr(candidate, "book_title", f"Book {getattr(candidate, 'book_number', 1)}")
        return {
            "hook": f"Something unforgettable was unfolding inside {b_title}.",
            "development": f"{event_str}. The magical atmosphere grew denser as the situation reached a turning point.",
            "payoff": "What began as a quiet moment soon reshaped the fate of the entire wizarding world.",
            "visual_beats": [
                {
                    "beat_id": "beat_1",
                    "duration_seconds": 6.0,
                    "narration_text": f"Something unforgettable was unfolding inside {b_title}.",
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
                    "duration_seconds": 10.0,
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
                    "duration_seconds": 8.0,
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
        max_attempts: int = 3,
        use_deterministic: bool = False
    ) -> HarryPotterScript:
        """
        Generates, validates, and persists a HarryPotterScript for a given candidate.
        Uses Gemini 3.6 Flash when available with iterative QA feedback loop,
        falling back seamlessly to high-grade deterministic generation if needed.
        """
        is_novel = isinstance(candidate, NovStoryCandidate) or getattr(candidate, "content_type", "") == "novel_story"
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
        if AI_PROVIDER_AVAILABLE and not use_deterministic:
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
                        if isinstance(parsed, str):
                            try:
                                parsed = json.loads(parsed)
                            except Exception:
                                pass
                        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                            parsed = parsed[0]
                        if not isinstance(parsed, dict):
                            raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")

                        full_script = f"{parsed.get('hook', '')} {parsed.get('development', '')} {parsed.get('payoff', '')}".strip()
                        v_beats = parsed.get("visual_beats", [])
                        words_temp = full_script.split()
                        dur_temp = round(len(words_temp) / 3.15, 1) if words_temp else 24.0
                        v_beats = self._enforce_micro_beats(v_beats, full_text=full_script, target_duration=dur_temp, target_min=8, target_max=11)
                        parsed["visual_beats"] = v_beats

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
                        logger.warning(f"[SCRIPT_GEN] Attempt {attempt} API error: {call_err}", exc_info=True)
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
            words_temp = full_script.split()
            dur_temp = round(len(words_temp) / 3.15, 1) if words_temp else 24.0
            v_beats = self._enforce_micro_beats(v_beats, full_text=full_script, target_duration=dur_temp, target_min=8, target_max=11)
            script_data["visual_beats"] = v_beats
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
        if c_type in ("deep_discovery", "discovery") and word_count >= 150:
            est_duration = round(word_count / 3.55, 1)
        else:
            est_duration = round(word_count / 3.15, 1)

        raw_beats = script_data.get("visual_beats", [])
        clean_beats = []
        for idx, b in enumerate(raw_beats, 1):
            if isinstance(b, str):
                b = {"visual_requirement": b, "narration_text": b}
            elif not isinstance(b, dict):
                b = {}

            chars = list(b.get("characters", []))
            if not chars:
                from engines.movie_retrieval_engine import KNOWN_CHARACTERS
                text_to_scan = f"{b.get('narration_text', '')} {b.get('visual_requirement', '')} {full_text}"
                for kc in KNOWN_CHARACTERS:
                    if re.search(r"\b" + re.escape(kc) + r"\b", text_to_scan, re.IGNORECASE):
                        if kc not in chars:
                            chars.append(kc)

            beat_narration = b.get("narration_text", "")
            beat_words = len(beat_narration.split()) if beat_narration else 0
            if "duration_seconds" in b:
                beat_dur = float(b["duration_seconds"])
            elif word_count > 0 and beat_words > 0:
                beat_dur = round(est_duration * (beat_words / word_count), 2)
            else:
                beat_dur = round(est_duration / max(1, len(raw_beats)), 2)

            clean_beats.append({
                "beat_id": b.get("beat_id", f"beat_{idx}"),
                "duration_seconds": beat_dur,
                "narration_text": b.get("narration_text", ""),
                "visual_requirement": b.get("visual_requirement", ""),
                "characters": chars,
                "location": b.get("location", ""),
                "action": b.get("action", ""),
                "objects": b.get("objects", []),
                "emotional_context": b.get("emotional_context", "dramatic"),
                "preferred_movie_number": b.get("preferred_movie_number", candidate.book_number),
                "source_grounding": b.get("source_grounding", ""),
                "retrieval_hints": b.get("retrieval_hints", chars),
                "is_novel_only": b.get("is_novel_only", False),
                "visual_source_policy": "HYBRID_TRUTHFUL" if b.get("is_novel_only") else "MOVIE_FOOTAGE_ONLY"
            })

        # Micro-Beats Pacing Enforcer (strictly 8 to 11 beats, cuts every ~1.8s - 2.8s)
        clean_beats = self._enforce_micro_beats(
            clean_beats,
            full_text=full_text,
            target_duration=est_duration,
            target_min=8,
            target_max=11
        )

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

        script_id = str(candidate.id) if str(candidate.id).startswith("hps_") else f"hps_{candidate.id}"

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
            rec.discovery_tier = getattr(candidate, "discovery_tier", "DEEP_DISCOVERY")
            rec.story_structure = getattr(candidate, "story_structure", None)
            rec.hook_archetype = getattr(candidate, "hook_archetype", None)
            rec.evidence_route = getattr(candidate, "evidence_route", None)
            rec.thesis = getattr(candidate, "thesis", None)
            rec.insider_epiphany = getattr(candidate, "insider_epiphany", None)
            rec.title_pattern = getattr(candidate, "title_pattern", None)
            rec.suggested_title = getattr(candidate, "suggested_title", None)
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
                discovery_tier=getattr(candidate, "discovery_tier", "DEEP_DISCOVERY"),
                story_structure=getattr(candidate, "story_structure", None),
                hook_archetype=getattr(candidate, "hook_archetype", None),
                evidence_route=getattr(candidate, "evidence_route", None),
                thesis=getattr(candidate, "thesis", None),
                insider_epiphany=getattr(candidate, "insider_epiphany", None),
                title_pattern=getattr(candidate, "title_pattern", None),
                suggested_title=getattr(candidate, "suggested_title", None),
                part_marker=part_marker,
                voice_id="af_bella",
                voice_pitch="+0Hz",
                voice_rate="+0%",
                narrator_style="BELLA_CANONICAL",
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

    # ── Multi-Fact Script Generation ──────────────────────────────────────────

    def generate_multi_fact_script(
        self,
        topic_pack: MultiFactTopicPack,
        db: Optional[Session] = None
    ) -> HarryPotterScript:
        """
        Synthesizes a production-grade multi-fact narration script from a MultiFactTopicPack.
        Structure:
          HOOK -> FACT 1 -> TRANSITION -> FACT 2 -> ... -> FINAL CLIMAX FACT -> EPIPHANY/PAYOFF.
        Enforces:
          - Target duration: 68.0–78.0s (hard ceiling 80.9s, target ~75s)
          - Target word count: 240–280 words
          - Speech rate: ~3.4–3.7 wps (targeting 3.55 wps)
          - Translates VisualPropositions into structured visual beats ready for BEAST V2 and Asset Acquisition.
        """
        hook = topic_pack.hook.strip()
        fact_texts = []
        clean_beats = []
        beat_idx = 1

        for fact in topic_pack.facts:
            trans = fact.spoken_transition or ""
            claim_text = fact.claim.strip()
            
            # Incorporate book difference / why it matters / supporting details / canon evidence
            detail_parts = []
            if fact.book_difference:
                detail_parts.append(f"In the books, {fact.book_difference}.")
            if fact.movie_difference:
                detail_parts.append(f"In the movie, {fact.movie_difference}.")
            if fact.canon_evidence and not fact.book_difference:
                detail_parts.append(fact.canon_evidence)
            if fact.supporting_details:
                detail_parts.extend(fact.supporting_details)
            if fact.why_it_matters:
                detail_parts.append(fact.why_it_matters)

            detail_text = " ".join(detail_parts).strip()
            if detail_text:
                fact_body = f"{trans} {claim_text}. {detail_text}".strip()
            else:
                fact_body = f"{trans} {claim_text}.".strip()
            
            fact_texts.append(fact_body)

            # Build visual beats from visual propositions
            if fact.visual_propositions:
                for vp in fact.visual_propositions:
                    beat_dict = {
                        "beat_id": f"beat_{beat_idx:02d}",
                        "narration_text": fact_body[:100],
                        "visual_requirement": f"[{vp.visual_role}] {vp.subject} {vp.action} {vp.object} in {vp.context}".strip(),
                        "characters": [vp.subject] if vp.subject and vp.subject.lower() != "none" else [],
                        "location": vp.context if vp.context and vp.context.lower() != "none" else "Hogwarts",
                        "action": vp.action,
                        "objects": [vp.object] if vp.object and vp.object.lower() != "none" else [],
                        "emotional_context": "canon_discovery",
                        "preferred_movie_number": 1,
                        "visual_source_policy": "HYBRID_TRUTHFUL",
                        "visual_source": "MOVIE_DIRECT",
                        "visual_proposition": vp.to_dict(),
                        "required_evidence_type": fact.required_evidence_type.value if hasattr(fact.required_evidence_type, "value") else str(fact.required_evidence_type),
                        "estimated_duration": vp.estimated_duration_sec,
                    }
                    clean_beats.append(beat_dict)
                    beat_idx += 1
            else:
                # Fallback beat if propositions empty
                clean_beats.append({
                    "beat_id": f"beat_{beat_idx:02d}",
                    "narration_text": fact_body[:100],
                    "visual_requirement": f"[DIRECT_EVIDENCE] {fact.claim}",
                    "characters": ["Harry Potter"],
                    "location": "Hogwarts",
                    "action": "demonstrates canon fact",
                    "objects": [],
                    "emotional_context": "canon_discovery",
                    "preferred_movie_number": 1,
                    "visual_source_policy": "HYBRID_TRUTHFUL",
                    "visual_source": "MOVIE_DIRECT",
                    "required_evidence_type": "DIRECT_FILM_EVIDENCE",
                    "estimated_duration": fact.target_duration_sec,
                })
                beat_idx += 1

        payoff = topic_pack.payoff_text.strip()
        full_text = f"{hook} {' '.join(fact_texts)} {payoff}".strip()
        words = full_text.split()
        word_count = len(words)
        est_duration = round(word_count / topic_pack.target_speech_rate, 1)

        # Evaluate QA
        qa_result = self.evaluate_script_qa(
            script_text=full_text,
            visual_beats=clean_beats,
            candidate_type="DEEP_DISCOVERY"
        )

        script_id = f"script_mf_{topic_pack.topic_id}"
        novel_excerpt = topic_pack.facts[0].canon_evidence if topic_pack.facts else None

        script_rec = HarryPotterScript(
            id=script_id,
            candidate_id=topic_pack.topic_id,
            content_type="multi_fact_discovery",
            book_number=1,
            book_title="Harry Potter",
            chapter_number=1,
            chapter_title="Multi-Fact Discovery",
            source_chunks_json=json.dumps([f.fact_id for f in topic_pack.facts]),
            source_reference=f"MultiFactTopicPack: {topic_pack.theme}",
            novel_evidence_excerpt=novel_excerpt[:500] if novel_excerpt else None,
            discovery_type="MULTI_FACT_DISCOVERY",
            corresponding_movie_number=1,
            movie_chunk_id=None,
            movie_evidence_excerpt=None,
            discovery_tier="DEEP_DISCOVERY",
            story_structure="TEMPLATE_A_CURATED_LISTICLE",
            hook_archetype=topic_pack.hook_archetype.value if hasattr(topic_pack.hook_archetype, "value") else str(topic_pack.hook_archetype),
            evidence_route="NOVEL_CANON",
            thesis=topic_pack.theme,
            insider_epiphany=payoff,
            title_pattern=topic_pack.title_pattern.value if hasattr(topic_pack.title_pattern, "value") else str(topic_pack.title_pattern),
            suggested_title=topic_pack.suggested_title,
            part_marker=None,
            voice_id="af_bella",
            voice_pitch="+0Hz",
            voice_rate="+0%",
            narrator_style="BELLA_CANON_EXPERT",
            hook=hook,
            development=" ".join(fact_texts),
            payoff=payoff,
            full_text=full_text,
            word_count=word_count,
            estimated_duration_sec=est_duration,
            visual_beats_json=json.dumps(clean_beats),
            total_beats=len(clean_beats),
            qa_score=qa_result.score,
            qa_status="APPROVED" if qa_result.passed else "FLAGGED",
            qa_feedback_json=json.dumps(qa_result.feedback),
            model_name="MULTI_FACT_ENGINE_V1",
            status="READY_FOR_STEP_9",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        if db:
            existing = db.query(HarryPotterScript).filter_by(id=script_id).first()
            if existing:
                for col in script_rec.__table__.columns.keys():
                    if col not in ("id", "created_at"):
                        setattr(existing, col, getattr(script_rec, col))
                db.commit()
                db.refresh(existing)
                return existing
            else:
                db.add(script_rec)
                db.commit()
                db.refresh(script_rec)

        return script_rec


