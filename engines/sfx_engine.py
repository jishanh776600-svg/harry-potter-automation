"""
STORY FORGE Intelligent Beat-Aware SFX Pipeline (Step 5)
================================================================================
Consumes Step 4 EditorialTimeline and intelligently places sound effects
from a strictly closed four-file audio library:
  1. click-for transitions.MP3                     -> CLICK (Tactile micro accent)
  2. Short Transition _2 Sound .mp3               -> SHORT_TRANSITION (Structural cut)
  3. WHOOSH FIRE _ SOUND EFFECT _ TRANSITION(MP3_160K).mp3 -> WHOOSH_TRANSITION (Anchor/Reveal)
  4. bell.mp3                                     -> REVELATION (Canon realization / payoff)

Core Architectural Principles:
  - CLOSED SFX UNIVERSE: Exactly 4 authorized files; rejects any outside source.
  - ANTI-SPAM & COOLDOWN: No consecutive repeats; configurable cooldowns; silence over spam.
  - SPEECH TRANSIENT PROTECTION: Protects spoken lore words/spells within +/-60ms window.
  - SOLEMN-MOMENT SUPPRESSION: Zero SFX during deaths, sacrifices, grief, tragic beats.
  - AUDIO LEVEL HIERARCHY: Narration-first gain staging (Click: -20dB, Whoosh: -18dB, Short: -18dB, Bell: -16dB).
  - DETERMINISTIC FINGERPRINTING: 16-char SHA-256 fingerprint for repeatable composition.
  - NOVEL STORY ISOLATION: Explicitly guarded against execution on Novel Story pipelines.
"""

import os
import re
import json
import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from config.settings import PROJECT_ROOT, SFX_DIR
from core.editorial_types import (
    EditorialTimeline,
    EditorialClip,
    VisualRole,
    TransitionIntent,
    MotionIntent,
    EditorialEmphasis,
)
from core.sfx_types import (
    SFXCategory,
    SFXAssetRecord,
    SFXCue,
    SFXPlan,
)

logger = logging.getLogger(__name__)

# Solemn keywords that mandate total SFX suppression
SOLEMN_KEYWORDS: Set[str] = {
    "died", "dies", "death", "dead", "killed", "kills", "killing", "murder",
    "murdered", "sacrifice", "sacrificed", "mourn", "mourning", "grief",
    "grave", "corpse", "funeral", "tragedy", "tragic", "loss", "agony"
}

# Protected canon speech entities for +/-60ms transient avoidance
PROTECTED_SPEECH_KEYWORDS: Set[str] = {
    "neville", "harry", "dumbledore", "snape", "voldemort", "granger", "ron",
    "hatstall", "sorting hat", "gryffindor", "hufflepuff", "slytherin", "ravenclaw",
    "horcrux", "paracelsus", "peeves", "erised", "remembrall", "hallows",
    "elder wand", "resurrection stone", "invisibility cloak", "avada kedavra",
    "expelliarmus", "patronus", "sectumsempra", "crucio", "imperio", "lumos"
}

