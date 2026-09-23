"""
Step 5: Intelligent Beat-Aware SFX Pipeline Test Suite
================================================================================
Verifies all 20 required capabilities of Step 5:
  1. exactly-four-source SFX registry
  2. metadata extraction
  3. deterministic asset IDs
  4. semantic category assignment
  5. beat-to-SFX eligibility
  6. cue generation
  7. anti-consecutive-repeat rule
  8. cooldown enforcement
  9. intelligent density suppression
 10. gain hierarchy
 11. +/-60ms speech/transient protection
 12. solemn-moment suppression
 13. deterministic SFX fingerprint
 14. Remotion timeline integration
 15. rejection of unregistered SFX
 16. Novel Story isolation
 17. empty/no-eligible-SFX behavior
 18. supplied-file integrity validation
 19. BELL-specific usage limit
 20. deterministic repeated generation
"""

import os
import hashlib
from pathlib import Path
import pytest

from config.settings import PROJECT_ROOT, SFX_DIR
from core.editorial_types import (
    MotionIntent,
    EditorialEmphasis,
    CaptionWord,
    CaptionSegment,
    TypographyConfig,
    EditorialClip,
    EditorialTimeline,
    VisualRole,
    TransitionIntent,
)
from core.sfx_types import (
    SFXCategory,
    SFXAssetRecord,
    SFXCue,
    SFXPlan,
)
from engines.sfx_engine import (
    SFXRegistry,
    IntelligentSFXEngine,
    AUTHORIZED_SFX_DEFINITIONS,
)


@pytest.fixture
def sfx_engine():
    """Provides an IntelligentSFXEngine backed by the authorized 4-file assets."""
    return IntelligentSFXEngine(sfx_dir=SFX_DIR, fps=30.0)


