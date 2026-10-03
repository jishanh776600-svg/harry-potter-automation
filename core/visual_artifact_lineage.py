"""
STORY FORGE — Visual Artifact Lineage & Provenance Engine
================================================================================
Guarantees cryptographic coupling between:
  Content / Topic ID
  -> Narration Hash
  -> Visual Proposition Hash
  -> Source Evidence Hash
  -> Timeline Hash
  -> VISUAL_PLAN_ID
  -> Master Render Fingerprint

Eliminates the cross-short visual reuse bug by enforcing:
  1. Deterministic VISUAL_PLAN_ID.
  2. Pre-render manifest provenance verification.
  3. Strict rejection of audio-only rebuilds on stale visual plans.
  4. Fail-closed StaleVisualPlanError on any identity or hash mismatch.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

logger = logging.getLogger("VisualArtifactLineage")


class StaleVisualPlanError(ValueError):
    """Raised when an existing visual plan, manifest, or timeline does not match current narration/propositions."""
    pass


def normalize_text_for_hash(text: str) -> str:
    """Normalizes text for deterministic cryptographic hashing."""
    if not text:
        return ""
    # Strip whitespace, lowercase, normalize spaces
    cleaned = re.sub(r"\s+", " ", str(text).strip().lower())
    # Remove standard punctuation for phonetic stability
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return cleaned


def compute_narration_hash(narration_text: str) -> str:
    """Computes a deterministic 16-character SHA-256 hash of spoken narration text."""
    norm = normalize_text_for_hash(narration_text)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def compute_proposition_hash(propositions: List[Any]) -> str:
    """
    Computes a deterministic 16-character SHA-256 hash of ordered visual propositions.
    Handles VisualProposition dataclasses or dicts.
    """
    canonical_items = []
    for p in propositions:
        if hasattr(p, "to_dict"):
            d = p.to_dict()
        elif isinstance(p, dict):
            d = p
        else:
            d = getattr(p, "__dict__", {})

        pid = str(d.get("proposition_id", ""))
        claim = normalize_text_for_hash(d.get("claim", ""))
        subj = normalize_text_for_hash(d.get("subject", ""))
        act = normalize_text_for_hash(d.get("action", ""))
        obj = normalize_text_for_hash(d.get("object", ""))
        ctx = normalize_text_for_hash(d.get("context", ""))
        ev_type = str(d.get("evidence_type", d.get("required_relationship", ""))).upper()
        canonical_items.append(f"{pid}|{claim}|{subj}|{act}|{obj}|{ctx}|{ev_type}")

    raw = ";".join(canonical_items)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_evidence_hash(evidence_records: List[Dict[str, Any]]) -> str:
    """Computes a deterministic 16-character SHA-256 hash of verified evidence records."""
    canonical_items = []
    for r in evidence_records:
        cid = str(r.get("cand_id", r.get("candidate_id", "")))
        pid = str(r.get("prop_id", r.get("proposition_id", "")))
        clip = str(r.get("source_clip", r.get("asset_id", "")))
        s_int = r.get("src_interval", (0.0, 0.0))
        st = f"{float(s_int[0]):.3f}-{float(s_int[1]):.3f}"
        ev_class = str(r.get("evidence_class", r.get("verdict", ""))).upper()
        sub_shot = str(r.get("sub_shot_id", r.get("verified_sub_shot", "")))
        engine_v = str(r.get("engine_version", r.get("engine_id", "")))
        crop_fp = str(r.get("crop_fingerprint", ""))
        extra = f"|{sub_shot}|{engine_v}|{crop_fp}" if (sub_shot or engine_v or crop_fp) else ""
        canonical_items.append(f"{cid}|{pid}|{clip}|{st}|{ev_class}{extra}")

    raw = ";".join(canonical_items)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_timeline_hash(units: List[Dict[str, Any]]) -> str:
    """Computes a deterministic 16-character SHA-256 hash of editorial timeline units."""
    canonical_items = []
    for u in units:
        uid = str(u.get("shot_idx", u.get("id", u.get("unit_id", ""))))
        cid = str(u.get("cand_id", ""))
        t_start = f"{float(u.get('timeline_start', u.get('start_time', 0.0))):.3f}"
        dur = f"{float(u.get('duration', u.get('duration_seconds', 0.0))):.3f}"
        t_end = f"{float(u.get('timeline_end', u.get('end_time', 0.0))):.3f}"
        canonical_items.append(f"{uid}|{cid}|{t_start}|{dur}|{t_end}")

    raw = ";".join(canonical_items)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_visual_plan_id(
    content_id: str,
    topic_id: str,
    narration_hash: str,
    proposition_hash: str,
    evidence_hash: str,
    timeline_hash: str,
) -> str:
    """
    Computes a deterministic, unique VISUAL_PLAN_ID.
    Guaranteed to change if any topic, narration, proposition, evidence, or timeline changes.
    """
    raw = f"{content_id}:{topic_id}:{narration_hash}:{proposition_hash}:{evidence_hash}:{timeline_hash}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"vp_{digest}"


def compute_bgm_fingerprint(
    bgm_path: Union[str, Path],
    volume_db: float = -18.0,
    speed_multiplier: float = 1.0,
) -> str:
    """Computes a deterministic cryptographic fingerprint of the BGM track and ducking configuration."""
    bp = Path(bgm_path)
    file_stat = f"{bp.name}_{bp.stat().st_size}" if bp.exists() else str(bp.name)
    raw = f"bgm:{file_stat}:vol={volume_db:.2f}dB:spd={speed_multiplier:.3f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def compute_render_fingerprint(
    content_id: str,
    narration_hash: str,
    visual_plan_id: str,
    evidence_hash: str,
    timeline_hash: str,
    bgm_fingerprint: str = "",
    voice_fingerprint: str = "",
    editorial_fingerprint: str = "",
    subtitle_fingerprint: str = "",
    crop_fingerprint: str = "",
) -> str:
    """
    Computes master render fingerprint binding video timeline, audio stems, subtitles, and crop composition.
    Prevents mismatched audio, video, subtitles, or framing from ever being considered a valid render.
    """
    raw = (
        f"{content_id}:{narration_hash}:{visual_plan_id}:{evidence_hash}:{timeline_hash}:"
        f"{bgm_fingerprint}:{voice_fingerprint}:{editorial_fingerprint}:"
        f"{subtitle_fingerprint}:{crop_fingerprint}"
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"rfp_{digest}"


@dataclass
class VisualManifestProvenance:
    """Strongly-typed metadata container embedded in visual manifests and timeline artifacts."""
    content_id: str
    topic_id: str
    narration_hash: str
    proposition_hash: str
    visual_plan_id: str
    source_evidence_hash: str
    timeline_hash: str
    render_fingerprint: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualManifestProvenance":
        return cls(
            content_id=str(data.get("content_id", "")),
            topic_id=str(data.get("topic_id", "")),
            narration_hash=str(data.get("narration_hash", "")),
            proposition_hash=str(data.get("proposition_hash", "")),
            visual_plan_id=str(data.get("visual_plan_id", "")),
            source_evidence_hash=str(data.get("source_evidence_hash", "")),
            timeline_hash=str(data.get("timeline_hash", "")),
            render_fingerprint=str(data.get("render_fingerprint", "")),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
        )


def verify_manifest_lineage(
    manifest_provenance: Union[Dict[str, Any], VisualManifestProvenance],
    current_content_id: str,
    current_narration_hash: str,
    current_proposition_hash: str,
    current_visual_plan_id: str,
) -> bool:
    """
    Hard production assertion gate executed prior to video rendering.
    Verifies that the visual manifest genuinely belongs to the current narration and propositions.
    Fails closed with StaleVisualPlanError on any mismatch.
    """
    if isinstance(manifest_provenance, VisualManifestProvenance):
        prov = manifest_provenance
    else:
        prov = VisualManifestProvenance.from_dict(manifest_provenance)

    errors = []
    if prov.content_id != current_content_id:
        errors.append(f"Content ID mismatch: manifest '{prov.content_id}' != current '{current_content_id}'")

    if prov.narration_hash != current_narration_hash:
        errors.append(
            f"STALE_VISUAL_PLAN_FOR_CURRENT_NARRATION: Narration hash mismatch "
            f"(manifest '{prov.narration_hash}' != current '{current_narration_hash}'). "
            f"Visual plan was generated for different voiceover text!"
        )

    if prov.proposition_hash != current_proposition_hash:
        errors.append(
            f"STALE_VISUAL_PLAN_FOR_CURRENT_NARRATION: Proposition hash mismatch "
            f"(manifest '{prov.proposition_hash}' != current '{current_proposition_hash}')."
        )

    if prov.visual_plan_id != current_visual_plan_id:
        errors.append(
            f"STALE_VISUAL_PLAN_FOR_CURRENT_NARRATION: Visual Plan ID mismatch "
            f"(manifest '{prov.visual_plan_id}' != current '{current_visual_plan_id}')."
        )

    if errors:
        msg = " | ".join(errors)
        logger.error(f"[LineageGate] REJECTED: {msg}")
        raise StaleVisualPlanError(msg)

    logger.info(f"[LineageGate] PASSED: Visual plan '{prov.visual_plan_id}' verified for content '{current_content_id}'.")
    return True
