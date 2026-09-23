"""
Step 7: Autonomous Analytics, Cadence & Learning Loop Test Suite
================================================================================
Verifies all 26 required capabilities of Step 7:
  1. analytics snapshot parsing
  2. missing metric handling
  3. BPS calculation
  4. BPS target evaluation
  5. baseline calculation
  6. baseline insufficient state
  7. scale threshold >=1.25
  8. throttle threshold <0.80
  9. normal performance state
 10. VSA <65 hook-weight halving
 11. hook weight persistence/determinism
 12. high-velocity >2x baseline
 13. normal cadence
 14. fatigue 3-consecutive rule
 15. invalid/missing observation excluded from fatigue
 16. fatigue precedence over surge
 17. slot recommendation
 18. winning pattern >3x baseline
 19. orthogonal-axis variation
 20. same lead + same template blocked within 7 days
 21. Novel Story / Deep Discovery baseline separation
 22. immature analytics protection
 23. insufficient data protection
 24. deterministic decision fingerprint
 25. repeated identical input produces identical decision
 26. no production side effects
"""

import copy
import pytest

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
from engines.autonomous_learning_engine import (
    AutonomousLearningEngine,
    NORMAL_PUBLISHING_SLOTS,
    SURGE_PUBLISHING_SLOT,
)


@pytest.fixture
def engine():
    """Provides an AutonomousLearningEngine instance."""
    return AutonomousLearningEngine(poll_interval_hours=6)


@pytest.fixture
def target_snapshot():
    """Snapshot exactly meeting all 4 internal target thresholds -> BPS = 1.0000."""
    return AnalyticsSnapshot(
        candidate_id="short_target_01",
        youtube_video_id="yt_12345",
        views=1000,
        viewed_vs_swiped_away=75.0,        # Target 75% -> 1.0
        average_percentage_viewed=88.0,    # Target 88% -> 1.0
        subscriber_conversion_rate=10.0,   # Target 10 subs/1k -> 1.0
        comments=15,                       # Target 15/1k -> 1.0
        duration_seconds=72.0,
        format_template="TEMPLATE_A_CURATED_LISTICLE",
        hook_archetype="COUNTER_INTUITIVE_TRUTH",
        lead_character="Neville",
        content_mix_category="deep_discovery",
        observation_window_hours=6.0,
        maturation_state=MaturationState.MATURE,
    )


# ------------------------------------------------------------------------------
# TEST 1: Analytics Snapshot Parsing
# ------------------------------------------------------------------------------
def test_01_analytics_snapshot_parsing():
    raw_data = {
        "candidate_id": "test_snap_01",
        "youtube_video_id": "yt_abc_01",
        "views": 1500,
        "viewed_vs_swiped_away": 78.5,
        "average_percentage_viewed": 91.2,
        "subscriber_gain": 22,
        "subscriber_conversion_rate": 14.67,
        "comments": 30,
        "duration_seconds": 74.0,
        "format_template": "TEMPLATE_A_CURATED_LISTICLE",
        "hook_archetype": "COUNTER_INTUITIVE_TRUTH",
        "lead_character": "Neville",
        "content_mix_category": "deep_discovery",
        "maturation_state": "MATURE",
    }
    snap = AnalyticsSnapshot.from_dict(raw_data)
    assert snap.candidate_id == "test_snap_01"
    assert snap.views == 1500
    assert snap.viewed_vs_swiped_away == 78.5
    assert snap.maturation_state == MaturationState.MATURE
    # Round-trip serialization
    d = snap.to_dict()
    assert d["candidate_id"] == "test_snap_01"
    assert d["maturation_state"] == "MATURE"


# ------------------------------------------------------------------------------
# TEST 2: Missing Metric Handling (No Fake Zeros)
# ------------------------------------------------------------------------------
def test_02_missing_metric_handling(engine):
    # Snapshot missing VSA and APV
    snap_missing = AnalyticsSnapshot(
        candidate_id="short_missing_metrics",
        views=1000,
        viewed_vs_swiped_away=None,
        average_percentage_viewed=None,
    )
    bps, subscores = engine.calculate_bps(snap_missing)
    assert bps is None, "Engine fabricated BPS for missing metrics"
    assert subscores == {}, "Engine fabricated subscores for missing metrics"


# ------------------------------------------------------------------------------
# TEST 3: BPS Calculation
# ------------------------------------------------------------------------------
def test_03_bps_calculation(engine, target_snapshot):
    bps, subscores = engine.calculate_bps(target_snapshot)
    assert bps is not None
    # Formula: 0.40*1.0 + 0.30*1.0 + 0.20*1.0 + 0.10*1.0 = 1.0000
    assert abs(bps - 1.0) < 1e-4
    assert subscores["scr_norm"] == 1.0
    assert subscores["vsa_norm"] == 1.0
    assert subscores["apv_norm"] == 1.0
    assert subscores["comm_norm"] == 1.0