@pytest.fixture
def mock_editorial_timeline():
    """Constructs a deterministic mock EditorialTimeline with 6 diverse narrative beats."""
    clips = [
        # Beat 1: Hook (Micro punch, caption accent)
        EditorialClip(
            clip_id="clip_01",
            storyboard_beat_id="beat_01_hook",
            source_asset_id="asset_norm_01",
            start_frame=0,
            end_frame=90,
            duration_frames=90,
            start_seconds=0.0,
            end_seconds=3.0,
            duration_seconds=3.0,
            visual_role=VisualRole.DIRECT_EVIDENCE,
            motion_intent=MotionIntent.MICRO_PUNCH,
            editorial_emphasis=EditorialEmphasis.STANDARD,
            captions=[
                CaptionSegment(
                    segment_id="cap_01_01",
                    text="DID YOU KNOW THIS",
                    start_frame=0,
                    end_frame=90,
                    words=[
                        CaptionWord("DID", 0, 20),
                        CaptionWord("YOU", 20, 40),
                        CaptionWord("KNOW", 40, 65),
                        CaptionWord("THIS", 65, 90),
                    ]
                )
            ]
        ),
        # Beat 2: Direct Evidence Progression
        EditorialClip(
            clip_id="clip_02",
            storyboard_beat_id="beat_02_evidence",
            source_asset_id="asset_norm_02",
            start_frame=90,
            end_frame=240,
            duration_frames=150,
            start_seconds=3.0,
            end_seconds=8.0,
            duration_seconds=5.0,
            visual_role=VisualRole.DIRECT_EVIDENCE,
            transition_intent=TransitionIntent.HARD_CUT,
            editorial_emphasis=EditorialEmphasis.STANDARD,
            captions=[
                CaptionSegment(
                    segment_id="cap_02_01",
                    text="IN THE ORIGINAL BOOK",
                    start_frame=90,
                    end_frame=240,
                    words=[
                        CaptionWord("IN", 90, 120),
                        CaptionWord("THE", 120, 150),
                        CaptionWord("ORIGINAL", 150, 195),
                        CaptionWord("BOOK", 195, 240),
                    ]
                )
            ]
        ),
        # Beat 3: Ironic Contrast (Novel vs Movie)
        EditorialClip(
            clip_id="clip_03",
            storyboard_beat_id="beat_03_ironic",
            source_asset_id="asset_norm_03",
            start_frame=240,
            end_frame=390,
            duration_frames=150,
            start_seconds=8.0,
            end_seconds=13.0,
            duration_seconds=5.0,
            visual_role=VisualRole.IRONIC_CONTRAST,
            editorial_emphasis=EditorialEmphasis.IRONIC_HIGHLIGHT,
            transition_intent=TransitionIntent.MATCH_CUT,
            captions=[
                CaptionSegment(
                    segment_id="cap_03_01",
                    text="THE FILMS CUT THIS",
                    start_frame=240,
                    end_frame=390,
                    words=[
                        CaptionWord("THE", 240, 275),
                        CaptionWord("FILMS", 275, 310),
                        CaptionWord("CUT", 310, 350),
                        CaptionWord("THIS", 350, 390),
                    ]
                )
            ]
        ),
        # Beat 4: Anchor Entrance
        EditorialClip(
            clip_id="clip_04",
            storyboard_beat_id="beat_04_anchor",
            source_asset_id="asset_norm_04",
            start_frame=390,
            end_frame=600,
            duration_frames=210,
            start_seconds=13.0,
            end_seconds=20.0,
            duration_seconds=7.0,
            is_anchor=True,
            visual_role=VisualRole.DIRECT_EVIDENCE,
            motion_intent=MotionIntent.SLOW_PUSH_IN,
            editorial_emphasis=EditorialEmphasis.ANCHOR_FOCAL,
            captions=[
                CaptionSegment(
                    segment_id="cap_04_01",
                    text="NEVILLE WAS A TRUE HATSTALL",
                    start_frame=390,
                    end_frame=600,
                    words=[
                        CaptionWord("NEVILLE", 390, 440, is_emphasized=True),
                        CaptionWord("WAS", 440, 480),
                        CaptionWord("A", 480, 500),
                        CaptionWord("TRUE", 500, 540),
                        CaptionWord("HATSTALL", 540, 600, is_emphasized=True),
                    ]
                )
            ]
        ),
        # Beat 5: Contextual Hold (Subtle, no major trigger -> silence)
        EditorialClip(
            clip_id="clip_05",
            storyboard_beat_id="beat_05_hold",
            source_asset_id="asset_norm_05",
            start_frame=600,
            end_frame=720,
            duration_frames=120,
            start_seconds=20.0,
            end_seconds=24.0,
            duration_seconds=4.0,
            visual_role=VisualRole.CONTEXTUAL_ENVIRONMENT,
            motion_intent=MotionIntent.NONE,
            editorial_emphasis=EditorialEmphasis.STANDARD,
            captions=[]
        ),
        # Beat 6: Climax Payoff Resolve
        EditorialClip(
            clip_id="clip_06",
            storyboard_beat_id="beat_06_payoff",
            source_asset_id="asset_norm_06",
            start_frame=720,
            end_frame=900,
            duration_frames=180,
            start_seconds=24.0,
            end_seconds=30.0,
            duration_seconds=6.0,
            visual_role=VisualRole.CHARACTER_REACTION,
            editorial_emphasis=EditorialEmphasis.PAYOFF_RESOLVE,
            captions=[
                CaptionSegment(
                    segment_id="cap_06_01",
                    text="FOR FIVE MINUTES",
                    start_frame=720,
                    end_frame=900,
                    words=[
                        CaptionWord("FOR", 720, 760),
                        CaptionWord("FIVE", 760, 810),
                        CaptionWord("MINUTES", 810, 900),
                    ]
                )
            ]
        ),
    ]

    return EditorialTimeline(
        composition_id="test_comp_sfx_01",
        storyboard_id="sb_test_01",
        width=1080,
        height=1920,
        fps=30.0,
        total_duration_seconds=30.0,
        total_frames=900,
        clips=clips,
        typography_config=TypographyConfig(),
        deterministic_fingerprint="test_ed_fp_123456",
        is_production_ready=True,
    )


# ------------------------------------------------------------------------------
# TEST 1: Exactly-Four-Source SFX Registry
# ------------------------------------------------------------------------------
def test_01_exactly_four_source_sfx_registry(sfx_engine):
    assets = sfx_engine.registry.get_all_assets()
    assert len(assets) == 4, f"Expected exactly 4 authorized SFX assets, found {len(assets)}"
    filenames = {a.filename for a in assets}
    expected_filenames = {
        "click-for transitions.MP3",
        "Short Transition _2 Sound .mp3",
        "WHOOSH FIRE _ SOUND EFFECT _ TRANSITION(MP3_160K).mp3",
        "bell.mp3",
    }
    assert filenames == expected_filenames, f"Mismatch in SFX library filenames: {filenames}"


