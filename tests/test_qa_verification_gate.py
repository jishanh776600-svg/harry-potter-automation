"""
Step 6: Automated 10-Point QA Verification Gate Test Suite
================================================================================
Verifies all 20 required capabilities of Step 6:
  1. duration pass
  2. duration fail
  3. hook timing pass/fail
  4. cut density pass/fail
  5. forbidden visual detection
  6. caption safe-zone validation
  7. audio loudness/peak validation
  8. NOT_APPLICABLE audio state
  9. black/frozen/corrupt frame detection
 10. visual repetition detection
 11. evidence provenance validation
 12. unsupported factual claim rejection
 13. payoff completeness
 14. blocker/error/warning severity
 15. production_ready decision
 16. cross-system fingerprint mismatch
 17. deterministic QA fingerprint
 18. Novel Story tier isolation
 19. no silent auto-repair
 20. deterministic repeated QA result
"""

import copy
import pytest

from core.storyboard_types import (
    VisualRole,
    TransitionIntent,
    StoryboardPlan,
    StoryboardBeatContract,
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
from core.sfx_types import (
    SFXCue,
    SFXPlan,
)
from core.discovery_types import (
    DeepDiscoveryStoryPlan,
    EvidencePoint,
    DiscoveryTier,
)
from core.qa_types import (
    QASeverity,
    QACheckStatus,
    QACheckResult,
    QAPackageReport,
)
from engines.qa_verification_gate import QAVerificationGate


@pytest.fixture
def qa_gate():
    """Provides a fresh QAVerificationGate instance."""
    return QAVerificationGate()


@pytest.fixture
def canonical_package():
    """
    Constructs a fully valid, production-ready Deep Discovery candidate package.
    72.0s duration, 42 clips (~1.7s per cut), immediate hook, verified evidence.
    """
    fps = 30.0
    total_clips = 42
    total_frames = 2160  # 72.0s @ 30fps
    frames_per_clip = total_frames // total_clips  # ~51 frames

    clips: list[EditorialClip] = []
    current_f = 0

    for i in range(total_clips):
        c_start = current_f
        c_end = total_frames if i == total_clips - 1 else c_start + frames_per_clip
        c_dur_f = c_end - c_start
        c_start_s = c_start / fps
        c_dur_s = c_dur_f / fps

        is_anchor = (i == 25)
        is_payoff = (i == total_clips - 1)
        emphasis = EditorialEmphasis.PAYOFF_RESOLVE if is_payoff else (
            EditorialEmphasis.ANCHOR_FOCAL if is_anchor else EditorialEmphasis.STANDARD
        )

        captions = []
        if i == 0:
            # Immediate hook: first word at frame 0 (0.0s <= 120ms)
            captions.append(
                CaptionSegment(
                    segment_id="cap_01_01",
                    text="DID YOU KNOW NEVILLE",
                    start_frame=0,
                    end_frame=c_dur_f,
                    words=[
                        CaptionWord("DID", 0, 12),
                        CaptionWord("YOU", 12, 24),
                        CaptionWord("KNOW", 24, 38),
                        CaptionWord("NEVILLE", 38, c_dur_f, is_emphasized=True),
                    ]
                )
            )

        clips.append(
            EditorialClip(
                clip_id=f"clip_{i+1:02d}",
                storyboard_beat_id=f"beat_{i+1:02d}",
                source_asset_id=f"asset_hp_movie_scene_{i:02d}",
                source_preprocessed_path=f"/assets/preprocessed/scene_{i:02d}.mp4",
                start_frame=c_start,
                end_frame=c_end,
                duration_frames=c_dur_f,
                start_seconds=c_start_s,
                end_seconds=c_start_s + c_dur_s,
                duration_seconds=c_dur_s,
                visual_role=VisualRole.DIRECT_EVIDENCE,
                is_anchor=is_anchor,
                editorial_emphasis=emphasis,
                captions=captions,
                source_provenance={"source_class": "MOVIE_CANON", "movie_index": 1},
            )
        )
        current_f = c_end

    typo = TypographyConfig(
        font_family="Harry P, Georgia, serif",
        font_size_px=84,
        text_color="#FFFFFF",
        stroke_color="#000000",
        stroke_width_px=4.5,
        safe_zone_bottom_px=1400,
        margin_v_px=520,
    )

    timeline = EditorialTimeline(
        composition_id="comp_deep_discovery_01",
        storyboard_id="sb_canon_01",
        width=1080,
        height=1920,
        fps=fps,
        total_duration_seconds=72.0,
        total_frames=total_frames,
        clips=clips,
        typography_config=typo,
        deterministic_fingerprint="ed_fp_valid_123456",
        is_production_ready=True,
    )

    sfx_plan = SFXPlan(
        composition_id="comp_deep_discovery_01",
        cues=[
            SFXCue(
                cue_id="sfx_01",
                source_sfx_id="sfx_click_tactile_01",
                beat_id="beat_01",
                start_time=0.0,
                start_frame=0,
                duration=0.34,
                duration_frames=10,
                category="CLICK",
                intensity=0.35,
                gain_db=-20.0,
            )
        ],
        sfx_fingerprint="sfx_fp_valid_9988",
        total_cues=1,
        metadata={"editorial_source_fingerprint": "ed_fp_valid_123456"},
    )

    story_plan = DeepDiscoveryStoryPlan(
        topic_id="neville_hatstall_truth",
        discovery_type="DISCOVERY_BOOK_MOVIE_DIFFERENCE",
        thesis="Neville Longbottom was a true Hatstall in novel canon.",
        evidence_points=[
            EvidencePoint(
                claim="The Sorting Hat argued with Neville for nearly five minutes",
                evidence_route="NOVEL_CANON",
                source_id="hp1_ch07_sorting",
                source_excerpt="The hat took almost five minutes to decide on Neville...",
                verified=True,
            )
        ],
    )

    audio_metrics = {
        "integrated_lufs": -13.0,
        "true_peak_dbtp": -0.5,
    }

    return {
        "timeline": timeline,
        "sfx_plan": sfx_plan,
        "story_plan": story_plan,
        "audio_metrics": audio_metrics,
    }


# ------------------------------------------------------------------------------
# TEST 1: Duration Pass
# ------------------------------------------------------------------------------
def test_01_duration_pass(qa_gate, canonical_package):
    report = qa_gate.evaluate_package(
        candidate_id="test_short_01",
        editorial_timeline=canonical_package["timeline"],
        sfx_plan=canonical_package["sfx_plan"],
        story_plan=canonical_package["story_plan"],
        audio_metrics=canonical_package["audio_metrics"],
    )
    c1 = next(c for c in report.checks if c.check_id == "check_01_duration")
    assert c1.status == QACheckStatus.PASS
    assert c1.severity == QASeverity.PASS


# ------------------------------------------------------------------------------
# TEST 2: Duration Fail
# ------------------------------------------------------------------------------
def test_02_duration_fail(qa_gate, canonical_package):
    # Case A: Violates hard ceiling (85.0s > 80.9s) -> BLOCKER
    timeline_too_long = copy.deepcopy(canonical_package["timeline"])
    timeline_too_long.total_duration_seconds = 85.0
    report_long = qa_gate.evaluate_package(
        candidate_id="test_long",
        editorial_timeline=timeline_too_long,
    )
    c_long = next(c for c in report_long.checks if c.check_id == "check_01_duration")
    assert c_long.status == QACheckStatus.FAIL
    assert c_long.severity == QASeverity.BLOCKER

    # Case B: Below Deep Discovery minimum (60.0s < 68.0s) -> ERROR
    timeline_too_short = copy.deepcopy(canonical_package["timeline"])
    timeline_too_short.total_duration_seconds = 60.0
    report_short = qa_gate.evaluate_package(
        candidate_id="test_short",
        editorial_timeline=timeline_too_short,
    )
    c_short = next(c for c in report_short.checks if c.check_id == "check_01_duration")
    assert c_short.status == QACheckStatus.FAIL
    assert c_short.severity == QASeverity.ERROR


# ------------------------------------------------------------------------------
# TEST 3: Hook Timing Pass / Fail
# ------------------------------------------------------------------------------
def test_03_hook_timing_pass_fail(qa_gate, canonical_package):
    # Pass case: First word starts at 0ms (<= 120ms)
    report_pass = qa_gate.evaluate_package(
        candidate_id="test_hook_pass",
        editorial_timeline=canonical_package["timeline"],
    )
    c_hook = next(c for c in report_pass.checks if c.check_id == "check_02_immediate_hook")
    assert c_hook.status == QACheckStatus.PASS

    # Fail case 1: Spoken word delayed to 300ms (> 120ms dead-air)
    timeline_delayed = copy.deepcopy(canonical_package["timeline"])
    timeline_delayed.clips[0].captions[0].words[0].start_frame = 9  # 9/30 = 300ms
    report_delayed = qa_gate.evaluate_package(
        candidate_id="test_hook_delayed",
        editorial_timeline=timeline_delayed,
    )
    c_delayed = next(c for c in report_delayed.checks if c.check_id == "check_02_immediate_hook")
    assert c_delayed.status == QACheckStatus.FAIL
    assert c_delayed.severity == QASeverity.ERROR

    # Fail case 2: Throat-clearing intro ("Hey guys welcome back")
    timeline_throat = copy.deepcopy(canonical_package["timeline"])
    timeline_throat.clips[0].captions[0].text = "HEY GUYS WELCOME BACK TO HARRY POTTER"
    report_throat = qa_gate.evaluate_package(
        candidate_id="test_hook_throat",
        editorial_timeline=timeline_throat,
    )
    c_throat = next(c for c in report_throat.checks if c.check_id == "check_02_immediate_hook")
    assert c_throat.status == QACheckStatus.FAIL
    assert "Throat-clearing" in c_throat.diagnostic_message


# ------------------------------------------------------------------------------
# TEST 4: Cut Density Pass / Fail
# ------------------------------------------------------------------------------
def test_04_cut_density_pass_fail(qa_gate, canonical_package):
    # Pass case: 42 cuts for 72s
    report_pass = qa_gate.evaluate_package(
        candidate_id="test_cut_pass",
        editorial_timeline=canonical_package["timeline"],
    )
    c_cut = next(c for c in report_pass.checks if c.check_id == "check_03_cut_density")
    assert c_cut.status == QACheckStatus.PASS

    # Fail case 1: Too sparse (only 12 cuts for 72s)
    timeline_sparse = copy.deepcopy(canonical_package["timeline"])
    timeline_sparse.clips = timeline_sparse.clips[:12]
    report_sparse = qa_gate.evaluate_package(
        candidate_id="test_sparse",
        editorial_timeline=timeline_sparse,
    )
    c_sparse = next(c for c in report_sparse.checks if c.check_id == "check_03_cut_density")
    assert c_sparse.status == QACheckStatus.FAIL
    assert c_sparse.severity == QASeverity.ERROR

    # Fail case 2: Non-anchor clip holds for 4.5s (> 3.5s limit)
    timeline_long_shot = copy.deepcopy(canonical_package["timeline"])
    timeline_long_shot.clips[1].duration_seconds = 4.5
    timeline_long_shot.clips[1].is_anchor = False
    timeline_long_shot.clips[1].editorial_emphasis = EditorialEmphasis.STANDARD
    report_long_shot = qa_gate.evaluate_package(
        candidate_id="test_long_shot",
        editorial_timeline=timeline_long_shot,
    )
    c_ls = next(c for c in report_long_shot.checks if c.check_id == "check_03_cut_density")
    assert c_ls.status == QACheckStatus.FAIL
    assert "Shot duration violation" in c_ls.diagnostic_message


# ------------------------------------------------------------------------------
# TEST 5: Forbidden Visual Detection
# ------------------------------------------------------------------------------
def test_05_forbidden_visual_detection(qa_gate, canonical_package):
    # Inject Pexels stock footage into clip 3
    timeline_bad = copy.deepcopy(canonical_package["timeline"])
    timeline_bad.clips[2].source_preprocessed_path = "/assets/stock/pexels_castle_123.mp4"
    report_bad = qa_gate.evaluate_package(
        candidate_id="test_forbidden_stock",
        editorial_timeline=timeline_bad,
    )
    c_source = next(c for c in report_bad.checks if c.check_id == "check_04_visual_source_policy")
    assert c_source.status == QACheckStatus.FAIL
    assert c_source.severity == QASeverity.BLOCKER
    assert "pexels" in c_source.diagnostic_message.lower()

    # Inject Midjourney AI image into clip 4
    timeline_ai = copy.deepcopy(canonical_package["timeline"])
    timeline_ai.clips[3].source_asset_id = "midjourney_v6_sorting_hat"
    report_ai = qa_gate.evaluate_package(
        candidate_id="test_forbidden_ai",
        editorial_timeline=timeline_ai,
    )
    c_ai = next(c for c in report_ai.checks if c.check_id == "check_04_visual_source_policy")
    assert c_ai.status == QACheckStatus.FAIL
    assert c_ai.severity == QASeverity.BLOCKER


# ------------------------------------------------------------------------------
# TEST 6: Caption Safe Zone Validation
# ------------------------------------------------------------------------------
def test_06_caption_safe_zone_validation(qa_gate, canonical_package):
    # Pass case
    report_pass = qa_gate.evaluate_package(
        candidate_id="test_cap_pass",
        editorial_timeline=canonical_package["timeline"],
    )
    c_cap = next(c for c in report_pass.checks if c.check_id == "check_05_caption_safe_zone")
    assert c_cap.status == QACheckStatus.PASS

    # Fail case 1: Placed in bottom UI area (Y = 1750)
    timeline_bad_y = copy.deepcopy(canonical_package["timeline"])
    timeline_bad_y.typography_config.safe_zone_bottom_px = 1750
    report_bad_y = qa_gate.evaluate_package(
        candidate_id="test_cap_y",
        editorial_timeline=timeline_bad_y,
    )
    c_bad_y = next(c for c in report_bad_y.checks if c.check_id == "check_05_caption_safe_zone")
    assert c_bad_y.status == QACheckStatus.FAIL
    assert c_bad_y.severity == QASeverity.ERROR

    # Fail case 2: Outline stroke too thin (1.0px < 3.0px)
    timeline_bad_stroke = copy.deepcopy(canonical_package["timeline"])
    timeline_bad_stroke.typography_config.stroke_width_px = 1.0
    report_bad_stroke = qa_gate.evaluate_package(
        candidate_id="test_cap_stroke",
        editorial_timeline=timeline_bad_stroke,
    )
    c_stroke = next(c for c in report_bad_stroke.checks if c.check_id == "check_05_caption_safe_zone")
    assert c_stroke.status == QACheckStatus.FAIL


# ------------------------------------------------------------------------------
# TEST 7: Audio Loudness / Peak Validation
# ------------------------------------------------------------------------------
def test_07_audio_loudness_peak_validation(qa_gate, canonical_package):
    # Pass: -13.0 LUFS, -0.5 dBTP
    report = qa_gate.evaluate_package(
        candidate_id="test_audio_pass",
        editorial_timeline=canonical_package["timeline"],
        audio_metrics={"integrated_lufs": -13.0, "true_peak_dbtp": -0.5},
    )
    c_audio = next(c for c in report.checks if c.check_id == "check_06_audio_loudness_peak")
    assert c_audio.status == QACheckStatus.PASS

    # Fail: Peak clipping (+0.4 dBTP > -0.1 dBTP)
    report_clip = qa_gate.evaluate_package(
        candidate_id="test_audio_clip",
        editorial_timeline=canonical_package["timeline"],
        audio_metrics={"integrated_lufs": -13.0, "true_peak_dbtp": 0.4},
    )
    c_clip = next(c for c in report_clip.checks if c.check_id == "check_06_audio_loudness_peak")
    assert c_clip.status == QACheckStatus.FAIL

    # Fail: Loudness too quiet (-19.0 LUFS < -14.5 LUFS)
    report_quiet = qa_gate.evaluate_package(
        candidate_id="test_audio_quiet",
        editorial_timeline=canonical_package["timeline"],
        audio_metrics={"integrated_lufs": -19.0, "true_peak_dbtp": -1.0},
    )
    c_quiet = next(c for c in report_quiet.checks if c.check_id == "check_06_audio_loudness_peak")
    assert c_quiet.status == QACheckStatus.FAIL


# ------------------------------------------------------------------------------
# TEST 8: NOT_APPLICABLE Audio State
# ------------------------------------------------------------------------------
def test_08_not_applicable_audio_state(qa_gate, canonical_package):
    # When audio metrics are omitted, status must be NOT_APPLICABLE without failing overall package
    report = qa_gate.evaluate_package(
        candidate_id="test_audio_na",
        editorial_timeline=canonical_package["timeline"],
        audio_metrics=None,
    )
    c_audio = next(c for c in report.checks if c.check_id == "check_06_audio_loudness_peak")
    assert c_audio.status == QACheckStatus.NOT_APPLICABLE
    assert c_audio.severity == QASeverity.PASS


# ------------------------------------------------------------------------------
# TEST 9: Visual Integrity Detection
# ------------------------------------------------------------------------------
def test_09_visual_integrity_detection(qa_gate, canonical_package):
    # Inject temporal gap between clip 2 and 3
    timeline_gap = copy.deepcopy(canonical_package["timeline"])
    timeline_gap.clips[2].start_frame += 10  # 10 frame gap
    report_gap = qa_gate.evaluate_package(
        candidate_id="test_gap",
        editorial_timeline=timeline_gap,
    )
    c_gap = next(c for c in report_gap.checks if c.check_id == "check_07_visual_integrity")
    assert c_gap.status == QACheckStatus.FAIL
    assert c_gap.severity == QASeverity.BLOCKER

    # Inject NO_VALID_VISUAL status
    timeline_nv = copy.deepcopy(canonical_package["timeline"])
    timeline_nv.clips[5].validation_status = "NO_VALID_VISUAL"
    report_nv = qa_gate.evaluate_package(
        candidate_id="test_nv",
        editorial_timeline=timeline_nv,
    )
    c_nv = next(c for c in report_nv.checks if c.check_id == "check_07_visual_integrity")
    assert c_nv.status == QACheckStatus.FAIL
    assert c_nv.severity == QASeverity.BLOCKER


# ------------------------------------------------------------------------------
# TEST 10: Visual Repetition Detection
# ------------------------------------------------------------------------------
def test_10_visual_repetition_detection(qa_gate, canonical_package):
    # Re-use identical asset across 4 clips to simulate lazy footage recycling
    timeline_rep = copy.deepcopy(canonical_package["timeline"])
    for idx in [2, 5, 8, 12]:
        timeline_rep.clips[idx].source_asset_id = "recycled_dumbledore_shot"

    report_rep = qa_gate.evaluate_package(
        candidate_id="test_rep",
        editorial_timeline=timeline_rep,
    )
    c_rep = next(c for c in report_rep.checks if c.check_id == "check_08_visual_repetition")
    assert c_rep.status == QACheckStatus.FAIL
    assert c_rep.severity == QASeverity.ERROR
    assert "recycled_dumbledore_shot" in c_rep.diagnostic_message


# ------------------------------------------------------------------------------
# TEST 11: Evidence Provenance Validation
# ------------------------------------------------------------------------------
def test_11_evidence_provenance_validation(qa_gate, canonical_package):
    report = qa_gate.evaluate_package(
        candidate_id="test_evidence",
        editorial_timeline=canonical_package["timeline"],
        story_plan=canonical_package["story_plan"],
    )
    c_ev = next(c for c in report.checks if c.check_id == "check_09_evidence_linkage")
    assert c_ev.status == QACheckStatus.PASS


# ------------------------------------------------------------------------------
# TEST 12: Unsupported Factual Claim Rejection
# ----------------------------------------------------------------IZED
def test_12_unsupported_factual_claim_rejection(qa_gate, canonical_package):
    bad_story_plan = copy.deepcopy(canonical_package["story_plan"])
    bad_story_plan.evidence_points.append(
        EvidencePoint(
            claim="Dumbledore had a secret twin brother in London",
            evidence_route="NOVEL_CANON",
            source_id="",  # Empty citation
            source_excerpt="",  # Empty excerpt
            verified=False,
        )
    )
    report = qa_gate.evaluate_package(
        candidate_id="test_unsupported_claim",
        editorial_timeline=canonical_package["timeline"],
        story_plan=bad_story_plan,
    )
    c_ev = next(c for c in report.checks if c.check_id == "check_09_evidence_linkage")
    assert c_ev.status == QACheckStatus.FAIL
    assert c_ev.severity == QASeverity.ERROR
    assert "Unsupported factual claim" in c_ev.diagnostic_message


# ------------------------------------------------------------------------------
# TEST 13: Payoff Completeness
# ------------------------------------------------------------------------------
def test_13_payoff_completeness(qa_gate, canonical_package):
    # Pass: Last clip has PAYOFF_RESOLVE
    report_pass = qa_gate.evaluate_package(
        candidate_id="test_payoff_pass",
        editorial_timeline=canonical_package["timeline"],
    )
    c_payoff = next(c for c in report_pass.checks if c.check_id == "check_10_payoff_completeness")
    assert c_payoff.status == QACheckStatus.PASS

    # Fail: Stripped payoff in second half
    timeline_no_payoff = copy.deepcopy(canonical_package["timeline"])
    for c in timeline_no_payoff.clips[21:]:
        c.editorial_emphasis = EditorialEmphasis.STANDARD
        c.is_anchor = False

    report_fail = qa_gate.evaluate_package(
        candidate_id="test_payoff_fail",
        editorial_timeline=timeline_no_payoff,
    )
    c_fail = next(c for c in report_fail.checks if c.check_id == "check_10_payoff_completeness")
    assert c_fail.status == QACheckStatus.FAIL
    assert c_fail.severity == QASeverity.ERROR


# ------------------------------------------------------------------------------
# TEST 14: Blocker / Error / Warning Severity Model
# ------------------------------------------------------------------------------
def test_14_blocker_error_warning_severity(qa_gate, canonical_package):
    # Introduce 1 Blocker (forbidden stock) and 1 Error (caption safe zone)
    timeline_multi = copy.deepcopy(canonical_package["timeline"])
    timeline_multi.clips[0].source_asset_id = "shutterstock_wand_123"
    timeline_multi.typography_config.safe_zone_bottom_px = 1800

    report = qa_gate.evaluate_package(
        candidate_id="test_severity",
        editorial_timeline=timeline_multi,
    )
    assert report.blocker_count >= 1
    assert report.error_count >= 1
    assert not report.overall_pass
    assert not report.production_ready


# ------------------------------------------------------------------------------
# TEST 15: Production-Ready Decision
# ------------------------------------------------------------------------------
def test_15_production_ready_decision(qa_gate, canonical_package):
    # Valid package -> production_ready is True
    report_valid = qa_gate.evaluate_package(
        candidate_id="test_ready",
        editorial_timeline=canonical_package["timeline"],
        sfx_plan=canonical_package["sfx_plan"],
        story_plan=canonical_package["story_plan"],
        audio_metrics=canonical_package["audio_metrics"],
    )
    assert report_valid.overall_pass is True
    assert report_valid.production_ready is True

    # Mutate to fail -> production_ready must be False
    timeline_broken = copy.deepcopy(canonical_package["timeline"])
    timeline_broken.total_duration_seconds = 92.0  # Blocker
    report_broken = qa_gate.evaluate_package(
        candidate_id="test_not_ready",
        editorial_timeline=timeline_broken,
    )
    assert report_broken.overall_pass is False
    assert report_broken.production_ready is False


# ------------------------------------------------------------------------------
# TEST 16: Cross-System Fingerprint Mismatch
# ------------------------------------------------------------------------------
def test_16_cross_system_fingerprint_mismatch(qa_gate, canonical_package):
    stale_sfx = copy.deepcopy(canonical_package["sfx_plan"])
    stale_sfx.metadata["editorial_source_fingerprint"] = "stale_outdated_fp"

    report = qa_gate.evaluate_package(
        candidate_id="test_stale_fp",
        editorial_timeline=canonical_package["timeline"],
        sfx_plan=stale_sfx,
    )
    c_fp = next(c for c in report.checks if c.check_id == "check_cross_system_fingerprints")
    assert c_fp.status == QACheckStatus.FAIL
    assert c_fp.severity == QASeverity.ERROR
    assert "does not match editorial fingerprint" in c_fp.diagnostic_message


# ------------------------------------------------------------------------------
# TEST 17: Deterministic QA Fingerprint
# ------------------------------------------------------------------------------
def test_17_deterministic_qa_fingerprint(qa_gate, canonical_package):
    report1 = qa_gate.evaluate_package(
        candidate_id="test_fp_01",
        editorial_timeline=canonical_package["timeline"],
        sfx_plan=canonical_package["sfx_plan"],
    )
    report2 = qa_gate.evaluate_package(
        candidate_id="test_fp_01",
        editorial_timeline=canonical_package["timeline"],
        sfx_plan=canonical_package["sfx_plan"],
    )
    assert report1.qa_fingerprint
    assert len(report1.qa_fingerprint) == 16
    assert report1.qa_fingerprint == report2.qa_fingerprint

    # Mutating input changes QA fingerprint
    mutated = copy.deepcopy(canonical_package["timeline"])
    mutated.deterministic_fingerprint = "different_ed_fp"
    report_mut = qa_gate.evaluate_package(
        candidate_id="test_fp_01",
        editorial_timeline=mutated,
        sfx_plan=canonical_package["sfx_plan"],
    )
    assert report_mut.qa_fingerprint != report1.qa_fingerprint


# ------------------------------------------------------------------------------
# TEST 18: Novel Story Tier Isolation
# ------------------------------------------------------------------------------
def test_18_novel_story_tier_isolation(qa_gate):
    # Construct a Novel Story timeline: 50.0s, only 14 cuts, atmospheric hook
    clips = [
        EditorialClip(
            clip_id=f"clip_{i}",
            storyboard_beat_id=f"beat_{i}",
            source_asset_id=f"asset_ns_{i}",
            start_frame=i * 107,
            end_frame=(i + 1) * 107,
            duration_frames=107,
            start_seconds=i * 3.57,
            end_seconds=(i + 1) * 3.57,
            duration_seconds=3.57,
            visual_role=VisualRole.DIRECT_EVIDENCE,
            editorial_emphasis=EditorialEmphasis.PAYOFF_RESOLVE if i == 13 else EditorialEmphasis.STANDARD,
        )
        for i in range(14)
    ]
    ns_timeline = EditorialTimeline(
        composition_id="comp_novel_story_01",
        storyboard_id="sb_ns_01",
        width=1080,
        height=1920,
        fps=30.0,
        total_duration_seconds=50.0,
        total_frames=1500,
        clips=clips,
        deterministic_fingerprint="ns_fp_123",
        metadata={"pipeline": "novel_story"},
    )

    report_ns = qa_gate.evaluate_package(
        candidate_id="test_ns_short",
        editorial_timeline=ns_timeline,
        candidate_type="novel_story",
    )
    # Check 1 Duration: passes 50s (45-60s range)
    c1 = next(c for c in report_ns.checks if c.check_id == "check_01_duration")
    assert c1.status == QACheckStatus.PASS

    # Check 3 Cut Density: does NOT fail for having only 14 cuts
    c3 = next(c for c in report_ns.checks if c.check_id == "check_03_cut_density")
    assert c3.status == QACheckStatus.PASS

    assert report_ns.candidate_type == "novel_story"


# ------------------------------------------------------------------------------
# TEST 19: No Silent Auto-Repair
# ------------------------------------------------------------------------------
def test_19_no_silent_auto_repair(qa_gate, canonical_package):
    # Mutate timeline with an error
    timeline = copy.deepcopy(canonical_package["timeline"])
    original_dur = 85.0
    timeline.total_duration_seconds = original_dur

    report = qa_gate.evaluate_package(
        candidate_id="test_no_repair",
        editorial_timeline=timeline,
    )
    # Timeline must NOT be modified in-place
    assert timeline.total_duration_seconds == original_dur, "Gate silently modified timeline duration"

    # Actionable diagnostic & remediation suggestion provided
    c_dur = next(c for c in report.checks if c.check_id == "check_01_duration")
    assert c_dur.status == QACheckStatus.FAIL
    assert len(c_dur.remediation_suggestion) > 0


# ------------------------------------------------------------------------------
# TEST 20: Deterministic Repeated QA Result
# ------------------------------------------------------------------------------
def test_20_deterministic_repeated_qa_result(qa_gate, canonical_package):
    report_a = qa_gate.evaluate_package(
        candidate_id="test_repeat",
        editorial_timeline=canonical_package["timeline"],
        sfx_plan=canonical_package["sfx_plan"],
        story_plan=canonical_package["story_plan"],
        audio_metrics=canonical_package["audio_metrics"],
    )
    report_b = qa_gate.evaluate_package(
        candidate_id="test_repeat",
        editorial_timeline=canonical_package["timeline"],
        sfx_plan=canonical_package["sfx_plan"],
        story_plan=canonical_package["story_plan"],
        audio_metrics=canonical_package["audio_metrics"],
    )

    assert report_a.overall_pass == report_b.overall_pass
    assert report_a.production_ready == report_b.production_ready
    assert report_a.qa_fingerprint == report_b.qa_fingerprint
    assert len(report_a.checks) == len(report_b.checks)

    for ca, cb in zip(report_a.checks, report_b.checks):
        assert ca.check_id == cb.check_id
        assert ca.status == cb.status
        assert ca.severity == cb.severity
        assert ca.measured_value == cb.measured_value
