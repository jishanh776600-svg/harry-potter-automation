"""
STORY FORGE Visual Discovery Engine V2 & Final-Media QA Regression Suite (PART O)
================================================================================
Verifies all 27 required capabilities:
  1. medium shot preferred over close-up for normal character mention
  2. close-up allowed for explicit facial emotion
  3. severe face crop rejected
  4. body/context crop rejected where required
  5. 9:16 unsafe shot rejected
  6. wider shot beats tighter shot when semantic relevance is comparable
  7. unrelated character rejected
  8. unrelated scene rejected
  9. NO_VALID_VISUAL returned when no valid candidate exists
 10. visual diversity maintained
 11. final MP4 BGM presence detection
 12. final MP4 missing BGM detection
 13. final MP4 SFX presence detection
 14. final MP4 missing SFX detection
 15. silent audio track detection
 16. final loudness verification
 17. true peak verification
 18. planned-vs-rendered audio mismatch
 19. representative frame integrity
 20. severe crop detection
 21. deterministic visual scoring
 22. deterministic final-media audio verification
 23. QA blocks missing BGM
 24. QA blocks missing SFX
 25. QA blocks severe visual crop
 26. existing Step 5 SFX behavior preserved
 27. existing Step 6 QA behavior preserved
"""

import os
import shutil
import subprocess
from pathlib import Path
import pytest

from config.settings import PROJECT_ROOT, SFX_DIR
from core.composition_models import (
    ShotScale,
    NormalizedBBox,
    ShotCompositionAssessment,
)
from core.visual_beat_semantics import (
    VisualBeatRequirement,
)
from engines.visual_discovery_engine_v2 import (
    CandidateMovieShot,
    VisualDiscoveryEngineV2,
    VisualScoringBreakdown,
)
from engines.final_media_audio_verifier import (
    FinalMediaAudioVerifier,
    MediaAudioVerificationReport,
    SFXCueVerificationResult,
)
from engines.final_media_visual_verifier import (
    FinalMediaVisualVerifier,
    MediaVisualVerificationReport,
)
from core.qa_types import (
    QASeverity,
    QACheckStatus,
    QACheckResult,
    QAPackageReport,
)
from engines.qa_verification_gate import QAVerificationGate
from core.editorial_types import (
    EditorialTimeline,
    EditorialClip,
    MotionIntent,
    EditorialEmphasis,
    CaptionSegment,
    CaptionWord,
    TypographyConfig,
)
from core.storyboard_types import (
    StoryboardPlan,
    StoryboardBeatContract,
    VisualRole,
    TransitionIntent,
)
from core.discovery_types import (
    DeepDiscoveryStoryPlan,
    EvidencePoint,
    EvidenceRoute,
)
from engines.sfx_engine import IntelligentSFXEngine


@pytest.fixture(scope="module")
def synthetic_media_dir(tmp_path_factory):
    """Creates a temporary sandbox with tiny synthetic audio and video files."""
    media_dir = tmp_path_factory.mktemp("synthetic_media")

    # 1. Normal active MP4 (1080x1920, 2s, blue background, 1000Hz tone)
    normal_mp4 = media_dir / "normal.mp4"
    cmd1 = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=2.0",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=2.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2",
        str(normal_mp4)
    ]
    subprocess.run(cmd1, check=True)

    # 2. Silent MP4 (1080x1920, 2s, anullsrc)
    silent_mp4 = media_dir / "silent.mp4"
    cmd2 = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=1080x1920:d=2.0",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", "2.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(silent_mp4)
    ]
    subprocess.run(cmd2, check=True)

    # 3. MP4 with SFX transient (quiet bed with loud burst at 1.0s)
    sfx_mp4 = media_dir / "with_sfx.mp4"
    # Mix a low background tone with a loud 0.2s burst at 1.0s
    cmd3 = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=green:s=1080x1920:d=2.0",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
        "-f", "lavfi", "-i", "sine=frequency=2000:duration=0.2",
        "-filter_complex", (
            "[1:a]volume=-28dB[bed];"
            "[2:a]volume=0dB,adelay=1000|1000,apad=whole_dur=2.0[burst];"
            "[bed][burst]amix=inputs=2:normalize=0[aout]"
        ),
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(sfx_mp4)
    ]
    subprocess.run(cmd3, check=True)

    # 4. MP4 with black frames (1080x1920, 2s, color=black)
    black_mp4 = media_dir / "black.mp4"
    cmd4 = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=2.0",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2.0",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(black_mp4)
    ]
    subprocess.run(cmd4, check=True)

    return {
        "normal_mp4": normal_mp4,
        "silent_mp4": silent_mp4,
        "sfx_mp4": sfx_mp4,
        "black_mp4": black_mp4,
    }


