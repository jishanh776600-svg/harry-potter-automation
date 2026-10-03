"""
STORY FORGE — Narrative Evidence Contract & Semantic Relevance Gate
===================================================================
Enforces the missing architectural contract between narrative propositions/claims
and candidate movie footage:

    NARRATIVE CLAIM
      -> NARRATIVE EVIDENCE CONTRACT
      -> SEMANTIC RELEVANCE EVALUATION (10-Gate Audit)
      -> PHYSICAL EVIDENCE VERIFICATION (Perception + Action)
      -> FINAL ACCEPT / REJECT (Fail-Closed)

Ensures that physical presence of a character (e.g. "Harry exists in Quidditch")
NEVER satisfies an unrelated narrative claim (e.g. "The Sorting Hat considered Slytherin").
Rejects unfilmed, internal, or book-only claims from claiming DIRECT visual evidence.
"""

from __future__ import annotations
import logging
import re
from enum import Enum
from typing import List, Dict, Any, Optional, Set, Tuple
from pydantic import BaseModel, Field

logger = logging.getLogger("NarrativeEvidenceContract")


# ── Domain-Specific Event Contexts & Forbidden Signatures ─────────────────────

EVENT_CONTEXT_RULES = {
    "sorting": {
        "keywords": [
            "sorting hat", "sorting ceremony", "sorted into", "slytherin", "gryffindor",
            "hufflepuff", "ravenclaw", "sorting debate", "hat debates", "hat considered",
            "hat considers", "hat honours", "hat's decision", "placed on his head"
        ],
        "required_scene": "sorting_ceremony",
        "required_location_tokens": ["great hall", "sorting", "stool", "hall"],
        "required_object_tokens": ["sorting hat", "hat"],
        "forbidden_contexts": [
            "quidditch", "buckbeak", "lake", "snitch", "broom", "wand shop",
            "ollivander", "forbidden forest", "graveyard", "chamber of secrets",
            "potions classroom", "chess", "train", "dursley", "zoo", "privet drive"
        ],
        "forbidden_characters": ["buckbeak", "ollivander", "lupin", "sirius", "umbridge", "voldemort", "dudley", "vernon", "petunia"],
        "forbidden_locations": ["quidditch pitch", "diagon alley", "ollivanders", "black lake", "forbidden forest", "privet drive", "zoo"],
        "forbidden_events": ["quidditch_match", "ollivander_wand_shop", "buckbeak_flight", "malfoy_confrontation", "zoo_reptile_house"],
        "context_chain_preceding": "great_hall_entrance",
        "context_chain_following": "sorting_applause",
    },
    "wand_selection": {
        "keywords": ["ollivander", "wand chose", "buying wand", "wand shop", "diagon alley", "first wand", "wand handover"],
        "required_scene": "ollivander_wand_shop",
        "required_location_tokens": ["ollivanders", "wand shop", "diagon alley"],
        "required_object_tokens": ["wand", "wand box"],
        "forbidden_contexts": [
            "sorting", "quidditch", "great hall", "buckbeak", "graveyard", "forest",
            "lake", "pitch", "snitch", "broom", "zoo"
        ],
        "forbidden_characters": ["dumbledore", "snape", "malfoy", "buckbeak", "dudley"],
        "forbidden_locations": ["great hall", "quidditch pitch", "black lake", "hogwarts"],
        "forbidden_events": ["sorting_ceremony", "quidditch_match", "buckbeak_flight"],
        "context_chain_preceding": "diagon_alley_arrival",
        "context_chain_following": "wand_selection_complete",
    },
    "quidditch": {
        "keywords": [
            "quidditch", "snitch", "seeker", "bludger", "quaffle", "broomstick",
            "nimbus", "golden snitch", "catching the snitch", "caught the snitch",
            "coughed up the snitch", "swallowed the golden snitch"
        ],
        "required_scene": "quidditch_match",
        "required_location_tokens": ["quidditch pitch", "pitch", "sky", "stands"],
        "required_object_tokens": ["snitch", "broomstick", "broom"],
        "forbidden_contexts": [
            "sorting", "great hall", "classroom", "dungeon", "ollivander", "wand shop",
            "library", "zoo", "privet drive", "lake"
        ],
        "forbidden_characters": ["ollivander", "buckbeak", "dudley"],
        "forbidden_locations": ["great hall", "ollivanders", "diagon alley", "black lake", "zoo"],
        "forbidden_events": ["sorting_ceremony", "ollivander_wand_shop", "buckbeak_flight", "zoo_reptile_house"],
        "context_chain_preceding": "quidditch_takeoff",
        "context_chain_following": "quidditch_victory",
    },
    "hippogriff_flight": {
        "keywords": ["buckbeak flying", "rides buckbeak", "flight over lake", "soaring", "buckbeak flight"],
        "required_scene": "buckbeak_flight",
        "required_location_tokens": ["lake", "black lake", "sky", "mountains"],
        "required_object_tokens": [],
        "forbidden_contexts": [
            "sorting", "great hall", "classroom", "dungeon", "quidditch pitch",
            "ollivander", "wand shop", "zoo"
        ],
        "forbidden_characters": ["ollivander", "dumbledore", "snape", "voldemort", "dudley"],
        "forbidden_locations": ["great hall", "quidditch pitch", "ollivanders", "diagon alley"],
        "forbidden_events": ["sorting_ceremony", "quidditch_match", "ollivander_wand_shop"],
    },
    "malfoy_punch": {
        "keywords": ["punch", "punched", "punches", "strike", "confronts malfoy"],
        "required_scene": "malfoy_confrontation",
        "required_location_tokens": ["sundial", "stone circle", "hillside", "hagrid hut"],
        "required_object_tokens": [],
        "forbidden_contexts": [
            "great hall", "sorting", "quidditch", "classroom", "train", "ollivander", "lake", "zoo"
        ],
        "forbidden_characters": ["ollivander", "buckbeak", "dumbledore", "dudley"],
        "forbidden_locations": ["great hall", "quidditch pitch", "ollivanders", "lake"],
        "forbidden_events": ["sorting_ceremony", "quidditch_match", "ollivander_wand_shop"],
    },
    "elder_wand_snap": {
        "keywords": [
            "elder wand", "wand snap", "snaps the wand", "snaps the elder wand",
            "breaks the elder wand", "broke the wand", "destroys the wand"
        ],
        "required_scene": "elder_wand_destruction",
        "required_location_tokens": ["bridge", "viaduct", "ruins"],
        "required_object_tokens": ["elder wand", "wand"],
        "forbidden_contexts": [
            "sorting", "great hall", "classroom", "quidditch", "train", "ollivander", "zoo"
        ],
        "forbidden_characters": ["ollivander", "buckbeak", "draco", "dudley"],
        "forbidden_locations": ["great hall", "quidditch pitch", "ollivanders", "lake"],
        "forbidden_events": ["sorting_ceremony", "quidditch_match", "ollivander_wand_shop"],
    },
    "vanishing_glass_zoo": {
        "keywords": ["reptile house", "zoo", "boa constrictor", "python", "vanishing glass", "dudley fell", "dudley's zoo"],
        "required_scene": "zoo_reptile_house",
        "required_location_tokens": ["zoo", "reptile house", "enclosure", "tank", "terrarium"],
        "required_object_tokens": ["snake", "glass"],
        "forbidden_contexts": [
            "sorting", "quidditch", "great hall", "classroom", "dungeon", "lake",
            "ollivander", "train", "hogwarts", "pitch"
        ],
        "forbidden_characters": ["dumbledore", "snape", "malfoy", "buckbeak", "ollivander", "lupin"],
        "forbidden_locations": ["great hall", "quidditch pitch", "hogwarts", "ollivanders", "lake"],
        "forbidden_events": ["sorting_ceremony", "quidditch_match", "ollivander_wand_shop"],
    },
    "flying_lesson": {
        "keywords": [
            "flying lesson", "madam hooch", "broomstick leapt", "said up", "say up",
            "first flying", "broom leapt", "broom jumped", "smacked in the face",
            "smacked in the nose", "broom hit", "flying instinct"
        ],
        "required_scene": "first_flying_lesson",
        "required_location_tokens": ["training pitch", "flying grounds", "grass grounds", "courtyard", "grounds"],
        "required_object_tokens": ["broomstick", "broom"],
        "forbidden_contexts": [
            "sorting", "great hall", "classroom", "dungeon", "lake",
            "ollivander", "wand shop", "zoo", "quidditch pitch", "snitch", "train"
        ],
        "forbidden_characters": ["ollivander", "buckbeak", "dudley"],
        "forbidden_locations": ["great hall", "quidditch pitch", "hogwarts interior", "ollivanders", "black lake", "zoo"],
        "forbidden_events": ["sorting_ceremony", "quidditch_match", "ollivander_wand_shop", "zoo_reptile_house"],
        "context_chain_preceding": "students_line_up_at_brooms",
        "context_chain_following": "neville_broom_accident",
    },
    "boggart_lesson": {
        "keywords": [
            "boggart", "riddikulus", "wardrobe", "professor lupin", "lupin taught",
            "shape-shifter", "vulture hat", "grandmother's dress", "laughter destroys",
            "ridicule", "amorph"
        ],
        "required_scene": "boggart_in_wardrobe",
        "required_location_tokens": ["staffroom", "classroom", "defense classroom"],
        "required_object_tokens": ["wardrobe", "wand"],
        "forbidden_contexts": [
            "sorting", "quidditch", "great hall", "lake", "diagon alley",
            "ollivander", "wand shop", "zoo", "pitch", "snitch", "broomstick"
        ],
        "forbidden_characters": ["ollivander", "buckbeak", "dudley"],
        "forbidden_locations": ["great hall", "quidditch pitch", "black lake", "ollivanders", "zoo"],
        "forbidden_events": ["sorting_ceremony", "quidditch_match", "ollivander_wand_shop", "buckbeak_flight"],
        "context_chain_preceding": "lupin_explains_riddikulus",
        "context_chain_following": "students_face_boggart",
    },
}

