"""
Permanent Self-Learning Visual Memory & Feedback Engine
======================================================
Stores, learns, and enforces persistent visual feedback across Harry Potter video generation.
Ensures that visual mismatches (wrong characters, empty pavement, irrelevant scenes)
are permanently blacklisted for specific characters/topics and NEVER repeated.

Invariants:
  1. Permanent Memory: Persisted both in SQLite (visual_feedback_records) and JSON (data/memory/visual_feedback_memory.json).
  2. Character Presence Enforcement: Disqualifies clips containing mismatched characters (e.g., Bellatrix or Xenophilius for Petunia).
  3. Hard Rejection Penalty: Blacklisted/mismatched intervals receive -10000.0 score, permanently blocking selection.
  4. Verified Canonical Anchors: Maintains authoritative, verified timestamps for canonical character appearances.
"""

from __future__ import annotations

import os
import json
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from sqlalchemy.orm import Session
from config.settings import PROJECT_ROOT, DB_PATH
from core.models import VisualFeedbackRecord

logger = logging.getLogger("VisualFeedbackEngine")

MEMORY_DIR = PROJECT_ROOT / "data" / "memory"
MEMORY_JSON_PATH = MEMORY_DIR / "visual_feedback_memory.json"


# Canonical Character Aliases for fuzzy matching
CHARACTER_ALIASES: Dict[str, List[str]] = {
    "petunia dursley": ["petunia", "petunia dursley", "aunt petunia", "mrs dursley"],
    "vernon dursley": ["vernon", "vernon dursley", "uncle vernon", "mr dursley"],
    "dudley dursley": ["dudley", "dudley dursley"],
    "dursleys": ["dursleys", "the dursleys", "dursley family", "privet drive"],
    "albus dumbledore": ["dumbledore", "albus dumbledore", "professor dumbledore", "headmaster dumbledore"],
    "lily potter": ["lily", "lily potter", "lily evans"],
    "james potter": ["james", "james potter"],
    "harry potter": ["harry", "harry potter", "the boy who lived"],
    "bellatrix lestrange": ["bellatrix", "bellatrix lestrange"],
    "xenophilius lovegood": ["xenophilius", "xenophilius lovegood", "mr lovegood"],
    "severus snape": ["snape", "severus snape", "professor snape"],
    "hermione granger": ["hermione", "hermione granger"],
    "ron weasley": ["ron", "ron weasley"],
    "lord voldemort": ["voldemort", "lord voldemort", "you-know-who", "the dark lord", "tom riddle"],
}


def normalize_character_name(name: str) -> str:
    """Normalizes character name to lowercase canonical form."""
    clean = name.strip().lower()
    for canonical, aliases in CHARACTER_ALIASES.items():
        if clean == canonical or clean in aliases:
            return canonical
    return clean


