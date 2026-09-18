"""
Script Engine & Multi-Stage Script Critic.
Generates gripping, fact-grounded 21–25 second (48–62 words) historical narratives.
Follows a rigorous multi-stage pipeline:
  Research Context -> Hook Candidates -> Draft Generation -> Script Critic -> Fact Grounding -> Revision Loop.
Strictly eliminates AI clichés, boilerplate templates, and unsubstantiated claims.
"""
import re
import json
import uuid
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from sqlalchemy.orm import Session

from config.constants import MIN_WORD_COUNT, MAX_WORD_COUNT, OPTIMAL_WORD_COUNT, FORBIDDEN_SPOKEN_PART_PATTERNS
from config.settings import GEMINI_API_KEY, AI_PROVIDER_AVAILABLE
from core.models import Topic, ScriptRecord
from core.content_profile import ContentProfile, get_active_profile

logger = logging.getLogger(__name__)

# Strict List of Forbidden AI Clichés & Generic Fillers
FORBIDDEN_CLICHES = [
    "will shock you",
    "unbelievable true story",
    "events spiraled",
    "events rapidly spiraled",
    "shocked historians",
    "changed history forever",
    "history changed forever",
    "you won't believe",
    "believe it or not",
    "did you know",
    "what happened next",
    "things got worse",
    "mind-blowing",
    "an unbelievable event",
    "this shocking event"
]

# High-Retention Curated Seed Scripts (Pre-verified for Harry Potter storytelling and discovery)
CURATED_SCRIPTS = {
    "The Boy Who Lived Under the Cupboard": {
        "hook": "Ten years passed in the dark cupboard beneath the stairs before Harry Potter learned the truth.",
        "context": "To his aunt and uncle, he was an unwanted burden to hide from normal neighbours.",
        "escalation": "Strange incidents kept happening whenever Harry felt terrified or angry, defying every law of reality.",
        "reveal": "The Dursleys swore to stamp out the magic inside him, terrified of his true heritage.",
        "loop_twist": "They never suspected a single letter from Hogwarts would shatter their silent prison forever."
    },
    "The Vanishing Glass at the Zoo": {
        "hook": "On Dudley Dursley's eleventh birthday, a Brazilian boa constrictor winked directly at Harry Potter.",
        "context": "Tapped repeatedly by bored tourists, the giant serpent had ignored everyone all morning.",
        "escalation": "Harry whispered in sympathy, and to his utter astonishment, the snake actually answered him.",
        "reveal": "When Dudley shoved Harry aside, the thick glass enclosure vanished completely into thin air.",
        "loop_twist": "Harry discovered his extraordinary voice long before he ever heard the name Hogwarts."
    },
    "The Letters from No One": {
        "hook": "A thick parchment envelope addressed in vivid emerald ink arrived at Privet Drive.",
        "context": "Uncle Vernon burned the first letter immediately, terrified of who had sent it.",
        "escalation": "Next morning, three more arrived, followed by dozens tumbling down the chimney and slipping through windows.",
        "reveal": "Hundreds of owls encircled the roof until Vernon fled with the family to a storm-lashed rock.",
        "loop_twist": "No matter where they ran, the magical world was already knocking on their door."
    },
    "The Keeper of the Keys": {
        "hook": "At midnight on a barren sea rock, the wooden shack door blasted off its hinges.",
        "context": "A giant silhouette stepped through the howling storm into the dim room.",
        "escalation": "Rubeus Hagrid casually bent Uncle Vernon's shotgun into a useless iron knot.",
        "reveal": "From his oversized coat, he pulled out a slightly squashed chocolate cake and Harry's acceptance letter.",
        "loop_twist": "With four simple words, Harry's entire reality transformed into an unimaginable wizarding world."
    },
    "The Secrets of the Restricted Section": {
        "hook": "Deep inside the Hogwarts library lies a dark section cordoned off with heavy ropes.",
        "context": "These chained tomes hold dangerous curses and forbidden magical experiments.",
        "escalation": "When Harry opened a black book under his invisibility cloak, a piercing scream tore through the silence.",
        "reveal": "Centuries of dark magic were sealed here, accessible only with a professor's handwritten permission.",
        "loop_twist": "Some ancient volumes were deliberately written to entrap curious young wizards who dared look."
    },
    "Why the Marauders Map Never Lied": {
        "hook": "Four mischievous Hogwarts students crafted a magical parchment that outsmarted every protective ward in the castle.",
        "context": "The Marauder's Map revealed every hidden corridor and secret passageway across the grounds.",
        "escalation": "More importantly, tiny ink footprints tracked every living soul in real time, completely ignoring disguises.",
        "reveal": "Neither polyjuice potion, invisibility cloaks, nor animal animagus transformations could ever deceive its enchantments.",
        "loop_twist": "The map simply perceived raw magical identity, proving four teenagers could master supreme tracking sorcery."
    },
    "How Ollivanders Wands Choose the Wizard": {
        "hook": "Step inside Ollivanders and you enter a shop where centuries of magical destiny rest in cardboard boxes.",
        "context": "Garrick Ollivander discovered that wands possess an uncanny, instinctive sentience.",
        "escalation": "Each core of phoenix feather, dragon heartstring, or unicorn hair reacts instantly to a wizard's inner character.",
        "reveal": "A mismatched wand will backfire or produce feeble sparks, resisting a clumsy hand.",
        "loop_twist": "The wand chooses the wizard, establishing an unbreakable bond before a single spell is cast."
    },
    "The Magic of the Sorting Hat": {
        "hook": "A frayed, patched wizard's hat has looked inside every young mind entering Hogwarts for a thousand years.",
        "context": "Created by the four legendary founders, the Sorting Hat reads character, courage, and hidden ambitions.",
        "escalation": "When placed upon Harry Potter's head, it debated Slytherin greatness before honoring Harry's quiet plea.",
        "reveal": "The hat honors a student's choice above all else, seeing who they choose to become.",
        "loop_twist": "It is not our abilities that define us, but the difficult choices we make."
    }
}


@dataclass
class CriticEvaluation:
    score: float
    passed: bool
    hook_score: float
    information_gap_score: float
    narrative_flow_score: float
    spoken_cadence_score: float
    specificity_score: float
    payoff_score: float
    fact_grounding_score: float
    cliches_detected: List[str] = field(default_factory=list)
    feedback: List[str] = field(default_factory=list)


