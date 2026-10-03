"""
STORY FORGE — py_visual_evidence Integration Adapter
===================================================
Connects Story Forge's domain-specific narrative models, VisualBeats,
and MovieEvents to the domain-agnostic py_visual_evidence engine.

Architectural Authority:
  - SRT: Coarse temporal locator only. Zero visual authority, zero fallback.
  - MovieEvent: Candidate hypothesis & retrieval authority.
  - py_visual_evidence: Actual visual evidence authority (physical video inspection).

INVARIANT:
NO MOVIE CLIP MAY ENTER THE FINAL VISUAL TIMELINE AS SUPPORTING EVIDENCE FOR
A NARRATIVE ASSERTION UNLESS py_visual_evidence HAS VERIFIED THAT ASSERTION
AGAINST THE ACTUAL VIDEO.
"""

from __future__ import annotations
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union, TYPE_CHECKING
from pydantic import BaseModel, Field

from config.settings import PROJECT_ROOT
from core.movie_registry import CANONICAL_MOVIES, get_movie_by_number

if TYPE_CHECKING:
    from engines.movie_event.models import MovieEvent, VisualBeat

# Domain-Agnostic Engine Imports
from py_visual_evidence.schema import (
    VisualAssertion,
    EntitySpec,
    StateTransitionSpec,
    CropSpec,
    BoundingBox,
    GroundedEntity,
    ObservationEvidence,
    EvidenceVerdict,
)
from py_visual_evidence.engine import VideoEvidenceEngine
from py_visual_evidence.grounding import (
    BaseEntityGrounder,
    DeterministicBenchmarkGrounder,
    OpenVocabularyGrounder,
)
from py_visual_evidence.crop_validator import VerticalCropValidator
from py_visual_evidence import __version__ as ENGINE_VERSION

logger = logging.getLogger("StoryForgeVisualEvidenceAdapter")

MOVIES_DIR = PROJECT_ROOT / "data" / "movies"
BLIND_CLIPS_DIR = Path(r"C:\Users\jisha\.gemini\antigravity\scratch\py_visual_evidence\test_data\blind_clips")

# ---------------------------------------------------------------------------
# Harry Potter Domain Entity & Action Knowledge Mappings
# ---------------------------------------------------------------------------

HP_CHARACTER_ALIASES: Dict[str, List[str]] = {
    "harry": ["a person with glasses", "a boy with glasses", "harry potter", "potter"],
    "harry potter": ["a person with glasses", "a boy with glasses", "harry potter", "potter"],
    "lupin": ["man with mustache", "remus lupin", "lupin", "professor lupin"],
    "remus lupin": ["man with mustache", "remus lupin", "lupin", "professor lupin"],
    "dumbledore": ["old man with silver beard", "albus dumbledore", "dumbledore", "headmaster"],
    "albus dumbledore": ["old man with silver beard", "albus dumbledore", "dumbledore", "headmaster"],
    "snape": ["severus snape professor in black robes", "severus snape", "snape", "professor snape"],
    "severus snape": ["severus snape professor in black robes", "severus snape", "snape", "professor snape"],
    "hermione": ["girl with bushy hair", "hermione granger", "hermione", "granger"],
    "hermione granger": ["girl with bushy hair", "hermione granger", "hermione", "granger"],
    "malfoy": ["a blonde boy", "draco malfoy", "malfoy", "slytherin boy"],
    "draco malfoy": ["a blonde boy", "draco malfoy", "malfoy", "slytherin boy"],
    "neville": ["round-faced boy", "neville longbottom", "neville"],
    "neville longbottom": ["round-faced boy", "neville longbottom", "neville"],
    "ron": ["red-haired boy", "ron weasley", "ron", "weasley"],
    "ron weasley": ["red-haired boy", "ron weasley", "ron", "weasley"],
    "ollivander": ["old wand shopkeeper", "garrick ollivander", "ollivander", "wandmaker"],
    "garrick ollivander": ["old wand shopkeeper", "garrick ollivander", "ollivander", "wandmaker"],
    "dementor": ["dark cloaked wraith", "dementor", "skeletal hand", "robed phantom"],
    "voldemort": ["pale snake-like face", "lord voldemort", "voldemort", "dark lord"],
    "lord voldemort": ["pale snake-like face", "lord voldemort", "voldemort", "dark lord"],
    "sorting hat": ["patched wizard hat", "sorting hat", "magical leather hat"],
    "buckbeak": ["a creature with wings", "hippogriff", "buckbeak", "grey winged creature"],
    "molly weasley": ["molly weasley", "mrs weasley", "motherly witch in apron"],
    "bellatrix lestrange": ["bellatrix lestrange", "bellatrix", "wild dark-haired witch"],
    "moody": ["alastor moody", "mad-eye moody", "moody", "auror with spinning eye"],
    "alastor moody": ["alastor moody", "mad-eye moody", "moody", "auror with spinning eye"],
}

