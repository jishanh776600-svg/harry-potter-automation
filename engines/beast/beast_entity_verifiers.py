"""
STORY FORGE — BEAST Entity, Object, Action & Location Verifiers (Phases 5, 6, 7, 8)
================================================================================
Implements independent multi-criteria entity and action verification:
  - Phase 5: Character & Face Presence, Multi-Character Co-presence (MediaPipe-compatible)
  - Phase 6: Canonical Object Verification (Sorting Hat, Sword, Mirror of Erised, Horcruxes)
  - Phase 7: Action & Interaction Verification (Action matching + Temporal Motion analysis)
  - Phase 8: Location & Environmental Context Verification (Great Hall, Forest, etc.)
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Set

from core.beast_visual_types import BeastVisualRequirement, BeastCandidateShot
from core.composition_models import ShotScale

logger = logging.getLogger("BeastEntityVerifiers")

# Character alias dictionary for robust canonical resolution
CHARACTER_ALIASES: Dict[str, Set[str]] = {
    "neville": {"neville", "neville longbottom", "longbottom"},
    "harry": {"harry", "harry potter", "potter", "the boy who lived"},
    "ron": {"ron", "ron weasley", "weasley"},
    "hermione": {"hermione", "hermione granger", "granger"},
    "dumbledore": {"dumbledore", "albus dumbledore", "albus", "headmaster"},
    "snape": {"snape", "severus snape", "severus", "half-blood prince"},
    "voldemort": {"voldemort", "lord voldemort", "dark lord", "he who must not be named", "you-know-who", "tom riddle"},
    "malfoy": {"malfoy", "draco malfoy", "draco"},
    "mcgonagall": {"mcgonagall", "minerva mcgonagall", "professor mcgonagall"},
    "sorting hat": {"sorting hat", "hat"},
    "bellatrix": {"bellatrix", "bellatrix lestrange", "lestrange"},
    "molly": {"molly", "molly weasley", "mrs weasley"},
    "hagrid": {"hagrid", "rubeus hagrid"},
    "grawp": {"grawp", "giant", "giants", "death eater giants"},
    "kreacher": {"kreacher", "house-elf", "house elf", "house-elves", "house elves"},
    "centaur": {"centaur", "centaurs", "bane", "ronan", "magorian", "firenze"},
    "peeves": {"peeves", "poltergeist"},
    "lupin": {"lupin", "remus lupin", "professor lupin", "remus"},
    "sirius": {"sirius", "sirius black", "padfoot"},
    "ollivander": {"ollivander", "garrick ollivander", "mr ollivander", "wandmaker"},
    "dementor": {"dementor", "dementors", "the dementor"},
    "vernon": {"vernon", "vernon dursley", "uncle vernon", "mr dursley"},
    "dudley": {"dudley", "dudley dursley"},
    "petunia": {"petunia", "petunia dursley", "aunt petunia"},
    "flitwick": {"flitwick", "filius flitwick", "professor flitwick"},
    "ginny": {"ginny", "ginny weasley"},
    "george": {"george", "george weasley"},
    "fred": {"fred", "fred weasley"},
    "arthur": {"arthur", "arthur weasley", "mr weasley"},
    "cedric": {"cedric", "cedric diggory", "diggory"},
    "luna": {"luna", "luna lovegood", "lovegood"},
    "moody": {"moody", "mad-eye moody", "alastor moody", "mad-eye"},
    "umbridge": {"umbridge", "dolores umbridge", "professor umbridge"},
    "slughorn": {"slughorn", "horace slughorn", "professor slughorn"},
    "filch": {"filch", "argus filch"},
    "lockhart": {"lockhart", "gilderoy lockhart", "professor lockhart"},
    "quirrell": {"quirrell", "professor quirrell"},
    "dobby": {"dobby", "dobby the house-elf", "dobby the house elf"},
    "fawkes": {"fawkes", "phoenix", "the phoenix"},
    "basilisk": {"basilisk", "serpent of slytherin", "giant serpent"},
    "buckbeak": {"buckbeak", "hippogriff"},
    "thestral": {"thestral", "thestrals"},
    "pettigrew": {"pettigrew", "peter pettigrew", "wormtail", "scabbers"},
}

# Object alias mapping
OBJECT_ALIASES: Dict[str, Set[str]] = {
    "sorting hat": {"sorting hat", "hat", "the hat"},
    "sword": {"sword", "sword of gryffindor", "silver sword", "godric's sword", "godric sword"},
    "mirror": {"mirror", "mirror of erised", "erised"},
    "wand": {"wand", "elder wand", "hawthorn wand", "holly wand", "phoenix wand"},
    "elder wand": {"elder wand", "wand", "deathstick"},
    "locket": {"locket", "slytherin's locket", "regulus black locket", "regulus locket", "horcrux locket", "horcrux"},
    "bow": {"bow", "bows", "arrow", "arrows", "wooden bow", "iron-tipped arrows"},
    "cleaver": {"cleaver", "cleavers", "carving knife", "carving knives", "kitchen knives", "knives"},
    "snitch": {"snitch", "golden snitch"},
    "stool": {"stool", "wooden stool", "sorting stool"},
    "horcrux": {"horcrux", "nagini", "diadem", "locket", "cup", "ring", "diary"},
    "nagini": {"nagini", "snake", "serpent", "horcrux"},
    "remembrall": {"remembrall", "glass ball"},
    "cloak": {"cloak", "invisibility cloak"},
    "potion": {"potion", "cauldron", "vial", "potions"},
}

# Action equivalence clusters
ACTION_CLUSTERS: Dict[str, Set[str]] = {
    "pleading": {"plead", "pleaded", "pleading", "beg", "begged", "begging", "arguing", "argued", "disputing", "desperate"},
    "arguing": {"argue", "argued", "arguing", "confront", "confronted", "disputing", "pleading", "resisting"},
    "sitting": {"sat", "sit", "sitting", "seated", "on stool"},
    "standing": {"stand", "stood", "standing", "upright", "facing"},
    "crying": {"cried", "cry", "crying", "weep", "wept", "weeping", "tears", "terrified"},
    "fighting": {"fight", "fighting", "battle", "battling", "duel", "dueling", "combat", "striking", "sword", "brawling"},
    "dueling": {"duel", "dueling", "wand clash", "jets of light", "curse", "strike over heart", "spell clash", "beam"},
    "charging": {"charge", "charging", "gallop", "galloping", "rush", "rushing", "advance", "brandishing"},
    "drawing_sword": {"draw", "drawing", "pulled", "pulling", "unsheathed", "sword from hat", "silver sword"},
    "slaying": {"slaying", "slayed", "struck", "striking", "killed", "killing", "beheading", "decapitating", "destroying"},
    "staring": {"stare", "stared", "staring", "gaze", "gazing", "looking", "reflected", "beholding"},
    "raising_hand": {"raise hand", "raised hand", "hand raised", "answering", "volunteer"},
    "running": {"run", "running", "ran", "rushing", "chasing", "fleeing"},
    "whispering": {"whisper", "whispered", "whispering", "murmur", "muttering"},
}


class BeastEntityVerifiers:
    """
    Independent multi-entity and action verifier suite.
    """

    @staticmethod
    def _normalize_name(name: str) -> str:
        clean = name.strip().lower()
        for canonical, aliases in CHARACTER_ALIASES.items():
            if clean in aliases:
                return canonical
            if any(re.search(rf"\b{re.escape(a)}\b", clean) for a in aliases):
                return canonical
        return clean

    @classmethod
    def verify_character(
        cls,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
    ) -> Tuple[float, float, List[str]]:
        """
        Verifies primary and secondary character presence.
        Returns (primary_char_score [0..100], secondary_char_score [0..100], diagnostics).
        """
        diags = []
        shot_chars_norm = {cls._normalize_name(c) for c in shot.characters_present}
        # Also check shot scene description for character names
        desc_lower = shot.scene_description.lower()
        for canonical, aliases in CHARACTER_ALIASES.items():
            if any(re.search(rf"\b{re.escape(a)}\b", desc_lower) for a in aliases):
                shot_chars_norm.add(canonical)

        p_score = 0.0
        s_score = 0.0

        req_p = cls._normalize_name(requirement.primary_subject) if requirement.primary_subject else ""
        req_s = cls._normalize_name(requirement.secondary_subject) if requirement.secondary_subject else ""

        # Primary subject verification
        if not req_p:
            p_score = 100.0
        elif req_p in shot_chars_norm:
            p_score = 100.0
            diags.append(f"Primary character '{requirement.primary_subject}' verified.")
        else:
            p_score = 0.0
            diags.append(f"Primary character '{requirement.primary_subject}' NOT detected.")

        # Secondary subject verification
        if not req_s:
            s_score = 100.0
        elif req_s in shot_chars_norm:
            s_score = 100.0
            diags.append(f"Secondary character '{requirement.secondary_subject}' verified.")
        else:
            s_score = 0.0
            diags.append(f"Secondary character '{requirement.secondary_subject}' NOT detected.")

        return p_score, s_score, diags

    @classmethod
    def verify_object(
        cls,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
    ) -> Tuple[float, List[str]]:
        """
        Verifies required objects (e.g. Sorting Hat, Sword of Gryffindor, Mirror of Erised).
        Returns (object_score [0..100], diagnostics).
        """
        if not requirement.required_objects:
            return 100.0, ["No specific objects required."]

        shot_objs_clean = {o.strip().lower() for o in shot.objects_present}
        desc_lower = shot.scene_description.lower()

        matched_count = 0
        diags = []

        for req_obj in requirement.required_objects:
            obj_clean = req_obj.strip().lower()
            aliases = OBJECT_ALIASES.get(obj_clean, {obj_clean})
            found = False

            # Check explicit object tags
            for alias in aliases:
                if any(alias in so for so in shot_objs_clean) or re.search(rf"\b{re.escape(alias)}\b", desc_lower):
                    found = True
                    break

            if found:
                matched_count += 1
                diags.append(f"Object '{req_obj}' confirmed.")
            else:
                diags.append(f"Object '{req_obj}' missing.")

        score = (matched_count / len(requirement.required_objects)) * 100.0
        return round(score, 2), diags

    @classmethod
    def verify_action(
        cls,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
    ) -> Tuple[float, List[str]]:
        """
        Verifies whether candidate shot depicts the requested action.
        Distinguishes actions like 'arguing' vs 'standing' vs 'fighting'.
        """
        if not requirement.required_action:
            return 100.0, ["No specific action required."]

        req_act_lower = requirement.required_action.lower()
        shot_acts = [a.lower() for a in shot.actions_depicted]
        desc_lower = shot.scene_description.lower()

        # Resolve target action cluster
        target_cluster: Set[str] = set()
        for cluster_name, syns in ACTION_CLUSTERS.items():
            if any(syn in req_act_lower for syn in syns):
                target_cluster.update(syns)
        if not target_cluster:
            target_cluster = {w for w in re.findall(r"\b[a-z]+\b", req_act_lower) if len(w) >= 4}

        score = 0.0
        diags = []

        # Check explicit actions and scene description
        match_found = False
        for act in shot_acts:
            if any(term in act for term in target_cluster):
                match_found = True
                break

        if not match_found:
            for term in target_cluster:
                if re.search(rf"\b{re.escape(term)}\b", desc_lower):
                    match_found = True
                    break

        if match_found:
            score = 100.0
            diags.append(f"Action '{requirement.required_action}' confirmed.")
        else:
            # Partial credit if motion is active and general action aligns
            score = 15.0
            diags.append(f"Action '{requirement.required_action}' not explicitly depicted.")

        # Temporal motion check: if multi-frame sample shows dynamic motion when required
        if shot.multi_frame_sample and shot.multi_frame_sample.motion_scores:
            avg_motion = float(sum(shot.multi_frame_sample.motion_scores) / len(shot.multi_frame_sample.motion_scores))
            if "fighting" in target_cluster or "running" in target_cluster:
                if avg_motion < 5.0:
                    score = max(0.0, score - 30.0)
                    diags.append("Action requires vigorous movement but shot is static.")
            elif "sitting" in target_cluster or "pleading" in target_cluster:
                if avg_motion > 40.0:
                    score = max(0.0, score - 20.0)
                    diags.append("Action is calm/focused dialogue but shot has extreme chaotic camera motion.")

        return round(score, 2), diags

    @classmethod
    def verify_location(
        cls,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
    ) -> Tuple[float, List[str]]:
        """
        Verifies environmental setting context (Great Hall, Forest, Courtyard, etc.).
        """
        if not requirement.required_location:
            return 100.0, ["No specific location required."]

        req_loc = requirement.required_location.lower()
        shot_loc = shot.environment.lower()
        desc_lower = shot.scene_description.lower()

        diags = []
        if req_loc in shot_loc or req_loc in desc_lower or any(word in shot_loc for word in req_loc.split() if len(word) >= 4):
            score = 100.0
            diags.append(f"Location '{requirement.required_location}' confirmed.")
        else:
            score = 20.0
            diags.append(f"Location '{requirement.required_location}' not matched (found: '{shot.environment}').")

        return score, diags