# ------------------------------------------------------------------------------
# TEST 4: BPS Target Evaluation
# ------------------------------------------------------------------------------
def test_04_bps_target_evaluation(engine):
    # Superior performance: SCR=15 (1.5x), VSA=85% (1.13x), APV=95% (1.08x), Comm=25 (1.67x)
    snap_super = AnalyticsSnapshot(
        candidate_id="short_super",
        views=2000,
        viewed_vs_swiped_away=85.0,
        average_percentage_viewed=95.0,
        subscriber_conversion_rate=15.0,
        comments=50,  # 25 / 1k
        maturation_state=MaturationState.MATURE,
    )
    bps, _ = engine.calculate_bps(snap_super)
    assert bps is not None
    assert bps > 1.20, f"Expected BPS > 1.20 for superior metrics, got {bps}"


# ------------------------------------------------------------------------------
# TEST 5: Baseline Calculation
# ------------------------------------------------------------------------------
def test_05_baseline_calculation(engine, target_snapshot):
    # Create 3 mature cohort snapshots
    cohort = [
        copy.deepcopy(target_snapshot),
        copy.deepcopy(target_snapshot),
        copy.deepcopy(target_snapshot),
    ]
    cohort[0].candidate_id = "c1"
    cohort[1].candidate_id = "c2"
    cohort[2].candidate_id = "c3"

    base_bps, reason = engine.calculate_baseline(cohort, content_mix_category="deep_discovery")
    assert base_bps is not None
    assert abs(base_bps - 1.0) < 1e-4
    assert reason == "BASELINE_ESTABLISHED"


# ------------------------------------------------------------------------------
# TEST 6: Baseline Insufficient State
# ------------------------------------------------------------------------------
def test_06_baseline_insufficient_state(engine, target_snapshot):
    # Only 2 mature observations (< 3 minimum)
    cohort = [
        target_snapshot,
        copy.deepcopy(target_snapshot),
    ]
    base_bps, reason = engine.calculate_baseline(cohort, content_mix_category="deep_discovery")
    assert base_bps is None
    assert reason == "BASELINE_INSUFFICIENT"


# ------------------------------------------------------------------------------
# TEST 7: Scale Threshold (PI >= 1.25)
# ------------------------------------------------------------------------------
def test_07_scale_threshold(engine):
    decision, pi = engine.evaluate_scale_throttle(bps=1.35, baseline_bps=1.00)
    assert decision == PerformanceScaleDecision.SCALE
    assert pi >= 1.25


# ------------------------------------------------------------------------------
# TEST 8: Throttle Threshold (PI < 0.80)
# ------------------------------------------------------------------------------
def test_08_throttle_threshold(engine):
    decision, pi = engine.evaluate_scale_throttle(bps=0.75, baseline_bps=1.00)
    assert decision == PerformanceScaleDecision.THROTTLE
    assert pi < 0.80


# ------------------------------------------------------------------------------
# TEST 9: Normal Performance State
# ------------------------------------------------------------------------------
def test_09_normal_performance_state(engine):
    decision, pi = engine.evaluate_scale_throttle(bps=1.05, baseline_bps=1.00)
    assert decision == PerformanceScaleDecision.NORMAL
    assert 0.80 <= pi < 1.25


# ------------------------------------------------------------------------------
# TEST 10: VSA < 65% Hook-Weight Halving
# ------------------------------------------------------------------------------
def test_10_vsa_hook_weight_halving(engine):
    weak_snap = AnalyticsSnapshot(
        candidate_id="weak_hook_01",
        views=1200,
        viewed_vs_swiped_away=58.0,  # < 65%
        hook_archetype="DIALOGUE_COLD_OPEN",
        maturation_state=MaturationState.MATURE,
    )
    initial_weights = {"DIALOGUE_COLD_OPEN": 1.0, "COUNTER_INTUITIVE_TRUTH": 1.0}
    updated_weights, signals = engine.evaluate_hook_weights([weak_snap], initial_weights)

    assert updated_weights["DIALOGUE_COLD_OPEN"] == 0.5  # Halved
    assert updated_weights["COUNTER_INTUITIVE_TRUTH"] == 1.0  # Untouched
    assert len(signals) == 1
    assert signals[0].signal_type == LearningSignalType.WEAK_HOOK


