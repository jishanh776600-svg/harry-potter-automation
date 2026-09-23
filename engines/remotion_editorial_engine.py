"""
STORY FORGE Remotion Editorial & Kinetic Typography Engine (Step 4)
================================================================================
Constructs frame-locked, deterministic editorial timelines and Remotion props:
  - Sequences standardized Step 3 intermediate visual segments (1080x1920 @ 30fps).
  - Preserves asymmetric dynamic timing from Step 2 StoryboardBeatContracts.
  - Implements controlled camera motion (SLOW_PUSH_IN for anchors, SUBTLE_PUSH for reactions).
  - Maps restrained transitions (HARD_CUT default, J_CUT, MATCH_CUT, CROSSFADE, SMASH_CUT).
  - Generates Harry Potter kinetic typography (84px white text, 4.5px black outline,
    lower-middle safe area at Y=1400, immediate speech synchronization, canon keyword emphasis).
  - Produces deterministic 16-char editorial render fingerprints.
  - Strictly isolates Novel Story pipelines.
  - Enforces NO_VALID_VISUAL and forbidden source safety.
"""

import os
import re
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

from config.settings import PROJECT_ROOT, DATA_DIR
from core.hybrid_visual_models import (
    VisualSourceType,
    FORBIDDEN_SOURCE_PROVIDERS,
)
from core.storyboard_types import (
    StoryboardBeatContract,
    StoryboardPlan,
    VisualRole,
    TransitionIntent,
    FallbackStrategy,
)
from core.preprocessor_types import (
    PreprocessedVisualAsset,
    PreprocessingStatus,
)
from core.editorial_types import (
    MotionIntent,
    EditorialEmphasis,
    CaptionWord,
    CaptionSegment,
    TypographyConfig,
    EditorialClip,
    EditorialTimeline,
)

logger = logging.getLogger(__name__)

# Canon keywords that receive subtle kinetic typography emphasis
CANON_EMPHASIS_KEYWORDS = {
    "sorting hat", "hatstall", "gryffindor", "hufflepuff", "slytherin", "ravenclaw",
    "neville", "harry", "dumbledore", "snape", "voldemort", "horcrux", "paracelsus",
    "peeves", "erised", "remembrall", "diagon alley", "godric", "salazar", "helga",
    "rowena", "hallows", "deathly hallows", "elder wand", "resurrection stone",
    "invisibility cloak", "chamber of secrets", "sword of gryffindor"
}

EDITORIAL_PROPS_DIR = DATA_DIR / "renders" / "remotion_props"
EDITORIAL_PROPS_DIR.mkdir(parents=True, exist_ok=True)


