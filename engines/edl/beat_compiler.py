"""
STORY FORGE — Visual Beat Compiler (Part 2 & Part 3)
====================================================
Compiles locked narration text and word-level timestamps into fine-grained
visual propositions with explicit physical requirements and coverage tiers.
"""

import logging
import re
from typing import List, Dict, Any, Optional, Tuple

from engines.edl.models import (
    LockedNarrationInput,
    VisualBeat,
    CoverageRequirement,
    WordTimestamp,
)
from engines.edl.evidence_contract import (
    INHERENTLY_NON_VISUAL_PATTERNS,
    NarrativeEvidenceContract,
)

logger = logging.getLogger("VisualBeatCompiler")

# Action keywords mapping to canonical physical action types
ACTION_KEYWORDS = {
    "punch": "PUNCH",
    "punched": "PUNCH",
    "punches": "PUNCH",
    "hit": "HIT",
    "hits": "HIT",
    "strike": "STRIKE_WITH_OBJECT",
    "struck": "STRIKE_WITH_OBJECT",
    "strikes": "STRIKE_WITH_OBJECT",
    "kick": "KICK",
    "kicked": "KICK",
    "push": "PUSH",
    "pushed": "PUSH",
    "handover": "HANDOVER",
    "hands": "HANDOVER",
    "handed": "HANDOVER",
    "gives": "HANDOVER",
    "gave": "HANDOVER",
    "throw": "THROW",
    "threw": "THROW",
    "throws": "THROW",
    "catch": "CATCH",
    "caught": "CATCH",
    "catches": "CATCH",
    "break": "BREAK",
    "broke": "BREAK",
    "breaks": "BREAK",
    "snap": "SNAP",
    "snapped": "SNAP",
    "snaps": "SNAP",
    "draw": "DRAW",
    "drew": "DRAW",
    "draws": "DRAW",
    "grab": "GRAB",
    "grabbed": "GRAB",
    "grabs": "GRAB",
    "knock": "KNOCK",
    "knocked": "KNOCK",
    "knocks": "KNOCK",
    "knocking": "KNOCK",
    "smack": "HIT",
    "smacked": "HIT",
    "smacks": "HIT",
    "transform": "TRANSFORM",
    "transforms": "TRANSFORM",
    "transformed": "TRANSFORM",
    "cast": "CAST_SPELL",
    "casts": "CAST_SPELL",
    "casting": "CAST_SPELL",
    "fly": "FLY",
    "flying": "FLY",
    "flew": "FLY",
    "fall": "FALL",
    "fell": "FALL",
    "falls": "FALL",
    "run": "RUN",
    "ran": "RUN",
    "runs": "RUN",
}

# Known canonical characters and objects for extraction
KNOWN_CHARACTERS = {
    "harry": "Harry Potter",
    "harry potter": "Harry Potter",
    "hermione": "Hermione Granger",
    "hermione granger": "Hermione Granger",
    "draco": "Draco Malfoy",
    "draco malfoy": "Draco Malfoy",
    "malfoy": "Draco Malfoy",
    "ron": "Ron Weasley",
    "ron weasley": "Ron Weasley",
    "weasley": "Ron Weasley",
    "snape": "Severus Snape",
    "severus snape": "Severus Snape",
    "dumbledore": "Albus Dumbledore",
    "voldemort": "Lord Voldemort",
    "neville": "Neville Longbottom",
    "neville longbottom": "Neville Longbottom",
    "ollivander": "Garrick Ollivander",
    "garrick ollivander": "Garrick Ollivander",
    "hagrid": "Rubeus Hagrid",
    "buckbeak": "Buckbeak",
    "nagini": "Nagini",
}

KNOWN_OBJECTS = {
    "elder wand": "elder_wand",
    "wand": "wand",
    "sorting hat": "sorting_hat",
    "hat": "sorting_hat",
    "sword": "sword of gryffindor",
    "sword of gryffindor": "sword of gryffindor",
    "remembrall": "remembrall",
    "broom": "broomstick",
    "letter": "hogwarts_letter",
    "snitch": "golden_snitch",
    "stone": "philosophers_stone",
}

# Clues for genuine VISUAL_OPTIONAL abstract / comparative commentary
OPTIONAL_CLUES = [
    "in the book",
    "in the novel",
    "j.k. rowling",
    "readers know",
    "chapter",
    "originally written",
    "never explained",
    "fans often wonder",
    "symbolizes",
    "the reason why",
    "unlike the movie",
    "foreshadowing",
]


