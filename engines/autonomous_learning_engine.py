"""
STORY FORGE Autonomous Learning, Cadence & Feedback Loop Engine (Step 7)
================================================================================
Directorial intelligence layer executing autonomous performance scoring,
fatigue braking, cadence arbitration, hook weight learning, and winning formula cloning.

Core Invariants:
  - BPS SCORING: 0.40*SCR + 0.30*VSA + 0.20*APV + 0.10*CommentRate (Targets: SCR>=10, VSA>=75%, APV>=88%, Comments>=15)
  - SCALE / THROTTLE: Scale if PI >= 1.25, Throttle if PI < 0.80, else Normal
  - HOOK WEIGHT LEARNING: If VSA < 65%, halve hook archetype weight (min 0.1)
  - FATIGUE BRAKE: 3 consecutive mature uploads with < 500 views -> 12h pause (precedes surge)
  - CADENCE PRECEDENCE: FATIGUE_PAUSE > CADENCE_INCREASE (>2x baseline) > CADENCE_NORMAL (3/day)
  - NOVEL STORY ISOLATION: Novel Story baselines strictly separated from Deep Discovery
  - ZERO PRODUCTION MUTATION: Produces decision artifacts only; zero publishing or rendering
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set

from core.analytics_types import (
    MaturationState,
    CadenceDecisionType,
    PerformanceScaleDecision,
    LearningSignalType,
    OrthogonalAxis,
    AnalyticsSnapshot,
    LearningSignal,
    WinningPattern,
    CadenceDecision,
)

logger = logging.getLogger(__name__)

# Canonical publishing slots in UTC
NORMAL_PUBLISHING_SLOTS: List[str] = ["13:00 UTC", "17:00 UTC", "21:00 UTC"]
SURGE_PUBLISHING_SLOT: str = "01:00 UTC"

# STORY FORGE internal control targets (not universal platform claims)
TARGET_SCR: float = 10.0          # 10 subscribers / 1,000 views
TARGET_VSA: float = 75.0          # 75.0% viewed vs swiped away
TARGET_APV: float = 88.0          # 88.0% average percentage viewed
TARGET_COMMENT_RATE: float = 15.0 # 15 comments / 1,000 views


class AutonomousLearningEngine:
    """
    Directorial feedback loop and autonomous decision orchestrator.
    Evaluates telemetry, scores performance, and guides publishing cadence.
    """

    def __init__(self, poll_interval_hours: int = 6):
        self.poll_interval_hours = poll_interval_hours

    # --------------------------------------------------------------------------
    # 1. BPS — SUBSCRIBER CONVERSION PERFORMANCE SCORE
    # --------------------------------------------------------------------------
    def calculate_bps(
        self,
        snapshot: AnalyticsSnapshot,
    ) -> Tuple[Optional[float], Dict[str, float]]:
        """
        Calculates the Subscriber Conversion Performance Score (BPS):
          BPS = 0.40 * SCR_norm + 0.30 * VSA_norm + 0.20 * APV_norm + 0.10 * CommentRate_norm
        Returns (bps_score, normalized_subscores).
        Returns (None, {}) if essential metrics are missing (no fake zeros).
        """
        if snapshot.views is None or snapshot.views <= 0:
            return (None, {})
        if snapshot.viewed_vs_swiped_away is None or snapshot.average_percentage_viewed is None:
            return (None, {})

        # Compute or extract SCR
        scr = snapshot.subscriber_conversion_rate
        if scr is None:
            if snapshot.subscriber_gain is not None:
                scr = (float(snapshot.subscriber_gain) / float(snapshot.views)) * 1000.0
            else:
                return (None, {})

        # Compute or extract Comment Rate
        if snapshot.comments is not None:
            comment_rate = (float(snapshot.comments) / float(snapshot.views)) * 1000.0
        else:
            comment_rate = 0.0

        vsa = float(snapshot.viewed_vs_swiped_away)
        apv = float(snapshot.average_percentage_viewed)

        # Normalize metrics relative to architectural targets (clipped safely to [0.0, 2.0])
        scr_norm = min(2.0, max(0.0, scr / TARGET_SCR))
        vsa_norm = min(2.0, max(0.0, vsa / TARGET_VSA))
        apv_norm = min(2.0, max(0.0, apv / TARGET_APV))
        comm_norm = min(2.0, max(0.0, comment_rate / TARGET_COMMENT_RATE))

        bps = (
            0.40 * scr_norm
            + 0.30 * vsa_norm
            + 0.20 * apv_norm
            + 0.10 * comm_norm
        )

        subscores = {
            "scr_norm": round(scr_norm, 4),
            "vsa_norm": round(vsa_norm, 4),
            "apv_norm": round(apv_norm, 4),
            "comm_norm": round(comm_norm, 4),
        }
        return (round(bps, 4), subscores)

    # --------------------------------------------------------------------------
    # 2. DATA MATURATION EVALUATION
    # --------------------------------------------------------------------------
    def evaluate_maturation(self, snapshot: AnalyticsSnapshot) -> MaturationState:
        """Determines if an observation has matured sufficiently to drive decisions."""
        if snapshot.observation_window_hours < float(self.poll_interval_hours) or (snapshot.views is not None and snapshot.views < 100):
            return MaturationState.TOO_EARLY

        if snapshot.views is None or snapshot.viewed_vs_swiped_away is None or snapshot.average_percentage_viewed is None:
            return MaturationState.INSUFFICIENT_DATA

        return MaturationState.MATURE

    # --------------------------------------------------------------------------
    # 3. BASELINE CALCULATION (WITH NOVEL STORY ISOLATION)
    # --------------------------------------------------------------------------
    def calculate_baseline(
        self,
        historical_snapshots: List[AnalyticsSnapshot],
        content_mix_category: str = "deep_discovery",
        format_template: Optional[str] = None,
    ) -> Tuple[Optional[float], str]:
        """
        Calculates cohort baseline BPS.
        Novel Story and Deep Discovery baselines are STRICTLY SEPARATED.
        Returns (baseline_bps, status_reason).
        """
        # Strict tier isolation
        cohort = [
            s for s in historical_snapshots
            if s.content_mix_category == content_mix_category
            and s.maturation_state == MaturationState.MATURE
        ]

        if format_template:
            template_cohort = [s for s in cohort if s.format_template == format_template]
            if len(template_cohort) >= 3:
                cohort = template_cohort

        # Require minimum 3 mature observations
        if len(cohort) < 3:
            return (None, "BASELINE_INSUFFICIENT")

        scores: List[float] = []
        for s in cohort:
            b_score, _ = self.calculate_bps(s)
            if b_score is not None:
                scores.append(b_score)

        if len(scores) < 3:
            return (None, "BASELINE_INSUFFICIENT")

        avg_bps = sum(scores) / len(scores)
        return (round(avg_bps, 4), "BASELINE_ESTABLISHED")

    # --------------------------------------------------------------------------
    # 4. SCALE / THROTTLE EVALUATION
    # --------------------------------------------------------------------------
    def evaluate_scale_throttle(
        self,
        bps: float,
        baseline_bps: float,
    ) -> Tuple[PerformanceScaleDecision, float]:
        """
        Evaluates production scale vs throttle:
          Performance Index (PI) = BPS / Baseline BPS
          PI >= 1.25 -> SCALE
          PI < 0.80  -> THROTTLE
          else       -> NORMAL
        """
        if baseline_bps <= 0.0:
            return (PerformanceScaleDecision.NORMAL, 1.0)

        pi = round(bps / baseline_bps, 3)
        if pi >= 1.25:
            return (PerformanceScaleDecision.SCALE, pi)
        elif pi < 0.80:
            return (PerformanceScaleDecision.THROTTLE, pi)
        return (PerformanceScaleDecision.NORMAL, pi)

    # --------------------------------------------------------------------------
    # 5. HOOK WEIGHT CONTROL
    # --------------------------------------------------------------------------
    def evaluate_hook_weights(
        self,
        snapshots: List[AnalyticsSnapshot],
        current_weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[Dict[str, float], List[LearningSignal]]:
        """
        If VSA < 65%, halves hook archetype weighting in future selection:
          weight = max(0.1, weight * 0.5)
        Does NOT mutate historical analytics; returns deterministic learning signal.
        """
        weights = dict(current_weights or {
            "COUNTER_INTUITIVE_TRUTH": 1.0,
            "INCREDULITY_AWARENESS_TEST": 1.0,
            "ABSURD_COMIC_REALITY": 1.0,
            "DIRECT_CHALLENGE": 1.0,
            "DIALOGUE_COLD_OPEN": 1.0,
        })
        signals: List[LearningSignal] = []

        for s in snapshots:
            if s.maturation_state != MaturationState.MATURE:
                continue
            if s.viewed_vs_swiped_away is not None and s.viewed_vs_swiped_away < 65.0:
                hook = s.hook_archetype
                old_w = weights.get(hook, 1.0)
                new_w = round(max(0.1, old_w * 0.5), 3)
                weights[hook] = new_w

                signals.append(
                    LearningSignal(
                        signal_type=LearningSignalType.WEAK_HOOK,
                        source_video_id=s.candidate_id,
                        threshold_used="VSA < 65.0%",
                        measured_value=f"VSA={s.viewed_vs_swiped_away:.1f}%",
                        confidence=0.90,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        explanation=f"Hook archetype '{hook}' recorded VSA {s.viewed_vs_swiped_away:.1f}% (< 65%); halved selection weight from {old_w} to {new_w}.",
                    )
                )

        return (weights, signals)

    # --------------------------------------------------------------------------
    # 6. FATIGUE BRAKE LOGIC
    # --------------------------------------------------------------------------
    def evaluate_fatigue(
        self,
        recent_snapshots: List[AnalyticsSnapshot],
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Fatigue Rule:
          3 consecutive uploads AND each has <500 views in valid observation window.
          Invalid, missing, or immature observations are EXCLUDED from the sequence.
          Returns (is_fatigued, reason_codes, fatigued_video_ids).
        """
        # Filter to only valid mature observations within valid window
        valid_obs = [
            s for s in recent_snapshots
            if s.maturation_state == MaturationState.MATURE
            and s.views is not None
            and s.observation_window_hours >= float(self.poll_interval_hours)
        ]

        if len(valid_obs) < 3:
            return (False, [], [])

        # Check if ANY sequence of 3 consecutive uploads has < 500 views
        for i in range(len(valid_obs) - 2):
            window = valid_obs[i:i + 3]
            if all(s.views is not None and s.views < 500 for s in window):
                video_ids = [s.candidate_id for s in window]
                reasons = [
                    f"FATIGUE_3_CONSECUTIVE_LOW_VIEWS: 3 consecutive mature uploads ({video_ids}) each recorded <500 views (views: {[s.views for s in window]})."
                ]
                return (True, reasons, video_ids)

        return (False, [], [])

    # --------------------------------------------------------------------------
    # 7. WINNING-FORMAT LEARNING LOOP
    # --------------------------------------------------------------------------
    def evaluate_winning_patterns(
        self,
        snapshots: List[AnalyticsSnapshot],
        baseline_bps: float,
        recent_history_7d: Optional[List[AnalyticsSnapshot]] = None,
    ) -> Tuple[List[WinningPattern], List[LearningSignal]]:
        """
        Winning Pattern Rule:
          Short exceeds 3x baseline (PI >= 3.0).
          Cloning requires shifting ONE orthogonal axis (SUBJECT, DYNAMIC, or PERSPECTIVE).
          Anti-repetition rule: Same lead character + same template combination is FORBIDDEN within 7 days.
        """
        patterns: List[WinningPattern] = []
        signals: List[LearningSignal] = []

        if baseline_bps <= 0.0:
            return (patterns, signals)

        # Build 7-day lead+template history for anti-repetition check
        recent_pairs: Set[Tuple[str, str]] = set()
        if recent_history_7d:
            for s in recent_history_7d:
                recent_pairs.add((s.lead_character.lower(), s.format_template))

        for s in snapshots:
            if s.maturation_state != MaturationState.MATURE:
                continue
            bps, _ = self.calculate_bps(s)
            if bps is None:
                continue

            pi = bps / baseline_bps
            if pi >= 3.0:
                pair = (s.lead_character.lower(), s.format_template)
                is_repeat_blocked = pair in recent_pairs

                wp = WinningPattern(
                    source_video_id=s.candidate_id,
                    format_template=s.format_template,
                    hook_archetype=s.hook_archetype,
                    topic_category=s.topic_category,
                    lead_character=s.lead_character,
                    performance_index=round(pi, 2),
                    orthogonal_axis_options=[
                        OrthogonalAxis.SUBJECT.value,
                        OrthogonalAxis.DYNAMIC.value,
                        OrthogonalAxis.PERSPECTIVE.value,
                    ],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                patterns.append(wp)

                exp = (
                    f"Video {s.candidate_id} achieved PI {pi:.2f} (>= 3.0x baseline). Structural pattern tagged for cloning. "
                    f"Must shift orthogonal axis (Subject, Dynamic, or Perspective)."
                )
                if is_repeat_blocked:
                    exp += f" Note: Character '{s.lead_character}' + Template '{s.format_template}' was used within 7d; subject shift mandatory."

                signals.append(
                    LearningSignal(
                        signal_type=LearningSignalType.WINNING_PATTERN,
                        source_video_id=s.candidate_id,
                        threshold_used="PI >= 3.0x baseline",
                        measured_value=f"PI={pi:.2f}",
                        confidence=0.95,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        explanation=exp,
                    )
                )

        return (patterns, signals)

    # --------------------------------------------------------------------------
    # 8. AUTONOMOUS CADENCE ARBITRATION
    # --------------------------------------------------------------------------
    def make_cadence_decision(
        self,
        current_snapshot: Optional[AnalyticsSnapshot],
        recent_snapshots: List[AnalyticsSnapshot],
        historical_cohort: List[AnalyticsSnapshot],
        current_hook_weights: Optional[Dict[str, float]] = None,
        recent_history_7d: Optional[List[AnalyticsSnapshot]] = None,
        content_mix_category: str = "deep_discovery",
    ) -> CadenceDecision:
        """
        Master decision loop arbitrating publishing cadence using strict precedence:
          1. FATIGUE_PAUSE (12h pause)
          2. CADENCE_INCREASE (4–5/day surge if velocity > 2x baseline)
          3. CADENCE_NORMAL (3/day)
        """
        all_snapshots = list(recent_snapshots)
        if current_snapshot and current_snapshot not in all_snapshots:
            all_snapshots.append(current_snapshot)

        # Baseline
        baseline_bps, base_reason = self.calculate_baseline(
            historical_snapshots=historical_cohort,
            content_mix_category=content_mix_category,
        )

        # BPS for current snapshot
        bps: Optional[float] = None
        pi: Optional[float] = None
        if current_snapshot:
            bps, _ = self.calculate_bps(current_snapshot)
            if bps is not None and baseline_bps is not None and baseline_bps > 0.0:
                pi = round(bps / baseline_bps, 3)

        # Learning Signals & Hook Weights
        updated_weights, hook_signals = self.evaluate_hook_weights(
            snapshots=all_snapshots,
            current_weights=current_hook_weights,
        )

        # Winning Patterns
        winning_patterns: List[WinningPattern] = []
        win_signals: List[LearningSignal] = []
        if baseline_bps is not None:
            winning_patterns, win_signals = self.evaluate_winning_patterns(
                snapshots=all_snapshots,
                baseline_bps=baseline_bps,
                recent_history_7d=recent_history_7d,
            )

        all_signals = hook_signals + win_signals

        # Check Fatigue Brake
        is_fatigued, fatigue_reasons, fatigue_vids = self.evaluate_fatigue(all_snapshots)

        # DECISION PRECEDENCE ARBITRATION
        # Precedence 1: FATIGUE PAUSE
        if is_fatigued:
            fatigue_signal = LearningSignal(
                signal_type=LearningSignalType.FATIGUE,
                source_video_id=",".join(fatigue_vids),
                threshold_used="3 consecutive mature uploads < 500 views",
                measured_value="3 consecutive <500 views",
                confidence=0.98,
                timestamp=datetime.now(timezone.utc).isoformat(),
                explanation="Channel audience fatigue detected. Enforcing mandatory 12-hour publication cooldown.",
            )
            all_signals.append(fatigue_signal)

            dec = CadenceDecision(
                decision_type=CadenceDecisionType.FATIGUE_PAUSE,
                recommended_daily_cadence=0,
                recommended_slots=[],
                pause_duration_hours=12.0,
                bps=bps,
                performance_index=pi,
                baseline_bps=baseline_bps,
                learning_signals=all_signals,
                winning_patterns=winning_patterns,
                hook_weight_adjustments=updated_weights,
                supporting_video_ids=fatigue_vids,
                reason_codes=fatigue_reasons,
                data_sufficiency="SUFFICIENT",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            dec.decision_fingerprint = self._compute_decision_fingerprint(dec)
            return dec

        # Precedence 2: CADENCE INCREASE (Performance velocity > 2x baseline)
        if pi is not None and pi > 2.0:
            slots = list(NORMAL_PUBLISHING_SLOTS) + [SURGE_PUBLISHING_SLOT]
            reasons = [f"HIGH_PERFORMANCE_VELOCITY: Performance Index {pi:.2f} > 2.0x baseline. Surge cadence authorized."]

            dec = CadenceDecision(
                decision_type=CadenceDecisionType.CADENCE_INCREASE,
                recommended_daily_cadence=4,
                recommended_slots=slots,
                pause_duration_hours=None,
                bps=bps,
                performance_index=pi,
                baseline_bps=baseline_bps,
                learning_signals=all_signals,
                winning_patterns=winning_patterns,
                hook_weight_adjustments=updated_weights,
                supporting_video_ids=[current_snapshot.candidate_id] if current_snapshot else [],
                reason_codes=reasons,
                data_sufficiency="SUFFICIENT",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            dec.decision_fingerprint = self._compute_decision_fingerprint(dec)
            return dec

        # Precedence 3: CADENCE NORMAL
        reasons = ["STANDARD_CADENCE: Performance within expected baseline envelope."]
        data_suf = "SUFFICIENT" if baseline_bps is not None else "BASELINE_INSUFFICIENT"
        if base_reason == "BASELINE_INSUFFICIENT":
            reasons.append("BASELINE_INSUFFICIENT: Operating under default cadence until 3 mature cohort observations exist.")

        dec = CadenceDecision(
            decision_type=CadenceDecisionType.CADENCE_NORMAL,
            recommended_daily_cadence=3,
            recommended_slots=list(NORMAL_PUBLISHING_SLOTS),
            pause_duration_hours=None,
            bps=bps,
            performance_index=pi,
            baseline_bps=baseline_bps,
            learning_signals=all_signals,
            winning_patterns=winning_patterns,
            hook_weight_adjustments=updated_weights,
            supporting_video_ids=[current_snapshot.candidate_id] if current_snapshot else [],
            reason_codes=reasons,
            data_sufficiency=data_suf,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        dec.decision_fingerprint = self._compute_decision_fingerprint(dec)
        return dec

    def _compute_decision_fingerprint(self, decision: CadenceDecision) -> str:
        """Deterministic 16-character SHA-256 fingerprint for reproducible arbitration."""
        parts = [
            f"type={decision.decision_type.value}",
            f"cadence={decision.recommended_daily_cadence}",
            f"slots={','.join(decision.recommended_slots)}",
            f"pause={decision.pause_duration_hours}",
            f"bps={decision.bps}",
            f"pi={decision.performance_index}",
            f"base={decision.baseline_bps}",
            f"signals={len(decision.learning_signals)}",
            f"winning={len(decision.winning_patterns)}",
            f"suf={decision.data_sufficiency}",
        ]
        raw = "||".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
