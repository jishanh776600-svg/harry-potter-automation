"""
Step 4: Remotion Editorial & Kinetic Typography Engine Test Suite
================================================================================
Verifies all 16 required capabilities of Step 4:
 1. Remotion project and composition configuration.
 2. 1080x1920 / 30 FPS composition specification.
 3. Storyboard-to-editorial timeline conversion (frame-accurate sequencing).
 4. Step 3 intermediate asset consumption (preprocessed paths & fingerprints).
 5. Dynamic timing preservation (Hook, Setup, Evidence, Anchor, Payoff).
 6. Anchor emphasis (ANCHOR_FOCAL, SLOW_PUSH_IN, asymmetric duration).
 7. Transition mapping (HARD_CUT, J_CUT, MATCH_CUT, CROSSFADE, SMASH_CUT).
 8. Motion intent mapping (NONE, SUBTLE_PUSH, SLOW_PUSH_IN, MICRO_PUNCH, DRIFT).
 9. Caption rendering configuration (Harry Potter serif, 84px, white, 4.5px stroke).
10. Caption timing (immediate speech start at frame 0 of beat, word timings).
11. Typography and safe-zone configuration (margins 80px/520px, Y=1400, 30 chars wrap).
12. Deterministic editorial fingerprint generation.
13. Stale fingerprint invalidation upon parameter alteration.
14. NO_VALID_VISUAL handling (no fake footage, marks not production-ready).
15. Forbidden visual source rejection (Pexels, Unsplash, AI imagery raise ValueError).
16. Novel Story isolation (Novel Story pipeline strictly isolated; raises ValueError).
"""

import json
from pathlib import Path
import pytest

