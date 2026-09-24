"""
STORY FORGE — BEAST V2 Action Verifier & Temporal Phase Inspector
================================================================================
Implements granular action categorization, action state verification,
and multi-frame temporal inspection (BEFORE, DURING, AFTER):
  - Classifies verbs and actions into explicit ActionCategory taxonomy
  - Detects Action State Contradictions (e.g. DESTROY vs merely HOLD)
  - Detects Emotional State Inversions (e.g. CRY vs LAUGH)
  - Inspects temporal phases to prevent mistaking aftermath/reaction for dynamic action
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Set

from core.beast_v2_types import (
    ActionCategory,
    TemporalPhase,
    MultiFrameTemporalAnalysis,
)
from core.beast_visual_types import BeastCandidateShot, MultiFrameSample

logger = logging.getLogger("BeastV2ActionVerifier")

# Pattern mappings for Action Categories
ACTION_KEYWORDS: Dict[ActionCategory, Set[str]] = {
    ActionCategory.PLEAD: {"plead", "pleaded", "pleading", "beg", "begged", "begging", "implore", "imploring"},
    ActionCategory.ARGUE: {"argue", "argued", "arguing", "dispute", "disputing", "confront", "objecting", "debate"},
    ActionCategory.HOLD: {"hold", "holding", "held", "carry", "carrying", "grasps", "grasping", "clutch"},
    ActionCategory.LOOK: {"look", "looking", "stare", "staring", "gaze", "gazing", "watch", "watching", "observing"},
    ActionCategory.WALK: {"walk", "walking", "walked", "stroll", "pacing"},
    ActionCategory.RUN: {"run", "running", "ran", "flee", "fleeing", "sprint", "sprinting", "chasing"},
    ActionCategory.TALK: {"talk", "talking", "speak", "speaking", "spoke", "whisper", "whispering", "shout", "announce"},
    ActionCategory.ATTACK: {"attack", "attacking", "charge", "charging", "lunge", "lunging"},
    ActionCategory.DEFEND: {"defend", "defending", "shield", "protect", "protecting", "block", "blocking"},
    ActionCategory.OPEN: {"open", "opening", "opened", "unlock", "unlocking"},
    ActionCategory.CLOSE: {"close", "closing", "closed", "shut"},
    ActionCategory.DESTROY: {"destroy", "destroying", "destroyed", "crush", "crushing", "smash", "smashing", "dissolve", "burn", "shatter"},
    ActionCategory.STRIKE: {"strike", "striking", "struck", "hit", "hitting", "stab", "stabbing", "stabbed", "slay", "slaying", "decapitate", "behead"},
    ActionCategory.CAST: {"cast", "casting", "wand", "spell", "incantation", "lumos", "expelliarmus", "curse"},
    ActionCategory.PICK_UP: {"pick up", "pull", "pulling", "pulled", "drawing", "drew", "unsheathe", "retrieve", "lift"},
    ActionCategory.DROP: {"drop", "dropping", "dropped", "release", "fall", "falling"},
    ActionCategory.TURN: {"turn", "turning", "turned", "spin", "spinning"},
    ActionCategory.ENTER: {"enter", "entering", "entered", "arrive", "arriving", "step in"},
    ActionCategory.EXIT: {"exit", "exiting", "leave", "leaving", "depart"},
    ActionCategory.REACT: {"react", "reacting", "gasp", "shocked", "flinch", "awed", "horrified"},
    ActionCategory.CRY: {"cry", "crying", "cried", "weep", "weeping", "tears", "sob", "sobbing"},
    ActionCategory.LAUGH: {"laugh", "laughing", "laughed", "smile", "smiling", "smirk", "smirking", "chuckle", "amused"},
    ActionCategory.FIGHT: {"fight", "fighting", "battle", "battling", "combat", "duel", "dueling"},
    ActionCategory.TRANSFORM: {"transform", "transforming", "morph", "animagus", "change into"},
}

# Incompatible / opposed action category pairs
# (RequiredCategory, CandidateCategory) -> Disqualification reason
ACTION_INCOMPATIBILITIES: List[Tuple[ActionCategory, ActionCategory, str]] = [
    (
        ActionCategory.DESTROY,
        ActionCategory.HOLD,
        "Narration requires destroying/annihilating the object, but candidate merely shows the character holding it"
    ),
    (
        ActionCategory.STRIKE,
        ActionCategory.HOLD,
        "Narration requires striking/slaying action, but candidate merely depicts static holding"
    ),
    (
        ActionCategory.CRY,
        ActionCategory.LAUGH,
        "Emotional contradiction: narration requires sadness/crying, but candidate depicts smiling/laughing"
    ),
    (
        ActionCategory.LAUGH,
        ActionCategory.CRY,
        "Emotional contradiction: narration requires lightheartedness/laughing, but candidate depicts weeping/crying"
    ),
    (
        ActionCategory.PLEAD,
        ActionCategory.FIGHT,
        "Action mismatch: narration requires pleading/begging, but candidate depicts high-intensity combat"
    ),
    (
        ActionCategory.PLEAD,
        ActionCategory.ATTACK,
        "Action mismatch: narration requires defensive pleading/begging, but candidate depicts aggressive attack"
    ),
]


class BeastV2ActionVerifier:
    """
    Evaluates fine-grained action alignment, state contradictions, and temporal phases.
    """

    @classmethod
    def classify_action(cls, action_text: str) -> ActionCategory:
        """
        Maps freeform action strings to canonical ActionCategory.
        """
        if not action_text:
            return ActionCategory.OTHER

        text_lower = action_text.lower()
        for cat, keywords in ACTION_KEYWORDS.items():
            for kw in keywords:
                if re.search(rf"\b{re.escape(kw)}\b", text_lower):
                    return cat

        return ActionCategory.OTHER

    @classmethod
    def verify_action_alignment(
        cls,
        required_action: str,
        candidate_actions: List[str],
        candidate_description: str = "",
    ) -> Tuple[float, Optional[ActionCategory], Optional[ActionCategory], List[str]]:
        """
        Compares required proposition action with candidate actions.
        Returns:
            (alignment_score: float [0..100],
             req_category: ActionCategory,
             cand_category: ActionCategory,
             contradictions: List[str])
        """
        if not required_action or not required_action.strip():
            # If no action is required by the proposition, neutrality (100% alignment)
            return 100.0, None, None, []

        req_cat = cls.classify_action(required_action)
        combined_cand_text = f"{' '.join(candidate_actions)} {candidate_description}".lower()
        cand_cat = cls.classify_action(combined_cand_text)

        contradictions: List[str] = []

        # Check explicit incompatibility matrix
        for inc_req, inc_cand, reason in ACTION_INCOMPATIBILITIES:
            if req_cat == inc_req and cand_cat == inc_cand:
                contradictions.append(f"Action State Contradiction: {reason}")
                return 0.0, req_cat, cand_cat, contradictions

        # Direct category match
        if req_cat == cand_cat and req_cat != ActionCategory.OTHER:
            return 100.0, req_cat, cand_cat, []

        # Check semantic action token overlap
        req_tokens = set(re.findall(r"\w+", required_action.lower()))
        cand_tokens = set(re.findall(r"\w+", combined_cand_text))
        stopwords = {"a", "an", "the", "in", "on", "at", "to", "for", "with", "and", "or", "of", "from"}
        req_clean = req_tokens - stopwords
        cand_clean = cand_tokens - stopwords

        if not req_clean:
            return 70.0, req_cat, cand_cat, []

        overlap = req_clean.intersection(cand_clean)
        jaccard = len(overlap) / len(req_clean)

        if jaccard >= 0.5:
            score = round(70.0 + (jaccard * 30.0), 2)
            return score, req_cat, cand_cat, []

        # Action is completely missing or distinct
        if cand_cat == ActionCategory.OTHER and not overlap:
            contradictions.append(
                f"Action Missing: Narration requires '{required_action}' ({req_cat.value}), "
                f"but candidate depicts '{candidate_actions}'"
            )
            return 15.0, req_cat, cand_cat, contradictions

        # Generic action mismatch
        contradictions.append(
            f"Action Mismatch: Narration requires '{req_cat.value}' but candidate depicts '{cand_cat.value}'"
        )
        return 20.0, req_cat, cand_cat, contradictions

    @classmethod
    def inspect_temporal_phases(
        cls,
        shot: BeastCandidateShot,
        required_action: str,
    ) -> Tuple[List[MultiFrameTemporalAnalysis], bool]:
        """
        Inspects multi-frame samples across BEFORE, DURING, AFTER phases.
        Returns:
            (analyses: List[MultiFrameTemporalAnalysis], action_confirmed_during: bool)
        """
        req_cat = cls.classify_action(required_action)
        results: List[MultiFrameTemporalAnalysis] = []

        mfs = shot.multi_frame_sample
        if not mfs or not mfs.timestamps or len(mfs.timestamps) < 3:
            # Synthetic / fallback 3-point timeline
            t_start = shot.start_seconds
            t_dur = shot.duration
            timestamps = [
                t_start + (t_dur * 0.15),  # BEFORE
                t_start + (t_dur * 0.50),  # DURING
                t_start + (t_dur * 0.85),  # AFTER
            ]
        else:
            n = len(mfs.timestamps)
            timestamps = [
                mfs.timestamps[0],
                mfs.timestamps[n // 2],
                mfs.timestamps[-1],
            ]

        phases = [TemporalPhase.BEFORE, TemporalPhase.DURING, TemporalPhase.AFTER]
        action_confirmed_during = False

        for phase, ts in zip(phases, timestamps):
            cand_cat = cls.classify_action(" ".join(shot.actions_depicted))
            
            # Determine action state relative to phase
            if phase == TemporalPhase.BEFORE:
                state = "PREPARATION"
            elif phase == TemporalPhase.DURING:
                if cand_cat == req_cat and req_cat is not None:
                    state = "PEAK_IMPACT"
                    action_confirmed_during = True
                else:
                    state = "STATIC" if cand_cat == ActionCategory.HOLD else "ACTIVITY"
            else:  # AFTER
                state = "AFTERMATH" if action_confirmed_during else "REACTION_ONLY"

            analysis = MultiFrameTemporalAnalysis(
                phase=phase,
                timestamp=ts,
                subjects_detected=list(shot.characters_present),
                objects_detected=list(shot.objects_present),
                action_detected=" ".join(shot.actions_depicted),
                action_category=cand_cat,
                action_state=state,
                confidence=85.0 if (phase == TemporalPhase.DURING and action_confirmed_during) else 70.0,
            )
            results.append(analysis)

        return results, action_confirmed_during
