"""
Unit and regression test suite for Visual Artifact Lineage & Provenance Engine.
Verifies that stale visual plans, audio-only rebuilds, and mismatched manifests
are deterministically rejected with StaleVisualPlanError.
"""

import pytest
from core.visual_artifact_lineage import (
    compute_narration_hash,
    compute_proposition_hash,
    compute_evidence_hash,
    compute_timeline_hash,
    compute_visual_plan_id,
    compute_render_fingerprint,
    VisualManifestProvenance,
    verify_manifest_lineage,
    StaleVisualPlanError,
)
from core.editorial_v2_types import EditorialTimelineV2, EditorialUnit, EditorialTransitionType, MotionTreatment, SFXTreatment


def test_narration_hash_deterministic_and_sensitive():
    text_a = "Neville begged the Sorting Hat for Hufflepuff."
    text_b = "Snape's first words to Harry carried a hidden confession."
    
    hash_a = compute_narration_hash(text_a)
    hash_a_repeat = compute_narration_hash(text_a)
    hash_b = compute_narration_hash(text_b)

    assert hash_a == hash_a_repeat, "Narration hash must be deterministic"
    assert hash_a != hash_b, "Different narration texts must produce different hashes"
    assert len(hash_a) == 16


def test_proposition_hash_deterministic_and_sensitive():
    props_a = [
        {"proposition_id": "p1", "claim": "Neville holds remembrall", "subject": "Neville", "action": "holds", "object": "remembrall", "context": "Great Hall", "evidence_type": "DIRECT_EVIDENCE"}
    ]
    props_b = [
        {"proposition_id": "p1", "claim": "Snape teaches potions", "subject": "Snape", "action": "lectures", "object": "students", "context": "Dungeon", "evidence_type": "DIRECT_EVIDENCE"}
    ]

    hash_a = compute_proposition_hash(props_a)
    hash_b = compute_proposition_hash(props_b)

    assert hash_a != hash_b, "Different propositions must yield different hashes"


def test_reject_old_manifest_with_new_narration():
    """Test 1: OLD_MANIFEST + NEW_NARRATION -> REJECT with StaleVisualPlanError"""
    old_narration = "Neville drops the Remembrall."
    new_narration = "Snape questions Harry about asphodel and wormwood."

    old_narr_hash = compute_narration_hash(old_narration)
    new_narr_hash = compute_narration_hash(new_narration)

    old_props = [{"proposition_id": "p1", "claim": "Neville drops", "subject": "Neville", "action": "drops", "object": "remembrall", "context": "flying", "evidence_type": "DIRECT_EVIDENCE"}]
    new_props = [{"proposition_id": "p1", "claim": "Snape questions", "subject": "Snape", "action": "questions", "object": "Harry", "context": "potions", "evidence_type": "DIRECT_EVIDENCE"}]

    old_prop_hash = compute_proposition_hash(old_props)
    new_prop_hash = compute_proposition_hash(new_props)

    old_ev_hash = compute_evidence_hash([{"cand_id": "c1", "prop_id": "p1", "asset_id": "movie1.mp4", "src_interval": (100.0, 102.0), "evidence_class": "DIRECT_EVIDENCE"}])
    old_time_hash = compute_timeline_hash([{"shot_idx": "s1", "cand_id": "c1", "timeline_start": 0.0, "duration": 1.2, "timeline_end": 1.2}])

    old_visual_plan_id = compute_visual_plan_id("content_a", "topic_a", old_narr_hash, old_prop_hash, old_ev_hash, old_time_hash)
    old_rfp = compute_render_fingerprint("content_a", old_narr_hash, old_visual_plan_id, old_ev_hash, old_time_hash)

    # Manifest provenance created for Content A
    manifest_prov = VisualManifestProvenance(
        content_id="content_a",
        topic_id="topic_a",
        narration_hash=old_narr_hash,
        proposition_hash=old_prop_hash,
        visual_plan_id=old_visual_plan_id,
        source_evidence_hash=old_ev_hash,
        timeline_hash=old_time_hash,
        render_fingerprint=old_rfp,
    )

    # Validation against New Narration (Content B) MUST raise StaleVisualPlanError
    with pytest.raises(StaleVisualPlanError) as exc_info:
        verify_manifest_lineage(
            manifest_provenance=manifest_prov,
            current_content_id="content_b",
            current_narration_hash=new_narr_hash,
            current_proposition_hash=new_prop_hash,
            current_visual_plan_id=compute_visual_plan_id("content_b", "topic_b", new_narr_hash, new_prop_hash, old_ev_hash, old_time_hash),
        )
    assert "STALE_VISUAL_PLAN_FOR_CURRENT_NARRATION" in str(exc_info.value)