# ------------------------------------------------------------------------------
# TEST 2: Metadata Extraction
# ------------------------------------------------------------------------------
def test_02_metadata_extraction(sfx_engine):
    for asset in sfx_engine.registry.get_all_assets():
        assert asset.duration_seconds > 0.0, f"Invalid duration for {asset.filename}"
        assert asset.sample_rate in (44100, 48000), f"Unexpected sample rate: {asset.sample_rate}"
        assert asset.channels in (1, 2), f"Unexpected channel count: {asset.channels}"
        assert asset.file_format == "mp3", f"Unexpected format: {asset.file_format}"
        assert len(asset.sha256) == 64, f"Invalid SHA-256 length for {asset.filename}"


# ------------------------------------------------------------------------------
# TEST 3: Deterministic Asset IDs
# ------------------------------------------------------------------------------
def test_03_deterministic_asset_ids(sfx_engine):
    expected_ids = {
        "sfx_click_tactile_01",
        "sfx_transition_short_02",
        "sfx_whoosh_fire_01",
        "sfx_bell_revelation_01",
    }
    registered_ids = {a.asset_id for a in sfx_engine.registry.get_all_assets()}
    assert registered_ids == expected_ids


# ------------------------------------------------------------------------------
# TEST 4: Semantic Category Assignment
# ------------------------------------------------------------------------------
def test_04_semantic_category_assignment(sfx_engine):
    click = sfx_engine.registry.get_asset("sfx_click_tactile_01")
    assert click.category == SFXCategory.CLICK

    short_t = sfx_engine.registry.get_asset("sfx_transition_short_02")
    assert short_t.category == SFXCategory.SHORT_TRANSITION

    whoosh = sfx_engine.registry.get_asset("sfx_whoosh_fire_01")
    assert whoosh.category == SFXCategory.WHOOSH_TRANSITION

    bell = sfx_engine.registry.get_asset("sfx_bell_revelation_01")
    assert bell.category == SFXCategory.REVELATION


# ------------------------------------------------------------------------------
# TEST 5: Beat-to-SFX Eligibility
# ------------------------------------------------------------------------------
def test_05_beat_to_sfx_eligibility(sfx_engine, mock_editorial_timeline):
    # Beat 1 (MICRO_PUNCH) -> CLICK
    cat_b1, conf_b1, reason_b1, role_b1 = sfx_engine._score_clip_eligibility(
        mock_editorial_timeline.clips[0], 0, 6, 0
    )
    assert cat_b1 == SFXCategory.CLICK
    assert conf_b1 >= 0.70

    # Beat 3 (IRONIC_CONTRAST) -> SHORT_TRANSITION
    cat_b3, conf_b3, _, _ = sfx_engine._score_clip_eligibility(
        mock_editorial_timeline.clips[2], 2, 6, 0
    )
    assert cat_b3 == SFXCategory.SHORT_TRANSITION

    # Beat 5 (Routine hold) -> None (silence)
    cat_b5, conf_b5, _, _ = sfx_engine._score_clip_eligibility(
        mock_editorial_timeline.clips[4], 4, 6, 0
    )
    assert cat_b5 is None
    assert conf_b5 == 0.0


# ------------------------------------------------------------------------------
# TEST 6: Cue Generation
# ------------------------------------------------------------------------------
def test_06_cue_generation(sfx_engine, mock_editorial_timeline):
    plan = sfx_engine.generate_sfx_plan(mock_editorial_timeline)
    assert plan.total_cues > 0
    assert len(plan.cues) == plan.total_cues

    for cue in plan.cues:
        assert cue.cue_id.startswith("sfx_cue_")
        assert sfx_engine.registry.validate_asset_registered(cue.source_sfx_id)
        assert cue.start_time >= 0.0
        assert cue.start_frame >= 0
        assert cue.duration > 0.0
        assert cue.duration_frames > 0
        assert cue.gain_db < 0.0  # Safe negative attenuation
        assert cue.file_path and os.path.exists(cue.file_path)