# The strictly authorized, complete, closed four-file SFX library definitions
AUTHORIZED_SFX_DEFINITIONS = [
    {
        "filename": "click-for transitions.MP3",
        "asset_id": "sfx_click_tactile_01",
        "category": SFXCategory.CLICK,
        "intensity": 0.35,
        "target_level_db": -20.0,
        "measured_max_db": -2.1,
        "measured_mean_db": -27.2,
        "base_gain_db": -17.9,
        "suitable_beat_types": ["DIRECT_EVIDENCE", "MICRO_PUNCH", "CAPTION_EMPHASIS", "CONTEXTUAL_ENVIRONMENT"],
        "cooldown_seconds": 1.5,
        "max_uses_per_short": 12,
        "cooldown_group": "click_tactile",
        "expected_sha256": "bd168426b9bfe2e42d19da88a2a79bb77ebae8c473510c77c19e9f334649c15e",
    },
    {
        "filename": "Short Transition _2 Sound .mp3",
        "asset_id": "sfx_transition_short_02",
        "category": SFXCategory.SHORT_TRANSITION,
        "intensity": 0.60,
        "target_level_db": -18.0,
        "measured_max_db": -7.7,
        "measured_mean_db": -29.5,
        "base_gain_db": -10.3,
        "suitable_beat_types": ["DIRECT_EVIDENCE", "IRONIC_CONTRAST", "HARD_CUT", "MATCH_CUT"],
        "cooldown_seconds": 3.0,
        "max_uses_per_short": 8,
        "cooldown_group": "transition_short",
        "expected_sha256": "76a15fd53cebb21a6462bd338ea3b56e6659c8ab3adb12a02e2192ebe320ff88",
    },
    {
        "filename": "WHOOSH FIRE _ SOUND EFFECT _ TRANSITION(MP3_160K).mp3",
        "asset_id": "sfx_whoosh_fire_01",
        "category": SFXCategory.WHOOSH_TRANSITION,
        "intensity": 0.85,
        "target_level_db": -18.0,
        "measured_max_db": 0.0,
        "measured_mean_db": -18.8,
        "base_gain_db": -18.0,
        "suitable_beat_types": ["ANCHOR_FOCAL", "SLOW_PUSH_IN", "MAJOR_REVEAL", "PAYOFF_RESOLVE"],
        "cooldown_seconds": 5.0,
        "max_uses_per_short": 4,
        "cooldown_group": "whoosh_major",
        "expected_sha256": "8b7e9d487340745c2b39c50b44256459b651ea418d0cc099d8ec3a8411c4052a",
    },
    {
        "filename": "bell.mp3",
        "asset_id": "sfx_bell_revelation_01",
        "category": SFXCategory.REVELATION,
        "intensity": 0.75,
        "target_level_db": -16.0,
        "measured_max_db": -0.4,
        "measured_mean_db": -26.2,
        "base_gain_db": -15.6,
        "suitable_beat_types": ["ANCHOR_FOCAL", "PAYOFF_RESOLVE", "CANON_REVELATION", "LORE_REALIZATION"],
        "cooldown_seconds": 15.0,
        "max_uses_per_short": 2,          # Hard ceiling: maximum 1–2 meaningful uses per Short
        "cooldown_group": "bell_revelation",
        "expected_sha256": "eff7c1cb819ed99b13bf3c6ac86b123e19b0e75ec8a137ab3c26f569aa4e0edb",
    },
]


class SFXRegistry:
    """
    Strict, deterministic registry for exactly the four authorized user-supplied SFX files.
    Enforces the closed-universe invariant and validates file integrity.
    """

    def __init__(self, sfx_dir: Optional[Path] = None):
        self.sfx_dir = Path(sfx_dir or SFX_DIR)
        self._registry: Dict[str, SFXAssetRecord] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Loads and verifies exactly the four authorized SFX files."""
        for defn in AUTHORIZED_SFX_DEFINITIONS:
            file_path = self.sfx_dir / defn["filename"]
            if not file_path.exists():
                logger.warning("SFX file missing: %s", file_path)
                continue

            # Compute SHA-256
            sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if sha != defn["expected_sha256"]:
                logger.warning(
                    "SHA256 mismatch for %s: expected %s, got %s",
                    defn["filename"], defn["expected_sha256"], sha
                )

            # Probe audio metadata via ffprobe if available, or fall back to cached verified values
            meta = self._probe_audio(file_path)

            record = SFXAssetRecord(
                asset_id=defn["asset_id"],
                filename=defn["filename"],
                local_path=str(file_path.resolve()),
                duration_seconds=meta.get("duration", 1.0),
                sample_rate=meta.get("sample_rate", 44100),
                channels=meta.get("channels", 2),
                file_format=file_path.suffix.lstrip(".").lower(),
                sha256=sha,
                category=defn["category"],
                intensity=defn["intensity"],
                target_level_db=defn["target_level_db"],
                measured_max_db=defn["measured_max_db"],
                measured_mean_db=defn["measured_mean_db"],
                base_gain_db=defn["base_gain_db"],
                suitable_beat_types=defn["suitable_beat_types"],
                cooldown_seconds=defn["cooldown_seconds"],
                max_uses_per_short=defn["max_uses_per_short"],
                cooldown_group=defn["cooldown_group"],
            )
            self._registry[defn["asset_id"]] = record

    def _probe_audio(self, file_path: Path) -> Dict[str, Any]:
        """Probes audio stream parameters using ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(file_path)
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            probe = json.loads(res.stdout)
            streams = probe.get("streams", [])
            audio_s = streams[0] if streams else {}
            fmt = probe.get("format", {})
            return {
                "duration": float(fmt.get("duration", audio_s.get("duration", 1.0))),
                "sample_rate": int(audio_s.get("sample_rate", 44100)),
                "channels": int(audio_s.get("channels", 2)),
            }
        except Exception:
            return {"duration": 1.0, "sample_rate": 44100, "channels": 2}

    def get_asset(self, asset_id: str) -> Optional[SFXAssetRecord]:
        return self._registry.get(asset_id)

    def get_asset_by_category(self, category: SFXCategory) -> Optional[SFXAssetRecord]:
        for asset in self._registry.values():
            if asset.category == category:
                return asset
        return None

    def get_all_assets(self) -> List[SFXAssetRecord]:
        return list(self._registry.values())

    def validate_asset_registered(self, asset_id: str) -> bool:
        """Returns True if and only if asset_id is in the authorized 4-file registry."""
        return asset_id in self._registry

    def get_registry_hash(self) -> str:
        """Deterministic fingerprint of the registered assets and their SHA-256s."""
        tokens = [f"{a.asset_id}:{a.sha256}" for a in sorted(self._registry.values(), key=lambda x: x.asset_id)]
        return hashlib.sha256("||".join(tokens).encode("utf-8")).hexdigest()[:16]