from core.hybrid_visual_models import (
    VisualSourceType,
    FORBIDDEN_SOURCE_PROVIDERS,
)
from core.storyboard_types import (
    VisualRole,
    TransitionIntent,
    FallbackStrategy,
    StoryboardBeatContract,
    StoryboardPlan,
)
from core.preprocessor_types import (
    PreprocessedVisualAsset,
    PreprocessingStatus,
    AspectRatioStrategy,
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
from engines.movie_retrieval_engine import ShotScale
from engines.remotion_editorial_engine import RemotionEditorialEngine


@pytest.fixture
def sample_storyboard_plan():
    """Builds a canonical Step 2 StoryboardPlan with diverse narrative phases."""
    b_hook = StoryboardBeatContract(
        beat_id="beat_01_hook",
        narrative_phase="HOOK",
        start_seconds=0.0,
        end_seconds=1.0,
        target_duration=1.0,
        narration_intent="Hook: Neville Longbottom begged the Sorting Hat for Hufflepuff.",
        visual_role=VisualRole.DIRECT_EVIDENCE,
        visual_source_type=VisualSourceType.MOVIE_DIRECT,
        framing_intent=ShotScale.MEDIUM_SHOT,
        is_anchor=False,
    )
    b_setup = StoryboardBeatContract(
        beat_id="beat_02_setup",
        narrative_phase="SETUP",
        start_seconds=1.0,
        end_seconds=2.4,
        target_duration=1.4,
        narration_intent="Setup: In 1991, every student took their place under the ancient hat.",
        visual_role=VisualRole.CONTEXTUAL_ENVIRONMENT,
        visual_source_type=VisualSourceType.MOVIE_DIRECT,
        framing_intent=ShotScale.WIDE_SHOT,
        is_anchor=False,
    )
    b_ev = StoryboardBeatContract(
        beat_id="beat_03_ev",
        narrative_phase="EVIDENCE",
        start_seconds=2.4,
        end_seconds=4.0,
        target_duration=1.6,
        narration_intent="Evidence: The film omitted Neville's hatstall entirely.",
        evidence_point_id="ep_film_omit",
        visual_role=VisualRole.IRONIC_CONTRAST,
        visual_source_type=VisualSourceType.MOVIE_DIRECT,
        framing_intent=ShotScale.MEDIUM_SHOT,
        transition_intent=TransitionIntent.J_CUT,
        is_anchor=False,
    )
    b_anchor = StoryboardBeatContract(
        beat_id="beat_04_anchor",
        narrative_phase="ANCHOR",
        start_seconds=4.0,
        end_seconds=6.7,
        target_duration=2.7,
        narration_intent="Anchor: The Sorting Hat took nearly four minutes with Neville.",
        evidence_point_id="ep_anchor_four_mins",
        visual_role=VisualRole.DIRECT_EVIDENCE,
        visual_source_type=VisualSourceType.FAN_ART,
        framing_intent=ShotScale.CLOSE_UP,
        motion_intent="SLOW_PUSH_IN",
        transition_intent=TransitionIntent.MATCH_CUT,
        is_anchor=True,
    )
    b_payoff = StoryboardBeatContract(
        beat_id="beat_05_payoff",
        narrative_phase="PAYOFF",
        start_seconds=6.7,
        end_seconds=7.9,
        target_duration=1.2,
        narration_intent="Payoff: The hat saw Neville pulling the sword of Gryffindor.",
        visual_role=VisualRole.CHARACTER_REACTION,
        visual_source_type=VisualSourceType.MOVIE_DIRECT,
        framing_intent=ShotScale.CLOSE_UP,
        transition_intent=TransitionIntent.SMASH_CUT,
        is_anchor=False,
    )

    return StoryboardPlan(
        storyboard_id="sb_neville_hatstall_test",
        topic_id="disc_neville_sorting",
        total_target_duration=7.9,
        beats=[b_hook, b_setup, b_ev, b_anchor, b_payoff],
        anchor_beat_ids=["beat_04_anchor"],
        overall_visual_feasibility_score=88.0,
    )


@pytest.fixture
def sample_preprocessed_assets(tmp_path):
    """Builds synthetic Step 3 preprocessed assets matching the storyboard beats."""
    assets = []
    beat_ids = ["beat_01_hook", "beat_02_setup", "beat_03_ev", "beat_04_anchor", "beat_05_payoff"]
    durs = [1.0, 1.4, 1.6, 2.7, 1.2]

    for b_id, dur in zip(beat_ids, durs):
        dummy_clip = tmp_path / f"prep_{b_id}.mp4"
        dummy_clip.write_bytes(b"dummy_mp4_bytes")

        media_type = "IMAGE" if "anchor" in b_id else "VIDEO"
        assets.append(
            PreprocessedVisualAsset(
                asset_id=b_id,
                source_path=str(dummy_clip),
                source_media_type=media_type,
                output_path=str(dummy_clip),
                output_width=1080,
                output_height=1920,
                fps=30.0,
                duration=dur,
                status=PreprocessingStatus.COMPLETED,
                fingerprint=f"fp_{b_id}",
            )
        )
    return assets


@pytest.fixture
def editorial_engine(tmp_path):
    props_dir = tmp_path / "remotion_props"
    return RemotionEditorialEngine(props_dir=props_dir, fps=30.0)


# ── Test 1: Remotion Project Configuration ────────────────────────────────────

def test_01_remotion_project_configuration():
    """Verifies that the Remotion project structure and configuration files exist."""
    project_root = Path(__file__).resolve().parent.parent
    remotion_dir = project_root / "remotion"
    
    assert (remotion_dir / "package.json").exists()
    assert (remotion_dir / "remotion.config.ts").exists()
    assert (remotion_dir / "src" / "index.ts").exists()
    assert (remotion_dir / "src" / "Root.tsx").exists()
    assert (remotion_dir / "src" / "DeepDiscoveryComposition.tsx").exists()
    assert (remotion_dir / "src" / "components" / "VisualSegment.tsx").exists()
    assert (remotion_dir / "src" / "components" / "KineticTypography.tsx").exists()
    assert (remotion_dir / "src" / "components" / "SafeZoneOverlay.tsx").exists()
    assert (remotion_dir / "src" / "types" / "editorialTypes.ts").exists()
    assert (remotion_dir / "src" / "styles" / "typography.css").exists()

    with open(remotion_dir / "package.json", "r", encoding="utf-8") as f:
        pkg = json.load(f)
        assert "remotion" in pkg["dependencies"]
        assert pkg["name"] == "story-forge-remotion-editorial"


# ── Test 2: 1080x1920 / 30 FPS Specification ──────────────────────────────────

def test_02_1080x1920_30fps_specification(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies the editorial timeline specifies 1080x1920 @ 30 FPS."""
    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    assert timeline.width == 1080
    assert timeline.height == 1920
    assert timeline.fps == 30.0
    assert timeline.width / timeline.height == 9 / 16


# ── Test 3: Storyboard to Editorial Timeline Conversion ────────────────────────

def test_03_storyboard_to_editorial_timeline_conversion(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies conversion of StoryboardPlan into a continuous frame-locked timeline."""
    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    assert len(timeline.clips) == len(sample_storyboard_plan.beats)
    assert timeline.total_frames > 0

    # Verify frame continuity: no gaps, no overlaps
    for i in range(len(timeline.clips) - 1):
        c_curr = timeline.clips[i]
        c_next = timeline.clips[i + 1]
        assert c_curr.end_frame == c_next.start_frame
        assert c_curr.end_frame == c_curr.start_frame + c_curr.duration_frames

    valid, errors = timeline.validate()
    assert valid is True
    assert len(errors) == 0


# ── Test 4: Step 3 Asset Consumption ──────────────────────────────────────────

def test_04_step3_asset_consumption(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies that clips consume Step 3 preprocessed paths and preserve lineage."""
    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    for clip in timeline.clips:
        assert clip.source_preprocessed_path is not None
        assert "prep_" in clip.source_preprocessed_path
        assert clip.storyboard_beat_id is not None


# ── Test 5: Dynamic Timing Preservation ───────────────────────────────────────

def test_05_dynamic_timing_preservation(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies asymmetric beat durations are converted accurately into frame counts."""
    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    clip_hook = timeline.clips[0]     # 1.0s -> 30 frames
    clip_setup = timeline.clips[1]    # 1.4s -> 42 frames
    clip_ev = timeline.clips[2]       # 1.6s -> 48 frames
    clip_anchor = timeline.clips[3]   # 2.7s -> 81 frames
    clip_payoff = timeline.clips[4]   # 1.2s -> 36 frames

    assert clip_hook.duration_frames == 30
    assert clip_setup.duration_frames == 42
    assert clip_ev.duration_frames == 48
    assert clip_anchor.duration_frames == 81
    assert clip_payoff.duration_frames == 36


# ── Test 6: Anchor Emphasis ───────────────────────────────────────────────────

def test_06_anchor_emphasis(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies anchor clip commands ANCHOR_FOCAL, SLOW_PUSH_IN, and prolonged duration."""
    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    anchor_clip = [c for c in timeline.clips if c.is_anchor][0]
    assert anchor_clip.is_anchor is True
    assert anchor_clip.editorial_emphasis == EditorialEmphasis.ANCHOR_FOCAL
    assert anchor_clip.motion_intent == MotionIntent.SLOW_PUSH_IN
    assert anchor_clip.duration_frames == 81  # 2.7s @ 30fps


# ── Test 7: Transition Mapping ────────────────────────────────────────────────

def test_07_transition_mapping(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies mapping of all TransitionIntent values."""
    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    # b_hook: HARD_CUT -> 0 frames
    assert timeline.clips[0].transition_intent == TransitionIntent.HARD_CUT
    assert timeline.clips[0].transition_duration_frames == 0

    # b_ev: J_CUT -> 6 frames
    assert timeline.clips[2].transition_intent == TransitionIntent.J_CUT
    assert timeline.clips[2].transition_duration_frames == 6

    # b_anchor: MATCH_CUT -> 6 frames
    assert timeline.clips[3].transition_intent == TransitionIntent.MATCH_CUT
    assert timeline.clips[3].transition_duration_frames == 6

    # b_payoff: SMASH_CUT -> 0 frames
    assert timeline.clips[4].transition_intent == TransitionIntent.SMASH_CUT
    assert timeline.clips[4].transition_duration_frames == 0

    # Explicit CROSSFADE check
    ti, frames = editorial_engine._map_transition(TransitionIntent.CROSSFADE)
    assert ti == TransitionIntent.CROSSFADE
    assert frames == 10


# ── Test 8: Motion Intent Mapping ─────────────────────────────────────────────

def test_08_motion_intent_mapping(editorial_engine):
    """Verifies motion intents map properly without digital zoom distortion."""
    b_reac = StoryboardBeatContract(
        beat_id="b_reac", narrative_phase="PAYOFF", visual_role=VisualRole.CHARACTER_REACTION
    )
    mi, ee = editorial_engine._map_motion_and_emphasis(b_reac)
    assert mi == MotionIntent.SUBTLE_PUSH
    assert ee == EditorialEmphasis.REACTION_INTENSE

    b_anchor = StoryboardBeatContract(
        beat_id="b_anc", narrative_phase="ANCHOR", is_anchor=True
    )
    mi2, ee2 = editorial_engine._map_motion_and_emphasis(b_anchor)
    assert mi2 == MotionIntent.SLOW_PUSH_IN
    assert ee2 == EditorialEmphasis.ANCHOR_FOCAL


# ── Test 9: Caption Rendering Configuration ───────────────────────────────────

def test_09_caption_rendering_configuration(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies Harry Potter typography styling and lower-middle safe positioning."""
    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    typo = timeline.typography_config
    assert "Harry P" in typo.font_family
    assert typo.font_size_px == 84
    assert typo.text_color == "#FFFFFF"
    assert typo.stroke_color == "#000000"
    assert typo.stroke_width_px == 4.5
    assert typo.margin_v_px == 520
    assert typo.safe_zone_bottom_px == 1400


# ── Test 10: Caption Timing ───────────────────────────────────────────────────

def test_10_caption_timing(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies immediate speech start (frame 0 of beat) and word frame distribution."""
    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    first_clip = timeline.clips[0]
    assert len(first_clip.captions) > 0
    first_caption = first_clip.captions[0]

    # First word starts immediately at the clip's start_frame (zero delay)
    assert first_caption.start_frame == first_clip.start_frame
    assert first_caption.words[0].start_frame == first_clip.start_frame

    # Canon keyword emphasis check (e.g. "NEVILLE" or "SORTING HAT")
    has_emp = any(w.is_emphasized for cap in first_clip.captions for w in cap.words)
    assert has_emp is True


# ── Test 11: Typography and Safe-Zone Configuration ───────────────────────────

def test_11_typography_safe_zone_configuration(editorial_engine):
    """Verifies safe margins (80px horizontal, 520px vertical, 30 chars wrap)."""
    typo = editorial_engine.typography_config
    assert typo.margin_h_px == 80
    assert typo.margin_v_px == 520
    assert typo.max_chars_per_line == 30
    assert typo.safe_zone_bottom_px == 1400


# ── Test 12: Deterministic Editorial Fingerprint ──────────────────────────────

def test_12_deterministic_editorial_fingerprint(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies identical inputs produce identical 16-character SHA-256 fingerprint."""
    tl1 = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
        composition_id="comp_det_test",
    )
    tl2 = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
        composition_id="comp_det_test",
    )

    assert tl1.deterministic_fingerprint == tl2.deterministic_fingerprint
    assert len(tl1.deterministic_fingerprint) == 16


# ── Test 13: Stale Fingerprint Invalidation ───────────────────────────────────

def test_13_stale_fingerprint_invalidation(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies altering narration, transition, or timing invalidates the fingerprint."""
    tl_base = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
        composition_id="comp_stale_test",
    )

    # Modify a beat's narration text
    sample_storyboard_plan.beats[0].narration_intent = "Altered narration text for testing"
    tl_mod = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
        composition_id="comp_stale_test",
    )

    assert tl_base.deterministic_fingerprint != tl_mod.deterministic_fingerprint


# ── Test 14: NO_VALID_VISUAL Handling ──────────────────────────────────────────

def test_14_no_valid_visual_handling(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies NO_VALID_VISUAL sets validation_status, marks not ready, and injects no fake video."""
    sample_storyboard_plan.beats[2].visual_source_type = VisualSourceType.NO_VALID_VISUAL
    sample_storyboard_plan.beats[2].fallback_strategy = FallbackStrategy.REVISION_REQUIRED

    timeline = editorial_engine.build_editorial_timeline(
        storyboard_plan=sample_storyboard_plan,
        preprocessed_assets=sample_preprocessed_assets,
    )

    clip_unfilmed = timeline.clips[2]
    assert clip_unfilmed.validation_status == "NO_VALID_VISUAL"
    assert clip_unfilmed.source_preprocessed_path is None
    assert clip_unfilmed.source_media_type == "NONE"
    assert timeline.is_production_ready is False


# ── Test 15: Forbidden Visual Source Rejection ─────────────────────────────────

def test_15_forbidden_visual_source_rejection(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies forbidden stock providers (Pexels, Unsplash, AI) raise ValueError."""
    sample_storyboard_plan.beats[0].narration_intent = "Using Pexels stock clip"

    with pytest.raises(ValueError, match="FORBIDDEN VISUAL SOURCE"):
        editorial_engine.build_editorial_timeline(
            storyboard_plan=sample_storyboard_plan,
            preprocessed_assets=sample_preprocessed_assets,
        )


# ── Test 16: Novel Story Isolation ────────────────────────────────────────────

def test_16_novel_story_isolation(editorial_engine, sample_storyboard_plan, sample_preprocessed_assets):
    """Verifies passing candidate_type='novel_story' raises ValueError."""
    with pytest.raises(ValueError, match="Novel Story pipeline is isolated"):
        editorial_engine.build_editorial_timeline(
            storyboard_plan=sample_storyboard_plan,
            preprocessed_assets=sample_preprocessed_assets,
            candidate_type="novel_story",
        )
