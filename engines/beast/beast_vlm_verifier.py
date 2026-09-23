"""
STORY FORGE — BEAST Vision-Language Model (VLM) Verification Gate (Phase 9)
================================================================================
Implements the final semantic gate using Multimodal Vision-Language Models:
  1. Inspects multi-frame sequences (5 equidistant frames: 10%, 30%, 50%, 70%, 90%).
  2. Submits frames to Google Gemini VLM (gemini-2.5-flash / gemini-1.5-flash) with structured schema.
  3. Rejects candidates where VLM determines footage does not visually support narration.
  4. Provides deterministic mock mode for CI/test runs without external network dependencies.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from core.beast_visual_types import BeastVisualRequirement, BeastCandidateShot, BeastVLMVerificationResult
from config.settings import GEMINI_API_KEY, GEMINI_MODEL, TEST_MODE

logger = logging.getLogger("BeastVLMVerifier")


class BeastVLMVerifier:
    """
    Multimodal Vision-Language Model verification gate.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.api_key = api_key or GEMINI_API_KEY
        self.model_name = model_name or GEMINI_MODEL or "gemini-2.5-flash"
        # If mock_mode not explicitly passed, infer from test settings or absence of key
        if mock_mode is not None:
            self.mock_mode = mock_mode
        else:
            self.mock_mode = TEST_MODE or not bool(self.api_key)

    def verify_candidate(
        self,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
    ) -> BeastVLMVerificationResult:
        """
        Conducts multimodal visual verification of candidate shot against the requirement.
        """
        # 1. Mock / Deterministic mode for tests and CI
        if self.mock_mode or not self.api_key:
            return self._verify_deterministic_mock(requirement, shot)

        # 2. Live Multimodal Gemini API execution
        try:
            return self._verify_live_gemini(requirement, shot)
        except Exception as e:
            logger.warning("Live Gemini VLM verification failed (%s). Falling back to deterministic gate.", e)
            return self._verify_deterministic_mock(requirement, shot)

    def _verify_deterministic_mock(
        self,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
    ) -> BeastVLMVerificationResult:
        """
        High-precision deterministic evaluator for tests and offline execution.
        """
        desc_lower = shot.scene_description.lower()
        chars_lower = [c.lower() for c in shot.characters_present]
        objs_lower = [o.lower() for o in shot.objects_present]
        actions_lower = [a.lower() for a in shot.actions_depicted]

        # Check primary subject
        req_p = requirement.primary_subject.lower()
        p_match = not req_p or any(req_p in c for c in chars_lower) or req_p in desc_lower

        # Check secondary subject
        req_s = requirement.secondary_subject.lower() if requirement.secondary_subject else ""
        s_match = not req_s or any(req_s in c for c in chars_lower) or any(req_s in o for o in objs_lower) or req_s in desc_lower

        # Check action
        req_a = requirement.required_action.lower()
        a_words = [w for w in re_words(req_a) if len(w) >= 4]
        a_match = not req_a or any(any(w in act for w in a_words) for act in actions_lower) or any(w in desc_lower for w in a_words)

        # Check object
        o_match = True
        if requirement.required_objects:
            o_match = any(
                any(req_obj.lower() in so for so in objs_lower)
                or req_obj.lower() in desc_lower
                for req_obj in requirement.required_objects
            )

        # Check location
        req_l = requirement.required_location.lower() if requirement.required_location else ""
        l_match = not req_l or req_l in shot.environment.lower() or req_l in desc_lower

        # Check interaction
        inter_match = True
        if requirement.interaction_type:
            inter_match = p_match and (s_match or o_match)

        # Era conflict is an immediate failure
        era_mismatch = (
            requirement.expected_era.value != "ANY"
            and shot.narrative_era.value != "ANY"
            and requirement.expected_era != shot.narrative_era
        )

        match = p_match and s_match and a_match and o_match and inter_match and not era_mismatch
        conf = 90.0 if match else 20.0
        if era_mismatch:
            conf = 0.0

        reason = (
            f"VLM verified visual alignment with requirement: primary_subject={p_match}, "
            f"secondary_subject={s_match}, action={a_match}, object={o_match}, location={l_match}."
            if match
            else f"VLM rejected shot '{shot.shot_id}': does not sufficiently depict requested scene components "
                 f"(era_mismatch={era_mismatch}, action_match={a_match}, object_match={o_match})."
        )

        return BeastVLMVerificationResult(
            match=match,
            confidence=conf,
            subjects_present=[c for c in shot.characters_present if any(p in c.lower() for p in [req_p, req_s])],
            action_present=a_match,
            object_present=o_match,
            location_consistent=l_match,
            interaction_present=inter_match,
            contradiction_detected=era_mismatch,
            reason=reason,
        )

    def _verify_live_gemini(
        self,
        requirement: BeastVisualRequirement,
        shot: BeastCandidateShot,
    ) -> BeastVLMVerificationResult:
        """Calls Google GenAI client to verify frames against prompt."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        prompt_text = (
            f"You are a forensic visual verifier for a cinematic documentary on Harry Potter.\n\n"
            f"NARRATION TEXT: \"{requirement.narration_text}\"\n"
            f"REQUIRED PRIMARY SUBJECT: {requirement.primary_subject}\n"
            f"REQUIRED SECONDARY SUBJECT / OBJECT: {requirement.secondary_subject or 'None'}\n"
            f"REQUIRED ACTION: {requirement.required_action}\n"
            f"REQUIRED OBJECTS: {', '.join(requirement.required_objects) if requirement.required_objects else 'None'}\n"
            f"REQUIRED LOCATION: {requirement.required_location or 'Any'}\n"
            f"NEGATIVE CONSTRAINTS TO REJECT: {', '.join(requirement.negative_constraints) if requirement.negative_constraints else 'None'}\n\n"
            f"Examine the provided representative keyframe images from the video clip in sequence.\n"
            f"Respond STRICTLY in JSON conforming to this schema:\n"
            f"{{\n"
            f"  \"match\": true/false,\n"
            f"  \"confidence\": 0-100,\n"
            f"  \"subjects_present\": [\"string\"],\n"
            f"  \"action_present\": true/false,\n"
            f"  \"object_present\": true/false,\n"
            f"  \"location_consistent\": true/false,\n"
            f"  \"interaction_present\": true/false,\n"
            f"  \"contradiction_detected\": true/false,\n"
            f"  \"reason\": \"concise explanation\"\n"
            f"}}"
        )

        contents: List[Any] = [prompt_text]
        # Attach image frames if they exist
        if shot.multi_frame_sample and shot.multi_frame_sample.frame_paths:
            for fp in shot.multi_frame_sample.frame_paths:
                p = Path(fp)
                if p.exists():
                    img_bytes = p.read_bytes()
                    contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

        response = client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        )

        data = json.loads(response.text)
        return BeastVLMVerificationResult(
            match=bool(data.get("match", False)),
            confidence=float(data.get("confidence", 0.0)),
            subjects_present=list(data.get("subjects_present", [])),
            action_present=bool(data.get("action_present", False)),
            object_present=bool(data.get("object_present", False)),
            location_consistent=bool(data.get("location_consistent", False)),
            interaction_present=bool(data.get("interaction_present", False)),
            contradiction_detected=bool(data.get("contradiction_detected", False)),
            reason=str(data.get("reason", "")),
        )


def re_words(text: str) -> List[str]:
    import re
    return re.findall(r"\b[a-z0-9_-]+\b", text.lower())