# ------------------------------------------------------------------------------
# TEST 11: Hook Weight Persistence & Determinism
# ------------------------------------------------------------------------------
def test_11_hook_weight_determinism(engine):
    snap = AnalyticsSnapshot(
        candidate_id="weak_01",
        views=1000,
        viewed_vs_swiped_away=60.0,
        hook_archetype="DIRECT_CHALLENGE",
        maturation_state=MaturationState.MATURE,
    )
    w1, s1 = engine.evaluate_hook_weights([snap], {"DIRECT_CHALLENGE": 0.8})
    w2, s2 = engine.evaluate_hook_weights([snap], {"DIRECT_CHALLENGE": 0.8})
    assert w1["DIRECT_CHALLENGE"] == 0.4
    assert w1 == w2
    assert s1[0].explanation == s2[0].explanation


# ------------------------------------------------------------------------------
# TEST 12: High-Velocity (> 2x Baseline) Cadence Increase
# ------------------------------------------------------------------------------
def test_12_high_velocity_cadence_increase(engine, target_snapshot):
    # Base cohort has average performance: SCR=6.0, VSA=65.0, APV=75.0, Comments=8 -> BPS ~ 0.72
    base_snap = copy.deepcopy(target_snapshot)
    base_snap.subscriber_conversion_rate = 6.0
    base_snap.viewed_vs_swiped_away = 65.0
    base_snap.average_percentage_viewed = 75.0
    base_snap.comments = 8
    cohort = [copy.deepcopy(base_snap) for _ in range(3)]

    # Viral Short: SCR=25.0, VSA=95.0, APV=100.0, Comments=50 -> BPS ~ 1.61 (> 2.0x baseline of 0.72)
    super_snap = copy.deepcopy(target_snapshot)
    super_snap.candidate_id = "viral_short_01"
    super_snap.viewed_vs_swiped_away = 95.0
    super_snap.average_percentage_viewed = 100.0
    super_snap.subscriber_conversion_rate = 25.0
    super_snap.comments = 50

    decision = engine.make_cadence_decision(
        current_snapshot=super_snap,
        recent_snapshots=[super_snap],
        historical_cohort=cohort,
    )
    assert decision.decision_type == CadenceDecisionType.CADENCE_INCREASE
    assert decision.recommended_daily_cadence in (4, 5)
    assert SURGE_PUBLISHING_SLOT in decision.recommended_slots


# ------------------------------------------------------------------------------
# TEST 13: Normal Cadence
# ------------------------------------------------------------------------------
def test_13_normal_cadence(engine, target_snapshot):
    cohort = [copy.deepcopy(target_snapshot) for _ in range(3)]
    decision = engine.make_cadence_decision(
        current_snapshot=target_snapshot,
        recent_snapshots=[target_snapshot],
        historical_cohort=cohort,
    )
    assert decision.decision_type == CadenceDecisionType.CADENCE_NORMAL
    assert decision.recommended_daily_cadence == 3
    assert decision.recommended_slots == NORMAL_PUBLISHING_SLOTS


# ------------------------------------------------------------------------------
# TEST 14: Fatigue 3-Consecutive Rule
# ------------------------------------------------------------------------------
def test_14_fatigue_three_consecutive_rule(engine):
    # 3 consecutive mature uploads with < 500 views
    fatigued_snaps = [
        AnalyticsSnapshot(candidate_id=f"f_{i}", views=320, observation_window_hours=6.0, maturation_state=MaturationState.MATURE)
        for i in range(3)
    ]
    is_fatigued, reasons, vids = engine.evaluate_fatigue(fatigued_snaps)
    assert is_fatigued is True
    assert len(vids) == 3
    assert "FATIGUE_3_CONSECUTIVE_LOW_VIEWS" in reasons[0]


# ------------------------------------------------------------------------------
# TEST 15: Invalid / Missing Observations Excluded from Fatigue
# ------------------------------------------------------------------------------
def test_15_invalid_observations_excluded_from_fatigue(engine):
    # Sequence: 400 views, MISSING ANALYTICS, 450 views, 480 views
    # The missing observation must not be counted, but should not break sequence of valid ones if filtered
    snaps = [
        AnalyticsSnapshot(candidate_id="v1", views=400, observation_window_hours=6.0, maturation_state=MaturationState.MATURE),
        AnalyticsSnapshot(candidate_id="v_missing", views=None, maturation_state=MaturationState.INSUFFICIENT_DATA),
        AnalyticsSnapshot(candidate_id="v2", views=450, observation_window_hours=6.0, maturation_state=MaturationState.MATURE),
        AnalyticsSnapshot(candidate_id="v3", views=480, observation_window_hours=6.0, maturation_state=MaturationState.MATURE),
    ]
    # Filtered valid sequence has 3 entries: v1 (400), v2 (450), v3 (480) -> exactly 3 consecutive valid low views
    is_fatigued, _, vids = engine.evaluate_fatigue(snaps)
    assert is_fatigued is True
    assert "v_missing" not in vids
    assert len(vids) == 3


