"""
STORY FORGE — Visual Evidence End-to-End Integration Test Suite
==============================================================
Validates the mandatory py_visual_evidence gate integrated into the Story Forge pipeline:
  SRT (coarse locator) -> MovieEvent (candidate hypothesis) -> py_visual_evidence (physical proof) -> Visual Timeline

Covers:
  - Step 11: Controlled Integration Tests (Fresh Discovery + Fresh Novel Story)
  - Step 12: 10 Comprehensive Negative Integration Tests (All fail closed)
  - Step 6: Multi-Proposition Timeline Independence (No silent reuse or stretching)
  - Step 8 & 9: 9:16 Crop Synchronization & Cryptographic Lineage Invalidation
"""

import os
import json
import pytest
import subprocess
from pathlib import Path
from typing import Dict, List, Any

from config.settings import PROJECT_ROOT
from core.models import MovieSubtitleChunk
from engines.movie_event.models import (
    MovieEvent,
    VisualBeat,
    MovieEventQuery,
    ClaimType,
    VerificationStatus,
    EventVerificationResult,
)
from engines.movie_event.index import MovieEventIndex
from engines.movie_event.storyboard_generator import VisualStoryboardGenerator
from engines.movie_event.retrieval_engine import MovieEventRetrievalEngine
from engines.movie_event.verifier import MovieEventVisualVerifier
from engines.movie_event.hybrid_matcher import (
    SRTTimeWindow,
    CandidateComparisonResult,
    HybridVisualSelectionOutput,
    SRTCoarseLocator,
    HybridVisualSelector,
    MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN,
)
from engines.visual_evidence.storyforge_adapter import (
    StoryForgeVisualEvidenceAdapter,
    StoryForgeEvidenceResult,
)
from core.visual_artifact_lineage import (
    compute_narration_hash,
    compute_proposition_hash,
    compute_evidence_hash,
    compute_timeline_hash,
    compute_visual_plan_id,
    compute_render_fingerprint,
    verify_manifest_lineage,
    VisualManifestProvenance,
    StaleVisualPlanError,
)
from engines.visual_evidence.subject_aware_composition import compute_crop_fingerprint

# Domain-Agnostic Engine Imports
from py_visual_evidence.schema import (
    VisualAssertion,
    EntitySpec,
    StateTransitionSpec,
    CropSpec,
    BoundingBox,
    EvidenceVerdict,
)
from py_visual_evidence.engine import VideoEvidenceEngine
from py_visual_evidence.grounding import DeterministicBenchmarkGrounder

BLIND_CLIPS_DIR = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\py_visual_evidence\test_data\blind_clips")
OUTPUT_DIR = PROJECT_ROOT / "data" / "vault" / "controlled_tests"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def index():
    return MovieEventIndex()


@pytest.fixture
def coarse_locator():
    return SRTCoarseLocator()


@pytest.fixture
def storyboard_gen():
    return VisualStoryboardGenerator()


@pytest.fixture
def adapter():
    return StoryForgeVisualEvidenceAdapter(allow_synthetic_grounding=True)


@pytest.fixture
def hybrid_selector_with_evidence(index, adapter):
    return HybridVisualSelector(
        index=index,
        evidence_adapter=adapter,
        require_video_evidence=True,
        min_improvement_margin=MOVIE_EVENT_MIN_IMPROVEMENT_MARGIN,
    )


# ==============================================================================
# STEP 11 — CONTROLLED INTEGRATION TESTS (FRESH DISCOVERY & NOVEL STORY)
# ==============================================================================