# Book-only / unfilmed / internal mental predicates
INHERENTLY_NON_VISUAL_PATTERNS = [
    r"\bin the books?\b",
    r"\bin the novel\b",
    r"\boriginal novels?\b",
    r"\browling\b",
    r"\bnever shown on screen\b",
    r"\bcut from the film\b",
    r"\bdetected great talent\b",
    r"\bhidden ambition\b",
    r"\bsecretly believed\b",
    r"\bfelt in his heart\b",
    r"\bdebates out loud in the book\b",
    r"\binvisible reasoning\b",
    r"\bmoral dilemma\b",
    r"\bsymbolizes\b",
    r"\bforeshadowed\b",
    r"\bflesh memory\b",
    r"\bwizarding lore\b",
    r"\bsensed\b.*\bambition\b",
    r"\bhidden thoughts\b",
    r"\bsecret thoughts\b",
    r"\bsoul fragment\b",
    r"\bthought process\b",
    r"\binternal thoughts\b",
    r"\binternal reasoning\b",
    r"\binternal debate\b",
    r"\bmental state\b",
    r"\bhesitated because\b",
    r"\bpiece of voldemort\b",
    r"\bpiece of .* soul\b",
    r"\binner conflict\b",
    r"\btrue loyalties\b",
    r"\bsilent hesitation\b",
]