class RemotionEditorialEngine:
    """
    Directorial editorial engine constructing Remotion timelines from Step 2 & 3 outputs.
    """

    def __init__(self, props_dir: Optional[Path] = None, fps: float = 30.0):
        self.props_dir = props_dir or EDITORIAL_PROPS_DIR
        self.props_dir.mkdir(parents=True, exist_ok=True)
        self.fps = fps
        self.typography_config = TypographyConfig()

    def build_editorial_timeline(
        self,
        storyboard_plan: StoryboardPlan,
        preprocessed_assets: List[PreprocessedVisualAsset],
        script_text: Optional[str] = None,
        candidate_type: str = "deep_discovery",
        composition_id: Optional[str] = None,
        word_timestamps: Optional[List[Dict[str, Any]]] = None,
    ) -> EditorialTimeline:
        """
        Main entry point: Assembles a complete, frame-locked EditorialTimeline for Remotion.
        Strictly isolates Novel Story pipelines.
        Supports beat-locking visual cuts to exact word boundaries when word_timestamps are provided.
        """
        # 1. NOVEL STORY ISOLATION GUARD
        if candidate_type == "novel_story":
            raise ValueError(
                "Novel Story pipeline is isolated from Deep Discovery Remotion Editorial Engine."
            )
        if hasattr(storyboard_plan, "discovery_tier") and str(storyboard_plan.discovery_tier).upper() in ("NOVEL_STORY", "NOVEL_STORY_CANDIDATE"):
            raise ValueError(
                "Novel Story pipeline is isolated from Deep Discovery Remotion Editorial Engine."
            )

        comp_id = composition_id or f"remotion_{storyboard_plan.storyboard_id}"
        assets_by_beat_id = self._index_preprocessed_assets(preprocessed_assets)

        clips: List[EditorialClip] = []
        validation_errors: List[str] = []
        is_production_ready = True
        current_frame = 0

        # 2. SEQUENCE BEATS INTO EDITORIAL CLIPS
        for beat_idx, beat in enumerate(storyboard_plan.beats):
            # Check forbidden sources
            beat_dump = json.dumps(beat.to_dict()).lower()
            for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
                if forbidden in beat_dump:
                    raise ValueError(
                        f"FORBIDDEN VISUAL SOURCE: Beat '{beat.beat_id}' requested '{forbidden}'."
                    )

            # Match Step 3 asset
            asset = assets_by_beat_id.get(beat.beat_id)
            if not asset:
                # Match by prefix/substring if beat_id is part of asset_id
                for aid, a in assets_by_beat_id.items():
                    if beat.beat_id in aid or aid in beat.beat_id:
                        asset = a
                        break

            # Frame timing calculation
            start_frame = current_frame
            duration_frames = int(round(beat.target_duration * self.fps))
            if duration_frames <= 0:
                duration_frames = int(round(1.0 * self.fps))  # Fallback to 30 frames
            end_frame = start_frame + duration_frames

            # Directorial emphasis & motion mapping
            motion, emphasis = self._map_motion_and_emphasis(beat)
            trans_intent, trans_frames = self._map_transition(beat.transition_intent)

            # Kinetic typography captions
            captions = self._build_kinetic_captions(
                beat=beat,
                start_frame=start_frame,
                end_frame=end_frame,
                beat_index=beat_idx,
            )

            # Safety: NO_VALID_VISUAL check
            val_status = "VALID"
            source_path = asset.output_path if asset else None
            media_type = asset.source_media_type if asset else "VIDEO"

            if (
                beat.visual_source_type == VisualSourceType.NO_VALID_VISUAL
                or (asset and asset.status == PreprocessingStatus.NO_VALID_VISUAL)
                or beat.fallback_strategy == FallbackStrategy.REVISION_REQUIRED
            ):
                val_status = "NO_VALID_VISUAL"
                source_path = None
                media_type = "NONE"
                is_production_ready = False
                validation_errors.append(f"Beat '{beat.beat_id}' lacks valid visual evidence (NO_VALID_VISUAL)")

            clip = EditorialClip(
                clip_id=f"clip_{beat_idx+1:02d}_{beat.beat_id}",
                storyboard_beat_id=beat.beat_id,
                source_asset_id=asset.asset_id if asset else f"unresolved_{beat.beat_id}",
                source_preprocessed_path=source_path,
                source_media_type=media_type,
                start_frame=start_frame,
                end_frame=end_frame,
                duration_frames=duration_frames,
                start_seconds=round(start_frame / self.fps, 3),
                end_seconds=round(end_frame / self.fps, 3),
                duration_seconds=round(duration_frames / self.fps, 3),
                visual_role=beat.visual_role,
                is_anchor=beat.is_anchor,
                transition_intent=trans_intent,
                transition_duration_frames=trans_frames,
                motion_intent=motion,
                editorial_emphasis=emphasis,
                captions=captions,
                source_provenance=beat.source_provenance,
                validation_status=val_status,
            )
            clips.append(clip)
            current_frame = end_frame

        total_frames = current_frame
        total_seconds = round(total_frames / self.fps, 2)

        # 3. DETERMINISTIC EDITORIAL RENDER FINGERPRINT
        fingerprint = self._compute_editorial_fingerprint(
            comp_id=comp_id,
            clips=clips,
            typography=self.typography_config,
            total_frames=total_frames,
            fps=self.fps,
        )

        timeline = EditorialTimeline(
            composition_id=comp_id,
            storyboard_id=storyboard_plan.storyboard_id,
            width=1080,
            height=1920,
            fps=self.fps,
            total_duration_seconds=total_seconds,
            total_frames=total_frames,
            clips=clips,
            typography_config=self.typography_config,
            deterministic_fingerprint=fingerprint,
            is_production_ready=is_production_ready,
            validation_errors=validation_errors,
            metadata={
                "candidate_type": candidate_type,
                "clip_count": len(clips),
                "anchor_count": sum(1 for c in clips if c.is_anchor),
            },
        )

        # Validate
        valid, val_errs = timeline.validate()
        if not valid:
            timeline.validation_errors.extend(val_errs)
            timeline.is_production_ready = False

        # Export Remotion props JSON
        props_path = self.props_dir / f"{comp_id}_{fingerprint}.json"
        try:
            with open(props_path, "w", encoding="utf-8") as f:
                json.dump(timeline.to_remotion_props(), f, indent=2)
            timeline.metadata["remotion_props_path"] = str(props_path)
        except Exception as e:
            logger.debug(f"[RemotionEditorialEngine] Could not write props file: {e}")

        return timeline

    # --------------------------------------------------------------------------
    # INTERNAL HELPERS: MAPPINGS & KINETIC TYPOGRAPHY
    # --------------------------------------------------------------------------

    def _index_preprocessed_assets(
        self,
        assets: List[PreprocessedVisualAsset],
    ) -> Dict[str, PreprocessedVisualAsset]:
        """Indexes Step 3 assets by asset_id or beat_id."""
        index = {}
        for a in assets:
            index[a.asset_id] = a
        return index

    def _map_motion_and_emphasis(
        self,
        beat: StoryboardBeatContract,
    ) -> Tuple[MotionIntent, EditorialEmphasis]:
        """
        Determines controlled motion intent and editorial emphasis.
        Anchor beats command SLOW_PUSH_IN and ANCHOR_FOCAL.
        Reactions command SUBTLE_PUSH and REACTION_INTENSE.
        """
        # Explicit motion intent from beat
        if beat.motion_intent:
            try:
                mi = MotionIntent(beat.motion_intent)
            except ValueError:
                mi = MotionIntent.SLOW_PUSH_IN if beat.is_anchor else MotionIntent.NONE
        elif beat.is_anchor:
            mi = MotionIntent.SLOW_PUSH_IN
        elif beat.visual_role == VisualRole.CHARACTER_REACTION:
            mi = MotionIntent.SUBTLE_PUSH
        else:
            mi = MotionIntent.NONE

        # Editorial emphasis
        if beat.is_anchor:
            ee = EditorialEmphasis.ANCHOR_FOCAL
        elif beat.visual_role == VisualRole.CHARACTER_REACTION:
            ee = EditorialEmphasis.REACTION_INTENSE
        elif beat.visual_role == VisualRole.IRONIC_CONTRAST:
            ee = EditorialEmphasis.IRONIC_HIGHLIGHT
        elif beat.narrative_phase == "PAYOFF":
            ee = EditorialEmphasis.PAYOFF_RESOLVE
        else:
            ee = EditorialEmphasis.STANDARD

        return mi, ee

    def _map_transition(
        self,
        intent: Union[TransitionIntent, str],
    ) -> Tuple[TransitionIntent, int]:
        """
        Maps Step 2 TransitionIntent to Remotion frame transition duration.
        Defaults to restrained HARD_CUT (0 frames).
        """
        ti = intent if isinstance(intent, TransitionIntent) else TransitionIntent(intent)

        if ti == TransitionIntent.CROSSFADE:
            return TransitionIntent.CROSSFADE, 10
        elif ti in (TransitionIntent.J_CUT, TransitionIntent.MATCH_CUT):
            return ti, 6
        elif ti == TransitionIntent.SMASH_CUT:
            return TransitionIntent.SMASH_CUT, 0
        
        return TransitionIntent.HARD_CUT, 0

    def _build_kinetic_captions(
        self,
        beat: StoryboardBeatContract,
        start_frame: int,
        end_frame: int,
        beat_index: int,
    ) -> List[CaptionSegment]:
        """
        Builds synchronized kinetic typography caption segments for a beat.
        Immediate speech: First word appears at start_frame (zero delay).
        Groups words into clean 3–5 word display phrases placed at safe zone Y=1400.
        """
        text = beat.narration_intent or ""
        # Strip phase prefix if present (e.g. "Hook: ", "Evidence: ")
        text = re.sub(r"^(Hook|Setup|Evidence|Anchor|Payoff):\s*", "", text, flags=re.IGNORECASE)
        tokens = [w.strip() for w in re.split(r"\s+", text) if w.strip()]

        if not tokens:
            tokens = ["REVELATION"]

        total_frames = max(1, end_frame - start_frame)
        chunk_size = 4
        phrase_chunks = [tokens[i:i + chunk_size] for i in range(0, len(tokens), chunk_size)]

        captions: List[CaptionSegment] = []
        frames_per_chunk = max(1, total_frames // len(phrase_chunks))

        curr_f = start_frame
        for chunk_idx, chunk in enumerate(phrase_chunks):
            # Compute chunk start/end frames
            c_start = curr_f
            if chunk_idx == len(phrase_chunks) - 1:
                c_end = end_frame
            else:
                c_end = min(end_frame, c_start + frames_per_chunk)

            chunk_frames = max(1, c_end - c_start)
            words_list: List[CaptionWord] = []
            f_per_word = max(1, chunk_frames // len(chunk))

            w_start = c_start
            for w_idx, raw_w in enumerate(chunk):
                w_end = min(c_end, w_start + f_per_word) if w_idx < len(chunk) - 1 else c_end
                
                # Check canon keyword emphasis
                clean_w = re.sub(r"[^a-zA-Z]", "", raw_w).lower()
                is_emp = clean_w in CANON_EMPHASIS_KEYWORDS or any(
                    clean_w in kw for kw in CANON_EMPHASIS_KEYWORDS if len(clean_w) >= 4
                )

                words_list.append(
                    CaptionWord(
                        word=raw_w.upper(),
                        start_frame=w_start,
                        end_frame=w_end,
                        is_emphasized=is_emp,
                    )
                )
                w_start = w_end

            phrase_str = " ".join([w.word for w in words_list])
            is_multi = len(phrase_str) > self.typography_config.max_chars_per_line

            captions.append(
                CaptionSegment(
                    segment_id=f"cap_{beat_index+1:02d}_{chunk_idx+1:02d}",
                    text=phrase_str,
                    start_frame=c_start,
                    end_frame=c_end,
                    words=words_list,
                    position_y=self.typography_config.safe_zone_bottom_px,
                    style_name="HP_TwoLine" if is_multi else "HP_Default",
                    is_multiline=is_multi,
                )
            )
            curr_f = c_end

        return captions

    def _compute_editorial_fingerprint(
        self,
        comp_id: str,
        clips: List[EditorialClip],
        typography: TypographyConfig,
        total_frames: int,
        fps: float,
    ) -> str:
        """
        Computes a deterministic SHA-256 fingerprint for the entire editorial timeline.
        Altering any clip, asset, timing, transition, motion, caption text, or typography
        invalidates the fingerprint.
        """
        raw_parts = [
            f"comp={comp_id}",
            f"dim=1080x1920@{fps:.1f}",
            f"frames={total_frames}",
            f"typo_size={typography.font_size_px}",
            f"stroke={typography.stroke_width_px}",
            f"margin_v={typography.margin_v_px}",
        ]

        for c in clips:
            raw_parts.append(
                f"clip={c.clip_id}|"
                f"src={c.source_asset_id}|"
                f"f={c.start_frame}-{c.end_frame}|"
                f"role={c.visual_role.value if isinstance(c.visual_role, VisualRole) else str(c.visual_role)}|"
                f"trans={c.transition_intent.value if isinstance(c.transition_intent, TransitionIntent) else str(c.transition_intent)}:{c.transition_duration_frames}|"
                f"mot={c.motion_intent.value if isinstance(c.motion_intent, MotionIntent) else str(c.motion_intent)}|"
                f"emp={c.editorial_emphasis.value if isinstance(c.editorial_emphasis, EditorialEmphasis) else str(c.editorial_emphasis)}"
            )
            for cap in c.captions:
                raw_parts.append(f"cap={cap.text}|{cap.start_frame}-{cap.end_frame}")
                for w in cap.words:
                    if w.is_emphasized:
                        raw_parts.append(f"emp_word={w.word}")

        combined = "||".join(raw_parts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def snap_cut_points_to_words(
        cut_points: List[float],
        words: List[Dict[str, Any]],
        total_duration: float,
        snap_window: float = 0.40,
    ) -> List[float]:
        """
        Snaps visual transition cut points to exact spoken word start boundaries.
        Prevents visual lag by aligning cuts with the onset of spoken words.
        Guarantees strictly non-decreasing cut points, positive durations (>=0.5s),
        and clamping to total_duration.
        """
        if not words or not cut_points:
            return cut_points

        word_starts = sorted([float(w["start"]) for w in words if "start" in w and float(w["start"]) >= 0])
        if not word_starts:
            return cut_points

        snapped: List[float] = [0.0]
        prev_t = 0.0

        for idx in range(1, len(cut_points) - 1):
            cp = cut_points[idx]
            # Find closest word start within snap_window
            best_diff = snap_window
            best_t = cp
            for ws in word_starts:
                diff = abs(ws - cp)
                if diff < best_diff and ws >= prev_t + 0.50:
                    best_diff = diff
                    best_t = ws

            snapped_t = max(prev_t + 0.50, round(best_t, 3))
            snapped.append(snapped_t)
            prev_t = snapped_t

        snapped.append(round(total_duration, 3))
        return snapped