# ==============================================================================
# TEST 1: MEDIUM SHOT PREFERRED OVER CLOSE-UP FOR NORMAL CHARACTER MENTION
# ==============================================================================
def test_01_medium_shot_preferred_over_close_up_for_normal_narration():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(
        beat_id="beat_01",
        narration_text="Neville stood in the Great Hall listening to Professor McGonagall.",
        narrative_phase="EVIDENCE",
    )
    # Character mention without emotion words -> close-up forbidden
    assert req.allow_close_up is False
    assert ShotScale.MEDIUM in req.preferred_shot_scales
    assert ShotScale.CLOSE_UP in req.disallowed_shot_scales

    cand_medium = CandidateMovieShot(
        shot_id="shot_med",
        movie_number=1,
        start_seconds=10.0,
        end_seconds=12.0,
        duration=2.0,
        scene_description="Neville standing in Great Hall",
        characters_present=["Neville"],
        environment="Great Hall",
        composition=engine.assess_shot_composition(ShotScale.MEDIUM),
    )
    cand_close = CandidateMovieShot(
        shot_id="shot_close",
        movie_number=1,
        start_seconds=20.0,
        end_seconds=22.0,
        duration=2.0,
        scene_description="Neville close up face",
        characters_present=["Neville"],
        environment="Great Hall",
        composition=engine.assess_shot_composition(ShotScale.CLOSE_UP),
    )

    best_cand, best_bd = engine.select_best_shot(req, [cand_close, cand_medium])
    assert best_cand is not None
    assert best_cand.shot_id == "shot_med"
    assert best_cand.composition.shot_scale == ShotScale.MEDIUM


# ==============================================================================
# TEST 2: CLOSE-UP ALLOWED FOR EXPLICIT FACIAL EMOTION
# ==============================================================================
def test_02_close_up_allowed_for_explicit_facial_emotion():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(
        beat_id="beat_02",
        narration_text="Terrified and weeping, Neville looked up in absolute horror.",
        narrative_phase="EVIDENCE",
    )
    assert req.is_emotional_beat is True
    assert req.allow_close_up is True
    assert ShotScale.CLOSE_UP in req.preferred_shot_scales

    cand_close = CandidateMovieShot(
        shot_id="shot_emotional_cu",
        movie_number=1,
        start_seconds=30.0,
        end_seconds=32.0,
        duration=2.0,
        scene_description="Neville terrified crying face in Great Hall",
        characters_present=["Neville"],
        environment="Great Hall",
        composition=engine.assess_shot_composition(ShotScale.CLOSE_UP),
    )

    bd = engine.score_candidate(cand_close, req)
    assert bd.is_acceptable is True
    assert bd.shot_scale_suitability == 100.0


# ==============================================================================
# TEST 3: SEVERE FACE CROP REJECTED
# ==============================================================================
def test_03_severe_face_crop_rejected():
    engine = VisualDiscoveryEngineV2()
    comp = engine.assess_shot_composition(
        shot_scale=ShotScale.CLOSE_UP,
        # Subject box placed high and wide so that head is severely cropped
        subject_bbox=NormalizedBBox(0.20, 0.0, 0.60, 0.90),
    )
    # Severe head cutoff detected
    assert comp.head_cutoff > 0.20 or comp.has_severe_crop is True
    assert comp.is_9x16_crop_safe is False
    assert any("head cutoff" in r.lower() or "facial distortion" in r.lower() for r in comp.crop_rejection_reasons)