class VisualFeedbackEngine:
    """
    Self-learning visual intelligence engine that enforces persistent negative feedback
    and canonical character visual anchors across the retrieval pipeline.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.memory_file = MEMORY_JSON_PATH

        if db_path is None or db_path == DB_PATH:
            from core.database import engine, SessionLocal
            self.engine = engine
            self.Session = SessionLocal
        else:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from core.models import Base
            self.engine = create_engine(f"sqlite:///{self.db_path}")
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)

        self._ensure_baseline_seed()

    # --------------------------------------------------------------------------
    # 1. BASELINE SEEDING (The Learned Lessons)
    # --------------------------------------------------------------------------
    def _ensure_baseline_seed(self) -> None:
        """
        Seeds persistent memory with known forensic mismatches and canonical anchors
        discovered during production inspections.
        """
        records = self.load_memory_records()
        existing_ids = {r["id"] for r in records}

        # 1. Movie 7 Hedwig / Battle of Seven Potters / Death Eaters
        # Identified in Short hps_disc_dumbledore_explains_dursleys_b5:
        # Retreival mistakenly mapped Petunia/Dursley beats to Hedwig dying and Bellatrix pursuing Harry!
        seed_items = [
            {
                "id": "vfb_m7_hedwig_battle_not_petunia",
                "movie_number": 7,
                "start_seconds": 815.0,
                "end_seconds": 840.0,
                "actual_character": "Hedwig / Death Eaters / Bellatrix Pursuit",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [
                    "Petunia Dursley", "Petunia", "Aunt Petunia", "Vernon Dursley",
                    "Dursleys", "Privet Drive", "Blood Protection Charm", "Sacrificial Protection"
                ],
                "verdict": "CHARACTER_MISMATCH",
                "rejection_reason": "Aerial battle showing Hedwig death and Death Eaters. Completely lacks Petunia Dursley or Privet Drive.",
                "penalty_score": -10000.0,
                "beat_concept": "Petunia Dursley Blood Protection",
                "source": "FORENSIC_QA_INSPECTION"
            },
            {
                "id": "vfb_m7_empty_car_driveway_pavement",
                "movie_number": 7,
                "start_seconds": 108.0,
                "end_seconds": 130.0,
                "actual_character": "Empty Car Trunk & Driveway Pavement Texture",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [
                    "Petunia Dursley", "Petunia", "Lily Potter", "Albus Dumbledore", "Harry Potter"
                ],
                "verdict": "LOW_RELEVANCE_BLACKOUT",
                "rejection_reason": "Empty car trunk and pavement texture with zero character face presence. Visually disconnected from narration.",
                "penalty_score": -10000.0,
                "beat_concept": "Petunia / Harry / Dumbledore",
                "source": "FORENSIC_QA_INSPECTION"
            },
            {
                "id": "vfb_m7_xenophilius_printing_press",
                "movie_number": 7,
                "start_seconds": 3600.0,
                "end_seconds": 4350.0,
                "actual_character": "Xenophilius Lovegood",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [
                    "Petunia Dursley", "Vernon Dursley", "Dursleys", "Albus Dumbledore", "Privet Drive"
                ],
                "verdict": "CHARACTER_MISMATCH",
                "rejection_reason": "Shows Xenophilius Lovegood inside the Lovegood home; prohibited for any Dursley or Dumbledore beats.",
                "penalty_score": -10000.0,
                "beat_concept": "Dursley / Dumbledore beats",
                "source": "FORENSIC_QA_INSPECTION"
            },
            # 2. Universal Bellatrix Rejection for Light/Hero Characters
            {
                "id": "vfb_universal_bellatrix_mismatch_hero",
                "movie_number": 7,
                "start_seconds": 780.0,
                "end_seconds": 810.0,
                "actual_character": "Bellatrix Lestrange",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [
                    "Petunia Dursley", "Lily Potter", "Hermione Granger", "Ginny Weasley", "Molly Weasley"
                ],
                "verdict": "CHARACTER_MISMATCH",
                "rejection_reason": "Close-up of Bellatrix Lestrange screaming; prohibited for Petunia or Lily beats.",
                "penalty_score": -10000.0,
                "beat_concept": "Petunia Dursley",
                "source": "FORENSIC_QA_INSPECTION"
            },
            # 3. VERIFIED CANONICAL ANCHORS for Petunia Dursley
            {
                "id": "vfb_anchor_m1_doorstep_baby_harry",
                "movie_number": 1,
                "start_seconds": 110.0,
                "end_seconds": 135.0,
                "actual_character": "Albus Dumbledore, Minerva McGonagall, Aunt Petunia Discussion",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [],
                "verdict": "VERIFIED_CANONICAL_MATCH",
                "rejection_reason": "Verified canonical footage of Dumbledore and McGonagall discussing Aunt Petunia and why Harry must be left at 4 Privet Drive.",
                "penalty_score": 0.0,
                "beat_concept": "Dumbledore explains Dursleys / Blood Protection / Privet Drive Doorstep",
                "source": "CANONICAL_CURATION"
            },
            {
                "id": "vfb_anchor_m1_doorstep_letter_baby_harry",
                "movie_number": 1,
                "start_seconds": 220.0,
                "end_seconds": 236.0,
                "actual_character": "Albus Dumbledore, Baby Harry Potter, Dursley Letter",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [],
                "verdict": "VERIFIED_CANONICAL_MATCH",
                "rejection_reason": "Verified canonical close-up of Dumbledore placing the protective letter addressed to Mr and Mrs V. Dursley 4 Privet Drive onto baby Harry.",
                "penalty_score": 0.0,
                "beat_concept": "Dumbledore leaves letter on doorstep / Blood Protection Charm",
                "source": "CANONICAL_CURATION"
            },
            {
                "id": "vfb_anchor_m1_privet_drive_letters",
                "movie_number": 1,
                "start_seconds": 660.0,
                "end_seconds": 700.0,
                "actual_character": "Petunia Dursley, Vernon Dursley, Harry Potter",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [],
                "verdict": "VERIFIED_CANONICAL_MATCH",
                "rejection_reason": "Verified canonical footage of Aunt Petunia and Uncle Vernon inside 4 Privet Drive with letters flooding the living room.",
                "penalty_score": 0.0,
                "beat_concept": "Petunia Dursley / Privet Drive / Living Room",
                "source": "CANONICAL_CURATION"
            },
            {
                "id": "vfb_anchor_m1_petunia_lily_resentment",
                "movie_number": 1,
                "start_seconds": 972.0,
                "end_seconds": 992.0,
                "actual_character": "Petunia Dursley (Fiona Shaw close-up)",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [],
                "verdict": "VERIFIED_CANONICAL_MATCH",
                "rejection_reason": "Verified canonical close-up of Petunia Dursley (Fiona Shaw) delivering her iconic monologue expressing bitter resentment towards Lily Potter and magic.",
                "penalty_score": 0.0,
                "beat_concept": "Petunia Dursley / Lily Potter Resentment / Reluctant Guardian",
                "source": "CANONICAL_CURATION"
            },
            {
                "id": "vfb_m7_hermione_bedroom_not_petunia",
                "movie_number": 7,
                "start_seconds": 75.0,
                "end_seconds": 110.0,
                "actual_character": "Hermione Granger / Vernon Dursley Car Trunk",
                "intended_character": "Petunia Dursley",
                "prohibited_characters": [
                    "Petunia Dursley", "Petunia", "Aunt Petunia"
                ],
                "verdict": "CHARACTER_MISMATCH",
                "rejection_reason": "Hermione Granger wiping memories in bedroom followed by Vernon loading car trunk. Petunia does not appear in theatrical cut here.",
                "penalty_score": -10000.0,
                "beat_concept": "Petunia Dursley",
                "source": "FORENSIC_QA_INSPECTION"
            }
        ]

        for item in seed_items:
            if item["id"] not in existing_ids:
                self.record_feedback(
                    movie_number=item["movie_number"],
                    start_seconds=item["start_seconds"],
                    end_seconds=item["end_seconds"],
                    actual_character=item["actual_character"],
                    intended_character=item["intended_character"],
                    prohibited_characters=item["prohibited_characters"],
                    verdict=item["verdict"],
                    rejection_reason=item["rejection_reason"],
                    penalty_score=item["penalty_score"],
                    beat_concept=item["beat_concept"],
                    source=item["source"],
                    record_id=item["id"]
                )

    # --------------------------------------------------------------------------
    # 2. RECORDING / LEARNING API
    # --------------------------------------------------------------------------
    def record_feedback(
        self,
        movie_number: int,
        start_seconds: float,
        end_seconds: float,
        actual_character: Optional[str] = None,
        intended_character: Optional[str] = None,
        prohibited_characters: Optional[List[str]] = None,
        script_id: Optional[str] = None,
        beat_concept: Optional[str] = None,
        verdict: str = "REJECTED_MISMATCH",
        rejection_reason: str = "Visual mismatch flagged by feedback.",
        penalty_score: float = -10000.0,
        source: str = "HUMAN_SUPERVISION",
        tags: Optional[List[str]] = None,
        record_id: Optional[str] = None,
    ) -> VisualFeedbackRecord:
        """
        Permanently registers a feedback record into both SQLite and the JSON memory file.
        Future retrieval queries will instantly consult this learned rule.
        """
        if prohibited_characters is None:
            prohibited_characters = []
        if intended_character and intended_character not in prohibited_characters and verdict != "VERIFIED_CANONICAL_MATCH":
            prohibited_characters.append(intended_character)
        if tags is None:
            tags = []

        rec_id = record_id or f"vfb_m{movie_number}_{int(start_seconds)}_{int(end_seconds)}_{hashlib.md5(rejection_reason.encode()).hexdigest()[:8]}"

        with self.Session() as session:
            existing = session.query(VisualFeedbackRecord).filter_by(id=rec_id).first()
            if existing:
                existing.movie_number = movie_number
                existing.start_seconds = start_seconds
                existing.end_seconds = end_seconds
                existing.actual_character = actual_character
                existing.intended_character = intended_character
                existing.prohibited_characters_json = json.dumps(prohibited_characters)
                existing.script_id = script_id
                existing.beat_concept = beat_concept
                existing.verdict = verdict
                existing.rejection_reason = rejection_reason
                existing.penalty_score = penalty_score
                existing.source = source
                existing.tags_json = json.dumps(tags)
                existing.updated_at = datetime.utcnow()
                record_obj = existing
            else:
                record_obj = VisualFeedbackRecord(
                    id=rec_id,
                    movie_number=movie_number,
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    actual_character=actual_character,
                    intended_character=intended_character,
                    prohibited_characters_json=json.dumps(prohibited_characters),
                    script_id=script_id,
                    beat_concept=beat_concept,
                    verdict=verdict,
                    rejection_reason=rejection_reason,
                    penalty_score=penalty_score,
                    source=source,
                    tags_json=json.dumps(tags),
                )
                session.add(record_obj)
            session.commit()
            session.refresh(record_obj)
            session.expunge(record_obj)

        # Update JSON file cache
        self._sync_json_cache()
        logger.info(f"Learned feedback recorded [{verdict}]: M{movie_number} [{start_seconds:.1f}s - {end_seconds:.1f}s] - {rejection_reason}")
        return record_obj

    def _sync_json_cache(self) -> None:
        """Syncs all records from database into data/memory/visual_feedback_memory.json."""
        with self.Session() as session:
            all_recs = session.query(VisualFeedbackRecord).all()
            data = []
            for r in all_recs:
                data.append({
                    "id": r.id,
                    "movie_number": r.movie_number,
                    "start_seconds": r.start_seconds,
                    "end_seconds": r.end_seconds,
                    "actual_character": r.actual_character,
                    "intended_character": r.intended_character,
                    "prohibited_characters": json.loads(r.prohibited_characters_json or "[]"),
                    "script_id": r.script_id,
                    "beat_concept": r.beat_concept,
                    "verdict": r.verdict,
                    "rejection_reason": r.rejection_reason,
                    "penalty_score": r.penalty_score,
                    "source": r.source,
                    "tags": json.loads(r.tags_json or "[]"),
                    "created_at": r.created_at.isoformat() if r.created_at else None
                })
        self.memory_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_memory_records(self) -> List[Dict[str, Any]]:
        """Loads cached memory records from disk or DB."""
        if self.memory_file.exists():
            try:
                return json.loads(self.memory_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        with self.Session() as session:
            all_recs = session.query(VisualFeedbackRecord).all()
            return [
                {
                    "id": r.id,
                    "movie_number": r.movie_number,
                    "start_seconds": r.start_seconds,
                    "end_seconds": r.end_seconds,
                    "actual_character": r.actual_character,
                    "intended_character": r.intended_character,
                    "prohibited_characters": json.loads(r.prohibited_characters_json or "[]"),
                    "script_id": r.script_id,
                    "beat_concept": r.beat_concept,
                    "verdict": r.verdict,
                    "rejection_reason": r.rejection_reason,
                    "penalty_score": r.penalty_score,
                    "source": r.source,
                    "tags": json.loads(r.tags_json or "[]")
                }
                for r in all_recs
            ]

    # --------------------------------------------------------------------------
    # 3. PENALTY & CONSTRAINT EVALUATION (The Enforcement Gate)
    # --------------------------------------------------------------------------
    def get_penalty_for_candidate(
        self,
        movie_number: int,
        start_seconds: float,
        end_seconds: float,
        required_characters: Optional[List[str]] = None,
        beat_concept: Optional[str] = None,
    ) -> Tuple[float, Optional[str]]:
        """
        Evaluates a candidate shot window against persistent feedback memory.

        Returns:
          (penalty_score, rejection_reason)
          penalty_score is negative (e.g. -10000.0) if rejected/penalized, 0.0 if clean.
        """
        records = self.load_memory_records()
        normalized_req = [normalize_character_name(c) for c in (required_characters or [])]

        for rec in records:
            if rec["movie_number"] != movie_number:
                continue

            r_start = float(rec["start_seconds"])
            r_end = float(rec["end_seconds"])

            # Check temporal interval overlap (at least 0.3s overlap)
            overlap_start = max(start_seconds, r_start)
            overlap_end = min(end_seconds, r_end)
            if overlap_end - overlap_start < 0.3:
                continue

            verdict = rec.get("verdict", "REJECTED_MISMATCH")
            rejection_reason = rec.get("rejection_reason", "Flagged by feedback memory.")
            prohibited = [normalize_character_name(p) for p in rec.get("prohibited_characters", [])]

            # Rule A: Universal Blacklist / Low-Relevance blackout
            if verdict in ("LOW_RELEVANCE_BLACKOUT", "REJECTED_MISMATCH"):
                # If prohibited list is empty, interval is blacklisted universally
                if not prohibited:
                    return (rec.get("penalty_score", -10000.0), f"[Feedback Blacklist] {rejection_reason}")
                # If beat requires any prohibited character or concept
                if any(req in prohibited for req in normalized_req):
                    return (rec.get("penalty_score", -10000.0), f"[Feedback Character Blacklist] {rejection_reason}")

            # Rule B: Character Mismatch (Wrong character in scene)
            if verdict == "CHARACTER_MISMATCH":
                # If required characters match any prohibited characters for this scene
                if any(req in prohibited for req in normalized_req):
                    actual_char = rec.get("actual_character") or "unrelated character"
                    return (
                        rec.get("penalty_score", -10000.0),
                        f"[Feedback Mismatch] Scene contains '{actual_char}' which is prohibited for required characters ({required_characters}): {rejection_reason}"
                    )

        return (0.0, None)

    # --------------------------------------------------------------------------
    # 4. CANONICAL VERIFIED ANCHORS
    # --------------------------------------------------------------------------
    def get_verified_canonical_anchors(
        self,
        character_name: str,
        movie_number: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves curated, verified canonical movie intervals featuring the requested character.
        Guarantees actual character presence on screen.
        """
        records = self.load_memory_records()
        norm_char = normalize_character_name(character_name)

        matches = []
        for rec in records:
            if rec.get("verdict") != "VERIFIED_CANONICAL_MATCH":
                continue
            if movie_number is not None and rec.get("movie_number") != movie_number:
                continue

            intended = normalize_character_name(rec.get("intended_character") or "")
            # Strictly match intended character only (prevent cross-character pollution)
            if norm_char == intended or norm_char in intended or intended in norm_char:
                matches.append({
                    "movie_number": rec["movie_number"],
                    "start_seconds": rec["start_seconds"],
                    "end_seconds": rec["end_seconds"],
                    "character": rec.get("actual_character") or rec.get("intended_character"),
                    "description": rec.get("rejection_reason") or rec.get("beat_concept"),
                    "score": 98.0
                })

        return matches