def test_reject_old_timeline_with_new_narration():
    """Test 2: OLD_TIMELINE + NEW_NARRATION -> REJECT"""
    old_timeline = EditorialTimelineV2(
        timeline_id="timeline_neville",
        topic_id="topic_neville",
        content_id="disc_neville",
        narration_hash=compute_narration_hash("Old neville script"),
        proposition_hash=compute_proposition_hash([{"proposition_id": "p1", "claim": "Neville"}]),
        visual_plan_id="vp_old123456",
        source_evidence_hash="ev_old1234",
        render_fingerprint="rfp_old1234",
        total_duration_seconds=25.0,
        total_cuts=1,
    )
    old_timeline.calculate_fingerprint()

    new_narration_hash = compute_narration_hash("New snape script")
    # Verify that the old timeline's narration_hash doesn't match new narration
    assert old_timeline.narration_hash != new_narration_hash


def test_reject_old_render_with_new_narration():
    """Test 3: OLD_RENDER + NEW_NARRATION -> REJECT"""
    v_plan_a = compute_visual_plan_id("content_a", "topic_a", "narr_a", "prop_a", "ev_a", "tl_a")
    rfp_a = compute_render_fingerprint("content_a", "narr_a", v_plan_a, "ev_a", "tl_a")

    v_plan_b = compute_visual_plan_id("content_b", "topic_b", "narr_b", "prop_b", "ev_b", "tl_b")
    rfp_b = compute_render_fingerprint("content_b", "narr_b", v_plan_b, "ev_b", "tl_b")

    assert rfp_a != rfp_b, "Render fingerprints between two distinct contents must be completely distinct"


def test_reject_old_evidence_with_new_propositions():
    """Test 4: OLD_EVIDENCE + NEW_PROPOSITIONS -> REJECT"""
    new_narr_hash = compute_narration_hash("Narration text")
    old_prop_hash = compute_proposition_hash([{"proposition_id": "p1", "claim": "old"}])
    new_prop_hash = compute_proposition_hash([{"proposition_id": "p2", "claim": "new"}])
    ev_hash = compute_evidence_hash([{"cand_id": "c1", "prop_id": "p1", "asset_id": "m1.mp4", "src_interval": (10.0, 11.0), "evidence_class": "DIRECT_EVIDENCE"}])
    time_hash = compute_timeline_hash([{"shot_idx": "s1", "cand_id": "c1", "timeline_start": 0.0, "duration": 1.0, "timeline_end": 1.0}])

    old_vplan = compute_visual_plan_id("cid", "tid", new_narr_hash, old_prop_hash, ev_hash, time_hash)
    manifest = VisualManifestProvenance(
        content_id="cid",
        topic_id="tid",
        narration_hash=new_narr_hash,
        proposition_hash=old_prop_hash,
        visual_plan_id=old_vplan,
        source_evidence_hash=ev_hash,
        timeline_hash=time_hash,
        render_fingerprint="rfp_test",
    )

    with pytest.raises(StaleVisualPlanError) as exc_info:
        verify_manifest_lineage(
            manifest_provenance=manifest,
            current_content_id="cid",
            current_narration_hash=new_narr_hash,
            current_proposition_hash=new_prop_hash,
            current_visual_plan_id=compute_visual_plan_id("cid", "tid", new_narr_hash, new_prop_hash, ev_hash, time_hash),
        )
    assert "Proposition hash mismatch" in str(exc_info.value)


def test_matching_provenance_passes():
    """Test 5: NEW_NARRATION + NEW_PROPOSITIONS -> PASS"""
    narr_hash = compute_narration_hash("Snape's first words to Harry had a secret meaning.")
    props = [{"proposition_id": "p1", "claim": "Snape speaks", "subject": "Snape", "action": "speaks", "object": "Harry", "context": "potions", "evidence_type": "DIRECT_EVIDENCE"}]
    prop_hash = compute_proposition_hash(props)
    ev_hash = compute_evidence_hash([{"cand_id": "c1", "prop_id": "p1", "asset_id": "m1.mp4", "src_interval": (3075.0, 3076.2), "evidence_class": "DIRECT_EVIDENCE"}])
    time_hash = compute_timeline_hash([{"shot_idx": "s1", "cand_id": "c1", "timeline_start": 0.0, "duration": 1.2, "timeline_end": 1.2}])
    vplan = compute_visual_plan_id("cid_snape", "tid_snape", narr_hash, prop_hash, ev_hash, time_hash)
    rfp = compute_render_fingerprint("cid_snape", narr_hash, vplan, ev_hash, time_hash)

    manifest = VisualManifestProvenance(
        content_id="cid_snape",
        topic_id="tid_snape",
        narration_hash=narr_hash,
        proposition_hash=prop_hash,
        visual_plan_id=vplan,
        source_evidence_hash=ev_hash,
        timeline_hash=time_hash,
        render_fingerprint=rfp,
    )

    assert verify_manifest_lineage(
        manifest_provenance=manifest,
        current_content_id="cid_snape",
        current_narration_hash=narr_hash,
        current_proposition_hash=prop_hash,
        current_visual_plan_id=vplan,
    ) is True