# ------------------------------------------------------------------------------
# TEST 7: Anti-Consecutive-Repeat Rule
# ------------------------------------------------------------------------------
def test_07_anti_consecutive_repeat_rule(sfx_engine, mock_editorial_timeline):
    plan = sfx_engine.generate_sfx_plan(mock_editorial_timeline)
    for i in range(len(plan.cues) - 1):
        c1 = plan.cues[i]
        c2 = plan.cues[i + 1]
        assert c1.source_sfx_id != c2.source_sfx_id, (
            f"Consecutive cue repeat violated between cue {c1.cue_id} and {c2.cue_id}: "
            f"both use {c1.source_sfx_id}"
        )


# ------------------------------------------------------------------------------
# TEST 8: Cooldown Enforcement
# ------------------------------------------------------------------------------
def test_08_cooldown_enforcement(sfx_engine):
    # Construct a rapid sequence of 3 micro-punch clips spaced only 0.5s apart (< 1.5s cooldown)
    rapid_clips = [
        EditorialClip(
            clip_id=f"clip_{i}",
            storyboard_beat_id=f"beat_{i}",
            source_asset_id=f"asset_{i}",
            start_frame=i * 15,
            end_frame=(i + 1) * 15,
            duration_frames=15,
            start_seconds=i * 0.5,
            end_seconds=(i + 1) * 0.5,
            duration_seconds=0.5,
            motion_intent=MotionIntent.MICRO_PUNCH,
        )
        for i in range(3)
    ]
    timeline = EditorialTimeline(
        composition_id="test_cooldown",
        storyboard_id="sb_cd",
        total_duration_seconds=1.5,
        total_frames=45,
        clips=rapid_clips,
    )
    plan = sfx_engine.generate_sfx_plan(timeline)
    # The first click can trigger, but the subsequent ones within 1.5s must be throttled
    click_cues = [c for c in plan.cues if c.source_sfx_id == "sfx_click_tactile_01"]
    assert len(click_cues) <= 1, "Cooldown failed to throttle consecutive rapid clicks"


# ------------------------------------------------------------------------------
# TEST 9: Intelligent Density Suppression
# ------------------------------------------------------------------------------
def test_09_intelligent_density_suppression(sfx_engine, mock_editorial_timeline):
    plan = sfx_engine.generate_sfx_plan(mock_editorial_timeline)
    # 6 clips should not have an SFX blindly slapped on every single clip
    # Clip 5 is an unembellished hold and must remain silent
    cued_beat_ids = {c.beat_id for c in plan.cues}
    assert "beat_05_hold" not in cued_beat_ids, "Routine hold beat received unnecessary SFX"
    assert len(plan.cues) < len(mock_editorial_timeline.clips), "Engine spammed SFX on every clip"


# ------------------------------------------------------------------------------
# TEST 10: Gain Hierarchy
# ------------------------------------------------------------------------------
def test_10_gain_hierarchy(sfx_engine):
    click = sfx_engine.registry.get_asset("sfx_click_tactile_01")
    whoosh = sfx_engine.registry.get_asset("sfx_whoosh_fire_01")
    bell = sfx_engine.registry.get_asset("sfx_bell_revelation_01")

    # Target levels: Bell (-16dB) > Whoosh (-18dB) >= Click (-20dB)
    assert bell.target_level_db > whoosh.target_level_db
    assert whoosh.target_level_db > click.target_level_db