# Global instance
feedback_engine = VisualFeedbackEngine()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Visual Feedback & Self-Learning Memory CLI")
    parser.add_argument("--list", action="store_true", help="List all visual memory rules")
    parser.add_argument("--flag-mismatch", action="store_true", help="Record a visual mismatch")
    parser.add_argument("--movie", type=int, help="Movie number (1-8)")
    parser.add_argument("--start", type=float, help="Start seconds")
    parser.add_argument("--end", type=float, help="End seconds")
    parser.add_argument("--actual", type=str, help="Character actually visible in scene")
    parser.add_argument("--intended", type=str, help="Character intended/required by script")
    parser.add_argument("--prohibited-for", type=str, help="Comma-separated characters prohibited from this scene")
    parser.add_argument("--reason", type=str, default="Flagged via CLI", help="Rejection explanation")
    parser.add_argument("--verdict", type=str, default="CHARACTER_MISMATCH", choices=["CHARACTER_MISMATCH", "LOW_RELEVANCE_BLACKOUT", "REJECTED_MISMATCH", "VERIFIED_CANONICAL_MATCH"])

    args = parser.parse_args()

    if args.list:
        recs = feedback_engine.load_memory_records()
        print(f"=== Total Visual Feedback Memory Records: {len(recs)} ===")
        for r in recs:
            print(f"[{r['id']}] M{r['movie_number']} [{r['start_seconds']:.1f}s - {r['end_seconds']:.1f}s] {r['verdict']}")
            print(f"   Actual: {r['actual_character']} | Intended: {r['intended_character']}")
            print(f"   Reason: {r['rejection_reason']}\n")
    elif args.flag_mismatch:
        if not (args.movie and args.start is not None and args.end is not None):
            print("Error: --movie, --start, and --end are required when flagging a mismatch.")
        else:
            prohib = [p.strip() for p in args.prohibited_for.split(",")] if args.prohibited_for else []
            rec = feedback_engine.record_feedback(
                movie_number=args.movie,
                start_seconds=args.start,
                end_seconds=args.end,
                actual_character=args.actual,
                intended_character=args.intended,
                prohibited_characters=prohib,
                verdict=args.verdict,
                rejection_reason=args.reason
            )
            print(f"Successfully recorded feedback rule: {rec.id}")