def test_controlled_fresh_discovery_integration(hybrid_selector_with_evidence, storyboard_gen, adapter, tmp_path):
    """
    Step 11 Test 1: Controlled fresh Discovery proposition
    Claim: "Harry Potter catches the Golden Snitch during the Quidditch match."
    Video: m1_snitch_catch.mp4
    Verifies: Candidate retrieved -> py_visual_evidence verifies -> timeline built -> 9:16 render.
    """
    clip_path = BLIND_CLIPS_DIR / "m1_snitch_catch.mp4"
    assert clip_path.exists(), f"Test clip not found: {clip_path}"

    grounder = DeterministicBenchmarkGrounder(strict=True)
    grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.30, y=0.20, w=0.35, h=0.60))
    grounder.register_ground_truth("Golden Snitch", BoundingBox(x=0.45, y=0.35, w=0.10, h=0.10))

    engine = VideoEvidenceEngine(grounder=grounder)
    adapter_custom = StoryForgeVisualEvidenceAdapter(engine=engine, grounder=grounder, allow_synthetic_grounding=True)

    # 1. Obtain proposition & VisualBeat
    beat = VisualBeat(
        beat_id="beat_disc_snitch_01",
        narrative_text="Harry Potter catches the Golden Snitch.",
        required_subjects=["Harry Potter"],
        required_action="catches",
        required_objects=["Golden Snitch"],
        required_location="Quidditch Pitch",
    )

    # 2. Formulate assertion via adapter
    assertion = adapter_custom.build_assertion_from_beat(beat, content_id="disc_snitch_v1")
    assert assertion.subject.name == "Harry Potter"

    # 3. Candidate MovieEvent
    ev = MovieEvent(
        event_id="evt_m1_quidditch_harry_catches_snitch",
        movie_id="hp_movie_1",
        movie_number=1,
        scene_id="s_quidditch",
        start_time=0.0,
        end_time=3.5,
        primary_subject="Harry Potter",
        action="catches the Golden Snitch on broom",
        location="Quidditch Pitch",
        visual_description="Harry catches the Golden Snitch.",
    )

    # 4. Verify candidate footage using adapter
    ev_res: StoryForgeEvidenceResult = adapter_custom.verify_candidate_event(
        event=ev,
        beat_or_prop=assertion,
        override_video_path=clip_path,
    )
    assert ev_res.is_verified is True, f"Evidence verification failed: {ev_res.rejection_reason}"
    assert ev_res.verdict == "PASS"
    assert ev_res.verified_sub_shot is not None

    # 5. Build visual timeline unit
    timeline_unit = {
        "unit_id": "unit_01",
        "cand_id": ev.event_id,
        "clip_path": str(clip_path),
        "timeline_start": 0.0,
        "duration": round(ev_res.source_end - ev_res.source_start, 3),
        "timeline_end": round(ev_res.source_end - ev_res.source_start, 3),
    }

    # 6. Render final 9:16 vertical crop
    out_mp4 = tmp_path / "fresh_discovery_9_16.mp4"
    crop_filter = "crop=450:800:735:0,scale=1080:1920:flags=lanczos,fps=30"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{ev_res.source_start:.3f}",
        "-i", str(clip_path),
        "-t", f"{timeline_unit['duration']:.3f}",
        "-vf", crop_filter,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-an",
        str(out_mp4)
    ]
    subprocess.run(cmd, check=True)
    assert out_mp4.exists()
    assert out_mp4.stat().st_size > 1000

    # 7. Lineage verification
    ev_hash = compute_evidence_hash([{
        "cand_id": ev.event_id,
        "prop_id": beat.beat_id,
        "source_clip": "m1_snitch_catch.mp4",
        "src_interval": (ev_res.source_start, ev_res.source_end),
        "evidence_class": "DIRECT",
        "sub_shot_id": ev_res.verified_sub_shot,
        "engine_version": ev_res.engine_version,
        "crop_fingerprint": ev_res.crop_fingerprint,
        "verdict": ev_res.verdict,
    }])
    assert len(ev_hash) == 16