# ------------------------------------------------------------------------------
# TEST 11: +/-60ms Speech / Transient Protection
# ------------------------------------------------------------------------------
def test_11_speech_transient_protection(sfx_engine):
    # Clip starts at 10.0s. Emphasized word starts exactly at 10.020s (+20ms into clip)
    clip = EditorialClip(
        clip_id="clip_speech_test",
        storyboard_beat_id="beat_speech",
        source_asset_id="asset_speech",
        start_frame=300,
        end_frame=390,
        duration_frames=90,
        start_seconds=10.0,
        end_seconds=13.0,
        duration_seconds=3.0,
        motion_intent=MotionIntent.MICRO_PUNCH,
        captions=[
            CaptionSegment(
                segment_id="cap_sp",
                text="VOLDEMORT SPEAKS",
                start_frame=300,
                end_frame=390,
                words=[
                    CaptionWord("VOLDEMORT", 301, 340, is_emphasized=True)
                ]
            )
        ]
    )
    protected = sfx_engine._extract_protected_speech_times(clip)
    assert len(protected) == 1
    # Check that speech protection nudges or attenuates
    adj_time, atten, is_safe = sfx_engine._apply_speech_protection(10.0, clip, protected)
    assert is_safe
    # Either shifted away from 10.033s (301/30) by > 60ms, or received attenuation
    word_start = 301 / 30.0
    collision_distance = abs(adj_time - word_start)
    assert collision_distance >= 0.055 or atten < 0.0


# ------------------------------------------------------------------------------
# TEST 12: Solemn-Moment Suppression
# ------------------------------------------------------------------------------
def test_12_solemn_moment_suppression(sfx_engine):
    solemn_clip = EditorialClip(
        clip_id="clip_solemn",
        storyboard_beat_id="beat_solemn_death",
        source_asset_id="asset_solemn",
        start_frame=0,
        end_frame=150,
        duration_frames=150,
        start_seconds=0.0,
        end_seconds=5.0,
        duration_seconds=5.0,
        is_anchor=True,
        editorial_emphasis=EditorialEmphasis.ANCHOR_FOCAL,
        captions=[
            CaptionSegment(
                segment_id="cap_solemn",
                text="SIRIUS BLACK DIED HERE",
                start_frame=0,
                end_frame=150,
                words=[
                    CaptionWord("SIRIUS", 0, 40),
                    CaptionWord("BLACK", 40, 80),
                    CaptionWord("DIED", 80, 120),
                    CaptionWord("HERE", 120, 150),
                ]
            )
        ]
    )
    timeline = EditorialTimeline(
        composition_id="solemn_test",
        storyboard_id="sb_solemn",
        total_duration_seconds=5.0,
        total_frames=150,
        clips=[solemn_clip],
    )
    plan = sfx_engine.generate_sfx_plan(timeline)
    assert plan.total_cues == 0, f"Expected 0 cues during solemn tragedy, got {plan.total_cues}"


# ------------------------------------------------------------------------------
# TEST 13: Deterministic SFX Fingerprint
# ------------------------------------------------------------------------------
def test_13_deterministic_sfx_fingerprint(sfx_engine, mock_editorial_timeline):
    plan1 = sfx_engine.generate_sfx_plan(mock_editorial_timeline)
    plan2 = sfx_engine.generate_sfx_plan(mock_editorial_timeline)

    assert plan1.sfx_fingerprint
    assert len(plan1.sfx_fingerprint) == 16
    assert plan1.sfx_fingerprint == plan2.sfx_fingerprint

    # Modifying editorial fingerprint must invalidate SFX fingerprint
    mutated_timeline = EditorialTimeline.from_dict(mock_editorial_timeline.to_dict())
    mutated_timeline.deterministic_fingerprint = "different_ed_fp"
    plan_mut = sfx_engine.generate_sfx_plan(mutated_timeline)
    assert plan_mut.sfx_fingerprint != plan1.sfx_fingerprint


# ------------------------------------------------------------------------------
# TEST 14: Remotion Timeline Integration
# ------------------------------------------------------------------------------
def test_14_remotion_timeline_integration(sfx_engine, mock_editorial_timeline):
    plan = sfx_engine.generate_sfx_plan(mock_editorial_timeline)
    props = mock_editorial_timeline.to_remotion_props(sfx_plan=plan)

    assert "sfxCues" in props
    assert "sfxFingerprint" in props
    assert props["sfxFingerprint"] == plan.sfx_fingerprint
    assert len(props["sfxCues"]) == plan.total_cues

    first_cue = props["sfxCues"][0]
    assert "cueId" in first_cue
    assert "volumeLinear" in first_cue
    assert "filePath" in first_cue
    assert first_cue["volumeLinear"] > 0.0