class VisualBeatCompiler:
    """
    Compiles locked narration and word-level timestamps into an ordered sequence
    of verified visual beats with exact narration spans.
    """

    def compile_beats(self, narration_input: LockedNarrationInput) -> List[VisualBeat]:
        """
        Compiles the locked narration into visual beats.
        Fails closed if timing is missing or invalid.
        """
        if not narration_input.word_timestamps:
            raise ValueError("FAIL_CLOSED: Missing word timestamps in LockedNarrationInput.")
        if narration_input.exact_narration_duration <= 0.0:
            raise ValueError("FAIL_CLOSED: Invalid narration duration.")

        # Check if editorial beat boundaries were pre-specified in the locked narration
        if narration_input.editorial_beat_boundaries:
            beats = self._compile_from_editorial_boundaries(narration_input)
        else:
            beats = self._compile_from_sentence_boundaries(narration_input)

        # Enforce exact span coverage
        beats = self._normalize_beat_spans(beats, narration_input.exact_narration_duration)
        return beats

    def _compile_from_editorial_boundaries(
        self, narration_input: LockedNarrationInput
    ) -> List[VisualBeat]:
        beats: List[VisualBeat] = []
        words = narration_input.word_timestamps

        for idx, ed_b in enumerate(narration_input.editorial_beat_boundaries):
            b_id = ed_b.get("beat_id", f"beat_{idx + 1:02d}")
            start_sec = float(ed_b.get("start_sec", 0.0))
            end_sec = float(ed_b.get("end_sec", 0.0))
            text_span = ed_b.get("text", "").strip()

            # Align to closest word timestamps if needed
            matched_words = [w for w in words if w.start_sec >= start_sec - 0.15 and w.end_sec <= end_sec + 0.15]
            if matched_words:
                eff_start = matched_words[0].start_sec
                eff_end = matched_words[-1].end_sec
                if not text_span:
                    text_span = " ".join(w.word for w in matched_words)
            else:
                eff_start = start_sec
                eff_end = end_sec

            req_coverage = self._determine_coverage_requirement(text_span, ed_b.get("coverage"))
            assertion, entities, objects, action = self._extract_visual_assertions(text_span, ed_b)

            beat = VisualBeat(
                beat_id=b_id,
                narration_start=round(eff_start, 3),
                narration_end=round(eff_end, 3),
                text_span=text_span,
                narrative_role=ed_b.get("narrative_role", "core_fact"),
                visual_assertion=assertion,
                required_entities=entities,
                required_objects=objects,
                required_action=action,
                required_state=ed_b.get("required_state"),
                required_relationship=ed_b.get("required_relationship"),
                required_location=ed_b.get("required_location"),
                direct_visual_requirement=(req_coverage == CoverageRequirement.DIRECT),
                coverage_requirement=req_coverage,
            )
            beats.append(beat)
        return beats

    def _compile_from_sentence_boundaries(
        self, narration_input: LockedNarrationInput
    ) -> List[VisualBeat]:
        beats: List[VisualBeat] = []
        words = narration_input.word_timestamps

        # If sentences exist, analyze clauses within sentences
        sentences = narration_input.sentence_boundaries
        if not sentences:
            # Fallback: treat all words as single sentence
            sentences = [
                SentenceBoundary(
                    sentence_index=0,
                    text=narration_input.narration_text,
                    start_sec=words[0].start_sec,
                    end_sec=words[-1].end_sec,
                    word_start_idx=0,
                    word_end_idx=len(words) - 1,
                )
            ]

        beat_idx = 1
        for s in sentences:
            s_words = words[s.word_start_idx : s.word_end_idx + 1]
            if not s_words:
                continue

            # Check for clause split points: conjunctions like "because", "while", "as", "but", commas
            sub_clauses = self._split_words_into_clauses(s_words)
            for c_words in sub_clauses:
                if not c_words:
                    continue
                c_start = c_words[0].start_sec
                c_end = c_words[-1].end_sec
                c_text = " ".join(w.word for w in c_words)

                req_coverage = self._determine_coverage_requirement(c_text)
                assertion, entities, objects, action = self._extract_visual_assertions(c_text)

                b = VisualBeat(
                    beat_id=f"beat_{beat_idx:02d}",
                    narration_start=round(c_start, 3),
                    narration_end=round(c_end, 3),
                    text_span=c_text,
                    narrative_role="action" if action else ("lore" if req_coverage == CoverageRequirement.VISUAL_OPTIONAL else "character_interaction"),
                    visual_assertion=assertion,
                    required_entities=entities,
                    required_objects=objects,
                    required_action=action,
                    direct_visual_requirement=(req_coverage == CoverageRequirement.DIRECT),
                    coverage_requirement=req_coverage,
                )
                beats.append(b)
                beat_idx += 1
        return beats

    def _split_words_into_clauses(self, words: List[WordTimestamp]) -> List[List[WordTimestamp]]:
        """
        Splits words into distinct visual clauses / micro-beats at information
        transition conjunctions and compound proposition boundaries.
        """
        if len(words) < 4:
            return [words]

        split_indices = []
        conjunctions = {"because", "while", "before", "after", "as", "when", "although", "but", "whereas"}

        for i, w in enumerate(words):
            cleaned = re.sub(r"[^\w\s]", "", w.word.lower())

            if 2 <= i <= len(words) - 2:
                # Subordinating conjunctions
                if cleaned in conjunctions:
                    split_indices.append(i)
                # Coordinating conjunction 'and' separating distinct propositions
                elif cleaned == "and":
                    remaining_words = [re.sub(r"[^\w\s]", "", rw.word.lower()) for rw in words[i + 1:]]
                    has_subsequent_subject = any(
                        any(c in rw or rw in c for c in KNOWN_CHARACTERS)
                        for rw in remaining_words
                    )
                    has_subsequent_action = any(
                        any(act in rw for act in ACTION_KEYWORDS)
                        for rw in remaining_words
                    )
                    if has_subsequent_subject or has_subsequent_action:
                        split_indices.append(i)
                # Punctuation clause boundary
                elif (w.word.endswith(",") or w.word.endswith(";")) and i < len(words) - 2:
                    split_indices.append(i + 1)

        if not split_indices:
            return [words]

        # Filter split indices to ensure each chunk has at least 2 words
        filtered_indices = []
        prev_idx = 0
        for s_idx in split_indices:
            if (s_idx - prev_idx) >= 2 and (len(words) - s_idx) >= 2:
                filtered_indices.append(s_idx)
                prev_idx = s_idx

        if not filtered_indices:
            return [words]

        clauses = []
        prev = 0
        for s_idx in filtered_indices:
            chunk = words[prev:s_idx]
            if chunk:
                clauses.append(chunk)
            prev = s_idx
        if prev < len(words):
            clauses.append(words[prev:])
        return clauses

    def _determine_coverage_requirement(
        self, text: str, explicit: Optional[str] = None
    ) -> CoverageRequirement:
        lower = text.lower()

        # Non-visual / book-only claims CANNOT be DIRECT visual proof
        for pat in INHERENTLY_NON_VISUAL_PATTERNS:
            if re.search(pat, lower):
                return CoverageRequirement.VISUAL_OPTIONAL

        if explicit:
            return CoverageRequirement(explicit)

        # Genuine VISUAL_OPTIONAL check
        for clue in OPTIONAL_CLUES:
            if clue in lower:
                return CoverageRequirement.VISUAL_OPTIONAL

        # If it mentions any physical character, object, or action -> DIRECT
        for char in KNOWN_CHARACTERS:
            if char in lower:
                return CoverageRequirement.DIRECT
        for act in ACTION_KEYWORDS:
            if act in lower:
                return CoverageRequirement.DIRECT
        for obj in KNOWN_OBJECTS:
            if obj in lower:
                return CoverageRequirement.DIRECT

        return CoverageRequirement.DIRECT

    def _extract_visual_assertions(
        self, text: str, ed_meta: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, List[str], List[str], Optional[str]]:
        lower = text.lower()
        entities = []
        objects = []
        action = None

        if ed_meta:
            if ed_meta.get("required_entities"):
                entities.extend(ed_meta["required_entities"])
            if ed_meta.get("required_objects"):
                objects.extend(ed_meta["required_objects"])
            if ed_meta.get("required_action"):
                action = ed_meta["required_action"]

        # Parse entities
        for name_key, canonical in KNOWN_CHARACTERS.items():
            pattern = r"\b" + re.escape(name_key) + r"\b"
            if re.search(pattern, lower) and canonical not in entities:
                entities.append(canonical)

        # Parse objects
        for obj_key, canonical in KNOWN_OBJECTS.items():
            pattern = r"\b" + re.escape(obj_key) + r"\b"
            if re.search(pattern, lower) and canonical not in objects:
                objects.append(canonical)

        # Parse actions
        if not action:
            for act_key, canonical_act in ACTION_KEYWORDS.items():
                pattern = r"\b" + re.escape(act_key) + r"\b"
                if re.search(pattern, lower):
                    action = canonical_act
                    break

        assertion_str = text
        if action and entities:
            assertion_str = f"{entities[0]} performs {action}"
            if len(entities) > 1:
                assertion_str += f" on {entities[1]}"
            elif objects:
                assertion_str += f" with {objects[0]}"

        return assertion_str, entities, objects, action

    def _normalize_beat_spans(
        self, beats: List[VisualBeat], total_duration: float
    ) -> List[VisualBeat]:
        """Ensures beats are contiguous and cover [0.0, total_duration] without gaps."""
        if not beats:
            return beats

        # Force first beat start to 0.0
        beats[0].narration_start = 0.0

        for i in range(len(beats) - 1):
            curr_b = beats[i]
            next_b = beats[i + 1]
            if curr_b.narration_end != next_b.narration_start:
                # Snap boundaries together
                midpoint = round((curr_b.narration_end + next_b.narration_start) / 2.0, 3)
                curr_b.narration_end = midpoint
                next_b.narration_start = midpoint

        # Force last beat to end at exact_narration_duration
        beats[-1].narration_end = round(total_duration, 3)
        return beats