def test_controlled_fresh_novel_story_integration(hybrid_selector_with_evidence, adapter, tmp_path):
    """
    Step 11 Test 2: Controlled fresh Novel Story proposition
    Claim: "Dudley Dursley falls forward through the vanishing glass into the snake habitat."
    Video: m1_zoo_glass_fall.mp4 (subject-aware 9:16 crop)
    """
    clip_path = BLIND_CLIPS_DIR / "m1_zoo_glass_fall.mp4"
    assert clip_path.exists(), f"Test clip not found: {clip_path}"

    grounder = DeterministicBenchmarkGrounder(strict=True)
    grounder.register_ground_truth("Dudley Dursley", BoundingBox(x=0.08, y=0.25, w=0.20, h=0.60))

    engine = VideoEvidenceEngine(grounder=grounder)
    adapter_custom = StoryForgeVisualEvidenceAdapter(engine=engine, grounder=grounder, allow_synthetic_grounding=True)

    beat = VisualBeat(
        beat_id="beat_ns_dudley_01",
        narrative_text="Dudley Dursley falls forward through the vanishing glass into the snake habitat.",
        required_subjects=["Dudley Dursley"],
        required_action="falls",
        required_location="Reptile House",
    )

    ev = MovieEvent(
        event_id="evt_m1_zoo_dudley_falls",
        movie_id="hp_movie_1",
        movie_number=1,
        scene_id="s_zoo",
        start_time=0.0,
        end_time=3.5,
        primary_subject="Dudley Dursley",
        action="falls forward through the vanishing glass",
        location="Reptile House",
        visual_description="Dudley falls into snake exhibit.",
    )

    crop_window = {"x": 120, "y": 0, "w": 450, "h": 800}
    ev_res = adapter_custom.verify_candidate_event(
        event=ev,
        beat_or_prop=beat,
        crop_window=crop_window,
        override_video_path=clip_path,
    )
    assert ev_res.is_verified is True
    assert ev_res.verdict == "PASS"

    # Lineage check
    prov = VisualManifestProvenance(
        content_id="ns_zoo_dudley_v1",
        topic_id="dudley_zoo_fall",
        narration_hash=compute_narration_hash("Dudley falls into the snake exhibit."),
        proposition_hash=compute_proposition_hash([{"proposition_id": "p1", "claim": "Dudley falls into snake exhibit"}]),
        visual_plan_id="vp_dudley_zoo_001",
        source_evidence_hash=compute_evidence_hash([{"cand_id": ev.event_id, "verdict": "PASS"}]),
        timeline_hash=compute_timeline_hash([{"unit_id": "u1", "cand_id": ev.event_id}]),
        render_fingerprint="rfp_dudley_zoo_001",
    )
    assert verify_manifest_lineage(
        prov,
        current_content_id="ns_zoo_dudley_v1",
        current_narration_hash=prov.narration_hash,
        current_proposition_hash=prov.proposition_hash,
        current_visual_plan_id="vp_dudley_zoo_001",
    ) is True


# ==============================================================================
# STEP 12 — 10 COMPREHENSIVE NEGATIVE INTEGRATION TESTS (FAIL-CLOSED)
# ==============================================================================

def test_negative_01_correct_character_wrong_action(adapter):
    """
    Scenario 1: Correct character + wrong action
    Assertion requires punch; candidate only shows wand standoff.
    Must fail closed with ACTION_ABSENT.
    """
    clip_path = BLIND_CLIPS_DIR / "m3_hermione_wand_standoff_nearmiss.mp4"
    grounder = DeterministicBenchmarkGrounder(strict=True)
    grounder.register_ground_truth("Hermione Granger", BoundingBox(x=0.20, y=0.15, w=0.30, h=0.75))
    grounder.register_ground_truth("Draco Malfoy", BoundingBox(x=0.55, y=0.15, w=0.30, h=0.75))

    engine = VideoEvidenceEngine(grounder=grounder)
    adapter_c = StoryForgeVisualEvidenceAdapter(engine=engine, grounder=grounder, allow_synthetic_grounding=True)

    beat = VisualBeat(
        beat_id="neg_01",
        narrative_text="Hermione Granger punches Draco Malfoy in the face.",
        required_subjects=["Hermione Granger", "Draco Malfoy"],
        required_action="punches",
        required_target="Draco Malfoy",
    )
    ev = MovieEvent(
        event_id="evt_m3_sundial_hermione_punches_malfoy",
        movie_id="hp_movie_3",
        movie_number=3,
        scene_id="s1",
        start_time=0.0,
        end_time=1.90,
        primary_subject="Hermione Granger",
        action="punches Draco Malfoy squarely",
        location="Sundial",
        visual_description="Hermione punches Malfoy.",
    )

    ev_res = adapter_c.verify_candidate_event(ev, beat, override_video_path=clip_path)
    assert ev_res.is_verified is False
    assert ev_res.verdict in [EvidenceVerdict.ACTION_ABSENT.value, EvidenceVerdict.RELATIONSHIP_ABSENT.value]
    assert "strike contact distance" in (ev_res.rejection_reason or "") or "action" in (ev_res.rejection_reason or "").lower()