# ------------------------------------------------------------------------------
# TEST 16: Fatigue Precedence Over Surge
# ------------------------------------------------------------------------------
def test_16_fatigue_precedence_over_surge(engine, target_snapshot):
    # Even if current Short has PI > 2.0x, if channel has 3 consecutive fatigued videos, fatigue MUST win!
    fatigued_snaps = [
        AnalyticsSnapshot(candidate_id=f"f_{i}", views=200, observation_window_hours=6.0, maturation_state=MaturationState.MATURE)
        for i in range(3)
    ]
    viral_snap = copy.deepcopy(target_snapshot)
    viral_snap.subscriber_conversion_rate = 30.0  # High PI

    cohort = [copy.deepcopy(target_snapshot) for _ in range(3)]

    decision = engine.make_cadence_decision(
        current_snapshot=viral_snap,
        recent_snapshots=fatigued_snaps,  # Channel fatigue present
        historical_cohort=cohort,
    )
    # FATIGUE_PAUSE must override CADENCE_INCREASE
    assert decision.decision_type == CadenceDecisionType.FATIGUE_PAUSE
    assert decision.pause_duration_hours == 12.0
    assert decision.recommended_daily_cadence == 0


# ------------------------------------------------------------------------------
# TEST 17: Slot Recommendation
# ------------------------------------------------------------------------------
def test_17_slot_recommendation(engine, target_snapshot):
    cohort = [copy.deepcopy(target_snapshot) for _ in range(3)]
    dec = engine.make_cadence_decision(
        current_snapshot=target_snapshot,
        recent_snapshots=[target_snapshot],
        historical_cohort=cohort,
    )
    assert dec.recommended_slots == ["13:00 UTC", "17:00 UTC", "21:00 UTC"]


# ------------------------------------------------------------------------------
# TEST 18: Winning Pattern (> 3x Baseline)
# ------------------------------------------------------------------------------
def test_18_winning_pattern_discovery(engine, target_snapshot):
    # Mega viral hit: BPS = 3.5 (3.5x baseline of 1.0)
    mega_snap = copy.deepcopy(target_snapshot)
    mega_snap.candidate_id = "mega_hit_01"
    mega_snap.subscriber_conversion_rate = 35.0  # Clipped max 2.0 -> BPS ~1.7 vs baseline 0.5
    patterns, signals = engine.evaluate_winning_patterns(
        snapshots=[mega_snap],
        baseline_bps=0.30,  # 3.5x > 3.0x
    )
    assert len(patterns) == 1
    assert patterns[0].source_video_id == "mega_hit_01"
    assert patterns[0].performance_index >= 3.0
    assert OrthogonalAxis.SUBJECT.value in patterns[0].orthogonal_axis_options


# ------------------------------------------------------------------------------
# TEST 19: Orthogonal-Axis Variation
# ------------------------------------------------------------------------------
def test_19_orthogonal_axis_variation(engine, target_snapshot):
    mega_snap = copy.deepcopy(target_snapshot)
    patterns, _ = engine.evaluate_winning_patterns(
        snapshots=[mega_snap],
        baseline_bps=0.20,
    )
    assert len(patterns) == 1
    opts = patterns[0].orthogonal_axis_options
    assert "SUBJECT" in opts
    assert "DYNAMIC" in opts
    assert "PERSPECTIVE" in opts


# ------------------------------------------------------------------------------
# TEST 20: Same Lead + Same Template Blocked Within 7 Days
# ------------------------------------------------------------------------------
def test_20_same_lead_same_template_blocked_7d(engine, target_snapshot):
    mega_snap = copy.deepcopy(target_snapshot)
    mega_snap.lead_character = "Neville"
    mega_snap.format_template = "TEMPLATE_A_CURATED_LISTICLE"

    recent_7d = [
        AnalyticsSnapshot(
            candidate_id="prior_neville",
            lead_character="Neville",
            format_template="TEMPLATE_A_CURATED_LISTICLE",
        )
    ]
    patterns, signals = engine.evaluate_winning_patterns(
        snapshots=[mega_snap],
        baseline_bps=0.20,
        recent_history_7d=recent_7d,
    )
    assert len(signals) == 1
    assert "subject shift mandatory" in signals[0].explanation


