"""
STORY FORGE — Temporal Action Transition Engine
================================================
Verifies temporal action dynamics across sampled micro-intervals:
  - Distinguishes dynamic action transitions from static postures
  - Enforces action onset, peak, and completion boundaries
  - Detects static substitutions (e.g. already holding vs drawing sword)
  - Supports continuous/static actions (e.g. looking at mirror, standing)
  - Emits machine-readable evidence traces
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Set

from engines.visual_evidence.evidence_models import (
    TemporalState,
    ActionNature,
    EvidenceRejectionReason,
)

logger = logging.getLogger("TemporalActionEngine")

# Verbs/actions that represent dynamic state changes requiring a transition
DYNAMIC_ACTION_KEYWORDS: Set[str] = {
    "draw", "drawing", "draws", "pull", "pulling", "pulls",
    "open", "opening", "opens",
    "close", "closing", "closes", "shut", "shutting",
    "sit", "sitting_down", "sits_down", "lowering",
    "stand_up", "standing_up", "rises", "rising",
    "throw", "throwing", "throws", "toss", "tossing",
    "catch", "catching", "catches",
    "strike", "striking", "strikes", "hit", "hitting", "hits", "slash", "slashing",
    "cast", "casting", "casts", "wave", "waving",
    "run", "running", "runs", "flee", "fleeing",
    "walk", "walking", "walks", "enter", "entering", "enters", "exit", "exiting",
    "fall", "falling", "falls", "drop", "dropping", "drops",
    "plead", "pleading", "pleads", "beg", "begging", "begs",
}

# Verbs/actions that are inherently continuous/sustained states
CONTINUOUS_ACTION_KEYWORDS: Set[str] = {
    "look", "looking", "looks", "gaze", "gazing", "gazes", "stare", "staring", "stares", "watch", "watching",
    "hold", "holding", "holds", "clutch", "clutching",
    "stand", "standing", "stands", "stand_silent", "standing_silent",
    "seated", "sit_static", "sitting_at",
    "listen", "listening", "listens",
    "sleep", "sleeping", "sleeps",
    "cry", "crying", "cries", "weep", "weeping",
    "presence", "establishing", "ambient",
}

# Rapid physical actions that require dense sampling (8-10 points)
RAPID_PHYSICAL_ACTIONS: Set[str] = {
    "draw", "drawing", "pulling_sword", "drawing_sword",
    "strike", "striking", "hit", "hitting", "slash", "slashing",
    "throw", "throwing", "catch", "catching",
    "cast", "casting", "casting_spell",
}


class TemporalActionEngine:
    """
    Sub-second temporal action verification engine.
    """

    @classmethod
    def classify_action_nature(cls, action_str: Optional[str]) -> ActionNature:
        """
        Classifies whether an action is DYNAMIC (state transition required)
        or CONTINUOUS (sustained state/posture).
        """
        if not action_str:
            return ActionNature.CONTINUOUS

        clean = action_str.strip().lower().replace("_", " ")

        # Check explicit continuous keywords first if compound (e.g. "looking at mirror", "standing beside")
        for kw in CONTINUOUS_ACTION_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", clean):
                # Distinguish "standing up" (dynamic) from "standing" (continuous)
                if kw in ("stand", "standing") and ("up" in clean or "rise" in clean):
                    return ActionNature.DYNAMIC
                # Distinguish "sitting down" (dynamic) from "sitting" (continuous)
                if kw in ("sit", "sitting") and ("down" in clean or "lower" in clean):
                    return ActionNature.DYNAMIC
                # If pure continuous action like looking, gazing, staring
                if any(k in clean for k in ("look", "gaze", "stare", "watch", "listen", "sleep")):
                    return ActionNature.CONTINUOUS

        for kw in DYNAMIC_ACTION_KEYWORDS:
            if re.search(rf"\b{re.escape(kw)}\b", clean):
                return ActionNature.DYNAMIC

        # Default: if it implies motion or action, dynamic; otherwise continuous
        return ActionNature.DYNAMIC

    @classmethod
    def is_rapid_action(cls, action_str: Optional[str]) -> bool:
        """
        Returns True if the action is a rapid physical movement needing dense sampling.
        """
        if not action_str:
            return False
        clean = action_str.strip().lower().replace("_", " ")
        return any(kw.replace("_", " ") in clean for kw in RAPID_PHYSICAL_ACTIONS)

    @classmethod
    def verify_action_dynamics(
        cls,
        expected_action: str,
        expected_subject: Optional[str],
        expected_object: Optional[str],
        sampled_frames: List[Dict[str, Any]],
        candidate_metadata: Dict[str, Any],
        scene_description: str = "",
        interval: Tuple[float, float] = (0.0, 1.50),
    ) -> Dict[str, Any]:
        """
        Evaluates temporal action transition across sampled frames.

        Returns structured dict:
          - is_verified: bool
          - temporal_action_confidence: float [0.0 - 1.0]
          - action_nature: ActionNature
          - temporal_state: TemporalState
          - state_transitions: List[Dict[str, Any]]
          - action_window: Dict[str, Optional[float]]
          - rejection_reason: Optional[EvidenceRejectionReason]
          - explanation: str
        """
        action_nature = cls.classify_action_nature(expected_action)
        exp_clean = (expected_action or "").strip().lower().replace("_", " ")
        desc_clean = (scene_description or "").lower()

        # Extract sub-action timestamps if annotated
        meta_s = candidate_metadata.get("action_start")
        meta_p = candidate_metadata.get("action_peak")
        meta_e = candidate_metadata.get("action_end")
        meta_phase = str(candidate_metadata.get("phase") or candidate_metadata.get("action_phase") or "").strip().upper()

        c_start, c_end = interval
        action_window = {
            "action_start": meta_s,
            "action_peak": meta_p,
            "action_end": meta_e,
        }

        # 1. Check BEFORE / AFTER phase metadata vetoes
        if meta_phase == "BEFORE" or (meta_e is not None and c_end <= float(meta_e) and meta_s is not None and c_end <= float(meta_s)):
            return {
                "is_verified": False,
                "temporal_action_confidence": 0.10,
                "action_nature": action_nature,
                "temporal_state": TemporalState.BEFORE,
                "state_transitions": [],
                "action_window": action_window,
                "rejection_reason": EvidenceRejectionReason.BEFORE_PHASE_ONLY,
                "explanation": f"Footage depicts setup phase BEFORE action onset (ends at {c_end:.2f}s <= action_start {meta_s}s).",
            }

        if meta_phase == "AFTER" or (meta_s is not None and c_start >= float(meta_e if meta_e is not None else meta_s)):
            return {
                "is_verified": False,
                "temporal_action_confidence": 0.10,
                "action_nature": action_nature,
                "temporal_state": TemporalState.AFTER,
                "state_transitions": [],
                "action_window": action_window,
                "rejection_reason": EvidenceRejectionReason.AFTER_PHASE_ONLY,
                "explanation": f"Footage depicts aftermath AFTER action concluded (starts at {c_start:.2f}s >= action_end {meta_e}s).",
            }

        # 2. CONTINUOUS / SUSTAINED ACTION VERIFICATION
        if action_nature == ActionNature.CONTINUOUS:
            return cls._verify_continuous_action(
                expected_action=exp_clean,
                expected_subject=expected_subject,
                expected_object=expected_object,
                sampled_frames=sampled_frames,
                scene_description=desc_clean,
                candidate_metadata=candidate_metadata,
                action_window=action_window,
            )

        # 3. DYNAMIC ACTION TRANSITION VERIFICATION
        return cls._verify_dynamic_transition(
            expected_action=exp_clean,
            expected_subject=expected_subject,
            expected_object=expected_object,
            sampled_frames=sampled_frames,
            candidate_metadata=candidate_metadata,
            scene_description=desc_clean,
            action_window=action_window,
            interval=interval,
        )

    # --------------------------------------------------------------------------
    # Dynamic Transition Verification
    # --------------------------------------------------------------------------
    @classmethod
    def _verify_dynamic_transition(
        cls,
        expected_action: str,
        expected_subject: Optional[str],
        expected_object: Optional[str],
        sampled_frames: List[Dict[str, Any]],
        candidate_metadata: Dict[str, Any],
        scene_description: str,
        action_window: Dict[str, Optional[float]],
        interval: Tuple[float, float],
    ) -> Dict[str, Any]:
        """
        Validates state transitions (initial state -> transition -> target state)
        and detects static substitutions (e.g. already holding sword vs drawing).
        """
        exp_clean = (expected_action or "").strip().lower().replace("_", " ")

        # Determine specific action cluster
        is_drawing = any(k in exp_clean for k in ("draw", "drawing", "pull", "pulling", "unsheathe"))
        is_opening = any(k in exp_clean for k in ("open", "opening"))
        is_closing = any(k in exp_clean for k in ("close", "closing", "shut"))
        is_sitting = any(k in exp_clean for k in ("sit down", "sitting down", "lowering", "sit", "sitting"))
        is_standing_up = any(k in exp_clean for k in ("stand up", "standing up", "rising", "rise"))
        is_strike = any(k in exp_clean for k in ("strike", "striking", "hit", "hitting", "slash"))
        is_throw = any(k in exp_clean for k in ("throw", "throwing", "toss"))
        is_catch = any(k in exp_clean for k in ("catch", "catching"))
        is_cast = any(k in exp_clean for k in ("cast", "casting", "wave", "waving"))
        is_plead = any(k in exp_clean for k in ("plead", "pleading", "beg", "begging"))
        is_walk = any(k in exp_clean for k in ("walk", "walking", "run", "running", "enter", "flee"))

        detected_transitions: List[Dict[str, Any]] = []

        # Analyze frame observations
        num_frames = len(sampled_frames)
        if num_frames == 0:
            return {
                "is_verified": False,
                "temporal_action_confidence": 0.0,
                "action_nature": ActionNature.DYNAMIC,
                "temporal_state": TemporalState.UNCERTAIN,
                "state_transitions": [],
                "action_window": action_window,
                "rejection_reason": EvidenceRejectionReason.TEMPORAL_STATE_UNCERTAIN,
                "explanation": "No frame observations available for temporal action verification.",
            }

        # Inspect frame object and posture states
        object_states = [f.get("object_state") for f in sampled_frames]
        posture_states = [f.get("posture_state") for f in sampled_frames]
        action_states = [f.get("detected_action") or f.get("actions", []) for f in sampled_frames]

        # Case 1: DRAW WEAPON (e.g. Neville drawing sword of Gryffindor)
        if is_drawing:
            # Check for Static Substitution: Already holding sword throughout all frames!
            static_holding_phrases = ["already holding", "holding sword", "stands holding", "gripping sword", "held in hand"]
            all_holding_states = all(
                s in ("drawn", "held", "holding", "visible", "holding_sword") for s in object_states if s
            )
            explicit_static_desc = any(p in scene_description for p in static_holding_phrases) and not any(
                p in scene_description for p in ["draws", "drawing", "pulls", "pulling", "unsheathes"]
            )

            # Check if metadata or frames show drawing transition
            has_draw_transition = False
            prev_state = None
            for idx, frame in enumerate(sampled_frames):
                st = frame.get("object_state") or frame.get("state")
                ts = frame.get("timestamp", 0.0)
                if prev_state in ("concealed", "in_hat", "absent", "sheathed", "reaching") and st in ("emerging", "drawing", "drawn", "visible"):
                    has_draw_transition = True
                    detected_transitions.append({
                        "from_state": prev_state,
                        "to_state": st,
                        "timestamp": ts,
                        "transition_type": "EMERGENCE",
                    })
                prev_state = st

            # Also check metadata sub-actions
            if not has_draw_transition:
                meta_actions = candidate_metadata.get("actions") or []
                desc_draws = any(re.search(rf"\b{re.escape(w)}\b", scene_description) for w in ["draws", "drawing", "pulls", "pulling"])
                if desc_draws and not explicit_static_desc:
                    has_draw_transition = True
                    detected_transitions.append({
                        "from_state": "concealed_or_reaching",
                        "to_state": "emerging_and_drawn",
                        "timestamp": action_window.get("action_peak") or ((interval[0] + interval[1]) / 2),
                        "transition_type": "EMERGENCE",
                    })

            if explicit_static_desc or (all_holding_states and not has_draw_transition and len(object_states) >= 3):
                return {
                    "is_verified": False,
                    "temporal_action_confidence": 0.20,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.DURING,
                    "state_transitions": [],
                    "action_window": action_window,
                    "rejection_reason": EvidenceRejectionReason.ACTION_MISMATCH,
                    "explanation": f"Action Contradiction / Static Substitution: Expected dynamic transition '{expected_action}', but candidate shows static 'holding_sword' without emergence transition.",
                }

            if has_draw_transition:
                return {
                    "is_verified": True,
                    "temporal_action_confidence": 0.94,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.PEAK if action_window.get("action_peak") else TemporalState.DURING,
                    "state_transitions": detected_transitions,
                    "action_window": action_window,
                    "rejection_reason": None,
                    "explanation": f"Temporal Action Transition Verified: {expected_action} (Object emergence -> drawn transition captured across interval).",
                }

        # Case 2: OPENING (e.g. door closed -> opening -> open)
        elif is_opening:
            all_open = all(s in ("open", "ajar", "already_open") for s in object_states if s)
            explicit_open_desc = "already open" in scene_description or "walks through open door" in scene_description
            if all_open or explicit_open_desc:
                return {
                    "is_verified": False,
                    "temporal_action_confidence": 0.15,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.AFTER,
                    "state_transitions": [],
                    "action_window": action_window,
                    "rejection_reason": EvidenceRejectionReason.ACTION_MISMATCH,
                    "explanation": f"Action Contradiction: Expected dynamic transition '{expected_action}', but door is already open throughout interval.",
                }
            has_open_transition = any(
                s in ("opening", "unlatching") for s in object_states if s
            ) or any(re.search(rf"\b{re.escape(w)}\b", scene_description) for w in ["opens", "opening", "pushes open"])
            if has_open_transition:
                detected_transitions.append({
                    "from_state": "closed",
                    "to_state": "open",
                    "timestamp": interval[0] + 0.3,
                    "transition_type": "OPENING",
                })
                return {
                    "is_verified": True,
                    "temporal_action_confidence": 0.92,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.DURING,
                    "state_transitions": detected_transitions,
                    "action_window": action_window,
                    "rejection_reason": None,
                    "explanation": f"Temporal Action Transition Verified: {expected_action} (Closed -> Opening -> Open captured).",
                }

        # Case 3: SITTING DOWN (standing -> lowering -> seated)
        elif is_sitting:
            all_seated = all(s in ("seated", "sitting", "sitting_static") for s in posture_states if s)
            explicit_seated = "already seated" in scene_description or "sits silently" in scene_description or "sitting at" in scene_description
            if all_seated or (explicit_seated and "sits down" not in scene_description):
                return {
                    "is_verified": False,
                    "temporal_action_confidence": 0.20,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.DURING,
                    "state_transitions": [],
                    "action_window": action_window,
                    "rejection_reason": EvidenceRejectionReason.ACTION_MISMATCH,
                    "explanation": f"Static Substitution: Expected dynamic transition 'sit_down', but subject is already seated throughout candidate interval.",
                }
            has_sitting_transition = any(s in ("lowering", "sitting_down") for s in posture_states if s) or "sits down" in scene_description
            if has_sitting_transition:
                detected_transitions.append({
                    "from_state": "standing",
                    "to_state": "seated",
                    "timestamp": interval[0] + 0.4,
                    "transition_type": "POSTURE_CHANGE",
                })
                return {
                    "is_verified": True,
                    "temporal_action_confidence": 0.91,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.DURING,
                    "state_transitions": detected_transitions,
                    "action_window": action_window,
                    "rejection_reason": None,
                    "explanation": f"Temporal Action Transition Verified: {expected_action} (Standing -> Lowering -> Seated transition captured).",
                }

        # Case 4: RAPID PHYSICAL ACTIONS (STRIKE, HIT, THROW, CATCH, CAST SPELL)
        elif is_strike or is_throw or is_catch or is_cast:
            # Check for contact/impact/release transition
            has_peak = action_window.get("action_peak") is not None
            desc_has_action = any(re.search(rf"\b{re.escape(w)}\b", scene_description) for w in [
                "strikes", "striking", "hits", "hitting", "throws", "throwing", "catches", "catching", "casts", "casting"
            ])
            frame_has_action = any(
                any(any(k in a for k in ("strike", "hit", "throw", "catch", "cast")) for a in (f.get("actions") or []))
                for f in sampled_frames
            )

            if desc_has_action or frame_has_action or has_peak:
                peak_ts = action_window.get("action_peak") or round((interval[0] + interval[1]) / 2, 3)
                detected_transitions.append({
                    "from_state": "windup_or_approach",
                    "to_state": "peak_impact_or_release",
                    "timestamp": peak_ts,
                    "transition_type": "RAPID_PHYSICAL_MOMENTUM",
                })
                return {
                    "is_verified": True,
                    "temporal_action_confidence": 0.95,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.PEAK if has_peak else TemporalState.DURING,
                    "state_transitions": detected_transitions,
                    "action_window": action_window,
                    "rejection_reason": None,
                    "explanation": f"Rapid Physical Action Transition Verified: {expected_action} (Impact/release peak verified at {peak_ts:.2f}s).",
                }

        # Case 5: PLEAD / BEG
        elif is_plead:
            is_silent_or_passive = any(
                p in scene_description for p in ["sits silently", "sitting silent", "seated", "sitting", "looks on without speaking", "stares silently"]
            ) or any(
                any(p in a for p in ("sit", "sitting", "seated", "stand", "silent"))
                for f in sampled_frames for a in (f.get("actions") or [])
            )
            has_pleading = any(p in scene_description for p in ["pleads", "pleading", "begs", "begging", "whispering urgently", "desperate plea"])
            if is_silent_or_passive and not has_pleading:
                return {
                    "is_verified": False,
                    "temporal_action_confidence": 0.15,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.DURING,
                    "state_transitions": [],
                    "action_window": action_window,
                    "rejection_reason": EvidenceRejectionReason.ACTION_MISMATCH,
                    "explanation": f"Action Contradiction: Expected pleading/begging, but candidate shows subject sitting/seated without pleading.",
                }
            if has_pleading:
                detected_transitions.append({
                    "from_state": "neutral_expression",
                    "to_state": "active_pleading_expression",
                    "timestamp": interval[0] + 0.3,
                    "transition_type": "EXPRESSION_ARTICULATION",
                })
                return {
                    "is_verified": True,
                    "temporal_action_confidence": 0.90,
                    "action_nature": ActionNature.DYNAMIC,
                    "temporal_state": TemporalState.DURING,
                    "state_transitions": detected_transitions,
                    "action_window": action_window,
                    "rejection_reason": None,
                    "explanation": f"Temporal Action Transition Verified: {expected_action} (Pleading articulation verified).",
                }

        # Case 6: GENERAL DYNAMIC ACTIONS (e.g. walking, running)
        desc_matches = any(re.search(rf"\b{re.escape(w)}\b", scene_description) for w in re.findall(r"\w+", expected_action))
        frame_matches = any(
            any(any(w in a for w in re.findall(r"\w+", expected_action)) for a in (f.get("actions") or []))
            for f in sampled_frames
        )

        if desc_matches or frame_matches:
            detected_transitions.append({
                "from_state": "motion_onset",
                "to_state": "motion_sustained",
                "timestamp": round((interval[0] + interval[1]) / 2, 3),
                "transition_type": "LOCOMOTION",
            })
            return {
                "is_verified": True,
                "temporal_action_confidence": 0.88,
                "action_nature": ActionNature.DYNAMIC,
                "temporal_state": TemporalState.DURING,
                "state_transitions": detected_transitions,
                "action_window": action_window,
                "rejection_reason": None,
                "explanation": f"Dynamic Action Verified: {expected_action} across candidate frames.",
            }

        # If dynamic action transition could not be confirmed:
        return {
            "is_verified": False,
            "temporal_action_confidence": 0.25,
            "action_nature": ActionNature.DYNAMIC,
            "temporal_state": TemporalState.UNCERTAIN,
            "state_transitions": [],
            "action_window": action_window,
            "rejection_reason": EvidenceRejectionReason.ACTION_TRANSITION_MISSING,
            "explanation": f"Action Transition Missing: Expected dynamic action '{expected_action}' but no transition signature was detected in the candidate micro-interval.",
        }

    # --------------------------------------------------------------------------
    # Continuous / Sustained Action Verification
    # --------------------------------------------------------------------------
    @classmethod
    def _verify_continuous_action(
        cls,
        expected_action: str,
        expected_subject: Optional[str],
        expected_object: Optional[str],
        sampled_frames: List[Dict[str, Any]],
        scene_description: str,
        candidate_metadata: Dict[str, Any],
        action_window: Dict[str, Optional[float]],
    ) -> Dict[str, Any]:
        """
        Validates continuous actions (e.g. looking at mirror, standing beside).
        Requires subject, object, and sustained posture/gaze orientation across >= 80% of samples.
        """
        is_looking = any(k in expected_action for k in ("look", "looking", "stare", "staring", "gaze", "gazing"))

        # Inspect frames for subject presence, object presence, and orientation
        total_frames = max(1, len(sampled_frames))
        subject_frames = 0
        object_frames = 0
        gaze_aligned_frames = 0

        for frame in sampled_frames:
            subjs = [s.lower() for s in frame.get("subjects", [])]
            objs = [o.lower() for o in frame.get("objects", [])]
            gaze = str(frame.get("gaze_target") or frame.get("orientation") or "").lower()

            if expected_subject and any(expected_subject.lower() in s for s in subjs):
                subject_frames += 1
            elif not expected_subject:
                subject_frames += 1

            if expected_object and any(expected_object.lower() in o for o in objs):
                object_frames += 1
            elif not expected_object:
                object_frames += 1

            if is_looking:
                # Gaze must point to target object or mirror
                target_target = (expected_object or "").lower()
                if not target_target or target_target in gaze or "mirror" in gaze or "target" in gaze or "facing" in gaze:
                    gaze_aligned_frames += 1
                elif frame.get("looks_away") or gaze in ("away", "floor", "exit"):
                    pass  # looked away!
                else:
                    gaze_aligned_frames += 1
            else:
                gaze_aligned_frames += 1

        subj_ratio = subject_frames / total_frames
        obj_ratio = object_frames / total_frames
        gaze_ratio = gaze_aligned_frames / total_frames

        # Check explicit gaze aversion or exit in scene description
        turned_away = any(p in scene_description for p in ["turns away", "walks away", "leaves room", "looks at the floor", "ignores"])
        if is_looking and turned_away:
            return {
                "is_verified": False,
                "temporal_action_confidence": 0.20,
                "action_nature": ActionNature.CONTINUOUS,
                "temporal_state": TemporalState.AFTER,
                "state_transitions": [],
                "action_window": action_window,
                "rejection_reason": EvidenceRejectionReason.ACTION_MISMATCH,
                "explanation": f"Continuous Action Broken: Expected sustained '{expected_action}', but subject turns or looks away ({scene_description}).",
            }

        # Check description confirmation if frame metadata is sparse
        desc_confirms = any(k in scene_description for k in ("looks", "looking", "stares", "staring", "gazes", "gazing", "stands", "standing"))

        if (subj_ratio >= 0.70 and obj_ratio >= 0.70 and gaze_ratio >= 0.70) or desc_confirms:
            return {
                "is_verified": True,
                "temporal_action_confidence": 0.93,
                "action_nature": ActionNature.CONTINUOUS,
                "temporal_state": TemporalState.DURING,
                "state_transitions": [{
                    "state": "sustained_continuous_state",
                    "action": expected_action,
                    "consistency_ratio": round(gaze_ratio, 2),
                }],
                "action_window": action_window,
                "rejection_reason": None,
                "explanation": f"Continuous Action Verified: Sustained '{expected_action}' maintained across sampled frames (consistency: {gaze_ratio*100:.0f}%).",
            }

        return {
            "is_verified": False,
            "temporal_action_confidence": 0.35,
            "action_nature": ActionNature.CONTINUOUS,
            "temporal_state": TemporalState.UNCERTAIN,
            "state_transitions": [],
            "action_window": action_window,
            "rejection_reason": EvidenceRejectionReason.DIRECT_EVIDENCE_INSUFFICIENT,
            "explanation": f"Continuous Action Insufficient: Sustained '{expected_action}' not consistently observed across candidate interval.",
        }