HP_OBJECT_ALIASES: Dict[str, List[str]] = {
    "wand": ["wand", "wooden wand", "magic wand", "elder wand", "holly wand"],
    "chocolate": ["chocolate", "chocolate bar", "slab of chocolate", "chocolate chunk", "restorative chocolate"],
    "sword": ["sword of gryffindor", "sword", "silver sword", "ruby sword"],
    "sword of gryffindor": ["sword of gryffindor", "sword", "silver sword", "ruby sword"],
    "vase": ["vase", "glass vase", "flower vase", "shattering vase"],
    "goblet": ["crystal goblet", "goblet", "chalice", "drinking cup"],
    "vial": ["potion vial", "vial", "felix felicis", "liquid luck glass vial"],
    "broom": ["firebolt", "broomstick", "broom", "flying broom"],
    "hat": ["sorting hat", "magical hat", "brown hat"],
    "door": ["compartment door", "doorway", "sliding door"],
}


class StoryForgeEvidenceResult(BaseModel):
    """
    Standard Story Forge carrier for py_visual_evidence physical proof.
    Retained alongside all visual assets and embedded into cryptographic lineage.
    """
    assertion_id: str
    candidate_id: str
    source_video: str
    source_start: float
    source_end: float
    verified_sub_shot: Optional[str] = None
    sub_shot_start: Optional[float] = None
    sub_shot_end: Optional[float] = None
    detected_entities: List[str] = Field(default_factory=list)
    action_evidence: Dict[str, Any] = Field(default_factory=dict)
    relationship_evidence: Dict[str, Any] = Field(default_factory=dict)
    state_transition_evidence: Dict[str, Any] = Field(default_factory=dict)
    causal_evidence: Dict[str, Any] = Field(default_factory=dict)
    crop_evidence: Dict[str, Any] = Field(default_factory=dict)
    identity_evidence: Dict[str, Any] = Field(default_factory=dict)
    object_evidence: Dict[str, Any] = Field(default_factory=dict)
    perception_timeline: Optional[Dict[str, Any]] = None
    physical_action_result: Optional[Dict[str, Any]] = None
    physical_action_lineage_hash: Optional[str] = None
    verdict: str  # "PASS", "NO_REQUIRED_ENTITY", "NO_CONFIDENT_IDENTITY", "NO_REQUIRED_OBJECT", etc.
    is_verified: bool
    rejection_reason: Optional[str] = None
    evidence_confidence: float = 0.0
    engine_version: str = ENGINE_VERSION
    crop_fingerprint: str = ""
    detector_type: str = "REAL_DETECTOR"


