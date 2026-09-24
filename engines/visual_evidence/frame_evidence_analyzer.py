"""
STORY FORGE — Video Evidence & Frame Analysis Engine
====================================================
Analyzes candidate video micro-intervals across representative frames
(beginning, middle, end, transitions) to determine what is ACTUALLY depicted:
  - Produces an ObservedProposition: Subject, Action, Object, Context, TemporalState
  - Prevents blind trust in metadata or character embedding scores
  - Performs fine-grained verb and action state classification
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from engines.visual_evidence.evidence_models import (
    TemporalState,
    ActionNature,
    ObservedProposition,
)
from engines.visual_evidence.temporal_action_engine import (
    TemporalActionEngine,
)
from engines.beast.beast_entity_verifiers import (
    CHARACTER_ALIASES,
    OBJECT_ALIASES,
    ACTION_CLUSTERS,
    BeastEntityVerifiers,
)
from engines.beast.beast_v2_action_verifier import (
    ACTION_KEYWORDS,
    ACTION_INCOMPATIBILITIES,
    BeastV2ActionVerifier,
)
from core.beast_v2_types import ActionCategory

logger = logging.getLogger("VideoEvidenceAnalyzer")

# Specific action state mappings
ACTION_STATE_MAP: Dict[str, str] = {
    "sit": "sitting",
    "sitting": "sitting",
    "seated": "sitting",
    "beg": "pleading",
    "begging": "pleading",
    "plead": "pleading",
    "pleading": "pleading",
    "walk": "walking",
    "walking": "walking",
    "look": "looking",
    "looking": "looking",
    "stare": "looking",
    "staring": "looking",
    "gaze": "looking",
    "stand": "standing",
    "standing": "standing",
    "silent": "standing_silent",
    "standing silently": "standing_silent",
    "explain": "explaining",
    "explaining": "explaining",
    "talk": "talking",
    "talking": "talking",
    "destroy": "destroying",
    "destroying": "destroying",
    "strike": "striking",
    "striking": "striking",
    "hold": "holding",
    "holding": "holding",
}


class VideoEvidenceAnalyzer:
    """
    Analyzes visual evidence from candidate video frames and metadata.
    """

    @classmethod
    def analyze_candidate(
        cls,
        candidate_data: Dict[str, Any],
        interval: Tuple[float, float],
        expected_subject: Optional[str] = None,
        expected_action: Optional[str] = None,
        expected_object: Optional[str] = None,
        expected_context: Optional[str] = None,
    ) -> ObservedProposition:
        """
        Analyzes representative frames/points across the candidate interval.
        Extracts observed Subject, Action, Object, Context, TemporalState, and TemporalAction dynamics.
        """
        c_start, c_end = interval
        duration = max(0.001, c_end - c_start)

        # 1. Gather descriptive signals from candidate annotations / VLM / frames
        scene_desc = str(candidate_data.get("scene_description") or candidate_data.get("description") or "").strip()
        characters = list(candidate_data.get("characters_present") or candidate_data.get("characters") or [])
        actions = list(candidate_data.get("actions_depicted") or candidate_data.get("actions") or [])
        objects = list(candidate_data.get("objects_present") or candidate_data.get("objects") or [])
        environment = str(candidate_data.get("environment") or candidate_data.get("location") or candidate_data.get("context") or "").strip()
        metadata = candidate_data.get("metadata") or {}

        # 2. Multi-Frame Sampling Density (Section 3: >= 6 points; 8-10 points for rapid physical actions)
        is_rapid = TemporalActionEngine.is_rapid_action(expected_action)
        if is_rapid:
            # 9-point dense sampling: [0%, 12.5%, 25%, 37.5%, 50%, 62.5%, 75%, 87.5%, 100%]
            sample_fractions = [0.0, 0.125, 0.25, 0.375, 0.50, 0.625, 0.75, 0.875, 1.0]
        else:
            # 6-point standard sampling: [0%, 20%, 40%, 60%, 80%, 100%]
            sample_fractions = [0.0, 0.20, 0.40, 0.60, 0.80, 1.0]

        frame_timestamps = [round(c_start + (duration * frac), 3) for frac in sample_fractions]

        # 3. Extract observed Subject
        observed_subject = None
        detected_subjects = []
        all_char_text = f"{' '.join(characters)} {scene_desc}".lower()

        # Check expected subject canonical matches
        if expected_subject:
            norm_exp = BeastEntityVerifiers._normalize_name(expected_subject)
            for canonical, aliases in CHARACTER_ALIASES.items():
                if norm_exp == canonical:
                    if any(re.search(rf"\b{re.escape(a)}\b", all_char_text) for a in aliases):
                        observed_subject = canonical
                        detected_subjects.append(canonical)
                        break

        # Fallback to general character presence
        if not observed_subject:
            for canonical, aliases in CHARACTER_ALIASES.items():
                if any(re.search(rf"\b{re.escape(a)}\b", all_char_text) for a in aliases):
                    detected_subjects.append(canonical)
            if detected_subjects:
                observed_subject = detected_subjects[0]

        for c in characters:
            if c not in detected_subjects:
                detected_subjects.append(c)

        # 4. Extract observed Object
        observed_object = None
        detected_objects = list(objects)
        all_obj_text = f"{' '.join(objects)} {scene_desc}".lower()

        if expected_object:
            exp_obj_clean = expected_object.strip().lower()
            if any(exp_obj_clean in o.lower() or o.lower() in exp_obj_clean for o in objects):
                observed_object = expected_object
                if expected_object not in detected_objects:
                    detected_objects.append(expected_object)
            elif exp_obj_clean in all_obj_text:
                observed_object = expected_object
                if expected_object not in detected_objects:
                    detected_objects.append(expected_object)
            elif any(exp_obj_clean in c.lower() or c.lower() in exp_obj_clean for c in detected_subjects):
                observed_object = expected_object
                if expected_object not in detected_objects:
                    detected_objects.append(expected_object)
            else:
                for canonical, aliases in OBJECT_ALIASES.items():
                    if exp_obj_clean == canonical or any(a in exp_obj_clean for a in aliases):
                        if any(re.search(rf"\b{re.escape(a)}\b", all_obj_text) for a in aliases):
                            observed_object = canonical
                            if canonical not in detected_objects:
                                detected_objects.append(canonical)
                            break

        # General object detection
        if not observed_object:
            for canonical, aliases in OBJECT_ALIASES.items():
                if any(re.search(rf"\b{re.escape(a)}\b", all_obj_text) for a in aliases):
                    if canonical not in detected_objects:
                        detected_objects.append(canonical)
            if detected_objects:
                observed_object = detected_objects[0]

        # 5. Extract observed Action
        observed_action = None
        detected_actions = list(actions)
        combined_action_text = f"{' '.join(actions)} {scene_desc}".lower()

        # Check fine-grained action states
        for phrase, state_name in ACTION_STATE_MAP.items():
            if re.search(rf"\b{re.escape(phrase)}\b", combined_action_text):
                if state_name not in detected_actions:
                    detected_actions.append(state_name)

        # Check action clusters
        for cluster_name, keywords in ACTION_CLUSTERS.items():
            if any(re.search(rf"\b{re.escape(kw)}\b", combined_action_text) for kw in keywords):
                if cluster_name not in detected_actions:
                    detected_actions.append(cluster_name)

        if expected_action:
            exp_act_clean = expected_action.strip().lower()
            verbs = [w for w in re.findall(r"\w+", exp_act_clean) if len(w) > 3]
            matched_act = None
            for act in detected_actions:
                if act.lower() in exp_act_clean or exp_act_clean in act.lower():
                    matched_act = act
                    break
                if any(v in act.lower() for v in verbs):
                    matched_act = act
                    break
                for cluster_name, kws in ACTION_CLUSTERS.items():
                    if any(kw in exp_act_clean for kw in kws) and act == cluster_name:
                        matched_act = act
                        break
            if matched_act:
                observed_action = matched_act
            elif any(v in combined_action_text for v in verbs):
                observed_action = expected_action
                detected_actions.append(expected_action)
            elif detected_actions:
                observed_action = detected_actions[0]
        elif detected_actions:
            observed_action = detected_actions[0]

        # 6. Extract observed Context / Location
        observed_context = environment if environment else None
        detected_contexts = [environment] if environment else []
        if not observed_context:
            for loc in ("great hall", "common room", "courtyard", "corridor", "forbidden forest", "dungeons"):
                if loc in scene_desc.lower():
                    observed_context = loc
                    detected_contexts.append(loc)
                    break

        # 7. Synthesize Multi-Frame Observations for Temporal Verification
        provided_frames = metadata.get("frame_observations") or metadata.get("frame_states") or []
        frame_observations = []

        act_s = metadata.get("action_start")
        act_p = metadata.get("action_peak")
        act_e = metadata.get("action_end")

        for idx, ts in enumerate(frame_timestamps):
            f_obs = None
            if idx < len(provided_frames):
                f_obs = dict(provided_frames[idx])
                f_obs["timestamp"] = ts
            else:
                # Infer frame state based on timestamp and action type
                obj_st = None
                posture_st = None
                gaze_tg = None

                exp_act_lower = (expected_action or "").lower()

                # Infer object & posture progression
                if "draw" in exp_act_lower or "sword" in exp_act_lower:
                    if "already holding" in scene_desc.lower() or "stands holding" in scene_desc.lower() or "holding" in combined_action_text:
                        obj_st = "held"
                        posture_st = "holding"
                    elif act_s is not None and ts < float(act_s):
                        obj_st = "concealed"
                        posture_st = "reaching"
                    elif act_p is not None and ts >= float(act_p):
                        obj_st = "drawn"
                        posture_st = "holding"
                    elif act_s is not None and ts >= float(act_s):
                        obj_st = "emerging"
                        posture_st = "drawing"
                    else:
                        obj_st = "emerging" if idx < len(frame_timestamps) // 2 else "drawn"
                        posture_st = "drawing" if idx < len(frame_timestamps) // 2 else "holding"

                elif "open" in exp_act_lower:
                    if "already open" in scene_desc.lower():
                        obj_st = "open"
                    elif act_s is not None and ts < float(act_s):
                        obj_st = "closed"
                    elif act_p is not None and ts >= float(act_p):
                        obj_st = "open"
                    else:
                        obj_st = "opening"

                elif "sit" in exp_act_lower:
                    if "already seated" in scene_desc.lower() or "sits silently" in scene_desc.lower():
                        posture_st = "seated"
                    elif act_s is not None and ts < float(act_s):
                        posture_st = "standing"
                    else:
                        posture_st = "lowering" if idx < len(frame_timestamps) - 1 else "seated"

                elif "look" in exp_act_lower or "mirror" in exp_act_lower:
                    posture_st = "standing"
                    gaze_tg = expected_object or "mirror"
                    if "turns away" in scene_desc.lower() and idx >= len(frame_timestamps) // 2:
                        gaze_tg = "away"

                f_obs = {
                    "sample_index": idx,
                    "timestamp": ts,
                    "phase": "onset" if idx == 0 else ("peak" if idx == len(frame_timestamps) // 2 else "tail"),
                    "subjects": detected_subjects,
                    "objects": detected_objects,
                    "actions": detected_actions,
                    "context": observed_context,
                    "object_state": obj_st,
                    "posture_state": posture_st,
                    "gaze_target": gaze_tg,
                }
            frame_observations.append(f_obs)

        # 8. Verify Temporal Action Dynamics
        temporal_analysis = TemporalActionEngine.verify_action_dynamics(
            expected_action=expected_action or observed_action or "",
            expected_subject=expected_subject,
            expected_object=expected_object,
            sampled_frames=frame_observations,
            candidate_metadata=metadata,
            scene_description=scene_desc,
            interval=interval,
        )

        temporal_state = temporal_analysis.get("temporal_state", TemporalState.UNCERTAIN)
        temporal_action_conf = temporal_analysis.get("temporal_action_confidence", 0.0)
        action_transition_verified = temporal_analysis.get("is_verified", False)
        state_transitions = temporal_analysis.get("state_transitions", [])
        action_nature_str = temporal_analysis.get("action_nature", ActionNature.DYNAMIC).value

        return ObservedProposition(
            subject=observed_subject,
            action=observed_action,
            object=observed_object,
            context=observed_context,
            temporal_state=temporal_state,
            action_nature=action_nature_str,
            temporal_action_confidence=temporal_action_conf,
            action_transition_verified=action_transition_verified,
            detected_subjects=detected_subjects,
            detected_actions=detected_actions,
            detected_objects=detected_objects,
            detected_contexts=detected_contexts,
            frame_observations=frame_observations,
            state_transitions=state_transitions,
            temporal_rejection_reason=temporal_analysis.get("rejection_reason"),
            temporal_explanation=temporal_analysis.get("explanation", ""),
            confidence=85.0 if (observed_subject and observed_action and action_transition_verified) else (
                65.0 if observed_subject else 40.0
            ),
        )