def test_negative_02_correct_action_wrong_object(adapter):
    """
    Scenario 2: Correct action + wrong object
    Assertion requires chocolate handover; clip has no chocolate grounded.
    Must fail closed with OBJECT_MISMATCH / NO_REQUIRED_ENTITY.
    """
    clip_path = BLIND_CLIPS_DIR / "m3_lupin_chocolate_handover.mp4"
    grounder = DeterministicBenchmarkGrounder(strict=True)
    # Ground Lupin and Harry, but NOT Chocolate
    grounder.register_ground_truth("Lupin", BoundingBox(x=0.10, y=0.15, w=0.25, h=0.75))
    grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.60, y=0.20, w=0.25, h=0.70))

    engine = VideoEvidenceEngine(grounder=grounder)
    adapter_c = StoryForgeVisualEvidenceAdapter(engine=engine, grounder=grounder, allow_synthetic_grounding=True)

    beat = VisualBeat(
        beat_id="neg_02",
        narrative_text="Lupin hands the golden locket to Harry.",
        required_subjects=["Lupin", "Harry Potter"],
        required_action="hands",
        required_objects=["golden locket"],
        required_target="Harry Potter",
    )
    ev = MovieEvent(
        event_id="evt_m3_lupin_chocolate",
        movie_id="hp_movie_3",
        movie_number=3,
        scene_id="s_train",
        start_time=0.0,
        end_time=3.5,
        primary_subject="Lupin",
        action="hands the chocolate",
        location="Hogwarts Express",
        visual_description="Lupin hands chocolate.",
    )

    ev_res = adapter_c.verify_candidate_event(ev, beat, override_video_path=clip_path)
    assert ev_res.is_verified is False
    assert ev_res.verdict in [EvidenceVerdict.NO_REQUIRED_ENTITY.value, EvidenceVerdict.OBJECT_MISMATCH.value]


def test_negative_03_correct_action_wrong_recipient(adapter):
    """
    Scenario 3: Correct action + wrong recipient
    Assertion requires handover to Ron Weasley; clip shows handover to Harry Potter.
    Must fail closed with CHARACTER_MISMATCH or NO_REQUIRED_ENTITY.
    """
    clip_path = BLIND_CLIPS_DIR / "m3_lupin_chocolate_handover.mp4"
    grounder = DeterministicBenchmarkGrounder(strict=True)
    grounder.register_ground_truth("Lupin", BoundingBox(x=0.10, y=0.15, w=0.25, h=0.75))
    grounder.register_ground_truth("Chocolate", BoundingBox(x=0.35, y=0.45, w=0.10, h=0.10))
    # Note: Harry Potter is in clip, but Ron Weasley is NOT registered
    grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.60, y=0.20, w=0.25, h=0.70))

    engine = VideoEvidenceEngine(grounder=grounder)
    adapter_c = StoryForgeVisualEvidenceAdapter(engine=engine, grounder=grounder, allow_synthetic_grounding=True)

    beat = VisualBeat(
        beat_id="neg_03",
        narrative_text="Professor Lupin hands a chocolate bar to Ron Weasley.",
        required_subjects=["Lupin"],
        required_action="hands",
        required_objects=["Chocolate"],
        required_target="Ron Weasley",
    )
    ev = MovieEvent(
        event_id="evt_m3_lupin_chocolate",
        movie_id="hp_movie_3",
        movie_number=3,
        scene_id="s_train",
        start_time=0.0,
        end_time=3.5,
        primary_subject="Lupin",
        action="hands chocolate",
        location="Hogwarts Express",
        visual_description="Lupin hands chocolate.",
    )

    ev_res = adapter_c.verify_candidate_event(ev, beat, override_video_path=clip_path)
    assert ev_res.is_verified is False
    assert ev_res.verdict in [EvidenceVerdict.NO_REQUIRED_ENTITY.value, EvidenceVerdict.CHARACTER_MISMATCH.value]