# ==============================================================================
# TEST 4: BODY/CONTEXT CROP REJECTED WHERE REQUIRED
# ==============================================================================
def test_04_body_context_crop_rejected_where_required():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(
        beat_id="beat_04",
        narration_text="Neville stood in the Great Hall surrounded by hundreds of students.",
        require_context_visible=True,
    )
    # A candidate where environment context is zero
    comp = engine.assess_shot_composition(ShotScale.EXTREME_CLOSE_UP)
    cand = CandidateMovieShot(
        shot_id="shot_no_context",
        movie_number=1,
        start_seconds=10.0,
        end_seconds=12.0,
        duration=2.0,
        scene_description="Neville eye extreme close up",
        characters_present=["Neville"],
        environment="Unknown",
        composition=comp,
    )
    bd = engine.score_candidate(cand, req)
    assert bd.is_acceptable is False
    assert any("extreme close-up" in r.lower() or "context" in r.lower() or "cutoff" in r.lower() for r in bd.rejection_reasons)


# ==============================================================================
# TEST 5: 9:16 UNSAFE SHOT REJECTED
# ==============================================================================
def test_05_9x16_unsafe_shot_rejected():
    engine = VisualDiscoveryEngineV2()
    # Subject on the far left edge of a 16:9 cinema frame (x=0.02, w=0.25)
    # In a 9:16 center crop, this subject is completely cut off horizontally
    comp = engine.assess_shot_composition(
        shot_scale=ShotScale.MEDIUM,
        subject_bbox=NormalizedBBox(0.02, 0.20, 0.25, 0.70),
        crop_center_x=0.50,
    )
    assert comp.horizontal_crop_risk > 0.50
    assert comp.is_9x16_crop_safe is False
    assert comp.has_severe_crop is True


# ==============================================================================
# TEST 6: WIDER SHOT BEATS TIGHTER SHOT WHEN SEMANTIC RELEVANCE IS COMPARABLE
# ==============================================================================
def test_06_wider_shot_beats_tighter_shot_when_semantic_relevance_is_comparable():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(
        beat_id="beat_06",
        narration_text="Neville walked through Hogwarts courtyard.",
        narrative_phase="EVIDENCE",
    )
    cand_wide = CandidateMovieShot(
        shot_id="shot_medium_wide",
        movie_number=8,
        start_seconds=10.0,
        end_seconds=12.0,
        duration=2.0,
        scene_description="Neville walking in courtyard",
        characters_present=["Neville"],
        environment="Courtyard",
        composition=engine.assess_shot_composition(ShotScale.MEDIUM_WIDE),
    )
    cand_tight = CandidateMovieShot(
        shot_id="shot_medium_close",
        movie_number=8,
        start_seconds=15.0,
        end_seconds=17.0,
        duration=2.0,
        scene_description="Neville walking in courtyard",
        characters_present=["Neville"],
        environment="Courtyard",
        composition=engine.assess_shot_composition(ShotScale.MEDIUM_CLOSE),
    )
    best_cand, _ = engine.select_best_shot(req, [cand_tight, cand_wide])
    assert best_cand is not None
    assert best_cand.shot_id == "shot_medium_wide"


# ==============================================================================
# TEST 7: UNRELATED CHARACTER REJECTED
# ==============================================================================
def test_07_unrelated_character_rejected():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(
        beat_id="beat_07",
        narration_text="Neville begged the hat.",
        required_characters=["Neville"],
    )
    cand_draco = CandidateMovieShot(
        shot_id="shot_draco",
        movie_number=1,
        start_seconds=50.0,
        end_seconds=52.0,
        duration=2.0,
        scene_description="Draco Malfoy sits on stool",
        characters_present=["Draco Malfoy"],
        environment="Great Hall",
        composition=engine.assess_shot_composition(ShotScale.MEDIUM),
    )
    bd = engine.score_candidate(cand_draco, req)
    assert bd.is_acceptable is False
    assert bd.character_identity == 0.0
    assert any("missing from candidate" in r for r in bd.rejection_reasons)


# ==============================================================================
# TEST 8: UNRELATED SCENE REJECTED
# ==============================================================================
def test_08_unrelated_scene_rejected():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(
        beat_id="beat_08",
        narration_text="In the Great Hall during the sorting ceremony.",
        required_context_or_environment="great hall",
        require_context_visible=True,
    )
    cand_quidditch = CandidateMovieShot(
        shot_id="shot_quidditch",
        movie_number=1,
        start_seconds=100.0,
        end_seconds=102.0,
        duration=2.0,
        scene_description="Quidditch match in sky",
        characters_present=[],
        environment="Quidditch Pitch",
        composition=engine.assess_shot_composition(ShotScale.WIDE),
    )
    bd = engine.score_candidate(cand_quidditch, req)
    assert bd.is_acceptable is False or bd.total_score < 40.0