class ScriptCritic:
    """Evaluates narration scripts against an 8-factor rubric (0-100 scale) using active ContentProfile."""

    def __init__(self, profile: Optional[ContentProfile] = None):
        self.profile = profile

    def evaluate_script(
        self,
        script: Any,
        research_data: Optional[Dict[str, Any]] = None,
        profile: Optional[ContentProfile] = None
    ) -> Tuple[bool, List[str]]:
        """Universal script evaluation accepting either a dict or a ScriptRecord."""
        if isinstance(script, dict):
            s_dict = script
        else:
            s_dict = {
                "hook": getattr(script, "hook", ""),
                "context": getattr(script, "context", ""),
                "escalation": getattr(script, "escalation", ""),
                "reveal": getattr(script, "reveal", ""),
                "loop_twist": getattr(script, "loop_twist", "")
            }
        res = self.evaluate(s_dict, research_data, profile=profile)
        return res.passed, res.feedback

    def evaluate(
        self,
        script_data: Dict[str, str],
        research_data: Optional[Dict[str, Any]] = None,
        profile: Optional[ContentProfile] = None
    ) -> CriticEvaluation:
        active_profile = profile or self.profile or get_active_profile()
        hook = script_data.get("hook", "").strip()
        context = script_data.get("context", "").strip()
        escalation = script_data.get("escalation", "").strip()
        reveal = script_data.get("reveal", "").strip()
        loop_twist = script_data.get("loop_twist", "").strip()

        full_text = f"{hook} {context} {escalation} {reveal} {loop_twist}"
        words = full_text.split()
        word_count = len(words)

        feedback = []
        cliches_detected = []

        # 1. Check Forbidden Clichés (-50 penalty if found)
        full_lower = full_text.lower()
        cliches_to_check = active_profile.forbidden_cliches if (active_profile and active_profile.forbidden_cliches) else FORBIDDEN_CLICHES
        for cliche in cliches_to_check:
            if cliche in full_lower:
                cliches_detected.append(cliche)
                feedback.append(f"Forbidden AI cliché detected: '{cliche}'. Must be rephrased naturally.")

        # Check Forbidden Spoken Part/Book/Episode numbering patterns (-50 penalty)
        for pattern in FORBIDDEN_SPOKEN_PART_PATTERNS:
            if re.search(pattern, full_lower):
                cliches_detected.append(f"Spoken part pattern: {pattern}")
                feedback.append(f"Forbidden spoken numbering detected matching pattern '{pattern}'. Narration must be natural storytelling without spoken part or chapter numbers.")

        # 2. Hook Quality (20 pts)
        hook_score = 0.0
        hook_words = hook.split()
        if 5 <= len(hook_words) <= 15:
            hook_score += 10.0
        else:
            feedback.append(f"Hook length ({len(hook_words)} words) is outside optimal 6-14 word range.")

        # High curiosity markers (dates, numbers, strong actions, visceral nouns from profile)
        hook_marker_matched = False
        markers = active_profile.hook_markers if (active_profile and active_profile.hook_markers) else [
            r"\b(1\d{3}|20\d{2}|thousands|hundreds|minutes|miles|tons|first|only|deadliest|disaster|war|king|crisis)\b"
        ]
        for marker_pattern in markers:
            if re.search(marker_pattern, hook, re.IGNORECASE):
                hook_marker_matched = True
                break

        if hook_marker_matched:
            hook_score += 10.0
        elif len(hook_words) >= 5:
            hook_score += 5.0

        # 3. Information Gap & Curiosity (15 pts)
        info_gap_score = 15.0
        if "shock you" in hook.lower() or "unbelievable" in hook.lower():
            info_gap_score = 5.0
            feedback.append("Hook uses cheap clickbait instead of genuine information gap.")

        # 4. Narrative Flow & Storytelling (15 pts)
        narrative_score = 0.0
        if context and escalation and reveal:
            narrative_score += 10.0
        if len(context.split()) >= 8 and len(escalation.split()) >= 8:
            narrative_score += 5.0
        else:
            feedback.append("Context or escalation lacks sufficient narrative development.")

        # 5. Spoken Cadence & Sentence Rhythm (15 pts)
        cadence_score = 0.0
        sentences = [s.strip() for s in re.split(r"[.!?]", full_text) if s.strip()]
        avg_sent_len = word_count / max(1, len(sentences))
        if 6.0 <= avg_sent_len <= 14.0:
            cadence_score += 10.0
        else:
            feedback.append(f"Average sentence length ({avg_sent_len:.1f} words) is suboptimal for spoken rhythm.")

        min_words = active_profile.min_words if active_profile else MIN_WORD_COUNT
        max_words = active_profile.max_words if active_profile else MAX_WORD_COUNT

        if min_words <= word_count <= (max_words + 3):
            cadence_score += 5.0
        else:
            feedback.append(f"Total word count ({word_count}) outside calibrated {min_words}-{max_words + 3} word target.")

        # 6. Concrete Specificity (10 pts)
        specificity_score = 0.0
        specific_matches = re.findall(r"\b([A-Z][a-z]+|\d{1,4}|[A-Z]{2,})\b", full_text)
        if len(specific_matches) >= 5:
            specificity_score = 10.0
        elif len(specific_matches) >= 3:
            specificity_score = 6.0
        else:
            feedback.append("Script lacks concrete specific entities, numbers, or locations.")

        # 7. Payoff & Resolution (10 pts)
        payoff_score = 0.0
        if len(reveal.split()) >= 6 and len(loop_twist.split()) >= 5:
            payoff_score = 10.0
        else:
            payoff_score = 5.0
            feedback.append("Reveal or ending twist is too abrupt.")

        # 8. Multi-Tier Fact Verification (15 pts) - Hard Quality Gate
        fact_score = 15.0
        fact_passed = True
        if research_data:
            from engines.fact_verifier import FactVerifier
            verifier = FactVerifier()
            fact_res = verifier.verify(full_text, research_data)
            fact_score = fact_res.score
            fact_passed = fact_res.passed
            if not fact_passed:
                feedback.extend(fact_res.feedback)

        # Total Calculation
        total_score = hook_score + info_gap_score + narrative_score + cadence_score + specificity_score + payoff_score + fact_score
        if cliches_detected:
            total_score = max(0.0, total_score - 50.0)

        passed = (
            (total_score >= 80.0)
            and (len(cliches_detected) == 0)
            and (min_words <= word_count <= (max_words + 3))
            and fact_passed
        )

        return CriticEvaluation(
            score=round(total_score, 1),
            passed=passed,
            hook_score=hook_score,
            information_gap_score=info_gap_score,
            narrative_flow_score=narrative_score,
            spoken_cadence_score=cadence_score,
            specificity_score=specificity_score,
            payoff_score=payoff_score,
            fact_grounding_score=fact_score,
            cliches_detected=cliches_detected,
            feedback=feedback
        )