def test_negative_04_correct_source_scene_unsupported_narration(adapter):
    """
    Scenario 4: Correct source scene + unsupported narration
    Scene is Potions classroom; assertion claims Harry flies on a broom in the classroom.
    Must fail closed with ACTION_ABSENT.
    """
    clip_path = BLIND_CLIPS_DIR / "m1_snitch_catch.mp4"
    grounder = DeterministicBenchmarkGrounder(strict=True)
    grounder.register_ground_truth("Harry Potter", BoundingBox(x=0.30, y=0.20, w=0.40, h=0.60))

    engine = VideoEvidenceEngine(grounder=grounder)
    adapter_c = StoryForgeVisualEvidenceAdapter(engine=engine, grounder=grounder, allow_synthetic_grounding=True)

    beat = VisualBeat(
        beat_id="neg_04",
        narrative_text="Harry Potter drinks polyjuice potion from a vial.",
        required_subjects=["Harry Potter"],
        required_action="drinks",
        required_objects=["polyjuice potion vial"],
    )
    ev = MovieEvent(
        event_id="evt_m1_quidditch",
        movie_id="hp_movie_1",
        movie_number=1,
        scene_id="s_quidditch",
        start_time=0.0,
        end_time=3.0,
        primary_subject="Harry Potter",
        action="catches Golden Snitch",
        location="Quidditch Pitch",
        visual_description="Harry catches the Golden Snitch.",
    )

    ev_res = adapter_c.verify_candidate_event(ev, beat, override_video_path=clip_path)
    assert ev_res.is_verified is False
    assert ev_res.verdict in [EvidenceVerdict.NO_REQUIRED_ENTITY.value, EvidenceVerdict.ACTION_ABSENT.value]


def test_negative_05_candidate_containing_cuts_when_uninterrupted_required(adapter):
    """
    Scenario 5: Candidate containing cuts when the assertion requires a continuous shot
    Clip contains a clear camera cut; assertion specifies require_uninterrupted_shot=True.
    Must fail closed with SHOT_BOUNDARY_CONFLICT.
    """
    clip_path = BLIND_CLIPS_DIR / "m3_shot_boundary_cut.mp4"
    assert clip_path.exists(), f"Test clip not found: {clip_path}"

    grounder = DeterministicBenchmarkGrounder(strict=False)
    engine = VideoEvidenceEngine(grounder=grounder)
    adapter_c = StoryForgeVisualEvidenceAdapter(engine=engine, grounder=grounder, allow_synthetic_grounding=True)

    assertion = VisualAssertion(
        assertion_id="neg_05_continuous",
        source_script_line="An uninterrupted continuous shot of the Hogwarts grounds.",
        subject=EntitySpec(name="Hogwarts", role="subject"),
        action="stands",
        temporal_requirements={"require_uninterrupted_shot": True},
    )

    ev = MovieEvent(
        event_id="evt_m3_shot_cut",
        movie_id="hp_movie_3",
        movie_number=3,
        scene_id="s_pan",
        start_time=0.0,
        end_time=3.5,
        primary_subject="Hogwarts",
        action="pan across grounds",
        location="Hogwarts Grounds",
        visual_description="Pan across Hogwarts grounds.",
    )

    ev_res = adapter_c.verify_candidate_event(ev, assertion, override_video_path=clip_path)
    assert ev_res.is_verified is False
    assert ev_res.verdict == EvidenceVerdict.SHOT_BOUNDARY_CONFLICT.value