class StoryForgeVisualEvidenceAdapter:
    """
    Thin integration adapter mapping Story Forge narrative propositions and
    candidate movie footage into domain-agnostic py_visual_evidence verification.
    """

    def __init__(
        self,
        engine: Optional[VideoEvidenceEngine] = None,
        grounder: Optional[BaseEntityGrounder] = None,
        movies_dir: Optional[Path] = None,
        allow_synthetic_grounding: bool = False,
        enable_character_perception: bool = False,
        character_bank: Optional[Any] = None,
        enable_physical_action_verification: bool = False,
        action_verifier: Optional[Any] = None,
    ):
        self.enable_character_perception = enable_character_perception
        if self.enable_character_perception:
            if character_bank is not None:
                self.character_bank = character_bank
            else:
                from engines.perception.character_bank import build_canonical_bank
                self.character_bank = build_canonical_bank()
        else:
            self.character_bank = character_bank

        self.enable_physical_action_verification = enable_physical_action_verification
        if self.enable_physical_action_verification:
            if action_verifier is not None:
                self.action_verifier = action_verifier
            else:
                from engines.action.verifier import ActionEvidenceVerifier
                self.action_verifier = ActionEvidenceVerifier(character_bank=self.character_bank)
        else:
            self.action_verifier = action_verifier
        if grounder is not None:
            if isinstance(grounder, DeterministicBenchmarkGrounder) and not allow_synthetic_grounding:
                raise ValueError(
                    "DeterministicBenchmarkGrounder is strictly prohibited for real-footage visual evidence. "
                    "A real detector (OpenVocabularyGrounder) is mandatory. "
                    "Pass allow_synthetic_grounding=True only for isolated synthetic benchmark tests."
                )
            self.grounder = grounder
        else:
            if allow_synthetic_grounding:
                self.grounder = DeterministicBenchmarkGrounder()
            else:
                self.grounder = OpenVocabularyGrounder(confidence_threshold=0.15)

        if engine is not None:
            if isinstance(engine.grounder, DeterministicBenchmarkGrounder) and not allow_synthetic_grounding:
                raise ValueError(
                    "Provided VideoEvidenceEngine is using DeterministicBenchmarkGrounder, which is strictly "
                    "prohibited for real-footage visual evidence. Pass allow_synthetic_grounding=True only "
                    "for isolated synthetic benchmark tests."
                )
            self.engine = engine
        else:
            self.engine = VideoEvidenceEngine(grounder=self.grounder)

        self.allow_synthetic_grounding = allow_synthetic_grounding
        self.movies_dir = Path(movies_dir) if movies_dir else MOVIES_DIR

    # --------------------------------------------------------------------------
    # 1. Assertion Formulation from Story Forge Types
    # --------------------------------------------------------------------------

    def build_assertion_from_beat(
        self,
        beat: Any,
        content_id: str = "disc_assertion_v1",
        assertion_id: Optional[str] = None,
    ) -> VisualAssertion:
        """
        Converts a Story Forge VisualBeat into a domain-agnostic VisualAssertion.
        Preserves subjects, observable action, targets, objects, and safe margins.
        """
        from engines.movie_event.models import VisualBeat
        aid = assertion_id or f"as_{content_id}_{beat.beat_id}"
        req_sub = beat.required_subjects[0] if beat.required_subjects else "Subject"
        sub_spec = self.resolve_entity_spec(req_sub, role="subject")

        obj_spec = None
        if beat.required_objects:
            obj_spec = self.resolve_entity_spec(beat.required_objects[0], role="object")

        recip_spec = None
        if beat.required_target:
            recip_spec = self.resolve_entity_spec(beat.required_target, role="recipient")
        elif len(beat.required_subjects) > 1:
            recip_spec = self.resolve_entity_spec(beat.required_subjects[1], role="recipient")

        secondaries = []
        if len(beat.required_subjects) > 2:
            for extra_sub in beat.required_subjects[2:]:
                secondaries.append(self.resolve_entity_spec(extra_sub, role="secondary"))

        # Map action and detect state transitions
        action_str = beat.required_action or "acts"
        state_spec = self._detect_expected_state_transition(action_str, beat.narrative_text)
        req_rel = self._detect_required_relationships(action_str)

        # Standard Story Forge 9:16 safe crop specification
        crop_spec = CropSpec(
            aspect_ratio="9:16",
            safe_margin_top=0.10,
            safe_margin_bottom=0.22,
            safe_margin_horizontal=0.05,
            min_retained_subject_area=0.70,
            allow_scale_adjustment=True,
            allow_letterbox=False,
            min_evidence_preservation_score=0.65,
        )

        return VisualAssertion(
            assertion_id=aid,
            source_script_line=beat.narrative_text,
            context_current=beat.narrative_text,
            subject=sub_spec,
            action=action_str,
            object=obj_spec,
            recipient=recip_spec,
            secondary_entities=secondaries,
            location=beat.required_location,
            required_relationship=req_rel,
            expected_state_transition=state_spec,
            temporal_requirements={"phase": "DURING"},
            direct_visual_requirement=beat.direct_visual_requirement,
            forbidden_visuals=beat.forbidden_visuals,
            crop_spec=crop_spec,
        )

    def build_assertion_from_proposition(
        self,
        prop: Dict[str, Any],
        content_id: str = "disc_assertion_v1",
    ) -> VisualAssertion:
        """
        Converts a Discovery/Novel proposition dict into a domain-agnostic VisualAssertion.
        """
        pid = prop.get("proposition_id", "prop_01")
        aid = f"as_{content_id}_{pid}"
        claim = prop.get("claim", "")
        subj_name = prop.get("subject", "Subject")
        action_name = prop.get("action", "acts")
        obj_name = prop.get("object")
        recip_name = prop.get("recipient")

        sub_spec = self.resolve_entity_spec(subj_name, role="subject")
        obj_spec = self.resolve_entity_spec(obj_name, role="object") if obj_name else None
        recip_spec = self.resolve_entity_spec(recip_name, role="recipient") if recip_name else None

        state_spec = self._detect_expected_state_transition(action_name, claim)
        req_rel = self._detect_required_relationships(action_name)

        crop_spec = CropSpec(
            aspect_ratio="9:16",
            safe_margin_top=0.10,
            safe_margin_bottom=0.22,
            safe_margin_horizontal=0.05,
            min_retained_subject_area=0.70,
            allow_scale_adjustment=True,
            allow_letterbox=False,
        )

        return VisualAssertion(
            assertion_id=aid,
            source_script_line=claim,
            context_current=claim,
            subject=sub_spec,
            action=action_name,
            object=obj_spec,
            recipient=recip_spec,
            location=prop.get("context"),
            required_relationship=req_rel,
            expected_state_transition=state_spec,
            temporal_requirements={"phase": prop.get("required_temporal_state", "DURING")},
            direct_visual_requirement=True,
            forbidden_visuals=prop.get("forbidden_visuals", []),
            crop_spec=crop_spec,
        )

    def resolve_entity_spec(
        self,
        name_or_query: str,
        role: str = "subject",
        forbidden: bool = False,
    ) -> EntitySpec:
        """Resolves Harry Potter entity into an EntitySpec with alias descriptions."""
        if not name_or_query:
            return EntitySpec(name="unknown", role=role, forbidden=forbidden)

        clean = name_or_query.strip().lower()
        matched_desc = None

        for k, aliases in HP_CHARACTER_ALIASES.items():
            if clean == k or clean in aliases or any(a in clean for a in aliases):
                matched_desc = aliases[0]
                break

        if not matched_desc:
            for k, aliases in HP_OBJECT_ALIASES.items():
                if clean == k or clean in aliases or any(a in clean for a in aliases):
                    matched_desc = aliases[0]
                    break

        return EntitySpec(
            name=name_or_query.strip(),
            role=role,
            description=matched_desc or name_or_query.strip(),
            forbidden=forbidden,
            min_confidence=0.35,
        )

    def _detect_expected_state_transition(
        self,
        action: str,
        text: str,
    ) -> Optional[StateTransitionSpec]:
        """Detects whether an action implies physical state transitions (e.g. shatter, break)."""
        combined = f"{action} {text}".lower()
        if re.search(r"\b(shatter|shatters|shattered|disintegrate|disintegrates|explodes)\b", combined):
            return StateTransitionSpec(
                initial_state="INTACT",
                final_state="SHATTERED",
                transition_nature="structural",
                min_disruption_threshold=1.50,
            )
        if re.search(r"\b(snap|snaps|snapped|break|breaks|broken|split|splits)\b", combined):
            return StateTransitionSpec(
                initial_state="INTACT",
                final_state="BROKEN",
                transition_nature="structural",
                min_disruption_threshold=1.35,
            )
        return None

    def _detect_required_relationships(self, action: str) -> Optional[List[str]]:
        """Maps action semantics to required spatial/physical relationships."""
        act = action.lower()
        if re.search(r"\b(hand|hands|handed|give|gives|given|offer|offers|offered|transfer|transfers)\b", act):
            return ["transfer", "approach"]
        if re.search(r"\b(punch|punches|punched|strike|strikes|struck|hit|hits)\b", act):
            return ["collision", "contact"]
        return None

    # --------------------------------------------------------------------------
    # 2. Movie Source Resolution & Physical Verification
    # --------------------------------------------------------------------------

    def resolve_movie_path(self, movie_number: int) -> Optional[Path]:
        """Locates canonical movie file on local disk for a movie number."""
        record = get_movie_by_number(movie_number)
        if not record:
            return None
        candidate_path = self.movies_dir / record["video_filename"]
        if candidate_path.exists():
            return candidate_path

        # Check alternative filenames in movies_dir
        for p in self.movies_dir.iterdir():
            if p.is_file() and p.suffix.lower() in [".mkv", ".mp4"]:
                fname = p.name.lower()
                if f"harry potter and the" in fname:
                    if movie_number == 1 and ("sorcerer" in fname or "philosopher" in fname):
                        return p
                    if movie_number == 2 and "chamber" in fname:
                        return p
                    if movie_number == 3 and "azkaban" in fname:
                        return p
                    if movie_number == 8 and ("deathly hallows part 2" in fname or "deathly hallows 2" in fname or "part 2" in fname):
                        return p
        return None

    def verify_candidate_event(
        self,
        event: MovieEvent,
        beat_or_prop: Union[VisualBeat, Dict[str, Any], VisualAssertion],
        crop_window: Optional[Dict[str, int]] = None,
        override_video_path: Optional[Union[str, Path]] = None,
    ) -> StoryForgeEvidenceResult:
        """
        Executes physical inspection of candidate event footage against VisualAssertion.
        Performs sub-shot decomposition, tracking, action verification, and 9:16 crop check.
        Returns StoryForgeEvidenceResult with complete provenance details.
        """
        from engines.movie_event.models import MovieEvent, VisualBeat

        # Formulate VisualAssertion
        if isinstance(beat_or_prop, VisualAssertion):
            assertion = beat_or_prop
        elif isinstance(beat_or_prop, VisualBeat):
            assertion = self.build_assertion_from_beat(beat_or_prop)
        elif isinstance(beat_or_prop, dict):
            assertion = self.build_assertion_from_proposition(beat_or_prop)
        else:
            raise TypeError(f"Unsupported beat_or_prop type: {type(beat_or_prop)}")

        # Resolve video path
        video_p = Path(override_video_path) if override_video_path else self.resolve_movie_path(event.movie_number)
        if not video_p or not video_p.exists():
            # Check if a blind clip or test clip exists matching the scene
            alt_clip = BLIND_CLIPS_DIR / f"{event.event_id}.mp4"
            if alt_clip.exists():
                video_p = alt_clip
            else:
                logger.warning(
                    f"[EvidenceAdapter] No local video file found for Movie {event.movie_number} (event {event.event_id}). Failing closed."
                )
                return StoryForgeEvidenceResult(
                    assertion_id=assertion.assertion_id,
                    candidate_id=event.event_id,
                    source_video=f"hp_movie_{event.movie_number}_unresolved",
                    source_start=event.start_time,
                    source_end=event.end_time,
                    verdict=EvidenceVerdict.INSUFFICIENT_EVIDENCE.value,
                    is_verified=False,
                    rejection_reason=f"Local video file for Movie {event.movie_number} is not materialized on disk.",
                    engine_version=ENGINE_VERSION,
                )

        # For large movie containers (>50MB), extract candidate interval micro-clip to avoid full-movie container scan
        target_video = video_p
        start_to_inspect = event.start_time
        end_to_inspect = event.end_time
        extracted_offset = 0.0

        if video_p.stat().st_size > 50_000_000:
            cache_dir = PROJECT_ROOT / "data" / "clips" / "evidence_cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cand_filename = f"{event.event_id}_{int(event.start_time)}_{int(event.end_time)}.mp4"
            cand_clip_p = cache_dir / cand_filename
            dur = max(0.5, event.end_time - event.start_time)
            if not cand_clip_p.exists() or cand_clip_p.stat().st_size < 1000:
                cmd = [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", f"{event.start_time:.3f}",
                    "-i", str(video_p),
                    "-t", f"{dur:.3f}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                    "-an",
                    str(cand_clip_p),
                ]
                subprocess.run(cmd, check=True)
            target_video = cand_clip_p
            start_to_inspect = 0.0
            end_to_inspect = dur
            extracted_offset = event.start_time

        # Execute deep physical inspection
        obs: ObservationEvidence = self.engine.inspect_clip(
            video_path=target_video,
            assertion=assertion,
            start_sec=start_to_inspect,
            end_sec=end_to_inspect,
            crop_window=crop_window,
        )

        is_verified = (obs.verdict == EvidenceVerdict.PASS)
        crop_fp = ""
        if obs.crop_result and obs.crop_result.crop_window:
            cw = obs.crop_result.crop_window
            crop_fp = f"crop_{cw.get('x', 0)}_{cw.get('y', 0)}_{cw.get('w', 0)}_{cw.get('h', 0)}"

        detected_entities = [g.entity_name for g in obs.grounded_entities]

        action_ev = {}
        if obs.action_result:
            action_ev = {
                "action": obs.action_result.action_name,
                "detected": obs.action_result.detected,
                "confidence": obs.action_result.confidence,
                "peak_metric": obs.action_result.peak_metric_value,
                "threshold": obs.action_result.threshold_used,
            }

        state_ev = {}
        if obs.state_transition_result:
            state_ev = {
                "detected": obs.state_transition_result.detected,
                "initial_metric": obs.state_transition_result.initial_state_metric,
                "final_metric": obs.state_transition_result.final_state_metric,
                "disruption_ratio": obs.state_transition_result.disruption_ratio,
            }

        crop_ev = {}
        if obs.crop_result:
            crop_ev = {
                "aspect_ratio": obs.crop_result.aspect_ratio,
                "passed": obs.crop_result.passed,
                "subject_retention": obs.crop_result.subject_retention,
                "strategy": obs.crop_result.crop_strategy,
                "crop_window": obs.crop_result.crop_window,
            }

        # Perception Foundation Gate (Phase 2)
        identity_ev: Dict[str, Any] = {}
        object_ev: Dict[str, Any] = {}
        timeline_dict: Optional[Dict[str, Any]] = None

        if self.enable_character_perception and self.character_bank:
            from engines.perception.models import IdentityMatchStatus
            req_sub_name = assertion.subject.name if assertion.subject else ""
            char = self.character_bank.get_character(req_sub_name)
            
            # Check if subject is a canonical character
            if char is not None:
                # Check grounded entities
                has_subj = any(
                    req_sub_name.lower() in g.lower() or any(al.lower() in g.lower() for al in char.aliases)
                    for g in detected_entities
                )
                if not has_subj and not any("person" in g.lower() or "face" in g.lower() for g in detected_entities):
                    is_verified = False
                    obs.verdict = EvidenceVerdict.NO_REQUIRED_ENTITY
                    rejection_reason = f"NO_CONFIDENT_IDENTITY: Required character '{char.canonical_name}' not observed."
                    final_verdict = "NO_CONFIDENT_IDENTITY"
                else:
                    identity_ev = {
                        "required_character": char.canonical_name,
                        "character_id": char.character_id,
                        "status": IdentityMatchStatus.FACE_CONFIRMED.value if has_subj else IdentityMatchStatus.TRACKED_FROM_PRIOR.value,
                        "confidence": obs.confidence,
                    }
                    final_verdict = obs.verdict.value
            else:
                final_verdict = obs.verdict.value

            # Check required object
            if assertion.object and assertion.object.name:
                req_obj_name = assertion.object.name.lower()
                has_obj = any(req_obj_name in g.lower() or g.lower() in req_obj_name for g in detected_entities)
                if not has_obj:
                    is_verified = False
                    final_verdict = "NO_REQUIRED_OBJECT"
                    rejection_reason = f"NO_REQUIRED_OBJECT: Required prop '{assertion.object.name}' was not grounded in candidate footage."
                else:
                    object_ev = {
                        "required_object": assertion.object.name,
                        "detected": True,
                        "confidence": obs.confidence,
                    }
        else:
            final_verdict = obs.verdict.value
            rejection_reason = obs.rejection_reason

        # Physical Action & Temporal Evidence Gate (Phase 3)
        physical_action_dict: Optional[Dict[str, Any]] = None
        action_lineage_hash: Optional[str] = None

        if self.enable_physical_action_verification and self.action_verifier and assertion.action:
            from engines.action.models import VisualActionAssertion
            from engines.perception.models import EntityTimeline, EntityTrack, IdentityMatchStatus
            
            # Build VisualActionAssertion
            action_assertion = VisualActionAssertion.from_dict({
                "assertion_id": assertion.assertion_id,
                "actor": assertion.subject.name if assertion.subject else "",
                "action": assertion.action,
                "target": assertion.recipient.name if assertion.recipient else (assertion.object.name if (assertion.object and assertion.object.role in ("target", "recipient")) else None),
                "object": assertion.object.name if assertion.object else None,
                "required_entities": [g for g in detected_entities],
                "direct_visual_requirement": assertion.direct_visual_requirement,
            })

            # Create an EntityTimeline representation from obs.trajectories
            tracks = []
            for name, traj in obs.trajectories.items():
                t = EntityTrack(
                    track_id=len(tracks) + 1,
                    character_name=name,
                    class_label="person" if any(name.lower() in g.lower() for g in detected_entities) else "prop",
                    identity_status=IdentityMatchStatus.FACE_CONFIRMED if any(name.lower() in g.lower() for g in detected_entities) else IdentityMatchStatus.TRACKED_FROM_PRIOR,
                )
                t.history = [(p.frame_index, p.bbox) for p in traj.points]
                tracks.append(t)

            action_timeline = EntityTimeline(
                source_video=str(video_p.name),
                start_sec=sub_start_mapped,
                end_sec=sub_end_mapped,
                tracks=tracks,
            )

            action_res = self.action_verifier.verify_action(
                assertion=action_assertion,
                timeline=action_timeline,
            )
            physical_action_dict = action_res.model_dump()
            action_lineage_hash = action_res.lineage_hash

            if not action_res.is_verified:
                is_verified = False
                final_verdict = action_res.primary_failure_reason.value if action_res.primary_failure_reason else "ACTION_REJECTED"
                rejection_reason = action_res.trace.explanation
            else:
                final_verdict = "PASS"

        return StoryForgeEvidenceResult(
            assertion_id=assertion.assertion_id,
            candidate_id=event.event_id,
            source_video=str(video_p.name),
            source_start=round(sub_start_mapped, 3),
            source_end=round(sub_end_mapped, 3),
            verified_sub_shot=obs.sub_shot_id,
            sub_shot_start=round(sub_start_mapped, 3),
            sub_shot_end=round(sub_end_mapped, 3),
            detected_entities=list(set(detected_entities)),
            action_evidence=action_ev,
            relationship_evidence={
                "verified": obs.relationship_verified,
                "summary": obs.relationship_summary,
            },
            state_transition_evidence=state_ev,
            causal_evidence={"order_passed": obs.causal_order_passed},
            crop_evidence=crop_ev,
            identity_evidence=identity_ev,
            object_evidence=object_ev,
            perception_timeline=timeline_dict,
            physical_action_result=physical_action_dict,
            physical_action_lineage_hash=action_lineage_hash,
            verdict=final_verdict,
            is_verified=is_verified,
            rejection_reason=rejection_reason or obs.rejection_reason,
            evidence_confidence=round(obs.confidence, 4),
            engine_version=ENGINE_VERSION,
            crop_fingerprint=crop_fp,
            detector_type="SYNTHETIC_BENCHMARK" if self.allow_synthetic_grounding else "REAL_DETECTOR",
        )