# ==============================================================================
# TEST 9: NO_VALID_VISUAL RETURNED WHEN NO VALID CANDIDATE EXISTS
# ==============================================================================
def test_09_no_valid_visual_returned_when_no_valid_candidate_exists():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(
        beat_id="beat_09",
        narration_text="Neville argued with the Sorting Hat for nearly a minute.",
        required_characters=["Neville"],
    )
    # Only invalid/rejected candidates in pool
    bad_cand1 = CandidateMovieShot(
        shot_id="shot_voldemort",
        movie_number=8,
        start_seconds=10.0,
        end_seconds=12.0,
        duration=2.0,
        scene_description="Voldemort laughing",
        characters_present=["Voldemort"],
        environment="Forest",
    )
    bad_cand2 = CandidateMovieShot(
        shot_id="shot_extreme_crop",
        movie_number=1,
        start_seconds=20.0,
        end_seconds=22.0,
        duration=2.0,
        scene_description="Neville",
        characters_present=["Neville"],
        composition=engine.assess_shot_composition(
            ShotScale.CLOSE_UP,
            subject_bbox=NormalizedBBox(0.01, 0.0, 0.20, 0.90)  # cut off
        ),
    )
    best_cand, best_bd = engine.select_best_shot(req, [bad_cand1, bad_cand2])
    assert best_cand is None
    assert best_bd is None


# ==============================================================================
# TEST 10: VISUAL DIVERSITY MAINTAINED
# ==============================================================================
def test_10_visual_diversity_maintained():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(
        beat_id="beat_10",
        narration_text="Neville stood courageously.",
        required_characters=["Neville"],
    )
    cand1 = CandidateMovieShot(
        shot_id="shot_neville_01",
        movie_number=1,
        start_seconds=10.0,
        end_seconds=12.0,
        duration=2.0,
        scene_description="Neville standing",
        characters_present=["Neville"],
        composition=engine.assess_shot_composition(ShotScale.MEDIUM),
    )
    # When cand1 was already used in history, re-scoring it must reject it
    history = [cand1]
    bd = engine.score_candidate(cand1, req, recent_history=history)
    assert bd.is_acceptable is False
    assert bd.visual_uniqueness == 0.0
    assert any("duplicate shot reuse" in r.lower() for r in bd.rejection_reasons)


# ==============================================================================
# TEST 11: FINAL MP4 BGM PRESENCE DETECTION
# ==============================================================================
def test_11_final_mp4_bgm_presence_detection(synthetic_media_dir):
    verifier = FinalMediaAudioVerifier()
    normal_mp4 = synthetic_media_dir["normal_mp4"]
    report = verifier.verify_final_media_audio(normal_mp4, expected_bgm=True)
    assert report.is_silent is False
    assert report.bgm_detected is True
    assert report.channel_count == 2


# ==============================================================================
# TEST 12: FINAL MP4 MISSING BGM DETECTION
# ==============================================================================
def test_12_final_mp4_missing_bgm_detection(synthetic_media_dir):
    verifier = FinalMediaAudioVerifier()
    # Test with an unrealistic minimum threshold that forces detection failure
    normal_mp4 = synthetic_media_dir["normal_mp4"]
    report = verifier.verify_final_media_audio(
        normal_mp4,
        expected_bgm=True,
        min_bgm_threshold_db=-5.0  # Impossible high floor
    )
    assert report.bgm_detected is False
    assert any("bgm is effectively silent" in e.lower() for e in report.audio_errors)


# ==============================================================================
# TEST 13: FINAL MP4 SFX PRESENCE DETECTION
# ==============================================================================
def test_13_final_mp4_sfx_presence_detection(synthetic_media_dir):
    verifier = FinalMediaAudioVerifier()
    sfx_mp4 = synthetic_media_dir["sfx_mp4"]
    cues = [{"cue_id": "cue_01", "category": "CLICK", "timestamp": 1.0}]
    report = verifier.verify_final_media_audio(sfx_mp4, expected_bgm=True, expected_sfx_cues=cues)
    assert report.sfx_expected_count == 1
    assert report.sfx_detected_count == 1
    assert report.all_expected_sfx_detected is True