# ------------------------------------------------------------------------------
# TEST 15: Rejection of Unregistered SFX
# ------------------------------------------------------------------------------
def test_15_rejection_of_unregistered_sfx(sfx_engine):
    assert not sfx_engine.registry.validate_asset_registered("unregistered_explosion_sound")
    assert not sfx_engine.registry.validate_asset_registered("random_ambient_track.wav")
    assert not sfx_engine.registry.validate_asset_registered("ai_generated_whoosh")


# ------------------------------------------------------------------------------
# TEST 16: Novel Story Isolation
# ------------------------------------------------------------------------------
def test_16_novel_story_isolation(sfx_engine, mock_editorial_timeline):
    with pytest.raises(ValueError, match="Novel Story pipeline is isolated"):
        sfx_engine.generate_sfx_plan(mock_editorial_timeline, candidate_type="novel_story")


# ------------------------------------------------------------------------------
# TEST 17: Empty / No-Eligible-SFX Behavior
# ------------------------------------------------------------------------------
def test_17_empty_timeline_behavior(sfx_engine):
    empty_timeline = EditorialTimeline(
        composition_id="empty_comp",
        storyboard_id="sb_empty",
        total_duration_seconds=0.0,
        total_frames=0,
        clips=[],
    )
    plan = sfx_engine.generate_sfx_plan(empty_timeline)
    assert plan.total_cues == 0
    assert len(plan.cues) == 0
    assert plan.sfx_fingerprint
    props = empty_timeline.to_remotion_props(sfx_plan=plan)
    assert props["sfxCues"] == []


# ------------------------------------------------------------------------------
# TEST 18: Supplied-File Integrity Validation
# ------------------------------------------------------------------------------
def test_18_supplied_file_integrity(sfx_engine):
    for defn in AUTHORIZED_SFX_DEFINITIONS:
        p = Path(SFX_DIR) / defn["filename"]
        assert p.exists(), f"Supplied SFX file missing: {p}"
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        assert sha == defn["expected_sha256"], f"Integrity hash mismatch on {defn['filename']}"


# ------------------------------------------------------------------------------
# TEST 19: BELL-Specific Usage Limit
# ------------------------------------------------------------------------------
def test_19_bell_specific_usage_limit(sfx_engine):
    # Construct a timeline with 5 consecutive anchor focal beats
    anchor_clips = [
        EditorialClip(
            clip_id=f"clip_anchor_{i}",
            storyboard_beat_id=f"beat_anchor_{i}",
            source_asset_id=f"asset_anchor_{i}",
            start_frame=i * 600,
            end_frame=(i + 1) * 600,
            duration_frames=600,
            start_seconds=i * 20.0,
            end_seconds=(i + 1) * 20.0,
            duration_seconds=20.0,
            is_anchor=True,
            editorial_emphasis=EditorialEmphasis.PAYOFF_RESOLVE,
        )
        for i in range(5)
    ]
    long_timeline = EditorialTimeline(
        composition_id="test_bell_cap",
        storyboard_id="sb_bell",
        total_duration_seconds=100.0,
        total_frames=3000,
        clips=anchor_clips,
    )
    plan = sfx_engine.generate_sfx_plan(long_timeline)
    bell_cues = [c for c in plan.cues if c.source_sfx_id == "sfx_bell_revelation_01"]
    assert len(bell_cues) <= 2, f"BELL usage cap exceeded! Expected <= 2, got {len(bell_cues)}"


# ------------------------------------------------------------------------------
# TEST 20: Deterministic Repeated Generation
# ------------------------------------------------------------------------------
def test_20_deterministic_repeated_generation(sfx_engine, mock_editorial_timeline):
    plan_a = sfx_engine.generate_sfx_plan(mock_editorial_timeline)
    plan_b = sfx_engine.generate_sfx_plan(mock_editorial_timeline)

    assert plan_a.sfx_fingerprint == plan_b.sfx_fingerprint
    assert len(plan_a.cues) == len(plan_b.cues)

    for c_a, c_b in zip(plan_a.cues, plan_b.cues):
        assert c_a.cue_id == c_b.cue_id
        assert c_a.source_sfx_id == c_b.source_sfx_id
        assert c_a.start_frame == c_b.start_frame
        assert c_a.duration_frames == c_b.duration_frames
        assert c_a.gain_db == c_b.gain_db
        assert c_a.deterministic_selection_key == c_b.deterministic_selection_key