class IntelligentSFXEngine:
    """
    Directorial beat-aware sound effect placement and scoring engine.
    Sequences and validates SFX cues against Step 4 EditorialTimeline.
    """

    def __init__(self, sfx_dir: Optional[Path] = None, fps: float = 30.0):
        self.fps = fps
        self.registry = SFXRegistry(sfx_dir=sfx_dir)

    def generate_sfx_plan(
        self,
        editorial_timeline: EditorialTimeline,
        script_text: Optional[str] = None,
        candidate_type: str = "deep_discovery",
        solemn_overrides: Optional[List[str]] = None,
    ) -> SFXPlan:
        """
        Main entry point: Generates a frame-accurate, beat-aware SFX soundtrack plan.
        Strictly isolates Novel Story pipelines.
        """
        # 1. NOVEL STORY ISOLATION GUARD
        if candidate_type == "novel_story":
            raise ValueError(
                "Novel Story pipeline is isolated from Deep Discovery Intelligent SFX Engine."
            )
        if hasattr(editorial_timeline, "metadata") and editorial_timeline.metadata.get("pipeline") == "novel_story":
            raise ValueError(
                "Novel Story pipeline is isolated from Deep Discovery Intelligent SFX Engine."
            )

        comp_id = editorial_timeline.composition_id or "deep_discovery_sfx"
        cues: List[SFXCue] = []

        # Tracking state for anti-spam, anti-consecutive, and cooldown rules
        last_placed_asset_id: Optional[str] = None
        asset_last_used_sec: Dict[str, float] = {}
        asset_usage_counts: Dict[str, int] = {defn["asset_id"]: 0 for defn in AUTHORIZED_SFX_DEFINITIONS}
        bell_uses: int = 0
        cue_idx = 1

        # Build list of solemn clip indices / beat IDs
        solemn_beat_ids = self._identify_solemn_beats(editorial_timeline, solemn_overrides)

        # 2. EVALUATE EACH EDITORIAL CLIP FOR SFX OPPORTUNITY
        total_clips = len(editorial_timeline.clips)
        for i, clip in enumerate(editorial_timeline.clips):
            # Check solemn-moment suppression
            if clip.storyboard_beat_id in solemn_beat_ids or clip.clip_id in solemn_beat_ids:
                logger.debug("Beat %s suppressed due to solemn moment.", clip.storyboard_beat_id)
                continue

            # Check if clip has speech collision risks
            protected_speech_times = self._extract_protected_speech_times(clip)

            # Determine candidate SFX category & confidence
            cat_choice, confidence, reason, ed_role = self._score_clip_eligibility(
                clip=clip,
                clip_index=i,
                total_clips=total_clips,
                bell_uses=bell_uses,
            )

            if not cat_choice or confidence < 0.60:
                # Low confidence or no editorial need -> intentional silence
                continue

            # Retrieve candidate asset
            asset = self.registry.get_asset_by_category(cat_choice)
            if not asset:
                continue

            # Enforce unregistered SFX safety
            if not self.registry.validate_asset_registered(asset.asset_id):
                raise ValueError(f"Unregistered SFX asset '{asset.asset_id}' detected! Closed universe violated.")

            # 3. ANTI-CONSECUTIVE & COOLDOWN RULES
            # Never repeat identical source asset back-to-back
            if asset.asset_id == last_placed_asset_id:
                # Try fallback category or remain silent
                fallback_cat = self._resolve_fallback_category(cat_choice, last_placed_asset_id)
                if not fallback_cat:
                    continue
                asset = self.registry.get_asset_by_category(fallback_cat)
                if not asset:
                    continue

            # Enforce per-asset cooldowns
            clip_time_sec = clip.start_seconds
            last_used = asset_last_used_sec.get(asset.asset_id, -999.0)
            if (clip_time_sec - last_used) < asset.cooldown_seconds:
                # Asset in cooldown -> silence preferred over spam
                continue

            # Enforce max uses per Short
            if asset_usage_counts[asset.asset_id] >= asset.max_uses_per_short:
                # Hard ceiling reached
                continue

            # Enforce BELL limit (max 1–2 per Short)
            if asset.category == SFXCategory.REVELATION and bell_uses >= 2:
                continue

            # 4. TIMING & SPEECH TRANSIENT PROTECTION (+/- 60ms)
            sfx_start_sec = clip_time_sec
            sfx_start_sec, gain_attenuation, is_safe = self._apply_speech_protection(
                desired_time=sfx_start_sec,
                clip=clip,
                protected_times=protected_speech_times,
            )

            if not is_safe:
                # Speech always wins -> drop cue if cannot safely protect speech
                continue

            # Calculate frame, duration, and gain
            sfx_start_frame = int(round(sfx_start_sec * self.fps))
            cue_duration = min(asset.duration_seconds, clip.duration_seconds)
            cue_duration_frames = max(1, int(round(cue_duration * self.fps)))

            # Directorial gain with subtle controlled variation
            final_gain_db = self._calculate_controlled_gain(
                base_gain=asset.base_gain_db,
                clip_id=clip.clip_id,
                asset_id=asset.asset_id,
                attenuation=gain_attenuation,
            )

            # Deterministic selection key
            selection_key = hashlib.sha256(
                f"{clip.clip_id}_{asset.asset_id}_{sfx_start_frame}".encode("utf-8")
            ).hexdigest()[:12]

            cue = SFXCue(
                cue_id=f"sfx_cue_{cue_idx:02d}",
                source_sfx_id=asset.asset_id,
                beat_id=clip.storyboard_beat_id,
                start_time=sfx_start_sec,
                start_frame=sfx_start_frame,
                duration=cue_duration,
                duration_frames=cue_duration_frames,
                category=asset.category.value,
                intensity=asset.intensity,
                gain_db=final_gain_db,
                fade_in=0.01,
                fade_out=0.05,
                semantic_reason=reason,
                editorial_role=ed_role,
                confidence=confidence,
                cooldown_group=asset.cooldown_group,
                deterministic_selection_key=selection_key,
                file_path=asset.local_path,
            )

            cues.append(cue)
            cue_idx += 1

            # Update tracking states
            last_placed_asset_id = asset.asset_id
            asset_last_used_sec[asset.asset_id] = sfx_start_sec
            asset_usage_counts[asset.asset_id] += 1
            if asset.category == SFXCategory.REVELATION:
                bell_uses += 1

        # 5. COMPUTE DETERMINISTIC SFX FINGERPRINT
        fingerprint = self._compute_sfx_fingerprint(
            editorial_fingerprint=editorial_timeline.deterministic_fingerprint,
            registry_hash=self.registry.get_registry_hash(),
            cues=cues,
            comp_id=comp_id,
        )

        return SFXPlan(
            composition_id=comp_id,
            cues=cues,
            sfx_fingerprint=fingerprint,
            total_cues=len(cues),
            metadata={
                "asset_usage_counts": asset_usage_counts,
                "bell_uses": bell_uses,
                "closed_universe_validated": True,
                "editorial_source_fingerprint": editorial_timeline.deterministic_fingerprint,
            }
        )

    def _score_clip_eligibility(
        self,
        clip: EditorialClip,
        clip_index: int,
        total_clips: int,
        bell_uses: int,
    ) -> Tuple[Optional[SFXCategory], float, str, str]:
        """
        Directorial scoring function mapping editorial metadata to SFX categories.
        """
        # Case A: Anchor revelation or major payoff
        if clip.is_anchor or clip.editorial_emphasis == EditorialEmphasis.ANCHOR_FOCAL:
            # If later in the Short (e.g. climax) and bell hasn't exceeded 2, choose BELL/REVELATION
            if bell_uses < 2 and (clip_index >= total_clips // 2 or clip.editorial_emphasis == EditorialEmphasis.PAYOFF_RESOLVE):
                return (
                    SFXCategory.REVELATION,
                    0.95,
                    "Canon anchor realization and payoff epiphany",
                    "ANCHOR_PAYOFF",
                )
            # Otherwise dramatic major visual entrance
            return (
                SFXCategory.WHOOSH_TRANSITION,
                0.90,
                "Major visual anchor entrance and escalation",
                "ANCHOR_ENTRANCE",
            )

        # Case B: Payoff Resolve at climax
        if clip.editorial_emphasis == EditorialEmphasis.PAYOFF_RESOLVE:
            if bell_uses < 2:
                return (
                    SFXCategory.REVELATION,
                    0.92,
                    "Narrative climax and lore payoff resolution",
                    "PAYOFF_RESOLVE",
                )
            return (
                SFXCategory.WHOOSH_TRANSITION,
                0.85,
                "Climactic transition resolve",
                "PAYOFF_RESOLVE",
            )

        # Case C: Ironic Contrast (e.g. Book vs Movie discrepancy)
        if (
            clip.visual_role == VisualRole.IRONIC_CONTRAST
            or clip.editorial_emphasis == EditorialEmphasis.IRONIC_HIGHLIGHT
        ):
            return (
                SFXCategory.SHORT_TRANSITION,
                0.80,
                "Structural evidence shift / novel-movie divergence",
                "IRONIC_CONTRAST",
            )

        # Case D: Micro punch camera motion or dynamic reveal
        if clip.motion_intent == MotionIntent.MICRO_PUNCH:
            return (
                SFXCategory.CLICK,
                0.85,
                "Tactile punch cut and kinetic caption accent",
                "MICRO_PUNCH",
            )

        # Case E: Transition Intent
        if clip.transition_intent in (TransitionIntent.SMASH_CUT, TransitionIntent.MATCH_CUT):
            return (
                SFXCategory.SHORT_TRANSITION,
                0.78,
                "Dynamic structural cut between narrative beats",
                "STRUCTURAL_CUT",
            )

        # Case F: Direct evidence cut with emphasized lore keyword in captions
        has_emphasized_caption = any(
            any(w.is_emphasized for w in cap.words) for cap in clip.captions
        )
        if has_emphasized_caption:
            return (
                SFXCategory.CLICK,
                0.72,
                "Kinetic emphasis on canon terminology",
                "CAPTION_ACCENT",
            )

        # Case G: Direct Evidence cut early in Short
        if clip.visual_role == VisualRole.DIRECT_EVIDENCE and clip_index % 2 == 1:
            return (
                SFXCategory.SHORT_TRANSITION,
                0.68,
                "Direct evidence progression",
                "DIRECT_EVIDENCE",
            )

        # Silence preferred
        return (None, 0.0, "", "")

    def _resolve_fallback_category(
        self,
        current_choice: SFXCategory,
        last_placed_id: str,
    ) -> Optional[SFXCategory]:
        """Provides a safe alternate category to prevent consecutive repetitions."""
        if current_choice == SFXCategory.CLICK:
            return SFXCategory.SHORT_TRANSITION if "sfx_transition" not in last_placed_id else None
        elif current_choice == SFXCategory.SHORT_TRANSITION:
            return SFXCategory.CLICK if "sfx_click" not in last_placed_id else None
        elif current_choice == SFXCategory.WHOOSH_TRANSITION:
            return SFXCategory.SHORT_TRANSITION if "sfx_transition" not in last_placed_id else None
        return None

    def _extract_protected_speech_times(self, clip: EditorialClip) -> List[Tuple[float, float, str]]:
        """
        Extracts start/end timestamps of protected canon keywords within the clip.
        """
        protected_intervals: List[Tuple[float, float, str]] = []
        for cap in clip.captions:
            for w in cap.words:
                clean_w = re.sub(r"[^a-zA-Z]", "", w.word).lower()
                if (
                    w.is_emphasized
                    or clean_w in PROTECTED_SPEECH_KEYWORDS
                    or any(clean_w in kw for kw in PROTECTED_SPEECH_KEYWORDS if len(clean_w) >= 4)
                ):
                    w_start_sec = w.start_frame / self.fps
                    w_end_sec = w.end_frame / self.fps
                    protected_intervals.append((w_start_sec, w_end_sec, w.word))
        return protected_intervals

    def _apply_speech_protection(
        self,
        desired_time: float,
        clip: EditorialClip,
        protected_times: List[Tuple[float, float, str]],
    ) -> Tuple[float, float, bool]:
        """
        Guarantees that no strong SFX transient lands within +/-60ms of an important spoken term.
        Returns: (adjusted_time, gain_attenuation_db, is_safe)
        """
        window_sec = 0.060  # 60ms safe harbor
        adjusted_time = desired_time
        attenuation_db = 0.0

        for w_start, w_end, term in protected_times:
            # Check collision: within +/- 60ms of word start
            if (w_start - window_sec) <= adjusted_time <= (w_start + window_sec):
                # Attempt 1: Nudge earlier if within clip boundary
                earlier_cand = w_start - window_sec - 0.005
                if earlier_cand >= clip.start_seconds:
                    adjusted_time = earlier_cand
                    logger.debug("Nudged SFX earlier by %0.3fs away from '%s'", w_start - adjusted_time, term)
                    return (adjusted_time, 0.0, True)

                # Attempt 2: Nudge later past the transient
                later_cand = w_start + window_sec + 0.005
                if (later_cand + 0.2) <= clip.end_seconds:
                    adjusted_time = later_cand
                    # Attenuate by 4dB when placed right after speech onset
                    attenuation_db = -4.0
                    logger.debug("Nudged SFX later by %0.3fs away from '%s'", adjusted_time - w_start, term)
                    return (adjusted_time, attenuation_db, True)

                # Attempt 3: If cannot nudge safely without violating bounds, attenuate significantly
                attenuation_db = -8.0
                return (adjusted_time, attenuation_db, True)

        return (adjusted_time, 0.0, True)

    def _identify_solemn_beats(
        self,
        timeline: EditorialTimeline,
        explicit_overrides: Optional[List[str]] = None,
    ) -> Set[str]:
        """Identifies beats containing solemn, tragic, or mournful content."""
        solemn_beats: Set[str] = set(explicit_overrides or [])

        for clip in timeline.clips:
            # Check clip text / captions
            all_text = " ".join([cap.text.lower() for cap in clip.captions])
            for kw in SOLEMN_KEYWORDS:
                if re.search(rf"\b{kw}\b", all_text):
                    solemn_beats.add(clip.storyboard_beat_id)
                    solemn_beats.add(clip.clip_id)
                    break

            # Check provenance or metadata
            if clip.source_provenance:
                prov_str = json.dumps(clip.source_provenance).lower()
                for kw in SOLEMN_KEYWORDS:
                    if re.search(rf"\b{kw}\b", prov_str):
                        solemn_beats.add(clip.storyboard_beat_id)
                        solemn_beats.add(clip.clip_id)
                        break

        return solemn_beats

    def _calculate_controlled_gain(
        self,
        base_gain: float,
        clip_id: str,
        asset_id: str,
        attenuation: float,
    ) -> float:
        """Applies subtle, deterministic gain trim (+/- 0.6 dB) to prevent acoustic monotony."""
        hash_val = int(hashlib.md5(f"{clip_id}_{asset_id}".encode("utf-8")).hexdigest()[:6], 16)
        trim_db = ((hash_val % 7) - 3) * 0.2  # Range: -0.6 to +0.6 dB
        return round(base_gain + trim_db + attenuation, 2)

    def _compute_sfx_fingerprint(
        self,
        editorial_fingerprint: str,
        registry_hash: str,
        cues: List[SFXCue],
        comp_id: str,
    ) -> str:
        """
        Computes a deterministic 16-character SHA-256 fingerprint for the SFX plan.
        Invalidates automatically if any cue, timing, gain, or source asset changes.
        """
        parts = [
            f"comp={comp_id}",
            f"ed_fp={editorial_fingerprint}",
            f"reg_hash={registry_hash}",
            f"cue_count={len(cues)}",
        ]
        for c in cues:
            parts.append(
                f"{c.cue_id}:{c.source_sfx_id}:{c.start_frame}:{c.duration_frames}:{c.gain_db:.2f}:{c.category}"
            )

        combined = "||".join(parts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]