def test_negative_06_source_evidence_lost_in_crop(adapter):
    """
    Scenario 6: Source evidence lost in final crop
    Subject is positioned at extreme edge (x=0.02) outside 9:16 safe crop window.
    Must fail closed with CROP_SUBJECT_LOST.
    """
    clip_path = BLIND_CLIPS_DIR / "m3_camera_pan_hogwarts.mp4"
    grounder = DeterministicBenchmarkGrounder(strict=True)
    # Subject placed at extreme left edge
    grounder.register_ground_truth("EdgeSubject", BoundingBox(x=0.01, y=0.30, w=0.10, h=0.40))

    engine = VideoEvidenceEngine(grounder=grounder)
    adapter_c = StoryForgeVisualEvidenceAdapter(engine=engine, grounder=grounder, allow_synthetic_grounding=True)

    assertion = VisualAssertion(
        assertion_id="neg_06_crop_loss",
        source_script_line="Subject visible at the far periphery.",
        subject=EntitySpec(name="EdgeSubject", role="subject"),
        action="visible",
        crop_spec=CropSpec(
            aspect_ratio="9:16",
            safe_margin_horizontal=0.05,
            min_retained_subject_area=0.85,
            allow_letterbox=False,
            allow_scale_adjustment=False,
        ),
    )

    ev = MovieEvent(
        event_id="evt_m3_edge",
        movie_id="hp_movie_3",
        movie_number=3,
        scene_id="s1",
        start_time=0.0,
        end_time=2.5,
        primary_subject="EdgeSubject",
        action="visible",
        location="Hogwarts Grounds",
        visual_description="Edge subject visible.",
    )

    # Force a centered crop window [x=735, w=450 on 1920x800] which completely misses x=0.01
    crop_win = {"x": 735, "y": 0, "w": 450, "h": 800}
    ev_res = adapter_c.verify_candidate_event(ev, assertion, crop_window=crop_win, override_video_path=clip_path)
    assert ev_res.is_verified is False
    assert ev_res.verdict == EvidenceVerdict.CROP_SUBJECT_LOST.value


def test_negative_07_changed_crop_after_verification():
    """
    Scenario 7: Changed crop after evidence verification
    Evidence verified with crop_fp_1; render attempted with crop_fp_2.
    Master render fingerprint changes, rejecting mismatched configuration.
    """
    rfp_original = compute_render_fingerprint(
        content_id="test_07",
        narration_hash="narr_hash_01",
        visual_plan_id="vp_01",
        evidence_hash="ev_hash_01",
        timeline_hash="tl_hash_01",
        crop_fingerprint="crop_735_0_450_800",
    )

    rfp_tampered = compute_render_fingerprint(
        content_id="test_07",
        narration_hash="narr_hash_01",
        visual_plan_id="vp_01",
        evidence_hash="ev_hash_01",
        timeline_hash="tl_hash_01",
        crop_fingerprint="crop_500_0_450_800",  # Changed crop configuration!
    )

    assert rfp_original != rfp_tampered, "Render fingerprint MUST change when crop changes!"


def test_negative_08_changed_proposition_after_verification():
    """
    Scenario 8: Changed proposition after evidence verification
    Evidence was verified for proposition P1, but manifest lineage is checked against modified P2.
    Must fail closed with StaleVisualPlanError.
    """
    p1 = [{"proposition_id": "p1", "claim": "Lupin offers chocolate.", "subject": "Lupin", "action": "offers"}]
    p2 = [{"proposition_id": "p1", "claim": "Lupin casts Patronus shield.", "subject": "Lupin", "action": "casts"}]

    hash_p1 = compute_proposition_hash(p1)
    hash_p2 = compute_proposition_hash(p2)
    assert hash_p1 != hash_p2

    prov = VisualManifestProvenance(
        content_id="content_08",
        topic_id="topic_08",
        narration_hash="narr_08",
        proposition_hash=hash_p1,  # Generated for p1
        visual_plan_id="vp_08",
        source_evidence_hash="ev_08",
        timeline_hash="tl_08",
        render_fingerprint="rfp_08",
    )

    with pytest.raises(StaleVisualPlanError, match="Proposition hash mismatch"):
        verify_manifest_lineage(
            manifest_provenance=prov,
            current_content_id="content_08",
            current_narration_hash="narr_08",
            current_proposition_hash=hash_p2,  # Current proposition has changed!
            current_visual_plan_id="vp_08",
        )


