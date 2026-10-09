"""
Franchise Vault Clip Selector & Semantic Matcher Engine
=======================================================
Selects the highest-scoring canonical micro-clips from the 1,193+ clip vault
using SQLite FTS5 search, character presence matching, and anti-repetition guard.
Enforces the Strict Zero-Filler Guard: Never returns random filler or unverified clips.
"""
import os
import re
import sys
import json
import sqlite3
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.franchise_clip_db import DB_PATH, get_connection
from core.models import HarryPotterScript, HPMovieClip
from core.smart_crop_engine import SmartCropEngine
from core.visual_mismatch_guard import VisualMismatchGuard
from core.beast_ground_truth_matcher import BeastGroundTruthMatcher
from engines.drive_engine import DriveVaultEngine

logger = logging.getLogger("VaultClipSelector")

STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "up", "about", "into", "over", "after", "is", "are", "was", "were", "shot",
    "close", "medium", "wide", "angle", "view", "pan", "zoom", "s", "and", "or",
    "direct", "scene", "camera", "looking", "look", "looks", "shows", "shown",
    "facing", "standing", "stands", "high", "low", "dramatic", "cinematic", "cut"
}

HONORIFICS = {
    "professor", "lord", "uncle", "aunt", "mr", "mrs", "ms", "miss",
    "sir", "madam", "madame", "headmaster", "minister"
}

CANON_CHAR_MAP = {
    "barty crouch jr": "Barty Crouch Jr.",
    "crouch jr": "Barty Crouch Jr.",
    "barty jr": "Barty Crouch Jr.",
    "david tennant": "Barty Crouch Jr.",
    "barty crouch sr": "Barty Crouch Sr.",
    "crouch sr": "Barty Crouch Sr.",
    "barty crouch senior": "Barty Crouch Sr.",
    "moody": "Alastor Moody",
    "mad-eye": "Alastor Moody",
    "mad-eye moody": "Alastor Moody",
    "alastor moody": "Alastor Moody",
    "voldemort": "Lord Voldemort",
    "quirrell": "Professor Quirrell",
    "harry": "Harry Potter",
    "hagrid": "Rubeus Hagrid",
    "snape": "Severus Snape",
    "dumbledore": "Albus Dumbledore",
    "mcgonagall": "Professor McGonagall",
    "ron": "Ron Weasley",
    "hermione": "Hermione Granger",
    "draco": "Draco Malfoy",
    "draco malfoy": "Draco Malfoy",
    "lucius": "Lucius Malfoy",
    "lucius malfoy": "Lucius Malfoy",
    "neville": "Neville Longbottom",
    "lupin": "Remus Lupin",
    "sirius": "Sirius Black",
    "bellatrix": "Bellatrix Lestrange",
    "umbridge": "Dolores Umbridge",
    "dobby": "Dobby the House-Elf",
    "cedric": "Cedric Diggory",
    "krum": "Viktor Krum",
    "fleur": "Fleur Delacour",
    "cho": "Cho Chang",
    "ginny": "Ginny Weasley",
    "percy": "Percy Weasley",
    "george": "George Weasley",
    "fred": "Fred Weasley",
    "arthur": "Arthur Weasley",
    "molly": "Molly Weasley",
    "fudge": "Cornelius Fudge"
}

# Negative conflict pairs: (Trigger keywords in query) -> (Forbidden terms in candidate clip)
# When the query specifies one entity, candidates matching the conflicting entity get a massive penalty (-800.0)
ENTITY_CONFLICT_RULES = [
    {
        "query_triggers": ["crouch jr", "barty jr", "david tennant", "barty crouch jr"],
        "forbidden_tokens": ["crouch sr", "crouch senior", "barty crouch sr", "bowler hat"],
        "penalty": 800.0
    },
    {
        "query_triggers": ["crouch sr", "crouch senior", "barty senior", "barty crouch sr"],
        "forbidden_tokens": ["crouch jr", "barty jr", "david tennant", "barty crouch jr"],
        "penalty": 800.0
    },
    {
        "query_triggers": ["draco", "draco malfoy"],
        "forbidden_tokens": ["lucius malfoy", "narcissa malfoy"],
        "penalty": 600.0
    },
    {
        "query_triggers": ["lucius", "lucius malfoy"],
        "forbidden_tokens": ["draco malfoy", "draco"],
        "penalty": 600.0
    },
    {
        "query_triggers": ["fred", "fred weasley"],
        "forbidden_tokens": ["george weasley"],
        "penalty": 300.0
    },
    {
        "query_triggers": ["young harry", "baby harry"],
        "forbidden_tokens": ["battle of hogwarts", "deathly hallows"],
        "penalty": 500.0
    }
]

MIN_CONFIDENCE_SCORE = 200.0


