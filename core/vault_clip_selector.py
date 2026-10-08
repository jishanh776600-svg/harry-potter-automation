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

MIN_CONFIDENCE_SCORE = 35.0



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
                            return gt_clip
                        else:
                            logger.warning(f"Vision audit rejected ground truth clip {cid}: {reason}")
        except Exception as gt_err:
            logger.warning(f"Tier-1 Beast Ground Truth Matcher error: {gt_err}")

        # --------------------------------------------------------------------------
        # TIER 2: FRANCHISE VISUAL VAULT (1,234+ Canonical Pre-Cut Vault Clips)
        # --------------------------------------------------------------------------
        conn = get_connection(self.db_path)
        cur = conn.cursor()

        clean_terms = self._extract_clean_keywords(query_text)
        search_terms = list(clean_terms)

        # Include characters, props, and retrieval hints in search tokens
        for char in active_characters:
            search_terms.extend(self._extract_clean_keywords(char))
        for prop in (preferred_props or []):
            search_terms.extend(self._extract_clean_keywords(prop))
        for hint in (retrieval_hints or []):
            search_terms.extend(self._extract_clean_keywords(hint))

        # Deduplicate while preserving order
        unique_terms = list(dict.fromkeys(search_terms))
        candidates: List[Dict[str, Any]] = []

        # FTS Query Execution (soft movie preference in scoring rather than hard SQL exclusion)
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
                candidates = [dict(row) for row in cur.fetchall()]
            except Exception as e:
                logger.warning(f"FTS query failed for '{fts_query}': {e}")
                candidates = []

        conn.close()

        # Strict Zero-Filler Guard: If FTS produced 0 candidate matches, return None
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

            # Character Matching
            chars_cand = cand.get("characters_present", "[]")
            try:
                cand_chars_list = json.loads(chars_cand) if isinstance(chars_cand, str) else chars_cand
            except Exception:
                cand_chars_list = []
            cand_chars_lower = set(c.lower() for c in cand_chars_list)
            subj_lower = cand.get("primary_subject", "").lower()

            # Crowd dilution penalty (avoid wide/generic crowd shots masquerading as specific characters)
            crowd_penalty = 0.6 if len(cand_chars_list) > 6 else 1.0

            for idx, char in enumerate(active_characters):
                char_low = char.lower()
                char_parts = [p for p in char_low.split() if len(p) > 2 and p not in HONORIFICS]
                if not char_parts:
                    char_parts = [p for p in char_low.split() if len(p) > 2]
                is_in_query = any(p in q_lower for p in char_parts) if char_parts else (char_low in q_lower)
                has_char = any(char_low in ccl or ccl in char_low or any(p in ccl for p in char_parts) for ccl in cand_chars_lower)
                is_subj = any(p in subj_lower for p in char_parts) if char_parts else (char_low in subj_lower)
                is_lead_char = (idx == 0)

                if is_in_query and is_lead_char:
                    if has_char:
                        score += 100.0 * crowd_penalty
                    if is_subj:
                        score += 120.0
                elif is_in_query:
                    if has_char:
                        score += 50.0 * crowd_penalty
                    if is_subj:
                        score += 60.0
                elif is_lead_char:
                    if has_char:
                        score += 30.0 * crowd_penalty
                    if is_subj:
                        score += 40.0
                else:
                    if has_char:
                        score += 15.0 * crowd_penalty
                    if is_subj:
                        score += 20.0

            # Props & Objects Matching
            objs_cand = cand.get("visible_objects_props", "[]")
            try:
                cand_objs_list = json.loads(objs_cand) if isinstance(objs_cand, str) else objs_cand
            except Exception:
                cand_objs_list = []
            cand_objs_lower = set(p.lower() for p in cand_objs_list)

            for prop in (preferred_props or []):
                prop_low = prop.lower()
                if prop_low in q_lower:
                    if any(prop_low in col for col in cand_objs_lower):
                        score += 50.0
                    if prop_low in subj_lower:
                        score += 60.0

            # Direct Primary Subject Keyword Match (+50 per matched keyword)
            for t in unique_terms:
                if len(t) > 3 and t in subj_lower:
                    score += 50.0

            # Action Description / Lore / Tags Keyword Matching (+10 per matched keyword)
            act_text = (
                str(cand.get("action_description") or "") + " " +
                str(cand.get("lore_context") or "") + " " +
                str(cand.get("search_tags") or "")
            ).lower()
            for t in unique_terms:
                if t in act_text:
                    score += 10.0

            # Retrieval Hints & Target Clip ID Matching (+600 for ID, +150 for subject, +80 for action)
            for hint in (retrieval_hints or []):
                h_low = str(hint).lower().strip()
                if h_low == cid.lower() or h_low in cid.lower():
                    score += 600.0
                elif h_low in subj_lower:
                    score += 150.0
                elif h_low in act_text:
                    score += 80.0

            # Hard Movie Preference & Era Lock
            if movie_number:
                if cand.get("movie_number") == movie_number:
                    score += 250.0  # Dominant priority for canonical movie
                else:
                    score -= 300.0  # Strict penalty to eliminate cross-movie hallucination

            # Strict Entity Conflict & Disambiguation Guard
            cand_full_text = (
                f"{cid} {subj_lower} {chars_cand} {act_text}"
            ).lower()
            for rule in ENTITY_CONFLICT_RULES:
                q_has_trigger = any(trig in q_lower for trig in rule["query_triggers"])
                if q_has_trigger:
                    cand_has_forbidden = any(forbid in cand_full_text for forbid in rule["forbidden_tokens"])
                    if cand_has_forbidden:
                        score -= rule["penalty"]
                        logger.info(
                            f"Entity Disambiguation Penalty applied to {cid}: -{rule['penalty']} "
                            f"(query triggered: {rule['query_triggers'][0]}, matched forbidden: {rule['forbidden_tokens'][0]})"
                        )

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
            sum_dur = sum(float(b.get("duration_seconds", 2.5)) for b in beats)
            if sum_dur > 0:
                scale = target_total_duration / sum_dur
                for b in beats:
                    b["duration_seconds"] = round(float(b.get("duration_seconds", 2.5)) * scale, 3)

        # Purge any old shots for this script
        session.query(HPMovieClip).filter_by(script_id=script_id).delete()
        session.commit()

        self.reset_used()
        resolved_shots: List[HPMovieClip] = []

        logger.info(f"Resolving {len(beats)} visual beats for {script_id} via Franchise Visual Vault...")

        for idx, beat in enumerate(beats):
            beat_id = beat.get("beat_id", f"beat_{idx + 1}")
            dur = float(beat.get("duration_seconds", 3.0))
            v_req = ((beat.get("visual_requirement") or "") + " " + (beat.get("narration_text") or "")).strip()
            chars = beat.get("characters", [])
            props = beat.get("objects", [])
            hints = beat.get("retrieval_hints", [])
            pref_movie = beat.get("preferred_movie_number") or script.corresponding_movie_number

            matched_clip = self.find_best_clip(
                query_text=v_req,
                preferred_characters=chars,
                preferred_props=props,
                movie_number=pref_movie,
                retrieval_hints=hints,
                allow_download=allow_download
            )

            # Strict Zero-Filler Guard: Random placeholders permanently banned
            if matched_clip is None:
                raise ValueError(
                    f"Strict Zero-Filler Guard: Could not find canonical vault clip for {script_id} "
                    f"beat {beat_id} ('{v_req[:50]}'). Production aborted to prevent visual mismatch."
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
                retrieval_query=v_req,
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
            v_req = ((beat.get("visual_requirement") or "") + " " + (beat.get("narration_text") or "")).strip()
            chars = beat.get("characters", [])
            props = beat.get("objects", [])
            hints = beat.get("retrieval_hints", [])
            pref_movie = beat.get("preferred_movie_number") or script.corresponding_movie_number

            matched = self.find_best_clip(
                query_text=v_req,
                preferred_characters=chars,
                preferred_props=props,
                movie_number=pref_movie,
                retrieval_hints=hints,
                allow_download=False
            )
            preview.append({
                "beat_index": idx + 1,
                "beat_id": beat_id,
                "duration_seconds": dur,
                "narration_text": beat.get("narration_text", ""),
                "visual_requirement": v_req,
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