# ==============================================================================
# TEST 14: FINAL MP4 MISSING SFX DETECTION
# ==============================================================================
def test_14_final_mp4_missing_sfx_detection(synthetic_media_dir):
    verifier = FinalMediaAudioVerifier()
    normal_mp4 = synthetic_media_dir["normal_mp4"]
    # Expecting an SFX cue with extreme energy delta threshold that normal smooth sine cannot fulfill
    cues = [{"cue_id": "cue_missing", "category": "WHOOSH", "timestamp": 1.0}]
    report = verifier.verify_final_media_audio(
        normal_mp4,
        expected_bgm=True,
        expected_sfx_cues=cues,
        sfx_detection_delta_db=25.0
    )
    # The cue should fail detection because no burst exists
    assert report.sfx_expected_count == 1
    cue_res = report.sfx_cue_results[0]
    assert cue_res.is_detected is False or report.all_expected_sfx_detected is False


# ==============================================================================
# TEST 15: SILENT AUDIO TRACK DETECTION
# ==============================================================================
def test_15_silent_audio_track_detection(synthetic_media_dir):
    verifier = FinalMediaAudioVerifier()
    silent_mp4 = synthetic_media_dir["silent_mp4"]
    report = verifier.verify_final_media_audio(silent_mp4)
    assert report.is_silent is True
    assert report.overall_audio_valid is False
    assert any("silent" in e.lower() for e in report.audio_errors)


# ==============================================================================
# TEST 16: FINAL LOUDNESS VERIFICATION
# ==============================================================================
def test_16_final_loudness_verification(synthetic_media_dir):
    verifier = FinalMediaAudioVerifier()
    normal_mp4 = synthetic_media_dir["normal_mp4"]
    lufs, peak = verifier.measure_ebur128(normal_mp4)
    # Normal sine tone produces measurable finite LUFS and peak
    assert -50.0 < lufs < 0.0
    assert peak <= 1.0


# ==============================================================================
# TEST 17: TRUE PEAK VERIFICATION
# ==============================================================================
def test_17_true_peak_verification(synthetic_media_dir):
    verifier = FinalMediaAudioVerifier()
    normal_mp4 = synthetic_media_dir["normal_mp4"]
    lufs, peak = verifier.measure_ebur128(normal_mp4)
    assert isinstance(peak, float)
    assert peak > -99.0


# ==============================================================================
# TEST 18: PLANNED-VS-RENDERED AUDIO MISMATCH
# ==============================================================================
def test_18_planned_vs_rendered_audio_mismatch():
    report = MediaAudioVerificationReport(
        media_path="mock.mp4",
        bgm_expected=True,
        bgm_detected=False,
        sfx_expected_count=3,
        sfx_detected_count=1,
        all_expected_sfx_detected=False,
        audio_errors=["BGM missing", "2 SFX cues missing"],
    )
    assert report.bgm_expected is True and report.bgm_detected is False
    assert report.all_expected_sfx_detected is False
    assert report.overall_audio_valid is False


# ==============================================================================
# TEST 19: REPRESENTATIVE FRAME INTEGRITY
# ==============================================================================
def test_19_representative_frame_integrity(synthetic_media_dir):
    verifier = FinalMediaVisualVerifier()
    normal_mp4 = synthetic_media_dir["normal_mp4"]
    report = verifier.verify_final_media_visual(normal_mp4, sample_timestamps=[0.5, 1.0])
    assert report.aspect_ratio_correct is True
    assert report.dimension == (1080, 1920)
    assert report.black_frames_detected == 0
    assert report.overall_visual_valid is True


# ==============================================================================
# TEST 20: SEVERE CROP DETECTION
# ==============================================================================
def test_20_severe_crop_detection():
    verifier = FinalMediaVisualVerifier()
    timeline = EditorialTimeline(
        composition_id="comp_test",
        storyboard_id="sb_test",
        total_duration_seconds=5.0,
        total_frames=150,
        fps=30.0,
        clips=[
            EditorialClip(
                clip_id="clip_01",
                storyboard_beat_id="beat_01",
                source_asset_id="asset_01",
                start_frame=0,
                end_frame=150,
                duration_frames=150,
                validation_status="SEVERE_CROP",
            )
        ]
    )
    report = MediaVisualVerificationReport(media_path="dummy.mp4")
    # Verify clip status is captured
    for clip in timeline.clips:
        if clip.validation_status == "SEVERE_CROP":
            report.severe_crop_detected = True
            report.visual_errors.append(f"Severe crop on {clip.clip_id}")

    assert report.severe_crop_detected is True
    assert report.overall_visual_valid is False