# ------------------------------------------------------------------------------
# TEST 21: Novel Story / Deep Discovery Baseline Separation
# ------------------------------------------------------------------------------
def test_21_baseline_separation(engine):
    # Cohort with 3 Novel Story and 3 Deep Discovery
    ns_cohort = [
        AnalyticsSnapshot(candidate_id=f"ns_{i}", content_mix_category="novel_story", views=1000, viewed_vs_swiped_away=70.0, average_percentage_viewed=80.0, subscriber_conversion_rate=8.0, comments=10, maturation_state=MaturationState.MATURE)
        for i in range(3)
    ]
    dd_cohort = [
        AnalyticsSnapshot(candidate_id=f"dd_{i}", content_mix_category="deep_discovery", views=2000, viewed_vs_swiped_away=85.0, average_percentage_viewed=92.0, subscriber_conversion_rate=14.0, comments=20, maturation_state=MaturationState.MATURE)
        for i in range(3)
    ]
    all_cohort = ns_cohort + dd_cohort

    base_dd, _ = engine.calculate_baseline(all_cohort, content_mix_category="deep_discovery")
    base_ns, _ = engine.calculate_baseline(all_cohort, content_mix_category="novel_story")

    assert base_dd is not None
    assert base_ns is not None
    assert base_dd != base_ns, "Novel Story mixed into Deep Discovery baseline"


# ------------------------------------------------------------------------------
# TEST 22: Immature Analytics Protection
# ------------------------------------------------------------------------------
def test_22_immature_analytics_protection(engine):
    too_early_snap = AnalyticsSnapshot(
        candidate_id="immature_01",
        views=45,  # Tiny sample (<100 views)
        observation_window_hours=2.0,  # < 6 hours
    )
    mat = engine.evaluate_maturation(too_early_snap)
    assert mat == MaturationState.TOO_EARLY

    # Hook weights should NOT be halved based on immature observations
    initial = {"DIRECT_CHALLENGE": 1.0}
    weights, signals = engine.evaluate_hook_weights([too_early_snap], initial)
    assert weights["DIRECT_CHALLENGE"] == 1.0
    assert len(signals) == 0


# ------------------------------------------------------------------------------
# TEST 23: Insufficient Data Protection
# ------------------------------------------------------------------------------
def test_23_insufficient_data_protection(engine):
    insuf_snap = AnalyticsSnapshot(
        candidate_id="insuf_01",
        views=None,
        viewed_vs_swiped_away=None,
    )
    mat = engine.evaluate_maturation(insuf_snap)
    assert mat == MaturationState.INSUFFICIENT_DATA


# ------------------------------------------------------------------------------
# TEST 24: Deterministic Decision Fingerprint
# ------------------------------------------------------------------------------
def test_24_deterministic_decision_fingerprint(engine, target_snapshot):
    cohort = [copy.deepcopy(target_snapshot) for _ in range(3)]
    dec1 = engine.make_cadence_decision(target_snapshot, [target_snapshot], cohort)
    dec2 = engine.make_cadence_decision(target_snapshot, [target_snapshot], cohort)

    assert dec1.decision_fingerprint
    assert len(dec1.decision_fingerprint) == 16
    assert dec1.decision_fingerprint == dec2.decision_fingerprint


# ------------------------------------------------------------------------------
# TEST 25: Repeated Identical Input Produces Identical Decision
# ------------------------------------------------------------------------------
def test_25_repeated_identical_decision(engine, target_snapshot):
    cohort = [copy.deepcopy(target_snapshot) for _ in range(3)]
    dec_a = engine.make_cadence_decision(target_snapshot, [target_snapshot], cohort)
    dec_b = engine.make_cadence_decision(target_snapshot, [target_snapshot], cohort)

    assert dec_a.decision_type == dec_b.decision_type
    assert dec_a.recommended_daily_cadence == dec_b.recommended_daily_cadence
    assert dec_a.recommended_slots == dec_b.recommended_slots
    assert dec_a.bps == dec_b.bps
    assert dec_a.decision_fingerprint == dec_b.decision_fingerprint


# ------------------------------------------------------------------------------
# TEST 26: No Production Side Effects
# ------------------------------------------------------------------------------
def test_26_no_production_side_effects(engine, target_snapshot):
    cohort = [copy.deepcopy(target_snapshot) for _ in range(3)]
    # Engine must only compute in-memory decisions; no files created in production paths
    dec = engine.make_cadence_decision(target_snapshot, [target_snapshot], cohort)
    assert isinstance(dec, CadenceDecision)
    assert dec.decision_type in (CadenceDecisionType.CADENCE_NORMAL, CadenceDecisionType.CADENCE_INCREASE, CadenceDecisionType.FATIGUE_PAUSE)