def test_negative_09_stale_evidence_from_previous_render():
    """
    Scenario 9: Stale evidence from previous render
    Narration has changed, but stale visual plan from earlier run is supplied.
    Must fail closed with StaleVisualPlanError.
    """
    narr_v1 = "The movie changes why Lupin gave chocolate."
    narr_v2 = "Rowling reveals the medicinal chemistry of magical chocolate."

    hash_v1 = compute_narration_hash(narr_v1)
    hash_v2 = compute_narration_hash(narr_v2)

    prov = VisualManifestProvenance(
        content_id="content_09",
        topic_id="topic_09",
        narration_hash=hash_v1,
        proposition_hash="prop_09",
        visual_plan_id="vp_09",
        source_evidence_hash="ev_09",
        timeline_hash="tl_09",
        render_fingerprint="rfp_09",
    )

    with pytest.raises(StaleVisualPlanError, match="STALE_VISUAL_PLAN_FOR_CURRENT_NARRATION"):
        verify_manifest_lineage(
            manifest_provenance=prov,
            current_content_id="content_09",
            current_narration_hash=hash_v2,  # Current voiceover is different!
            current_proposition_hash="prop_09",
            current_visual_plan_id="vp_09",
        )


def test_negative_10_movie_event_candidate_no_valid_visual(hybrid_selector_with_evidence):
    """
    Scenario 10: MovieEvent candidate with NO_VALID_VISUAL
    When no candidate satisfies the visual assertion across all search levels:
    Fails closed at Level 5 with NO_VALID_VISUAL and ZERO SRT fallback.
    """
    unfulfillable_beat = VisualBeat(
        beat_id="beat_unfulfillable_10",
        narrative_text="Harry Potter tames a Hungarian Horntail dragon in the Great Hall.",
        required_subjects=["Harry Potter", "Hungarian Horntail"],
        required_action="tames",
        required_location="Great Hall",
    )

    output = hybrid_selector_with_evidence.select_visual_for_beat(
        beat=unfulfillable_beat,
        content_id="neg_10_test",
        inferred_movie=1,
    )

    assert output.status == "NO_VALID_VISUAL"
    assert output.selected_candidate is None
    assert output.comparison.selected_source == "NO_VALID_VISUAL"
    assert output.comparison.fallback_used is False
    assert "Level 5 rejection" in output.comparison.selection_reason
    assert "SRT fallback is strictly prohibited" in (output.comparison.srt_rejection_reason or "")


# ==============================================================================
# STEP 6 — MULTI-PROPOSITION INDEPENDENCE TEST
# ==============================================================================

def test_multi_proposition_timeline_independence(hybrid_selector_with_evidence):
    """
    Step 6: Proves that if P1 passes, P2 passes, and P3 fails:
    P1/P2 footage is NOT silently reused to cover P3.
    """
    b1 = VisualBeat(
        beat_id="p1",
        narrative_text="Snape questions Harry directly in the Potions classroom.",
        required_subjects=["Severus Snape", "Harry Potter"],
        required_action="questions and confronts Harry directly",
    )
    b2 = VisualBeat(
        beat_id="p2",
        narrative_text="Harry Potter chalenges Snape verbally.",
        required_subjects=["Harry Potter", "Severus Snape"],
        required_action="speaks back and challenges Snape",
    )
    b3 = VisualBeat(
        beat_id="p3",
        narrative_text="Darth Vader teleports across galaxies to Mars in an alien spacecraft.",
        required_subjects=["Darth Vader"],
        required_action="teleports across galaxies to Mars",
        required_location="Mars",
    )

    # In index-only pre-filter check
    out1 = hybrid_selector_with_evidence.select_visual_for_beat(b1, inferred_movie=1, require_video_evidence=False)
    out2 = hybrid_selector_with_evidence.select_visual_for_beat(b2, inferred_movie=1, require_video_evidence=False)
    out3 = hybrid_selector_with_evidence.select_visual_for_beat(b3, inferred_movie=1, require_video_evidence=False)

    assert out1.status == "VERIFIED"
    assert out2.status == "VERIFIED"
    assert out3.status == "NO_VALID_VISUAL"

    # Invariant: P3 must NOT borrow P1 or P2 candidates
    assert out3.selected_candidate is None
    p1_cand = out1.selected_candidate["candidate_id"]
    p2_cand = out2.selected_candidate["candidate_id"]
    assert p1_cand != p2_cand
    assert out3.comparison.selected_candidate_id is None