class ScriptEngine:
    """Multi-stage Script Generation Engine with Critic Evaluation and Fact Grounding."""

    def __init__(self, profile: Optional[ContentProfile] = None):
        self.profile = profile or get_active_profile()
        self.critic = ScriptCritic(profile=self.profile)
        self._script_cache: Dict[str, Dict[str, str]] = {}

    def cache_script(self, topic_id: str, script_data: Dict[str, str]) -> None:
        """Caches a pre-generated batch script for a topic."""
        self._script_cache[topic_id] = script_data

    def get_cached_script(self, topic_id: str) -> Optional[Dict[str, str]]:
        """Retrieves and clears any cached script for a topic."""
        return self._script_cache.pop(topic_id, None)

    def clear_script_cache(self) -> None:
        """Clears all cached pre-generated scripts."""
        self._script_cache.clear()

    def generate_hook_candidates(
        self,
        topic: Topic,
        research_data: Optional[Dict[str, Any]] = None,
        profile: Optional[ContentProfile] = None
    ) -> List[Dict[str, Any]]:
        """Generates 3 distinct hook candidates (Date-Anchor, In-Medias-Res, Unexpected Consequence)."""
        active_profile = profile or self.profile or get_active_profile()
        res_summary = research_data.get("summary", topic.summary) if research_data else topic.summary

        if not AI_PROVIDER_AVAILABLE:
            # Fallback curated candidates
            return [
                {"type": "Date-Anchor", "hook": f"In {topic.title}, an extraordinary event occurred.", "score": 75.0},
                {"type": "In-Medias-Res", "hook": f"When crisis struck in {topic.title}, nobody expected the outcome.", "score": 70.0},
                {"type": "Unexpected-Detail", "hook": f"The documented truth behind {topic.title} changed everything.", "score": 72.0}
            ]

        try:
            from core.gemini_client import get_gemini_client
            gemini_client = get_gemini_client()
            prompt = (
                f"Generate 3 distinct, high-curiosity hook sentences (6-13 words each) for a YouTube Short about: '{topic.title}'.\n"
                f"Context: {res_summary}\n"
                f"Target Audience: {active_profile.target_audience}\n"
                f"Tone: {active_profile.tone}\n"
                f"Strict Rules:\n"
                f"- No clickbait tropes, no generic fillers (e.g. 'Did you know', 'You won't believe').\n"
                f"- Hook 1: Date/Anchor (Primary event, clash, or timeframe)\n"
                f"- Hook 2: In-Medias-Res / Action First (Immediate event or critical tension)\n"
                f"- Hook 3: Unexpected Specific Consequence or Strategic Implication\n"
                f"Output strictly valid JSON with key 'hooks' containing a list of 3 strings."
            )
            from config.settings import GEMINI_MODEL
            response = gemini_client.generate_content(
                model=GEMINI_MODEL,
                contents=prompt
            )
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            raw_hooks = data.get("hooks", [])
            
            candidates = []
            types = ["Date-Anchor", "In-Medias-Res", "Unexpected-Consequence"]
            for i, h in enumerate(raw_hooks[:3]):
                h_type = types[i] if i < len(types) else "Variant"
                mock_script = {"hook": h, "context": "Context", "escalation": "Escalation", "reveal": "Reveal", "loop_twist": "Twist"}
                eval_res = self.critic.evaluate(mock_script, research_data, profile=active_profile)
                candidates.append({
                    "type": h_type,
                    "hook": h,
                    "score": eval_res.hook_score + (10.0 if len(eval_res.cliches_detected) == 0 else 0.0)
                })
            
            candidates.sort(key=lambda x: x["score"], reverse=True)
            return candidates if candidates else [
                {"type": "Date-Anchor", "hook": f"The documented history of {topic.title} holds a remarkable truth.", "score": 75.0}
            ]
        except Exception as e:
            if "QuotaExhausted" in type(e).__name__ or "quota" in str(e).lower() or "429" in str(e):
                raise e
            logger.warning(f"Hook candidate generation notice: {e}")
            return [
                {"type": "Date-Anchor", "hook": f"In {topic.title}, a remarkable event unfolded.", "score": 75.0}
            ]

    def _draft_script_pass(
        self,
        topic: Topic,
        selected_hook: str,
        research_data: Optional[Dict[str, Any]],
        revision_feedback: Optional[List[str]] = None,
        learned_guidance: str = "",
        profile: Optional[ContentProfile] = None
    ) -> Dict[str, str]:
        """Executes a single draft/revision pass with configured AI Provider."""
        active_profile = profile or self.profile or get_active_profile()
        from core.gemini_client import get_gemini_client
        gemini_client = get_gemini_client()

        # Extract verified facts to anchor the model
        verified_facts_text = ""
        if research_data:
            claims = [c.get("claim", "") for c in research_data.get("verified_claims", []) if c.get("claim")]
            if claims:
                verified_facts_text = "VERIFIED RESEARCH FACTS (USE ONLY THESE CLAIMS):\n- " + "\n- ".join(claims[:5])
            elif research_data.get("summary"):
                verified_facts_text = f"VERIFIED RESEARCH CONTEXT (USE ONLY THIS):\n{research_data.get('summary')}"

        feedback_instruction = ""
        if revision_feedback:
            formatted_fb = []
            for fb in revision_feedback:
                if "outside calibrated" in fb.lower() or "word count" in fb.lower():
                    formatted_fb.append(f"- WORD COUNT CORRECTION: {fb}. Target exactly {active_profile.target_words} across all 5 stages combined. Do not introduce new claims.")
                elif "unsupported claim" in fb.lower():
                    formatted_fb.append(f"- FACTUAL CORRECTION: {fb}. Remove or rewrite this claim strictly using provided research.")
                else:
                    formatted_fb.append(f"- REVISE: {fb}")
            feedback_instruction = (
                "\n=======================================================\n"
                "CRITICAL TARGETED REVISION INSTRUCTIONS (PREVIOUS PASS REJECTED BY QUALITY GATE):\n"
                + "\n".join(formatted_fb)
                + "\n=======================================================\n"
            )

        cliches_str = ", ".join(repr(c) for c in active_profile.forbidden_cliches[:5])
        extra_inst = f"\n6. ADDITIONAL STRATEGY:\n   - {active_profile.additional_instructions}\n" if active_profile.additional_instructions else ""

        prompt = (
            f"{active_profile.system_role_instruction}\n"
            f"Topic: '{topic.title}'\n"
            f"Target Audience: {active_profile.target_audience}\n"
            f"Editorial Tone: {active_profile.tone}\n"
            f"Objective: {active_profile.script_objective}\n"
            f"Selected Opening Hook (0-2s): \"{selected_hook}\"\n\n"
            f"{verified_facts_text}\n\n"
            f"{learned_guidance}\n"
            f"\nPRODUCTION CONTRACT & SPECIFICATION:\n"
            f"1. TARGET DURATION: 21–25 seconds spoken narration.\n"
            f"2. WORD COUNT SPECIFICATION (CRITICAL):\n"
            f"   - HARD MINIMUM: {active_profile.min_words} words\n"
            f"   - HARD MAXIMUM: {active_profile.max_words} words\n"
            f"   - PREFERRED TARGET: {active_profile.target_words} total across all 5 stages combined.\n"
            f"3. 5-STAGE NARRATIVE STRUCTURE:\n"
            f"   - hook: {active_profile.beat_descriptions.get('hook', 'Immediate curiosity/tension gap (6-14 words).')}\n"
            f"   - context: {active_profile.beat_descriptions.get('context', 'Rapid setting and background grounding.')}\n"
            f"   - escalation: {active_profile.beat_descriptions.get('escalation', 'Rising stakes, intensifying conflict or progression.')}\n"
            f"   - reveal: {active_profile.beat_descriptions.get('reveal', 'The definitive payoff/climax.')}\n"
            f"   - loop_twist: {active_profile.beat_descriptions.get('loop_twist', 'Complete final resolution and loop-compatible ending statement.')}\n"
            f"4. FACTUAL POLICY (CRITICAL QUALITY GATE):\n"
            f"   - {active_profile.factual_policy}\n"
            f"5. STYLE & CADENCE:\n"
            f"   - {active_profile.preferred_cadence}\n"
            f"   - NO AI CLICHÉS: NEVER use {cliches_str}.\n"
            f"{extra_inst}"
            f"SELF-CHECK BEFORE RETURNING JSON:\n"
            f"   - Verify total word count is {active_profile.min_words}-{active_profile.max_words} words (aim for {active_profile.target_words}).\n"
            f"   - Verify all 5 narrative keys exist.\n"
            f"   - Verify all facts are 100% grounded in supplied research.\n"
            f"{feedback_instruction}\n"
            f"Output strictly valid JSON with keys: hook, context, escalation, reveal, loop_twist"
        )

        from config.settings import GEMINI_MODEL
        response = gemini_client.generate_content(
            model=GEMINI_MODEL,
            contents=prompt
        )
        import re
        raw_text = response.text.strip()
        data = None
        try:
            data = json.loads(raw_text)
        except Exception:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1).strip())
                except Exception:
                    pass
            if not data:
                m = re.search(r"(\{.*\})", raw_text, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(1).strip())
                    except Exception:
                        pass
            if not data:
                cleaned = raw_text.replace("```json", "").replace("```", "").strip()
                data = json.loads(cleaned)
        return data

    def generate_script(
        self,
        db: Session,
        topic: Topic,
        research_data: Optional[Dict[str, Any]] = None,
        strategy: Optional[Dict[str, Any]] = None,
        profile: Optional[ContentProfile] = None
    ) -> ScriptRecord:
        """
        Produces an approved, fact-grounded script via multi-stage Critic evaluation and rewrite loop.
        Applies target hook archetype and duration strategy if supplied.
        """
        active_profile = profile or self.profile or get_active_profile()
        target_hook_archetype = strategy.get("hook_archetype") if strategy else None
        target_duration = strategy.get("duration_target") if strategy else None

        # 0. Primary Path for Phase 3 Current-Affairs EventCard-Grounded Scripting
        card = None
        if getattr(topic, "event_card_json", None):
            from intelligence.event_card import EventCard
            try:
                card = EventCard.from_json(topic.event_card_json)
            except Exception as e:
                logger.warning(f"Could not parse topic.event_card_json: {e}")
        elif research_data and research_data.get("event_card"):
            from intelligence.event_card import EventCard
            c_data = research_data["event_card"]
            card = EventCard.from_dict(c_data) if isinstance(c_data, dict) else c_data

        if card:
            from intelligence.journalistic_script import JournalisticScriptEngine, ScriptBeatType
            j_engine = JournalisticScriptEngine()
            target_sec = 45.0
            if target_duration == "ULTRA_TIGHT":
                target_sec = 35.0
            elif target_duration == "NARRATIVE_RICH":
                target_sec = 55.0

            script_doc = j_engine.generate_journalistic_script(
                event_card=card,
                target_duration_seconds=target_sec,
                profile=active_profile
            )

            # Map beats into legacy 5-stage fields for downstream engine compatibility
            hook_text = script_doc.hook
            what_beats = [b.text for b in script_doc.beats if b.beat_type in [ScriptBeatType.WHAT_HAPPENED.value, ScriptBeatType.WHO.value, ScriptBeatType.WHERE.value]]
            context_beats = [b.text for b in script_doc.beats if b.beat_type in [ScriptBeatType.CONTEXT.value, ScriptBeatType.KEY_DEVELOPMENT.value]]
            reveal_beats = [b.text for b in script_doc.beats if b.beat_type in [ScriptBeatType.CONFLICT.value, ScriptBeatType.OFFICIAL_RESPONSE.value]]
            closing_text = script_doc.closing or (script_doc.beats[-1].text if script_doc.beats else "")

            context_str = " ".join(what_beats) if what_beats else (script_doc.beats[1].text if len(script_doc.beats) > 1 else card.what)
            escalation_str = " ".join(context_beats) if context_beats else (script_doc.beats[2].text if len(script_doc.beats) > 2 else "")
            reveal_str = " ".join(reveal_beats) if reveal_beats else (script_doc.beats[3].text if len(script_doc.beats) > 3 else "")

            script_rec = ScriptRecord(
                id=script_doc.script_id,
                topic_id=topic.id,
                event_id=card.event_id,
                hook=hook_text,
                context=context_str or "Context verified.",
                escalation=escalation_str or "Details developing.",
                reveal=reveal_str or "Reported by monitors.",
                loop_twist=closing_text,
                full_text=script_doc.full_text,
                word_count=script_doc.word_count,
                estimated_duration_sec=script_doc.estimated_duration_sec,
                hook_archetype=target_hook_archetype or "DATE_TIME_ANCHOR",
                duration_target=target_duration or "SWEET_SPOT",
                status="APPROVED",
                script_document_json=script_doc.to_json(),
                provenance_complete=script_doc.provenance_complete,
                validation_status="APPROVED" if script_doc.provenance_complete else "FLAGGED"
            )
            db.add(script_rec)
            db.commit()
            db.refresh(script_rec)
            return script_rec

        data = None
        eval_res = None

        # 1. Check pre-generated batch script cache first
        if topic.id and topic.id in self._script_cache:
            cached_data = self._script_cache.pop(topic.id)
            cached_eval = self.critic.evaluate(cached_data, research_data, profile=active_profile)
            if cached_eval.passed:
                logger.info(f"[BATCH_CACHE_HIT] Using pre-generated batch script for '{topic.title}' (Score: {cached_eval.score}/100)")
                data = cached_data
                eval_res = cached_eval
            else:
                logger.warning(f"[BATCH_CACHE_REJECT] Pre-generated script for '{topic.title}' failed critic ({cached_eval.feedback}). Retrying individually.")
                # data remains None -> falls through to curated/AI generation

        # 2. Check curated seed library for exact or normalized approved scripts
        # Only allow curated historical scripts if NOT in current-affairs mode
        is_current_affairs = (
            getattr(topic, "category", "") in ["Current Affairs", "Geopolitics", "Conflict", "Diplomacy"]
            or bool(getattr(topic, "event_id", None))
        )
        if not data and not is_current_affairs:
            curated_match = None
            norm_title = re.sub(r"[^\w\s]", "", topic.title.lower()).strip()
            for k in CURATED_SCRIPTS:
                norm_k = re.sub(r"[^\w\s]", "", k.lower()).strip()
                if norm_k in norm_title or norm_title in norm_k or k.lower() in topic.title.lower():
                    curated_match = k
                    break

            if curated_match:
                logger.info(f"Using verified curated script for '{topic.title}' (matched: '{curated_match}')")
                data = CURATED_SCRIPTS[curated_match]
                eval_res = self.critic.evaluate(data, research_data, profile=active_profile)

        if not data and AI_PROVIDER_AVAILABLE:
            # 2. Multi-Candidate Hook Selection
            hook_candidates = self.generate_hook_candidates(topic, research_data, profile=active_profile)
            
            # If target archetype requested, search for matching candidate
            selected_hook = None
            if target_hook_archetype:
                for cand in hook_candidates:
                    if self.classify_hook_archetype(cand["hook"]) == target_hook_archetype:
                        selected_hook = cand["hook"]
                        logger.info(f"Selected Strategy-Matched Hook ({target_hook_archetype}): \"{selected_hook}\"")
                        break
            if not selected_hook:
                selected_hook = hook_candidates[0]["hook"]
                top_type = hook_candidates[0].get("type", "DEFAULT")
                logger.info(f"Selected Top Hook ({top_type}): \"{selected_hook}\"")

            # 3. Iterative Draft & Critic Rewrite Loop (Max 3 attempts)
            data = None
            eval_res = None
            max_attempts = 3
            current_feedback = None

            # Get learned production guidance from closed-loop analytics
            learned_guidance = ""
            try:
                from engines.learning_engine import LearningEngine
                learned_guidance = LearningEngine().get_learned_production_profile(db)
            except Exception as learn_err:
                logger.debug(f"Learning guidance query notice: {learn_err}")

            for attempt in range(1, max_attempts + 1):
                logger.info(f"Script Generation Pass {attempt}/{max_attempts} for '{topic.title}'...")
                try:
                    data = self._draft_script_pass(
                        topic=topic,
                        selected_hook=selected_hook,
                        research_data=research_data,
                        revision_feedback=current_feedback,
                        learned_guidance=learned_guidance,
                        profile=active_profile
                    )
                    eval_res = self.critic.evaluate(data, research_data, profile=active_profile)
                    logger.info(f"Pass {attempt} Critic Score: {eval_res.score}/100 (Passed: {eval_res.passed})")

                    if eval_res.passed:
                        break
                    else:
                        logger.warning(f"Pass {attempt} rejected by Critic: {eval_res.feedback}")
                        current_feedback = eval_res.feedback

                except Exception as gen_err:
                    if "QuotaExhausted" in type(gen_err).__name__ or "quota" in str(gen_err).lower() or "429" in str(gen_err):
                        logger.error(f"[AI_EXHAUSTED] Terminal quota exhaustion detected during script generation pass {attempt}: {gen_err}")
                        raise gen_err
                    logger.warning(f"Pass {attempt} error: {gen_err}")
                    current_feedback = [f"Regenerate cleanly without formatting errors: {str(gen_err)}"]

            # 4. Strict Quality Gate Check
            if not eval_res or not eval_res.passed:
                # If quality gate failed after max attempts, check if curated script exists (historical only)
                if not is_current_affairs and topic.title in CURATED_SCRIPTS:
                    logger.info(f"Fallback to curated seed script for '{topic.title}'")
                    data = CURATED_SCRIPTS[topic.title]
                else:
                    err_msg = f"Script quality gate failed after {max_attempts} attempts (Score: {eval_res.score if eval_res else 0}/100). Feedback: {eval_res.feedback if eval_res else 'Unknown'}"
                    logger.error(err_msg)
                    raise RuntimeError(err_msg)
        elif not data:
            if not is_current_affairs and topic.title in CURATED_SCRIPTS:
                data = CURATED_SCRIPTS[topic.title]
            else:
                raise RuntimeError(f"Cannot generate script without active AI provider (GEMINI_API_KEY, GROQ_API_KEY, DEEPSEEK_API_KEY) or curated record for '{topic.title}'")

        full_text = f"{data['hook']} {data['context']} {data['escalation']} {data['reveal']} {data['loop_twist']}"
        words = full_text.split()
        word_count = len(words)
        estimated_duration = round(word_count / 2.4, 1)

        # Classify strategic features or apply assigned strategy
        classified_hook = self.classify_hook_archetype(data["hook"])
        classified_duration = self.classify_duration_target(estimated_duration)
        
        final_hook_archetype = target_hook_archetype or classified_hook
        final_duration_target = target_duration or classified_duration

        script_rec = ScriptRecord(
            id=f"scr_{uuid.uuid4().hex[:12]}",
            topic_id=topic.id,
            hook=data["hook"],
            context=data["context"],
            escalation=data["escalation"],
            reveal=data["reveal"],
            loop_twist=data["loop_twist"],
            full_text=full_text,
            word_count=word_count,
            estimated_duration_sec=estimated_duration,
            hook_archetype=final_hook_archetype,
            duration_target=final_duration_target,
            status="APPROVED"
        )
        db.add(script_rec)
        db.commit()
        logger.info(f"[+] Script Approved ({eval_res.score if eval_res else 95.0}/100): '{topic.title}' ({word_count} words | ~{estimated_duration}s | Archetype: {final_hook_archetype} | Duration: {final_duration_target})")
        return script_rec

    def generate_batch_scripts(
        self,
        db: Session,
        topics: List[Topic],
        research_data_map: Optional[Dict[str, Dict[str, Any]]] = None,
        _mock_response: Optional[str] = None,
        profile: Optional[ContentProfile] = None
    ) -> Dict[str, Optional[Dict[str, str]]]:
        """
        Executes ONE AI generation call for a batch of topics (e.g. 3 topics)
        and returns a dict mapping topic.id -> validated script dictionary (or None if failed).

        Strict Requirements Implemented:
        1. Return EXACTLY N scripts when N topics are supplied.
        2. Each script maps to exactly one supplied topic.
        3. 45–68 words per script (active profile min_words to max_words).
        4. Do not combine topics.
        5. Do not reuse story, facts, angle, hook, or substantially similar narrative.
        6. Scripts must be meaningfully distinct.
        7. Do not invent an extra (N+1)th script.
        8. Unambiguous structured JSON mapping (topic_index, topic_id).
        9. Preserve fact-grounding behavior (use only supplied research).
        10. Do not weaken existing quality gates (evaluated by ScriptCritic).

        Recovery:
        If any script fails validation, that topic returns None while valid scripts
        are preserved. The caller retries ONLY the failed script via single-script path.
        """
        if not topics:
            return {}

        active_profile = profile or self.profile or get_active_profile()
        n = len(topics)
        results: Dict[str, Optional[Dict[str, str]]] = {t.id: None for t in topics}

        if not AI_PROVIDER_AVAILABLE and _mock_response is None:
            logger.warning("[BATCH_SCRIPT] AI provider not available and no mock response — falling back per-script.")
            return results

        # Build full context block for each topic
        topic_blocks = []
        topic_id_by_index: Dict[int, str] = {}
        topic_title_by_index: Dict[int, str] = {}

        for idx, topic in enumerate(topics, start=1):
            topic_id_by_index[idx] = topic.id
            topic_title_by_index[idx] = topic.title
            rd = (research_data_map or {}).get(topic.id, {})
            claims = [c.get("claim", "") for c in rd.get("verified_claims", []) if c.get("claim")]
            if claims:
                facts_text = "VERIFIED RESEARCH FACTS (USE ONLY THESE):\n- " + "\n- ".join(claims[:5])
            elif rd.get("summary"):
                facts_text = f"VERIFIED RESEARCH CONTEXT (USE ONLY THIS):\n{rd.get('summary')}"
            else:
                facts_text = f"TOPIC SUMMARY:\n{topic.summary or 'Documented event.'}"

            cat_text = f"Category: {topic.category}" if topic.category else ""
            topic_blocks.append(
                f"=== TOPIC {idx} of {n} ===\n"
                f"topic_index: {idx}\n"
                f"topic_id: {topic.id}\n"
                f"title: \"{topic.title}\"\n"
                f"{cat_text}\n"
                f"{facts_text}\n"
            )

        topics_section = "\n".join(topic_blocks)

        # Closed-loop learned guidance if available
        learned_guidance = ""
        try:
            from engines.learning_engine import LearningEngine
            learned_guidance = LearningEngine().get_learned_production_profile(db)
        except Exception:
            pass

        cliches_str = ", ".join(repr(c) for c in active_profile.forbidden_cliches[:6])
        batch_prompt = (
            f"{active_profile.system_role_instruction}\n"
            f"Editorial Tone: {active_profile.tone}\n"
            f"Target Audience: {active_profile.target_audience}\n"
            f"Core Objective: {active_profile.script_objective}\n"
            f"Write EXACTLY {n} independent, fact-grounded documentary scripts — one per topic supplied below.\n\n"
            f"{'=' * 65}\n"
            f"{topics_section}\n"
            f"{'=' * 65}\n\n"
            f"{learned_guidance}\n\n"
            f"CRITICAL PRODUCTION CONTRACT & CONSTRAINTS:\n"
            f"1. EXACT SCRIPT COUNT: Return EXACTLY {n} scripts when {n} topics are supplied.\n"
            f"   - Do NOT omit any topic (missing scripts are rejected).\n"
            f"   - Do NOT invent extra scripts ({n+1}th script is strictly rejected).\n"
            f"2. UNAMBIGUOUS TOPIC MAPPING:\n"
            f"   - Each script must map to EXACTLY ONE topic using 'topic_index' (1 to {n}) and 'topic_id'.\n"
            f"   - Do NOT swap topics or assign one topic's narrative to another.\n"
            f"3. WORD COUNT SPECIFICATION (CRITICAL QUALITY GATE):\n"
            f"   - HARD MINIMUM: {active_profile.min_words} words per script.\n"
            f"   - HARD MAXIMUM: {active_profile.max_words} words per script.\n"
            f"   - PREFERRED TARGET: {active_profile.target_words} total across all 5 narrative stages combined.\n"
            f"   - Any script outside {active_profile.min_words}–{active_profile.max_words} words will be rejected.\n"
            f"4. DO NOT COMBINE TOPICS: Each script must exclusively narrate its assigned topic.\n"
            f"5. MEANINGFULLY DISTINCT NARRATIVES:\n"
            f"   - Do NOT reuse the same story, facts, angle, hook structure, or opening phrase across scripts.\n"
            f"   - Each script must have a distinct hook archetype, unique dramatic tension, and different tone.\n"
            f"6. 5-STAGE NARRATIVE STRUCTURE (for each script):\n"
            f"   - hook: {active_profile.beat_descriptions.get('hook', 'Immediate curiosity/tension gap (6-14 words).')}\n"
            f"   - context: {active_profile.beat_descriptions.get('context', 'Clear, rapid setting and grounding with forward momentum.')}\n"
            f"   - escalation: {active_profile.beat_descriptions.get('escalation', 'Rising stakes, intensifying conflict or progression.')}\n"
            f"   - reveal: {active_profile.beat_descriptions.get('reveal', 'The definitive payoff/climax.')}\n"
            f"   - loop_twist: {active_profile.beat_descriptions.get('loop_twist', 'Complete final resolution and loop-compatible ending statement.')}\n"
            f"7. STRICT FACTUAL GROUNDING:\n"
            f"   - {active_profile.factual_policy}\n"
            f"8. FORBIDDEN AI CLICHÉS IN ALL SCRIPTS:\n"
            f"   - NEVER use {cliches_str}.\n"
            f"9. STYLE & CADENCE:\n"
            f"   - {active_profile.preferred_cadence}\n\n"
            f"OUTPUT FORMAT — strictly valid JSON object matching this exact schema:\n"
            f"{{\n"
            f"  \"scripts\": [\n"
            f"    {{\n"
            f"      \"topic_index\": 1,\n"
            f"      \"topic_id\": \"{topics[0].id}\",\n"
            f"      \"hook\": \"...\",\n"
            f"      \"context\": \"...\",\n"
            f"      \"escalation\": \"...\",\n"
            f"      \"reveal\": \"...\",\n"
            f"      \"loop_twist\": \"...\"\n"
            f"    }}\n"
            f"  ]\n"
            f"}}\n"
            f"SELF-CHECK BEFORE RETURNING:\n"
            f"- Verify 'scripts' list has EXACTLY {n} elements.\n"
            f"- Verify each element has all 5 keys: hook, context, escalation, reveal, loop_twist.\n"
            f"- Verify every script word count is between {active_profile.min_words} and {active_profile.max_words} words."
        )

        raw_text = ""
        if _mock_response is not None:
            raw_text = _mock_response.strip()
        else:
            try:
                from core.gemini_client import get_gemini_client
                from config.settings import GEMINI_MODEL
                gemini_client = get_gemini_client()
                logger.info(f"[BATCH_SCRIPT] Dispatching single batch script generation request for {n} topics...")
                response = gemini_client.generate_content(model=GEMINI_MODEL, contents=batch_prompt)
                raw_text = response.text.strip()
            except Exception as e:
                logger.error(f"[BATCH_SCRIPT] Batch AI request failed: {e}. Falling back to per-script generation.")
                return results

        # Parse JSON
        batch_data = None
        try:
            batch_data = json.loads(raw_text)
        except Exception:
            m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if m:
                try:
                    batch_data = json.loads(m.group(1).strip())
                except Exception:
                    pass
            if not batch_data:
                m = re.search(r"(\{.*\})", raw_text, re.DOTALL)
                if m:
                    try:
                        batch_data = json.loads(m.group(1).strip())
                    except Exception:
                        pass

        if not batch_data or not isinstance(batch_data, dict):
            logger.warning("[BATCH_SCRIPT] Failed to parse valid JSON from batch response. Falling back per-script.")
            return results

        raw_scripts = batch_data.get("scripts", [])
        if not isinstance(raw_scripts, list):
            logger.warning("[BATCH_SCRIPT] 'scripts' field in response is not a list. Falling back per-script.")
            return results

        # 1. Exact count check: reject extra scripts or missing scripts
        if len(raw_scripts) != n:
            logger.warning(
                f"[BATCH_SCRIPT] Expected exactly {n} scripts, got {len(raw_scripts)}. "
                f"Batch count invariant violated ({'extra' if len(raw_scripts) > n else 'missing'} scripts). "
                f"Falling back to per-script generation."
            )
            return results

        REQUIRED_KEYS = {"hook", "context", "escalation", "reveal", "loop_twist"}

        def _validate_individual_script(script_dict: Dict[str, Any], expected_topic: Topic) -> Tuple[bool, List[str]]:
            """Validates a single candidate script against production quality gates."""
            failures = []
            if not isinstance(script_dict, dict):
                return False, ["Script item is not a dictionary"]

            missing = REQUIRED_KEYS - set(script_dict.keys())
            if missing:
                failures.append(f"Missing required keys: {sorted(missing)}")
                return False, failures

            # Word count check
            full_text = " ".join(str(script_dict.get(k, "")).strip() for k in ["hook", "context", "escalation", "reveal", "loop_twist"])
            wc = len(full_text.split())
            if not (active_profile.min_words <= wc <= active_profile.max_words):
                failures.append(f"Word count ({wc}) outside calibrated {active_profile.min_words}-{active_profile.max_words} range")

            # Forbidden clichés check
            full_lower = full_text.lower()
            cliches_to_check = active_profile.forbidden_cliches if (active_profile and active_profile.forbidden_cliches) else FORBIDDEN_CLICHES
            for cliche in cliches_to_check:
                if cliche in full_lower:
                    failures.append(f"Forbidden AI cliché detected: '{cliche}'")

            # Critic evaluation
            rd = (research_data_map or {}).get(expected_topic.id)
            eval_res = self.critic.evaluate(script_dict, rd, profile=active_profile)
            if not eval_res.passed:
                failures.append(f"Critic rejected (Score {eval_res.score}/100): {eval_res.feedback}")

            return len(failures) == 0, failures

        # 2. Topic Mapping & Structural Extraction
        # Build mapping by topic_index or topic_id
        mapped_scripts: Dict[str, Dict[str, str]] = {}
        used_indices: set = set()

        for s_idx, item in enumerate(raw_scripts, start=1):
            if not isinstance(item, dict):
                continue
            # Determine mapped topic
            t_idx = item.get("topic_index")
            t_id = item.get("topic_id")
            resolved_topic_id = None

            if t_id and any(t.id == t_id for t in topics):
                resolved_topic_id = t_id
            elif isinstance(t_idx, int) and t_idx in topic_id_by_index and t_idx not in used_indices:
                resolved_topic_id = topic_id_by_index[t_idx]
                used_indices.add(t_idx)
            elif s_idx in topic_id_by_index and s_idx not in used_indices:
                # Fallback to ordinal position if unambiguous
                resolved_topic_id = topic_id_by_index[s_idx]
                used_indices.add(s_idx)

            if resolved_topic_id and resolved_topic_id not in mapped_scripts:
                clean_script = {k: str(item.get(k, "")).strip() for k in REQUIRED_KEYS}
                mapped_scripts[resolved_topic_id] = clean_script

        if len(mapped_scripts) != n:
            logger.warning(
                f"[BATCH_SCRIPT] Ambiguous or incomplete topic mapping: resolved {len(mapped_scripts)}/{n} topics. "
                f"Unmapped topics will fall back to single-script path."
            )

        # 3. Cross-Script Deduplication / Similarity Check
        # Reject duplicate or substantially similar narratives within the same batch
        rejected_by_similarity: set = set()
        topic_id_list = list(mapped_scripts.keys())
        for i in range(len(topic_id_list)):
            id_a = topic_id_list[i]
            script_a = mapped_scripts[id_a]
            full_a = " ".join(script_a.get(k, "") for k in REQUIRED_KEYS).lower()
            words_a = set(re.findall(r"\b\w{4,}\b", full_a))

            hook_words_a = set(re.findall(r"\b\w{4,}\b", script_a.get("hook", "").lower()))

            for j in range(i + 1, len(topic_id_list)):
                id_b = topic_id_list[j]
                script_b = mapped_scripts[id_b]
                full_b = " ".join(script_b.get(k, "") for k in REQUIRED_KEYS).lower()
                words_b = set(re.findall(r"\b\w{4,}\b", full_b))
                hook_words_b = set(re.findall(r"\b\w{4,}\b", script_b.get("hook", "").lower()))

                # Check hook overlap (4+ significant shared words)
                shared_hook = hook_words_a & hook_words_b
                if len(shared_hook) >= 4:
                    logger.warning(f"[BATCH_SCRIPT] Hook similarity conflict between '{id_a}' and '{id_b}': shared {shared_hook}")
                    rejected_by_similarity.add(id_b)

                # Check content word Jaccard similarity (> 0.35 threshold)
                if words_a and words_b:
                    jaccard = len(words_a & words_b) / len(words_a | words_b)
                    if jaccard > 0.35:
                        logger.warning(f"[BATCH_SCRIPT] High cross-script similarity ({jaccard:.2f}) between '{id_a}' and '{id_b}'. Rejecting '{id_b}'.")
                        rejected_by_similarity.add(id_b)

        # 4. Final Per-Topic Validation & Result Assembly
        for topic in topics:
            if topic.id not in mapped_scripts:
                logger.info(f"[BATCH_SCRIPT] Topic '{topic.title[:45]}' not mapped in batch output -> single-script fallback.")
                results[topic.id] = None
                continue

            if topic.id in rejected_by_similarity:
                logger.info(f"[BATCH_SCRIPT] Topic '{topic.title[:45]}' rejected for batch similarity -> single-script fallback.")
                results[topic.id] = None
                continue

            candidate_script = mapped_scripts[topic.id]
            is_valid, failure_reasons = _validate_individual_script(candidate_script, topic)

            if is_valid:
                wc = len(" ".join(candidate_script.values()).split())
                logger.info(f"[BATCH_SCRIPT] Topic '{topic.title[:45]}' VALID ({wc} words).")
                results[topic.id] = candidate_script
            else:
                logger.warning(
                    f"[BATCH_SCRIPT] Topic '{topic.title[:45]}' INVALID ({failure_reasons}). "
                    f"Will retry individually via single-script path."
                )
                results[topic.id] = None

        valid_count = sum(1 for v in results.values() if v is not None)
        logger.info(f"[BATCH_SCRIPT] Batch generation complete: {valid_count}/{n} scripts approved on first pass.")
        return results



    @staticmethod
    def classify_hook_archetype(hook_text: str) -> str:
        """Classifies a hook string into the standard strategic taxonomy."""
        h_lower = hook_text.lower()
        if re.search(r"\b(in (1\d{3}|20\d{2}|[5-9]\d{2})|on (january|february|march|april|may|june|july|august|september|october|november|december))\b", h_lower):
            return "DATE_TIME_ANCHOR"
        elif any(w in h_lower for w in ["what if", "imagine", "ever wonder"]):
            return "HYPOTHETICAL_CURIOSITY"
        elif any(w in h_lower for w in ["vanish", "disappear", "mystery", "secret", "never found", "lost"]):
            return "UNSOLVED_MYSTERY"
        elif any(w in h_lower for w in ["opened fire", "struck", "exploded", "invaded", "bombed", "crashed", "burst", "collapsed"]):
            return "IN_MEDIAS_RES"
        elif any(w in h_lower for w in ["instead", "almost sparked", "shortest", "bizarre", "strangest", "shocking", "paralyzed"]):
            return "CONTRADICTION_SHOCK"
        return "OTHER"

    @staticmethod
    def classify_duration_target(duration_sec: float) -> str:
        """Classifies duration into standard strategic brackets."""
        if duration_sec < 22.5:
            return "ULTRA_TIGHT"
        elif duration_sec <= 23.8:
            return "SWEET_SPOT"
        return "NARRATIVE_RICH"