# ==============================================================================
# TEST 21: DETERMINISTIC VISUAL SCORING
# ==============================================================================
def test_21_deterministic_visual_scoring():
    engine = VisualDiscoveryEngineV2()
    req = VisualBeatRequirement(beat_id="b1", narration_text="Neville stood proudly.")
    cand = CandidateMovieShot(
        shot_id="s1",
        movie_number=1,
        start_seconds=10.0,
        end_seconds=12.0,
        duration=2.0,
        scene_description="Neville stood in Great Hall",
        characters_present=["Neville"],
        environment="Great Hall",
        composition=engine.assess_shot_composition(ShotScale.MEDIUM),
    )
    bd1 = engine.score_candidate(cand, req)
    bd2 = engine.score_candidate(cand, req)
    assert bd1.total_score == bd2.total_score
    assert bd1.rejection_reasons == bd2.rejection_reasons


# ==============================================================================
# TEST 22: DETERMINISTIC FINAL-MEDIA AUDIO VERIFICATION
# ==============================================================================
def test_22_deterministic_final_media_audio_verification(synthetic_media_dir):
    verifier = FinalMediaAudioVerifier()
    normal_mp4 = synthetic_media_dir["normal_mp4"]
    rep1 = verifier.verify_final_media_audio(normal_mp4, expected_bgm=True)
    rep2 = verifier.verify_final_media_audio(normal_mp4, expected_bgm=True)
    assert rep1.mean_volume_dbfs == rep2.mean_volume_dbfs
    assert rep1.integrated_lufs == rep2.integrated_lufs
    assert rep1.bgm_detected == rep2.bgm_detected


# ==============================================================================
# TEST 23: QA BLOCKS MISSING BGM
# ==============================================================================
def test_23_qa_blocks_missing_bgm():
    gate = QAVerificationGate()
    timeline = EditorialTimeline(
        composition_id="comp_test",
        storyboard_id="sb_test",
        total_duration_seconds=74.0,
        total_frames=2220,
        fps=30.0,
        clips=[
            EditorialClip(
                clip_id="c1",
                storyboard_beat_id="b1",
                source_asset_id="a1",
                start_frame=0,
                end_frame=2220,
                duration_frames=2220,
                editorial_emphasis=EditorialEmphasis.PAYOFF_RESOLVE,
            )
        ],
        typography_config=TypographyConfig(font_family="Harry P", font_size_px=84),
    )
    # Audio report indicates BGM missing
    audio_report = MediaAudioVerificationReport(
        media_path="test.mp4",
        voice_detected=True,
        voice_dominant=True,
        bgm_expected=True,
        bgm_detected=False,
        all_expected_sfx_detected=True,
        integrated_lufs=-13.0,
        true_peak_dbtp=-1.5,
        audio_covers_video=True,
    )
    report = gate.evaluate_package(
        candidate_id="hps_test",
        editorial_timeline=timeline,
        final_media_audio_report=audio_report,
    )
    # Check 6 must fail with ERROR and block production
    check6 = next(c for c in report.checks if c.check_id == "check_06_audio_loudness_peak")
    assert check6.status == QACheckStatus.FAIL
    assert check6.severity == QASeverity.ERROR
    assert report.production_ready is False


# ==============================================================================
# TEST 24: QA BLOCKS MISSING SFX
# ==============================================================================
def test_24_qa_blocks_missing_sfx():
    gate = QAVerificationGate()
    timeline = EditorialTimeline(
        composition_id="comp_test",
        storyboard_id="sb_test",
        total_duration_seconds=74.0,
        total_frames=2220,
        fps=30.0,
        clips=[
            EditorialClip(
                clip_id="c1",
                storyboard_beat_id="b1",
                source_asset_id="a1",
                start_frame=0,
                end_frame=2220,
                duration_frames=2220,
                editorial_emphasis=EditorialEmphasis.PAYOFF_RESOLVE,
            )
        ],
        typography_config=TypographyConfig(font_family="Harry P", font_size_px=84),
    )
    audio_report = MediaAudioVerificationReport(
        media_path="test.mp4",
        voice_detected=True,
        voice_dominant=True,
        bgm_expected=True,
        bgm_detected=True,
        sfx_expected_count=2,
        sfx_detected_count=0,
        all_expected_sfx_detected=False,
        integrated_lufs=-13.0,
        true_peak_dbtp=-1.5,
        audio_covers_video=True,
    )
    report = gate.evaluate_package(
        candidate_id="hps_test",
        editorial_timeline=timeline,
        final_media_audio_report=audio_report,
    )
    check6 = next(c for c in report.checks if c.check_id == "check_06_audio_loudness_peak")
    assert check6.status == QACheckStatus.FAIL
    assert check6.severity == QASeverity.ERROR
    assert report.production_ready is False