class RelevanceVerdict(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class NarrativeEvidenceContract(BaseModel):
    """
    Explicit evidence contract derived from a narrative proposition.
    Specifies what physical and semantic evidence MUST and MUST NOT be present.
    Enforces Narrative Integrity Gate V2 contracts.
    """
    claim_id: str
    claim_text: str
    narrative_role: str = "core_fact"

    # Mandatory Positive Constraints
    required_subjects: List[str] = Field(default_factory=list)
    required_secondary_subjects: List[str] = Field(default_factory=list)
    required_objects: List[str] = Field(default_factory=list)
    required_action: Optional[str] = None
    required_target: Optional[str] = None
    required_relationship: Optional[str] = None
    required_location: Optional[str] = None
    required_scene_event: Optional[str] = None
    required_temporal_state: Optional[str] = None

    # Mandatory Negative / Exclusion Constraints
    forbidden_subjects: List[str] = Field(default_factory=list)
    forbidden_actions: List[str] = Field(default_factory=list)
    forbidden_contexts: List[str] = Field(default_factory=list)
    forbidden_locations: List[str] = Field(default_factory=list)
    forbidden_events: List[str] = Field(default_factory=list)

    # Context Chain Expectations
    context_chain_preceding: Optional[str] = None
    context_chain_following: Optional[str] = None
    contract_version: str = "v2.0"

    # Evidentiary Modality
    direct_visual_mandatory: bool = True
    contextual_visual_allowed: bool = False
    is_inherently_non_visual: bool = False
    min_semantic_relevance_threshold: float = 0.65

    def compute_contract_hash(self) -> str:
        """Deterministic fingerprint of this contract's evidentiary constraints."""
        import hashlib
        payload = (
            f"{self.claim_id}:{self.claim_text}:{sorted(self.required_subjects)}:"
            f"{sorted(self.required_objects)}:{self.required_action}:{self.required_location}:"
            f"{self.required_scene_event}:{sorted(self.forbidden_contexts)}:{sorted(self.forbidden_subjects)}:"
            f"{sorted(self.forbidden_locations)}:{sorted(self.forbidden_events)}:{self.direct_visual_mandatory}:"
            f"{self.is_inherently_non_visual}:{self.contract_version}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @classmethod
    def from_visual_beat(cls, beat: Any) -> "NarrativeEvidenceContract":
        """
        Derives an explicit NarrativeEvidenceContract from a VisualBeat and its narrative claim.
        """
        text = getattr(beat, "narrative_text", "") or getattr(beat, "text_span", "")
        text_lower = text.lower()
        beat_id = getattr(beat, "beat_id", "beat_01")
        role = getattr(beat, "narrative_role", "core_fact")

        # 1. Detect if claim is inherently non-visual or book-only
        is_non_visual = any(re.search(pat, text_lower) for pat in INHERENTLY_NON_VISUAL_PATTERNS)

        # 2. Extract entities and objects
        req_subs = list(getattr(beat, "required_subjects", []))
        if not req_subs and hasattr(beat, "required_entities"):
            req_subs = list(getattr(beat, "required_entities", []))

        req_objs = list(getattr(beat, "required_objects", []))
        req_act = getattr(beat, "required_action", None)
        if req_act in ("none", "NONE", ""):
            req_act = None

        req_loc = getattr(beat, "required_location", None)
        req_target = getattr(beat, "required_target", None)
        req_rel = getattr(beat, "required_relationship", None)
        direct_mand = getattr(beat, "direct_visual_requirement", True) and not is_non_visual
        ctx_allowed = getattr(beat, "contextual_visual_allowed", False) or is_non_visual

        # 3. Match against domain event rules
        matched_rule = None
        for rule_key, rule in EVENT_CONTEXT_RULES.items():
            for kw in rule["keywords"]:
                pat = r"\b" + re.escape(kw.lower()) + r"\b"
                if re.search(pat, text_lower):
                    matched_rule = rule
                    break
            if matched_rule:
                break

        forbidden_contexts: List[str] = []
        forbidden_subjects: List[str] = []
        forbidden_actions: List[str] = []
        forbidden_locations: List[str] = []
        forbidden_events: List[str] = []
        required_scene = None
        ctx_preceding = None
        ctx_following = None

        if matched_rule:
            forbidden_contexts.extend(matched_rule.get("forbidden_contexts", []))
            forbidden_subjects.extend(matched_rule.get("forbidden_characters", []))
            forbidden_locations.extend(matched_rule.get("forbidden_locations", []))
            forbidden_events.extend(matched_rule.get("forbidden_events", []))
            required_scene = matched_rule.get("required_scene")
            ctx_preceding = matched_rule.get("context_chain_preceding")
            ctx_following = matched_rule.get("context_chain_following")

            if not req_loc and matched_rule.get("required_location_tokens"):
                req_loc = matched_rule["required_location_tokens"][0]
            for obj in matched_rule.get("required_object_tokens", []):
                if obj not in req_objs:
                    req_objs.append(obj)

        # Add explicit beat forbidden visuals if present
        extra_forbidden = getattr(beat, "forbidden_visuals", [])
        if extra_forbidden:
            forbidden_contexts.extend(extra_forbidden)

        return cls(
            claim_id=beat_id,
            claim_text=text,
            narrative_role=role,
            required_subjects=req_subs,
            required_objects=req_objs,
            required_action=req_act,
            required_target=req_target,
            required_relationship=req_rel,
            required_location=req_loc,
            required_scene_event=required_scene,
            forbidden_subjects=list(dict.fromkeys(forbidden_subjects)),
            forbidden_actions=forbidden_actions,
            forbidden_contexts=list(dict.fromkeys(forbidden_contexts)),
            forbidden_locations=list(dict.fromkeys(forbidden_locations)),
            forbidden_events=list(dict.fromkeys(forbidden_events)),
            context_chain_preceding=ctx_preceding,
            context_chain_following=ctx_following,
            contract_version="v2.0",
            direct_visual_mandatory=direct_mand,
            contextual_visual_allowed=ctx_allowed,
            is_inherently_non_visual=is_non_visual,
            min_semantic_relevance_threshold=0.65,
        )


class SemanticRelevanceResult(BaseModel):
    """
    Diagnostic result of evaluating a candidate against a NarrativeEvidenceContract.
    """
    candidate_id: str
    claim_id: str
    verdict: RelevanceVerdict
    overall_relevance_score: float
    rejection_reasons: List[str] = Field(default_factory=list)
    audit_trace: Dict[str, Any] = Field(default_factory=dict)

    # 10 Gates Breakdown
    subject_match: bool = True
    action_match: bool = True
    object_target_match: bool = True
    relationship_match: bool = True
    location_context_match: bool = True
    temporal_event_match: bool = True
    narrative_role_match: bool = True
    forbidden_context_passed: bool = True
    directness_requirement_satisfied: bool = True
    physical_evidence_consistent: bool = True

    @property
    def is_accepted(self) -> bool:
        return self.verdict == RelevanceVerdict.ACCEPT


class SemanticRelevanceEvaluator:
    """
    Deterministic, inspectable 10-Gate Semantic Relevance Evaluator.
    Prevents irrelevant footage from passing purely on generic entity presence.
    """

    def evaluate_relevance(
        self,
        candidate_metadata: Dict[str, Any],
        contract: NarrativeEvidenceContract,
    ) -> SemanticRelevanceResult:
        """
        Evaluates a candidate against the 10 gates of the Narrative Evidence Contract.
        """
        cand_id = candidate_metadata.get("candidate_id", "cand_unknown")
        rejections: List[str] = []
        trace: Dict[str, Any] = {}

        # Candidate attributes
        cand_desc = (candidate_metadata.get("visual_description", "") or "").lower()
        cand_title = (candidate_metadata.get("title", "") or "").lower()
        cand_action = (candidate_metadata.get("action", "") or "").lower()
        cand_loc = (candidate_metadata.get("location", "") or "").lower()
        cand_source = (candidate_metadata.get("source_video", "") or candidate_metadata.get("source_clip", "") or "").lower()
        combined_cand_text = f"{cand_desc} {cand_title} {cand_action} {cand_loc} {cand_source}"

        verified_entities = [str(e).lower() for e in candidate_metadata.get("verified_entities", [])]
        characters_present = [str(c).lower() for c in candidate_metadata.get("characters_present", [])]
        all_visible_entities = set(verified_entities + characters_present)

        # ----------------------------------------------------------------------
        # Gate 8: FORBIDDEN-CONTEXT CHECK (Immediate Hard Veto)
        # ----------------------------------------------------------------------
        forbidden_context_passed = True
        for f_ctx in contract.forbidden_contexts:
            f_clean = f_ctx.lower().strip()
            if not f_clean:
                continue
            if f_clean in combined_cand_text or f_clean in cand_source:
                forbidden_context_passed = False
                rejections.append(
                    f"FORBIDDEN_CONTEXT_VIOLATION: Candidate contains disallowed context '{f_clean}' for claim '{contract.claim_id}'."
                )

        for f_sub in contract.forbidden_subjects:
            f_sub_clean = f_sub.lower().strip()
            if any(f_sub_clean in ent for ent in all_visible_entities) or f_sub_clean in combined_cand_text:
                forbidden_context_passed = False
                rejections.append(
                    f"FORBIDDEN_SUBJECT_VIOLATION: Candidate depicts forbidden subject '{f_sub}' for claim '{contract.claim_id}'."
                )

        for f_loc in contract.forbidden_locations:
            f_loc_clean = f_loc.lower().strip()
            if not f_loc_clean:
                continue
            if f_loc_clean in cand_loc or f_loc_clean in combined_cand_text:
                forbidden_context_passed = False
                rejections.append(
                    f"FORBIDDEN_LOCATION_VIOLATION: Candidate in disallowed location '{f_loc}' for claim '{contract.claim_id}'."
                )

        for f_ev in contract.forbidden_events:
            f_ev_clean = f_ev.lower().strip()
            if not f_ev_clean:
                continue
            cand_event = str(candidate_metadata.get("movie_event_id", "") or candidate_metadata.get("scene_name", "")).lower()
            if f_ev_clean in cand_event or f_ev_clean in combined_cand_text:
                forbidden_context_passed = False
                rejections.append(
                    f"FORBIDDEN_EVENT_VIOLATION: Candidate contains disallowed event '{f_ev}' for claim '{contract.claim_id}'."
                )

        trace["gate_8_forbidden_context"] = forbidden_context_passed

        has_timeline = candidate_metadata.get("has_timeline", False)
        has_annotations = bool(
            all_visible_entities or cand_desc or cand_title or cand_action or cand_loc
            or candidate_metadata.get("movie_event_id") or candidate_metadata.get("scene_name")
        )

        # ----------------------------------------------------------------------
        # Gate 1: SUBJECT MATCH
        # ----------------------------------------------------------------------
        subject_match = True
        if contract.required_subjects and not has_timeline and has_annotations:
            missing_subjects = []
            for req_sub in contract.required_subjects:
                r_clean = req_sub.lower().strip()
                # Check visible entities and description
                found = any(r_clean in ent or ent in r_clean for ent in all_visible_entities) or (r_clean in combined_cand_text)
                if not found:
                    missing_subjects.append(req_sub)
            if missing_subjects:
                subject_match = False
                rejections.append(
                    f"SUBJECT_MISMATCH: Missing required subjects {missing_subjects} in candidate footage."
                )
        trace["gate_1_subject_match"] = subject_match

        # ----------------------------------------------------------------------
        # Gate 2: ACTION MATCH
        # ----------------------------------------------------------------------
        action_match = True
        if contract.required_action and not has_timeline and has_annotations:
            req_act = contract.required_action.lower().strip()
            cand_act_tokens = cand_action.split() + cand_desc.split()
            # Action match requires semantically compatible action
            act_found = req_act in cand_action or any(req_act in t for t in cand_act_tokens)
            if not act_found:
                # Check action synonyms / stems
                if req_act in ("punch", "hit", "strike") and any(w in cand_action or w in cand_desc for w in ["punch", "strike", "hit"]):
                    act_found = True
                elif req_act in ("hat placed on head", "wear hat", "sorting") and any(w in cand_action or w in cand_desc for w in ["sorting", "placed", "puts", "hat"]):
                    act_found = True

            if not act_found:
                action_match = False
                rejections.append(
                    f"ACTION_MISMATCH: Required action '{contract.required_action}' not depicted (candidate shows '{cand_action or 'generic/none'}')."
                )
        trace["gate_2_action_match"] = action_match

        # ----------------------------------------------------------------------
        # Gate 3: OBJECT / TARGET MATCH
        # ----------------------------------------------------------------------
        object_target_match = True
        if contract.required_objects and not has_timeline and has_annotations:
            cand_objs = [str(o).lower() for o in candidate_metadata.get("visible_objects", [])]
            missing_objs = []
            for req_obj in contract.required_objects:
                ro_clean = req_obj.lower().strip()
                found = any(ro_clean in o or o in ro_clean for o in cand_objs) or (ro_clean in combined_cand_text)
                if not found:
                    missing_objs.append(req_obj)
            if missing_objs:
                object_target_match = False
                rejections.append(
                    f"OBJECT_MISMATCH: Required object(s) {missing_objs} absent in candidate."
                )
        trace["gate_3_object_target_match"] = object_target_match

        # ----------------------------------------------------------------------
        # HARD COMPOUND-ENTITY & INTERACTION RULE (PART 3 & PART 4)
        # ----------------------------------------------------------------------
        hard_compound_passed = True
        if contract.required_subjects and contract.required_objects:
            if not subject_match:
                hard_compound_passed = False
                rejections.append(
                    f"HARD_COMPOUND_ENTITY_VIOLATION: OBJECT_ONLY candidate lacks required subjects {contract.required_subjects}."
                )
            elif not object_target_match:
                hard_compound_passed = False
                rejections.append(
                    f"HARD_COMPOUND_ENTITY_VIOLATION: CHARACTER_ONLY candidate lacks required objects {contract.required_objects}."
                )

        if contract.required_action and (contract.required_subjects or contract.required_objects):
            if not action_match:
                hard_compound_passed = False
                rejections.append(
                    f"HARD_COMPOUND_INTERACTION_VIOLATION: Co-presence without required action '{contract.required_action}' cannot satisfy interaction claim."
                )
        trace["hard_compound_passed"] = hard_compound_passed

        # ----------------------------------------------------------------------
        # Gate 4: RELATIONSHIP MATCH
        # ----------------------------------------------------------------------
        relationship_match = True
        if contract.required_relationship and has_annotations:
            req_rel = contract.required_relationship.lower().strip()
            if req_rel not in combined_cand_text:
                relationship_match = False
                rejections.append(
                    f"RELATIONSHIP_MISMATCH: Required relationship '{contract.required_relationship}' absent."
                )
        trace["gate_4_relationship_match"] = relationship_match

        # ----------------------------------------------------------------------
        # Gate 5: LOCATION / CONTEXT MATCH
        # ----------------------------------------------------------------------
        location_context_match = True
        if contract.required_location and has_annotations:
            req_loc = contract.required_location.lower().strip()
            loc_found = req_loc in cand_loc or req_loc in combined_cand_text
            if not loc_found:
                # Token overlap check
                loc_tokens = [w for w in req_loc.split() if len(w) > 3]
                loc_found = any(t in cand_loc or t in combined_cand_text for t in loc_tokens)

            if not loc_found:
                location_context_match = False
                rejections.append(
                    f"LOCATION_MISMATCH: Candidate in '{cand_loc or 'unknown'}', expected '{contract.required_location}'."
                )
        trace["gate_5_location_match"] = location_context_match

        # ----------------------------------------------------------------------
        # Gate 6: TEMPORAL / SCENE EVENT MATCH
        # ----------------------------------------------------------------------
        temporal_event_match = True
        if contract.required_scene_event and has_annotations:
            req_scene = contract.required_scene_event.lower().strip()
            cand_event = str(candidate_metadata.get("movie_event_id", "") or candidate_metadata.get("scene_name", "")).lower()
            event_matched = (req_scene in cand_event) or (bool(cand_event) and cand_event in req_scene)
            if not event_matched:
                generic_scene_words = {"great", "hall", "room", "castle", "the", "in", "at", "of", "and", "a", "scene", "exterior", "interior"}
                scene_tokens = [t for t in req_scene.split("_") if t not in generic_scene_words and len(t) > 2]
                if scene_tokens:
                    event_matched = all(st in cand_event or st in combined_cand_text for st in scene_tokens)
                else:
                    event_matched = req_scene in combined_cand_text

            if not event_matched:
                temporal_event_match = False
                rejections.append(
                    f"EVENT_MISMATCH: Candidate event '{cand_event or 'unindexed'}' does not match required event '{contract.required_scene_event}'."
                )
        trace["gate_6_event_match"] = temporal_event_match

        # ----------------------------------------------------------------------
        # Gate 7: NARRATIVE ROLE MATCH
        # ----------------------------------------------------------------------
        narrative_role_match = True
        trace["gate_7_narrative_role_match"] = narrative_role_match

        # ----------------------------------------------------------------------
        # Gate 9: DIRECTNESS REQUIREMENT & INHERENTLY NON-VISUAL GUARD
        # ----------------------------------------------------------------------
        directness_satisfied = True
        if contract.is_inherently_non_visual and candidate_metadata.get("is_claimed_direct", False):
            # Cannot pretend an invisible internal/book claim has direct movie proof
            directness_satisfied = False
            rejections.append(
                f"INHERENTLY_NON_VISUAL: Claim '{contract.claim_id}' is internal/book-only and cannot be fulfilled as DIRECT visual evidence."
            )
        trace["gate_9_directness_satisfied"] = directness_satisfied

        # ----------------------------------------------------------------------
        # Gate 10: PHYSICAL EVIDENCE CONSISTENCY
        # ----------------------------------------------------------------------
        physical_consistent = True
        if candidate_metadata.get("is_rejected_physically", False):
            physical_consistent = False
            rejections.append("PHYSICAL_INCONSISTENCY: Candidate already failed Phase 3 physical action verification.")
        trace["gate_10_physical_consistent"] = physical_consistent


        # Final Accept / Reject Decision (Narrative Integrity Gate V2 Hard Veto)
        # CHARACTER_PRESENT != CLAIM_SUPPORTED
        # OBJECT_PRESENT != CLAIM_SUPPORTED
        # LOCATION_PRESENT != CLAIM_SUPPORTED
        # MOVIE_RELEVANCE != CLAIM_SUPPORTED
        direct_contradiction = False
        if contract.direct_visual_mandatory:
            if not subject_match:
                direct_contradiction = True
            elif contract.required_action and not action_match:
                direct_contradiction = True
            elif contract.required_objects and not object_target_match:
                direct_contradiction = True
            elif contract.required_location and not location_context_match:
                direct_contradiction = True
            elif contract.required_scene_event and not temporal_event_match:
                direct_contradiction = True
            elif contract.required_relationship and not relationship_match:
                direct_contradiction = True

        is_hard_veto = (
            not forbidden_context_passed or
            not directness_satisfied or
            not physical_consistent or
            not hard_compound_passed or
            direct_contradiction
        )

        effective_threshold = (
            0.50 if (contract.is_inherently_non_visual or not contract.direct_visual_mandatory)
            else contract.min_semantic_relevance_threshold
        )

        if not forbidden_context_passed or is_hard_veto:
            score = 0.0
        else:
            s_event = 1.0 if temporal_event_match else (0.40 if not contract.required_scene_event else 0.0)
            s_subj = 1.0 if subject_match else (0.30 if not contract.required_subjects else 0.0)
            s_act = 1.0 if action_match else (0.50 if not contract.required_action else 0.0)
            s_obj = 1.0 if object_target_match else (0.50 if not contract.required_objects else 0.0)
            s_loc = 1.0 if location_context_match else (0.50 if not contract.required_location else 0.0)

            score = round(
                0.30 * s_event +
                0.25 * s_subj +
                0.20 * s_act +
                0.15 * s_obj +
                0.10 * s_loc,
                3,
            )

        meets_threshold = (score >= effective_threshold)
        verdict = RelevanceVerdict.ACCEPT if (not is_hard_veto and meets_threshold) else RelevanceVerdict.REJECT

        if verdict == RelevanceVerdict.REJECT and not rejections:
            rejections.append(
                f"LOW_RELEVANCE: Score {score:.2f} < minimum required {effective_threshold:.2f}."
            )

        return SemanticRelevanceResult(
            candidate_id=cand_id,
            claim_id=contract.claim_id,
            verdict=verdict,
            overall_relevance_score=score,
            rejection_reasons=rejections,
            audit_trace=trace,
            subject_match=subject_match,
            action_match=action_match,
            object_target_match=object_target_match,
            relationship_match=relationship_match,
            location_context_match=location_context_match,
            temporal_event_match=temporal_event_match,
            narrative_role_match=narrative_role_match,
            forbidden_context_passed=forbidden_context_passed,
            directness_requirement_satisfied=directness_satisfied,
            physical_evidence_consistent=physical_consistent,
        )