def get_character_variants(char_name: str) -> List[str]:
    """
    Returns search variants for a character name to match DB primary_subject and characters_present.
    e.g. 'Severus Snape' -> ['Severus Snape', 'Snape', 'Professor Snape', 'Severus']
    """
    if not char_name:
        return []
    variants = [char_name.strip()]
    low = char_name.lower().strip()
    
    aliases = {
        "severus snape": ["Snape", "Professor Snape", "Severus"],
        "snape": ["Severus Snape", "Professor Snape", "Snape"],
        "professor snape": ["Severus Snape", "Snape", "Professor Snape"],
        "albus dumbledore": ["Dumbledore", "Professor Dumbledore", "Albus", "Headmaster Dumbledore"],
        "dumbledore": ["Albus Dumbledore", "Professor Dumbledore", "Albus"],
        "professor dumbledore": ["Albus Dumbledore", "Dumbledore"],
        "minerva mcgonagall": ["McGonagall", "Professor McGonagall", "Minerva"],
        "mcgonagall": ["Minerva McGonagall", "Professor McGonagall"],
        "professor mcgonagall": ["Minerva McGonagall", "McGonagall"],
        "lord voldemort": ["Voldemort", "Tom Riddle", "Dark Lord", "Lord Voldemort"],
        "voldemort": ["Lord Voldemort", "Tom Riddle", "Dark Lord"],
        "tom riddle": ["Lord Voldemort", "Voldemort", "Tom Riddle"],
        "remus lupin": ["Lupin", "Professor Lupin", "Remus", "Moony"],
        "lupin": ["Remus Lupin", "Professor Lupin", "Moony"],
        "professor lupin": ["Remus Lupin", "Lupin"],
        "sirius black": ["Sirius", "Padfoot", "Sirius Black"],
        "sirius": ["Sirius Black", "Padfoot"],
        "lily potter": ["Lily Evans", "Lily", "Lily Potter"],
        "lily evans": ["Lily Potter", "Lily", "Lily Evans"],
        "lily": ["Lily Potter", "Lily Evans"],
        "james potter": ["James", "Prongs", "James Potter"],
        "james": ["James Potter", "Prongs"],
        "barty crouch jr": ["Barty Crouch Jr.", "Barty Crouch Jr", "Barty Crouch", "Crouch Jr"],
        "barty crouch jr.": ["Barty Crouch Jr.", "Barty Crouch Jr", "Barty Crouch", "Crouch Jr"],
        "barty crouch sr": ["Barty Crouch Sr.", "Barty Crouch Sr", "Barty Crouch", "Crouch Sr"],
        "barty crouch sr.": ["Barty Crouch Sr.", "Barty Crouch Sr", "Barty Crouch", "Crouch Sr"],
        "alastor moody": ["Mad-Eye Moody", "Moody", "Mad-Eye"],
        "mad-eye moody": ["Alastor Moody", "Moody", "Mad-Eye"],
        "harry potter": ["Harry", "Harry Potter"],
        "ron weasley": ["Ron", "Ron Weasley"],
        "hermione granger": ["Hermione", "Hermione Granger"],
        "draco malfoy": ["Draco", "Malfoy", "Draco Malfoy"],
        "lucius malfoy": ["Lucius", "Malfoy", "Lucius Malfoy"],
        "arthur weasley": ["Arthur", "Arthur Weasley"],
        "molly weasley": ["Molly", "Molly Weasley", "Mrs. Weasley", "Mrs Weasley"],
        "fred weasley": ["Fred", "Fred Weasley"],
        "george weasley": ["George", "George Weasley"],
        "fred and george": ["Fred Weasley", "George Weasley", "Fred", "George", "Weasley twins"],
        "ginny weasley": ["Ginny", "Ginny Weasley"],
        "neville longbottom": ["Neville", "Neville Longbottom"],
        "luna lovegood": ["Luna", "Luna Lovegood"],
        "bellatrix lestrange": ["Bellatrix", "Bellatrix Lestrange"],
        "dolores umbridge": ["Umbridge", "Dolores Umbridge"],
        "rubeus hagrid": ["Hagrid", "Rubeus Hagrid"],
        "peter pettigrew": ["Wormtail", "Pettigrew", "Peter Pettigrew"],
        "sybill trelawney": ["Trelawney", "Professor Trelawney"],
        "argus filch": ["Filch", "Argus Filch"],
        "dobby": ["Dobby", "Dobby the House-Elf"],
        "dobby the house-elf": ["Dobby", "Dobby the House-Elf"]
    }
    
    if low in aliases:
        variants.extend(aliases[low])
        
    parts = [p for p in re.split(r'[\s\.\-]+', char_name) if p and p.lower() not in HONORIFICS and len(p) >= 3]
    variants.extend(parts)
    
    seen = set()
    result = []
    for v in variants:
        v_clean = v.strip()
        if v_clean and v_clean.lower() not in seen and len(v_clean) >= 3:
            seen.add(v_clean.lower())
            result.append(v_clean)
    return result


