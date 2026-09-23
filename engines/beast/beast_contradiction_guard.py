"""
STORY FORGE — BEAST Contradiction Guard (Phase 12)
================================================================================
Implements hard contradiction detection and anti-hallucination semantic filtering:
  1. Detects narrative era / character age mismatches (e.g. Year 1 Sorting vs Year 7 Battle).
  2. Enforces explicit negative constraints (e.g. "reject battle of hogwarts", "reject sword").
  3. Detects diametrically opposed actions (e.g. pleading on stool vs sprinting through corridor).
  4. Penalizes or hard-rejects candidates where character presence exists but action/evidence contradicts.
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional, Set

from core.beast_visual_types import BeastVisualRequirement, BeastCandidateShot, NarrativeEra
from core.storyboard_types import VisualRole

logger = logging.getLogger("BeastContradictionGuard")

# Opposed action pairs that constitute immediate semantic contradiction
OPPOSED_ACTION_PAIRS: List[Tuple[Set[str], Set[str], str]] = [
    (
        {"pleading", "begging", "arguing", "sitting on stool", "sorting hat"},
        {"battle", "fighting", "dueling", "striking nagini", "drawing sword", "war", "ruins", "sword of gryffindor"},
        "Narration requires Year 1 Sorting Hat argument on stool, but candidate depicts Year 7 Battle of Hogwarts combat"
    ),
    (
        {"mirror of erised", "looking into mirror", "staring at parents"},
        {"running in corridor", "broomstick", "quidditch", "flying", "fighting troll"},
        "Narration requires quiet reflection at Mirror of Erised, but candidate depicts high-speed running or action"
    ),
    (
        {"potion", "potions classroom", "brewing", "riddle chamber"},
        {"quidditch", "flying", "outdoor grounds", "train station"},
        "Narration requires subterranean potion or dungeon setting, but candidate depicts open-air sports or transit"
    ),
    (
        {"slaying nagini", "decapitating snake", "drawing sword in battle"},
        {"sorting stool", "first year sorting", "feast in great hall", "childhood classroom"},
        "Narration requires heroic final Horcrux slaying with sword, but candidate depicts childhood first-year feast"
    ),
]


class BeastContradictionGuard:
    """
    Detects semantic contradictions between narrative beat requirements and candidate footage.
    """

    @classmethod
    def evaluate_contradiction(
        cls,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
    ) -> Tuple[bool, float, List[str]]:
        """
        Evaluates whether candidate shot contradicts the narration requirement.
        Returns:
            (has_contradiction: bool, penalty_score: float, contradiction_reasons: List[str])
        """
        reasons: List[str] = []
        desc_lower = shot.scene_description.lower()
        actions_lower = " ".join(shot.actions_depicted).lower()
        objs_lower = " ".join(shot.objects_present).lower()
        full_shot_text = f"{desc_lower} {actions_lower} {objs_lower}"

        # 1. Narrative Era / Age Conflict
        if requirement.expected_era != NarrativeEra.ANY and shot.narrative_era != NarrativeEra.ANY:
            if requirement.expected_era == NarrativeEra.YEAR_1 and shot.narrative_era == NarrativeEra.YEAR_7:
                reasons.append(
                    f"Era Mismatch: Narration specifies Year 1 canon, but candidate shot is from Year 7 ({shot.shot_id})"
                )
            elif requirement.expected_era == NarrativeEra.YEAR_7 and shot.narrative_era == NarrativeEra.YEAR_1:
                reasons.append(
                    f"Era Mismatch: Narration specifies Year 7 climax, but candidate shot is from Year 1 ({shot.shot_id})"
                )

        # 2. Negative Constraints Verification
        for neg in requirement.negative_constraints:
            neg_clean = neg.lower().replace("reject ", "").strip()
            # If negative constraint keywords are detected in the candidate (including digits like '7', '1')
            words = [w for w in re.findall(r"\b[a-z0-9_-]+\b", neg_clean) if len(w) >= 1 and (len(w) >= 3 or w.isdigit())]
            if words and all(w in full_shot_text for w in words):
                reasons.append(f"Negative Constraint Triggered: Shot matches forbidden criteria '{neg}'")

        # 3. Forbidden Characters Verification
        for fc in requirement.forbidden_characters:
            fc_clean = fc.lower().strip()
            if any(fc_clean in c.lower() for c in shot.characters_present) or re.search(rf"\b{re.escape(fc_clean)}\b", desc_lower):
                reasons.append(f"Forbidden Character Detected: '{fc}' is present in shot")

        # 4. Action Opposition & Semantic Inversion
        req_text_lower = f"{requirement.narration_text.lower()} {requirement.required_action.lower()}"
        for set_req, set_cand, explanation in OPPOSED_ACTION_PAIRS:
            if any(term in req_text_lower for term in set_req):
                if any(term in full_shot_text for term in set_cand):
                    reasons.append(f"Opposed Action Contradiction: {explanation}")

        # 5. Visual Role Integrity (DIRECT_EVIDENCE cannot be satisfied by unanchored background)
        if requirement.visual_role == VisualRole.DIRECT_EVIDENCE:
            if requirement.primary_subject and not any(
                requirement.primary_subject.lower() in c.lower() for c in shot.characters_present
            ):
                # If neither the primary character nor the primary object is present in direct evidence
                if requirement.required_objects and not any(
                    any(obj.lower() in so.lower() for so in shot.objects_present)
                    for obj in requirement.required_objects
                ):
                    reasons.append(
                        f"Direct Evidence Violation: Neither required subject '{requirement.primary_subject}' "
                        f"nor required objects {requirement.required_objects} are present in shot"
                    )

        has_contradiction = len(reasons) > 0
        penalty = 100.0 if has_contradiction else 0.0

        if has_contradiction:
            logger.debug(
                "Contradiction detected for beat '%s' vs shot '%s': %s",
                requirement.beat_id, shot.shot_id, "; ".join(reasons)
            )

        return has_contradiction, penalty, reasons