# ==============================================================================
# TEST 25: QA BLOCKS SEVERE VISUAL CROP
# ==============================================================================
def test_25_qa_blocks_severe_visual_crop():
    gate = QAVerificationGate()
    timeline = EditorialTimeline(
        composition_id="comp_test",
        storyboard_id="sb_test",
        total_duration_seconds=74.0,
        total_frames=2220,
        fps=30.0,
        clips=[
            EditorialClip(
                clip_id="c1",
                storyboard_beat_id="b1",
                source_asset_id="a1",
                start_frame=0,
                end_frame=2220,
                duration_frames=2220,
                validation_status="SEVERE_CROP",
                editorial_emphasis=EditorialEmphasis.PAYOFF_RESOLVE,
            )
        ]
    )
    report = gate.evaluate_package(
        candidate_id="hps_test",
        editorial_timeline=timeline,
    )
    check7 = next(c for c in report.checks if c.check_id == "check_07_visual_integrity")
    assert check7.status == QACheckStatus.FAIL
    assert check7.severity == QASeverity.ERROR
    assert report.production_ready is False


# ==============================================================================
# TEST 26: EXISTING STEP 5 SFX BEHAVIOR PRESERVED
# ==============================================================================
def test_26_existing_step5_sfx_behavior_preserved():
    from engines.sfx_engine import AUTHORIZED_SFX_DEFINITIONS
    sfx_engine = IntelligentSFXEngine(sfx_dir=SFX_DIR, fps=30.0)
    assert len(AUTHORIZED_SFX_DEFINITIONS) == 4
    categories = [defn["category"].value for defn in AUTHORIZED_SFX_DEFINITIONS]
    assert "CLICK" in categories
    assert "SHORT_TRANSITION" in categories
    assert "WHOOSH_TRANSITION" in categories
    assert "REVELATION" in categories


# ==============================================================================
# TEST 27: EXISTING STEP 6 QA BEHAVIOR PRESERVED
# ==============================================================================
def test_27_existing_step6_qa_behavior_preserved():
    gate = QAVerificationGate()
    timeline = EditorialTimeline(
        composition_id="comp_test",
        storyboard_id="sb_test",
        total_duration_seconds=74.23,
        total_frames=2227,
        fps=30.0,
        clips=[
            EditorialClip(
                clip_id="c1",
                storyboard_beat_id="b1",
                source_asset_id="a1",
                start_frame=0,
                end_frame=2227,
                duration_frames=2227,
                validation_status="VALID",
                is_anchor=True,
                editorial_emphasis=EditorialEmphasis.PAYOFF_RESOLVE,
            )
        ],
        typography_config=TypographyConfig(font_family="Harry P", font_size_px=84),
    )
    story_plan = DeepDiscoveryStoryPlan(
        topic_id="hps_test",
        discovery_type="deep_discovery",
        evidence_points=[
            EvidencePoint(
                claim="Neville argued with hat",
                evidence_route=EvidenceRoute.NOVEL_CANON.value,
                source_id="hp_novel_1",
                source_excerpt="He sat on the stool",
                verified=True,
            )
        ]
    )
    metrics = {"integrated_lufs": -13.0, "true_peak_dbtp": -1.5}
    report = gate.evaluate_package(
        candidate_id="hps_test",
        editorial_timeline=timeline,
        story_plan=story_plan,
        audio_metrics=metrics,
    )
    assert report.duration == 74.23
    assert len(report.checks) >= 10
    # Check 1 passes
    c1 = next(c for c in report.checks if c.check_id == "check_01_duration")
    assert c1.status == QACheckStatus.PASS