class VaultClipSelector:
    def __init__(self, db_path: Path = DB_PATH, clips_output_dir: Optional[Path] = None):
        self.db_path = db_path
        self.clips_dir = clips_output_dir or (PROJECT_ROOT / "data" / "clips")
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        self.used_clip_ids: Set[str] = set()
        self.used_intervals: List[Tuple[int, float, float]] = []
        self.drive_engine: Optional[DriveVaultEngine] = None
        self.smart_crop = SmartCropEngine()
        self.visual_guard = VisualMismatchGuard()
        self.ground_truth_matcher = BeastGroundTruthMatcher()

    def _get_drive_engine(self) -> DriveVaultEngine:
        if self.drive_engine is None:
            self.drive_engine = DriveVaultEngine()
        return self.drive_engine

    def _extract_clean_keywords(self, text: str) -> List[str]:
        """Extracts informative search tokens removing noise and stopwords."""
        raw_tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
        return [t for t in raw_tokens if t not in STOPWORDS and len(t) > 2]

    def find_best_clip(
        self,
        query_text: str,
        preferred_characters: Optional[List[str]] = None,
        preferred_props: Optional[List[str]] = None,
        preferred_location: Optional[str] = None,
        preferred_action: Optional[str] = None,
        movie_number: Optional[int] = None,
        retrieval_hints: Optional[List[str]] = None,
        min_duration: float = 1.0,
        max_duration: float = 12.0,
        min_score: float = MIN_CONFIDENCE_SCORE,
        allow_download: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the highest-scoring canonical clip in the vault matching the beat.
        Guarantees 0% repetition, strict zero-filler enforcement, and verified disk asset.
        """
        q_lower = query_text.lower()

        # Auto-expand active characters from query text using canonical character map
        active_characters = list(preferred_characters or [])
        for alias, canon_name in CANON_CHAR_MAP.items():
            if alias in q_lower and canon_name not in active_characters:
                active_characters.append(canon_name)

        # --------------------------------------------------------------------------
        # TIER 1 ADDON: BEAST GROUND-TRUTH MATCHER (Audio Descriptions + SDH + Screenplays)
        # Directly identifies canonical scenes & slices Blu-ray master files frame-accurately
        # --------------------------------------------------------------------------
        try:
            gt_clip = self.ground_truth_matcher.find_best_ground_truth_slice(
                query_text=query_text,
                preferred_characters=active_characters,
                preferred_props=preferred_props,
                movie_number=movie_number,
                target_duration=3.0,
                used_clip_ids=self.used_clip_ids
            )
            if gt_clip and gt_clip.get("match_score", 0) >= 70.0:
                cid = gt_clip["clip_id"]
                cand_m = gt_clip.get("movie_number")
                cand_s = gt_clip.get("start_seconds")
                cand_e = gt_clip.get("end_seconds")
                has_conflict = False
                if cand_m is not None and cand_s is not None and cand_e is not None:
                    for um, us, ue in self.used_intervals:
                        if um == int(cand_m):
                            overlap = min(ue, float(cand_e)) - max(us, float(cand_s))
                            if overlap > 0.5 or abs(float(cand_s) - us) < 1.5:
                                has_conflict = True
                                break
                if cid not in self.used_clip_ids and not has_conflict:
                    local_p = Path(gt_clip["local_path"])
                    if local_p.exists() and local_p.stat().st_size > 1000:
                        passed, conf, reason = self.visual_guard.verify_clip_against_beat(
                            clip_path=local_p,
                            narration_text=query_text,
                            expected_subject=gt_clip.get("primary_subject", ""),
                            expected_characters=active_characters,
                            clip_metadata=gt_clip
                        )
                        if passed:
                            self.used_clip_ids.add(cid)
                            if cand_m is not None and cand_s is not None and cand_e is not None:
                                self.used_intervals.append((int(cand_m), float(cand_s), float(cand_e)))
                            logger.info(
                                f"[BEAST GROUND TRUTH TIER-1 MATCH] '{query_text[:45]}' -> {cid} "
                                f"(Scene: {gt_clip.get('scene_heading')}, score: {gt_clip['match_score']:.1f})"
                            )
                            gt_clip.setdefault("visible_objects_props", gt_clip.get("objects", "[]"))
                            gt_clip.setdefault("location_setting", gt_clip.get("locations", ""))
                            gt_clip.setdefault("characters_present", gt_clip.get("primary_characters", "[]"))
                            return gt_clip
                        else:
                            logger.warning(f"Vision audit rejected ground truth clip {cid}: {reason}")
        except Exception as gt_err:
            logger.warning(f"Tier-1 Beast Ground Truth Matcher error: {gt_err}")

        # --------------------------------------------------------------------------
        # --------------------------------------------------------------------------
        # TIER 2: FRANCHISE VISUAL VAULT (1,234+ Canonical Pre-Cut Vault Clips)
        # Deterministic Multi-Field Structured Sourcing & Scoring
        # --------------------------------------------------------------------------
        conn = get_connection(self.db_path)
        cur = conn.cursor()

        clean_terms = self._extract_clean_keywords(query_text)
        search_terms = list(clean_terms)
        if preferred_action:
            search_terms.extend(self._extract_clean_keywords(preferred_action))
        if preferred_location:
            search_terms.extend(self._extract_clean_keywords(preferred_location))

        for char in active_characters:
            search_terms.extend(self._extract_clean_keywords(char))
        for prop in (preferred_props or []):
            search_terms.extend(self._extract_clean_keywords(prop))
        for hint in (retrieval_hints or []):
            search_terms.extend(self._extract_clean_keywords(hint))

        unique_terms = list(dict.fromkeys(search_terms))
        candidates_dict: Dict[str, Dict[str, Any]] = {}

        # 1. Targeted Character Queries (pulls all clips featuring requested characters and variants)
        for char in active_characters:
            char_variants = get_character_variants(char)
            for cv in char_variants:
                cv_clean = cv.strip()
                if len(cv_clean) > 2:
                    try:
                        cur.execute(
                            "SELECT fc.* FROM franchise_clips fc WHERE fc.characters_present LIKE ? OR fc.primary_subject LIKE ? LIMIT 40",
                            [f"%{cv_clean}%", f"%{cv_clean}%"]
                        )
                        for row in cur.fetchall():
                            r = dict(row)
                            candidates_dict[r["clip_id"]] = r
                    except Exception as e:
                        logger.warning(f"Character targeted query notice: {e}")

        # 2. Targeted Prop / Object Queries (pulls all clips featuring requested props and prop tokens)
        for prop in (preferred_props or []):
            prop_clean = prop.strip()
            tokens = [w for w in re.sub(r"[^a-zA-Z0-9\s]", " ", prop_clean).split() if len(w) > 3 and w.lower() not in STOPWORDS]
            search_variants = list(dict.fromkeys([prop_clean] + tokens))
            for pv in search_variants:
                if len(pv) > 2:
                    try:
                        cur.execute(
                            "SELECT fc.* FROM franchise_clips fc WHERE fc.visible_objects_props LIKE ? OR fc.primary_subject LIKE ? OR fc.action_description LIKE ? LIMIT 40",
                            [f"%{pv}%", f"%{pv}%", f"%{pv}%"]
                        )
                        for row in cur.fetchall():
                            r = dict(row)
                            candidates_dict[r["clip_id"]] = r
                    except Exception as e:
                        logger.warning(f"Prop targeted query notice: {e}")

        # 3. Targeted Location Queries (pulls clips from requested setting)
        if preferred_location and len(preferred_location.strip()) > 2:
            try:
                cur.execute(
                    "SELECT fc.* FROM franchise_clips fc WHERE fc.location_setting LIKE ? LIMIT 30",
                    [f"%{preferred_location.strip()}%"]
                )
                for row in cur.fetchall():
                    r = dict(row)
                    candidates_dict[r["clip_id"]] = r
            except Exception as e:
                logger.warning(f"Location targeted query notice: {e}")

        # 4. FTS Semantic Search
        if unique_terms:
            fts_query = " OR ".join(unique_terms[:12])
            sql = """
                SELECT fc.*, rank
                FROM franchise_clips_fts fts
                JOIN franchise_clips fc ON fts.clip_id = fc.clip_id
                WHERE franchise_clips_fts MATCH ?
                ORDER BY rank LIMIT 50
            """
            try:
                cur.execute(sql, [fts_query])
                for row in cur.fetchall():
                    r = dict(row)
                    if r["clip_id"] not in candidates_dict:
                        candidates_dict[r["clip_id"]] = r
            except Exception as e:
                logger.warning(f"FTS query failed for '{fts_query}': {e}")

        conn.close()
        candidates = list(candidates_dict.values())

        # Strict Zero-Filler Guard: If candidate pool is empty, return None
        if not candidates:
            logger.warning(f"Zero candidates matched beat query: '{query_text[:60]}'")
            return None

        scored: List[Tuple[float, Dict[str, Any]]] = []

        for cand in candidates:
            cid = cand["clip_id"]
            if cid in self.used_clip_ids:
                continue

            # Anti-Loop Timestamp Guard: Reject clips with overlapping or adjacent timestamp windows in same movie
            cand_m = cand.get("movie_number")
            cand_s = cand.get("start_seconds")
            cand_e = cand.get("end_seconds")
            if cand_m is not None and cand_s is not None and cand_e is not None:
                has_conflict = False
                for um, us, ue in self.used_intervals:
                    if um == int(cand_m):
                        overlap = min(ue, float(cand_e)) - max(us, float(cand_s))
                        if overlap > 0.5 or abs(float(cand_s) - us) < 1.5:
                            has_conflict = True
                            break
                if has_conflict:
                    continue

            score = 10.0

            # ------------------------------------------------------------------
            # Field 1: Character Matching & Strict Elimination
            # ------------------------------------------------------------------
            chars_cand = cand.get("characters_present", "[]")
            try:
                cand_chars_list = json.loads(chars_cand) if isinstance(chars_cand, str) else chars_cand
            except Exception:
                cand_chars_list = []
            cand_chars_lower = set(c.lower() for c in cand_chars_list)
            subj_lower = str(cand.get("primary_subject", "")).lower()

            crowd_penalty = 0.5 if len(cand_chars_list) > 6 else 1.0
            has_any_char_match = False
            char_match_count = 0

            for idx, char in enumerate(active_characters):
                char_variants = get_character_variants(char)
                char_vars_lower = [v.lower() for v in char_variants]

                has_char = any(any(v in ccl or ccl in v for v in char_vars_lower) for ccl in cand_chars_lower)
                is_subj = any(v in subj_lower for v in char_vars_lower)
                is_lead = (idx == 0)

                if has_char or is_subj:
                    char_match_count += 1
                    has_any_char_match = True
                    if is_lead:
                        if is_subj:
                            score += 500.0
                        else:
                            score += 250.0 * crowd_penalty
                    else:
                        if is_subj:
                            score += 200.0
                        else:
                            score += 100.0 * crowd_penalty

            # Crowd penalty: if lead character is in a huge crowd scene (> 6 characters) and is NOT primary_subject
            if active_characters and len(cand_chars_list) > 6:
                lead_vars = [v.lower() for v in get_character_variants(active_characters[0])]
                if not any(v in subj_lower for v in lead_vars):
                    score -= 400.0

            # ------------------------------------------------------------------
            # Field 2: Props & Objects Matching & Strict Elimination
            # ------------------------------------------------------------------
            objs_cand = cand.get("visible_objects_props", "[]")
            try:
                cand_objs_list = json.loads(objs_cand) if isinstance(objs_cand, str) else objs_cand
            except Exception:
                cand_objs_list = []
            cand_objs_lower = set(p.lower() for p in cand_objs_list)

            act_text = (
                str(cand.get("action_description") or "") + " " +
                str(cand.get("lore_context") or "") + " " +
                str(cand.get("search_tags") or "")
            ).lower()

            DISTINCTIVE_CANONICAL_PROPS = {
                "marauder's map", "marauder map", "marauders map", "mirror of erised",
                "tom riddle's diary", "riddle's diary", "riddle diary", "diary", "sorting hat",
                "triwizard cup", "goblet of fire", "prophecy", "prophecy orb", "glass orb",
                "howler", "remembrall", "invisibility cloak", "pensieve", "resurrection stone",
                "elder wand", "deluminator", "basilisk fang", "sword of gryffindor",
                "firebolt", "nimbus 2000", "golden snitch", "quaffle", "bludger",
                "monster book", "devil's snare", "mandrake", "time turner", "time-turner",
                "ford anglia", "flying car", "hogwarts express", "knight bus", "dark mark",
                "parchment"
            }

            has_any_prop_match = False
            has_distinctive_prop_match = False
            if preferred_props:
                prop_match_count = 0
                has_distinctive_prop_req = any(
                    any(dp in p.lower() for dp in DISTINCTIVE_CANONICAL_PROPS)
                    for p in preferred_props
                )
                for prop in preferred_props:
                    prop_low = prop.lower().strip()
                    prop_clean = re.sub(r"[^a-z0-9\s]", " ", prop_low).strip()
                    p_tokens = [w for w in prop_clean.split() if len(w) > 2 and w not in STOPWORDS]
                    is_distinctive = any(dp in prop_low for dp in DISTINCTIVE_CANONICAL_PROPS)

                    # Check match: candidate object must be exact or contain prop, or all significant tokens must match
                    in_objs = any(
                        (prop_low == col or prop_low in col) or
                        (p_tokens and len(p_tokens) > 1 and all(t in re.sub(r"[^a-z0-9\s]", " ", col) for t in p_tokens))
                        for col in cand_objs_lower
                    )
                    in_subj = (
                        prop_low in subj_lower or
                        (p_tokens and len(p_tokens) > 1 and all(t in re.sub(r"[^a-z0-9\s]", " ", subj_lower) for t in p_tokens))
                    )
                    in_act = (
                        prop_low in act_text or
                        (p_tokens and len(p_tokens) > 1 and all(t in re.sub(r"[^a-z0-9\s]", " ", act_text) for t in p_tokens))
                    )
                    if in_objs or in_subj or in_act:
                        if is_distinctive:
                            # Candidate MUST contain the distinctive keyword itself, not just a generic modifier
                            distinctive_keywords = [dp for dp in DISTINCTIVE_CANONICAL_PROPS if dp in prop_low]
                            matched_distinctive_kw = any(
                                any(dk in col for dk in distinctive_keywords) for col in cand_objs_lower
                            ) or any(dk in subj_lower for dk in distinctive_keywords) or any(dk in act_text for dk in distinctive_keywords)

                            if matched_distinctive_kw:
                                prop_match_count += 1
                                has_any_prop_match = True
                                has_distinctive_prop_match = True
                                score += 450.0
                                if in_subj:
                                    score += 200.0
                        else:
                            prop_match_count += 1
                            has_any_prop_match = True
                            score += 50.0

                if has_distinctive_prop_req and not has_distinctive_prop_match:
                    score -= 1500.0

            # Character Disqualification: Strict Canonical Entity Enforcement
            if active_characters:
                lead_char = active_characters[0]
                lead_vars = [v.lower() for v in get_character_variants(lead_char)]
                has_lead = any(v in subj_lower or any(v in ccl for ccl in cand_chars_lower) for v in lead_vars)

                # If primary_subject is a person but NOT one of the active characters:
                if subj_lower not in ("none", "general", "scene", "landscape", "establishing", "object", "the parchment", "parchment"):
                    is_subj_active = any(any(v in subj_lower for v in [ac.lower()] + [x.lower() for x in get_character_variants(ac)]) for ac in active_characters)
                    if not is_subj_active and len(cand_chars_list) > 0:
                        score -= 1500.0

                if char_match_count == 0:
                    # ZERO requested characters matched: lethal penalty
                    if len(cand_chars_list) > 0:
                        score -= 2500.0  # Instant elimination if candidate shows people other than requested
                    elif not has_distinctive_prop_match:
                        score -= 1000.0
                elif not has_lead and len(active_characters) > 1 and len(cand_chars_list) > 0:
                    # Missing the primary lead subject when other characters were matched
                    score -= 600.0

            # ------------------------------------------------------------------
            # Field 3: Location / Environment Setting Matching
            # ------------------------------------------------------------------
            if preferred_location:
                loc_low = preferred_location.lower().strip()
                cand_loc = str(cand.get("location_setting") or "").lower()
                if loc_low in cand_loc or any(lp in cand_loc for lp in loc_low.split() if len(lp) > 3):
                    score += 150.0

            # ------------------------------------------------------------------
            # Field 4: Action & Subject Keyword Matching
            # ------------------------------------------------------------------
            for t in unique_terms:
                if len(t) > 3:
                    if t in subj_lower:
                        score += 50.0
                    if t in act_text:
                        score += 15.0

            # Retrieval Hints & Target Clip ID Matching (+600 for ID, +150 for subject, +80 for action)
            for hint in (retrieval_hints or []):
                h_low = str(hint).lower().strip()
                if h_low == cid.lower() or h_low in cid.lower():
                    score += 600.0
                elif h_low in subj_lower:
                    score += 150.0
                elif h_low in act_text:
                    score += 80.0

            # ------------------------------------------------------------------
            # Field 5: Movie Preference & Era Lock
            # ------------------------------------------------------------------
            if movie_number:
                if cand.get("movie_number") == movie_number:
                    score += 250.0  # Dominant priority for canonical movie
                else:
                    if has_any_char_match or has_any_prop_match:
                        score -= 50.0  # Allow exact canonical asset across films
                    else:
                        score -= 400.0  # Strict penalty to eliminate cross-movie hallucination

            # Strict Entity Conflict & Disambiguation Guard
            cand_full_text = f"{cid} {subj_lower} {chars_cand} {act_text}".lower()
            for rule in ENTITY_CONFLICT_RULES:
                q_has_trigger = any(trig in q_lower for trig in rule["query_triggers"])
                if q_has_trigger:
                    cand_has_forbidden = any(forbid in cand_full_text for forbid in rule["forbidden_tokens"])
                    if cand_has_forbidden:
                        score -= rule["penalty"]

            # Duration Suitability Bonus (+25)
            dur = cand.get("duration_seconds", 3.0)
            if min_duration <= dur <= max_duration:
                score += 25.0

            if score >= min_score:
                scored.append((score, cand))

        if not scored:
            logger.warning(
                f"No candidate met the minimum score {min_score} for '{query_text[:50]}'. "
                f"Max candidate score was below threshold."
            )
            return None

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        # Iterate through best candidates to ensure physical file existence
        vault_clips_dir = PROJECT_ROOT / "data" / "franchise_vault_clips"
        for candidate_score, best_clip in scored:
            cid = best_clip["clip_id"]
            local_p = Path(best_clip.get("local_path") or "")

            # Check if local path is valid on this system
            if not local_p.exists() or local_p.stat().st_size == 0:
                alt_path = vault_clips_dir / f"{cid}.mp4"
                if alt_path.exists() and alt_path.stat().st_size > 1000:
                    local_p = alt_path
                    best_clip["local_path"] = str(local_p)

            # If still missing, attempt Google Drive download if allowed
            if (not local_p.exists() or local_p.stat().st_size == 0) and best_clip.get("drive_file_id") and allow_download:
                dest = vault_clips_dir / f"{cid}.mp4"
                dest.parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"Downloading verified clip {cid} from Drive ID {best_clip['drive_file_id']}...")
                try:
                    de = self._get_drive_engine()
                    de.download_video_from_vault(best_clip["drive_file_id"], dest)
                    if dest.exists() and dest.stat().st_size > 1000:
                        local_p = dest
                        best_clip["local_path"] = str(local_p)
                except Exception as de_err:
                    logger.error(f"Failed to download vault clip {cid} from Drive: {de_err}")
                    continue

            # If valid file on disk confirmed
            if local_p.exists() and local_p.stat().st_size > 1000:
                # Pre-Render Vision Audit Guard: inspect frame & metadata against query
                passed, conf, reason = self.visual_guard.verify_clip_against_beat(
                    clip_path=local_p,
                    narration_text=query_text,
                    expected_subject=best_clip.get("primary_subject", ""),
                    expected_characters=active_characters,
                    clip_metadata=best_clip
                )
                if not passed:
                    logger.warning(
                        f"Visual Mismatch Guard REJECTED candidate {cid} for query '{query_text[:50]}': {reason}. "
                        f"Trying next best candidate..."
                    )
                    continue

                self.used_clip_ids.add(cid)
                if best_clip.get("movie_number") is not None and best_clip.get("start_seconds") is not None and best_clip.get("end_seconds") is not None:
                    self.used_intervals.append((
                        int(best_clip["movie_number"]),
                        float(best_clip["start_seconds"]),
                        float(best_clip["end_seconds"])
                    ))
                best_clip["match_score"] = candidate_score
                best_clip["local_path"] = str(local_p)
                return best_clip

        logger.warning(f"All {len(scored)} candidates for '{query_text[:50]}' failed physical file check or vision audit.")
        return None

    def get_clip_by_id(
        self,
        clip_id: str,
        drive_file_id: Optional[str] = None,
        allow_download: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Directly retrieves a clip by ID from franchise_visual_vault.db.
        Guarantees exact canonical asset matching (0% visual mismatch).
        Downloads asset from Google Drive if not yet cached locally.
        """
        try:
            conn = get_connection(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT * FROM franchise_clips WHERE clip_id = ?", (clip_id,))
            row = cur.fetchone()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to query franchise_clips for {clip_id}: {e}")
            return None

        if not row:
            logger.warning(f"Clip {clip_id} not found in franchise_visual_vault.db.")
            return None

        best_clip = dict(row)
        if drive_file_id and not best_clip.get("drive_file_id"):
            best_clip["drive_file_id"] = drive_file_id

        vault_clips_dir = PROJECT_ROOT / "data" / "franchise_vault_clips"
        local_p = Path(best_clip.get("local_path") or "")

        # Check if local path is valid on this system
        if not local_p.exists() or local_p.stat().st_size == 0:
            alt_path = vault_clips_dir / f"{clip_id}.mp4"
            if alt_path.exists() and alt_path.stat().st_size > 1000:
                local_p = alt_path
                best_clip["local_path"] = str(local_p)

        # If still missing, attempt Google Drive download if allowed
        if (not local_p.exists() or local_p.stat().st_size == 0) and best_clip.get("drive_file_id") and allow_download:
            dest = vault_clips_dir / f"{clip_id}.mp4"
            dest.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Downloading verified clip {clip_id} from Drive ID {best_clip['drive_file_id']}...")
            try:
                de = self._get_drive_engine()
                de.download_video_from_vault(best_clip["drive_file_id"], dest)
                if dest.exists() and dest.stat().st_size > 1000:
                    local_p = dest
                    best_clip["local_path"] = str(local_p)
            except Exception as de_err:
                logger.error(f"Failed to download vault clip {clip_id} from Drive: {de_err}")
                return None

        if local_p.exists() and local_p.stat().st_size > 1000:
            self.used_clip_ids.add(clip_id)
            if best_clip.get("movie_number") is not None and best_clip.get("start_seconds") is not None and best_clip.get("end_seconds") is not None:
                self.used_intervals.append((
                    int(best_clip["movie_number"]),
                    float(best_clip["start_seconds"]),
                    float(best_clip["end_seconds"])
                ))
            best_clip["match_score"] = 1500.0
            best_clip["local_path"] = str(local_p)
            return best_clip

        logger.warning(f"Clip {clip_id} file not found locally or on Drive.")
        return None

    def resolve_script_shots(
        self,
        script_id: str,
        session: Any,
        target_total_duration: Optional[float] = None,
        allow_download: bool = True
    ) -> List[HPMovieClip]:
        """
        Resolves each visual beat in a script against the verified Visual Vault.
        Conforms clips to beat duration and saves HPMovieClip records in the database.
        Strict Zero-Filler Guard: If any beat cannot be matched, raises ValueError.
        """
        script = session.query(HarryPotterScript).filter_by(id=script_id).first()
        if not script:
            raise ValueError(f"Script not found: {script_id}")

        if not script.visual_beats_json:
            raise ValueError(f"Script {script_id} has empty visual_beats_json.")

        beats = json.loads(script.visual_beats_json)
        if not beats:
            raise ValueError(f"Script {script_id} has 0 visual beats.")

        # Audio-synchronized duration rescaling: ensures sum of video shots perfectly matches audio duration
        if target_total_duration and target_total_duration > 0:
            for b in beats:
                if float(b.get("duration_seconds") or 0.0) <= 0.0:
                    b["duration_seconds"] = target_total_duration / max(1, len(beats))
            sum_dur = sum(float(b.get("duration_seconds", 2.5)) for b in beats)
            if sum_dur > 0:
                scale = target_total_duration / sum_dur
                for b in beats:
                    b["duration_seconds"] = max(1.2, round(float(b.get("duration_seconds", 2.5)) * scale, 3))

        # Purge any old shots for this script
        session.query(HPMovieClip).filter_by(script_id=script_id).delete()
        session.commit()

        self.reset_used()
        resolved_shots: List[HPMovieClip] = []

        logger.info(f"Resolving {len(beats)} visual beats for {script_id} via Franchise Visual Vault...")

        for idx, beat in enumerate(beats):
            beat_id = beat.get("beat_id", f"beat_{idx + 1}")
            dur = max(1.2, float(beat.get("duration_seconds", 3.0)))
            pure_visual = (beat.get("visual_requirement") or beat.get("description") or beat.get("action") or "").strip()
            clip_id_target = beat.get("clip_id")
            matched_clip = None

            # 1. Exact clip_id direct retrieval (100% VISUAL-FIRST GUARANTEE)
            if clip_id_target:
                matched_clip = self.get_clip_by_id(
                    clip_id_target,
                    drive_file_id=beat.get("drive_file_id"),
                    allow_download=allow_download
                )

            # 2. Semantic fallback if not pre-linked
            if not matched_clip:
                chars = beat.get("characters", [])
                props = beat.get("objects", [])
                location = beat.get("location") or beat.get("setting") or ""
                action = beat.get("action") or ""
                hints = beat.get("retrieval_hints", [])
                pref_movie = beat.get("preferred_movie_number") or script.corresponding_movie_number

                matched_clip = self.find_best_clip(
                    query_text=pure_visual,
                    preferred_characters=chars,
                    preferred_props=props,
                    preferred_location=location,
                    preferred_action=action,
                    movie_number=pref_movie,
                    retrieval_hints=hints,
                    allow_download=allow_download
                )

            # Strict Zero-Filler Guard: Random placeholders permanently banned
            if matched_clip is None:
                raise ValueError(
                    f"Strict Zero-Filler Guard: Could not find canonical vault clip for {script_id} "
                    f"beat {beat_id} ('{pure_visual[:50]}'). Production aborted to prevent visual mismatch."
                )

            # Conform / Trim clip to exact beat duration @ 1080x1920 30fps
            out_clip_path = self.clips_dir / f"{script_id}_{beat_id}_shot_1.mp4"
            src_path = Path(matched_clip["local_path"])

            # Dynamic Smart Subject-Aware Crop (centers characters/faces, eliminates headless/off-center framing)
            vf_filter = self.smart_crop.get_filter_for_clip(src_path)

            # FFmpeg conform command: trim/loop to exact beat duration, smart scale/crop to 1080x1920, strip audio
            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-stream_loop", "-1",
                "-i", str(src_path),
                "-t", f"{dur:.2f}",
                "-vf", vf_filter,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-an",
                str(out_clip_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0 or not out_clip_path.exists():
                raise RuntimeError(f"FFmpeg shot conform failed for {out_clip_path.name}: {res.stderr}")

            score = matched_clip.get("match_score", 50.0)
            confidence = min(1.0, score / 100.0)

            shot_rec = HPMovieClip(
                id=f"clip_{script_id}_{beat_id}_shot_1",
                script_id=script_id,
                beat_id=beat_id,
                shot_id="shot_1",
                shot_index=idx + 1,
                movie_id=f"hp_movie_{matched_clip['movie_number']}",
                movie_number=matched_clip["movie_number"],
                movie_title=matched_clip["movie_title"],
                source_asset_id=matched_clip["clip_id"],
                source_drive_id=matched_clip.get("drive_file_id"),
                source_mode="CLOUD_MATERIALIZED",
                source_start_seconds=matched_clip["start_seconds"],
                source_end_seconds=matched_clip["end_seconds"],
                clip_start_seconds=0.0,
                clip_end_seconds=dur,
                duration_seconds=dur,
                matched_text=f"{matched_clip['primary_subject']} - {matched_clip['action_description'][:80]}",
                retrieval_query=pure_visual,
                retrieval_score=score,
                confidence=confidence,
                match_status="ACCEPTED",
                file_path=str(out_clip_path),
                file_size_bytes=out_clip_path.stat().st_size,
                audio_stream_count=0,
                width=1080,
                height=1920,
                visual_source_policy="MOVIE_FOOTAGE_ONLY",
                visual_source="MOVIE_DIRECT"
            )
            session.add(shot_rec)
            resolved_shots.append(shot_rec)
            logger.info(
                f"  [+] Beat {idx+1}/{len(beats)}: {matched_clip['clip_id']} "
                f"(M{matched_clip['movie_number']} {matched_clip['primary_subject']}, score={score:.1f}) -> {dur:.2f}s"
            )

        session.commit()
        logger.info(f"Successfully resolved and conformed {len(resolved_shots)} shots for {script_id}.")
        return resolved_shots

    def preview_storyboard(self, script_id: str, session: Any) -> List[Dict[str, Any]]:
        """
        Simulates shot matching without rendering, providing beat-by-beat storyboard preview.
        """
        script = session.query(HarryPotterScript).filter_by(id=script_id).first()
        if not script or not script.visual_beats_json:
            return []

        beats = json.loads(script.visual_beats_json)
        self.reset_used()
        preview = []

        for idx, beat in enumerate(beats):
            beat_id = beat.get("beat_id", f"beat_{idx + 1}")
            dur = float(beat.get("duration_seconds", 3.0))
            pure_visual = (beat.get("visual_requirement") or beat.get("description") or beat.get("action") or "").strip()
            chars = beat.get("characters", [])
            props = beat.get("objects", [])
            location = beat.get("location") or beat.get("setting") or ""
            action = beat.get("action") or ""
            hints = beat.get("retrieval_hints", [])
            pref_movie = beat.get("preferred_movie_number") or script.corresponding_movie_number

            matched = self.find_best_clip(
                query_text=pure_visual,
                preferred_characters=chars,
                preferred_props=props,
                preferred_location=location,
                preferred_action=action,
                movie_number=pref_movie,
                retrieval_hints=hints,
                allow_download=False
            )
            preview.append({
                "beat_index": idx + 1,
                "beat_id": beat_id,
                "duration_seconds": dur,
                "narration_text": beat.get("narration_text", ""),
                "visual_requirement": pure_visual,
                "matched_clip_id": matched["clip_id"] if matched else None,
                "matched_movie": matched["movie_number"] if matched else None,
                "primary_subject": matched["primary_subject"] if matched else None,
                "action_description": matched["action_description"] if matched else None,
                "match_score": matched["match_score"] if matched else 0.0,
                "passed_guard": matched is not None
            })

        return preview

    def reset_used(self):
        self.used_clip_ids.clear()
        self.used_intervals.clear()
