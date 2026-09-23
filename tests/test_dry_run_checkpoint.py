"""
Step 8: End-to-End Dry Run & System Checkpoint Test Suite
================================================================================
Verifies all 22 required capabilities of Step 8:
  1. Step 1 -> Step 2 contract
  2. Step 2 -> Step 3 contract
  3. Step 3 -> Step 4 contract
  4. Step 4 -> Step 5 contract
  5. Step 5 -> Step 6 contract
  6. Step 6 valid package
  7. Step 6 invalid package
  8. Step 7 normal decision
  9. Step 7 surge decision
 10. Step 7 fatigue decision
 11. full contract chain
 12. deterministic repeated dry-run
 13. fingerprint propagation
 14. provenance propagation
 15. Novel Story isolation
 16. invalid package blocks readiness
 17. no production side effects
 18. no YouTube calls
 19. no Drive production mutation
 20. AL AMR isolation
 21. configuration/path assertions
 22. checkpoint report generation
"""

import copy
import pytest

from config.settings import (
    PROJECT_ROOT,
    EXPECTED_GOOGLE_ACCOUNT,
    EXPECTED_DRIVE_ROOT_ID,
    EXPECTED_YOUTUBE_CHANNEL_ID,
    AUTOMATION_ID,
)
from core.dry_run_types import (
    StepContractStatus,
    ContractVerificationResult,
    DryRunSystemReport,
)
from core.preprocessor_types import PreprocessingStatus
from engines.dry_run_checkpoint import DryRunCheckpointEngine


@pytest.fixture
def checkpoint_engine():
    """Provides an initialized DryRunCheckpointEngine instance."""
    return DryRunCheckpointEngine()


@pytest.fixture
def system_report(checkpoint_engine):
    """Executes a full dry run report for inspection."""
    return checkpoint_engine.execute_dry_run(candidate_id="checkpoint_test_01")


# ------------------------------------------------------------------------------
# TEST 1: Step 1 -> Step 2 Contract
# ------------------------------------------------------------------------------
def test_01_step1_to_step2_contract(checkpoint_engine):
    story_plan = checkpoint_engine._build_synthetic_story_plan("test_c1")
    storyboard = checkpoint_engine._build_synthetic_storyboard(story_plan)
    assert storyboard.storyboard_id.startswith("sb_topic_")
    assert len(storyboard.beats) == 42
    assert storyboard.total_target_duration == 72.0
    assert storyboard.metadata.get("evidence_provenance") == "NOVEL_CANON"


# ------------------------------------------------------------------------------
# TEST 2: Step 2 -> Step 3 Contract
# ------------------------------------------------------------------------------
def test_02_step2_to_step3_contract(checkpoint_engine):
    story_plan = checkpoint_engine._build_synthetic_story_plan("test_c2")
    storyboard = checkpoint_engine._build_synthetic_storyboard(story_plan)
    assets = checkpoint_engine._build_synthetic_preprocessed_assets(storyboard)
    assert len(assets) == len(storyboard.beats)
    for a in assets:
        assert a.output_width == 1080
        assert a.output_height == 1920
        assert a.fps == 30.0
        assert len(a.fingerprint) == 16
        assert a.status == PreprocessingStatus.COMPLETED


# ------------------------------------------------------------------------------
# TEST 3: Step 3 -> Step 4 Contract
# ------------------------------------------------------------------------------
def test_03_step3_to_step4_contract(checkpoint_engine):
    story_plan = checkpoint_engine._build_synthetic_story_plan("test_c3")
    storyboard = checkpoint_engine._build_synthetic_storyboard(story_plan)
    assets = checkpoint_engine._build_synthetic_preprocessed_assets(storyboard)
    timeline = checkpoint_engine.remotion_engine.build_editorial_timeline(
        storyboard_plan=storyboard,
        preprocessed_assets=assets,
        script_text=story_plan.thesis,
        candidate_type="deep_discovery",
    )
    assert 70.0 <= timeline.total_duration_seconds <= 75.0
    assert 2100 <= timeline.total_frames <= 2250
    assert len(timeline.clips) == len(storyboard.beats)
    assert timeline.deterministic_fingerprint


# ------------------------------------------------------------------------------
# TEST 4: Step 4 -> Step 5 Contract
# ------------------------------------------------------------------------------
def test_04_step4_to_step5_contract(checkpoint_engine):
    story_plan = checkpoint_engine._build_synthetic_story_plan("test_c4")
    storyboard = checkpoint_engine._build_synthetic_storyboard(story_plan)
    assets = checkpoint_engine._build_synthetic_preprocessed_assets(storyboard)
    timeline = checkpoint_engine.remotion_engine.build_editorial_timeline(
        storyboard_plan=storyboard,
        preprocessed_assets=assets,
        script_text=story_plan.thesis,
        candidate_type="deep_discovery",
    )
    sfx_plan = checkpoint_engine.sfx_engine.generate_sfx_plan(
        editorial_timeline=timeline,
        candidate_type="deep_discovery",
    )
    assert sfx_plan.total_cues > 0
    assert sfx_plan.sfx_fingerprint
    assert sfx_plan.metadata.get("editorial_source_fingerprint") == timeline.deterministic_fingerprint


# ------------------------------------------------------------------------------
# TEST 5: Step 5 -> Step 6 Contract
# ------------------------------------------------------------------------------
def test_05_step5_to_step6_contract(checkpoint_engine):
    report = checkpoint_engine.execute_dry_run("test_c5")
    c56 = next(c for c in report.contract_results if c.boundary_id == "step5_to_step6")
    assert c56.status == StepContractStatus.PASS
    assert c56.is_schema_compliant is True


# ------------------------------------------------------------------------------
# TEST 6: Step 6 Valid Package
# ------------------------------------------------------------------------------
def test_06_step6_valid_package(system_report):
    assert system_report.valid_dry_run_passed is True
    assert system_report.overall_status == StepContractStatus.PASS


# ------------------------------------------------------------------------------
# TEST 7: Step 6 Invalid Package
# ------------------------------------------------------------------------------
def test_07_step6_invalid_package(system_report):
    assert system_report.invalid_dry_run_blocked is True
    c_inv = next(c for c in system_report.contract_results if c.boundary_id == "step6_invalid_adversarial_test")
    assert c_inv.status == StepContractStatus.PASS
    assert "Forbidden visual correctly blocked readiness" in c_inv.diagnostic_message


# ------------------------------------------------------------------------------
# TEST 8: Step 7 Normal Decision
# ------------------------------------------------------------------------------
def test_08_step7_normal_decision(system_report):
    assert "case_a_normal" in system_report.cadence_simulations
    assert "CADENCE_NORMAL" in system_report.cadence_simulations["case_a_normal"]
    assert "Cadence: 3/day" in system_report.cadence_simulations["case_a_normal"]


# ------------------------------------------------------------------------------
# TEST 9: Step 7 Surge Decision
# ------------------------------------------------------------------------------
def test_09_step7_surge_decision(system_report):
    assert "case_b_surge" in system_report.cadence_simulations
    assert "CADENCE_INCREASE" in system_report.cadence_simulations["case_b_surge"]
    assert "SurgeSlot: 01:00 UTC" in system_report.cadence_simulations["case_b_surge"]


# ------------------------------------------------------------------------------
# TEST 10: Step 7 Fatigue Decision
# ------------------------------------------------------------------------------
def test_10_step7_fatigue_decision(system_report):
    assert "case_c_fatigue" in system_report.cadence_simulations
    assert "FATIGUE_PAUSE" in system_report.cadence_simulations["case_c_fatigue"]
    assert "Pause: 12.0h" in system_report.cadence_simulations["case_c_fatigue"]


# ------------------------------------------------------------------------------
# TEST 11: Full Contract Chain
# ------------------------------------------------------------------------------
def test_11_full_contract_chain(system_report):
    expected_boundaries = [
        "step1_to_step2",
        "step2_to_step3",
        "step3_to_step4",
        "step4_to_step5",
        "step5_to_step6",
        "step6_to_step7",
    ]
    registered_boundaries = [c.boundary_id for c in system_report.contract_results]
    for exp in expected_boundaries:
        assert exp in registered_boundaries, f"Missing boundary contract: {exp}"


# ------------------------------------------------------------------------------
# TEST 12: Deterministic Repeated Dry Run
# ------------------------------------------------------------------------------
def test_12_deterministic_repeated_dry_run(checkpoint_engine):
    report_a = checkpoint_engine.execute_dry_run("det_run", run_determinism_check=False)
    report_b = checkpoint_engine.execute_dry_run("det_run", run_determinism_check=False)

    assert report_a.fingerprints == report_b.fingerprints
    assert report_a.valid_dry_run_passed == report_b.valid_dry_run_passed
    assert report_a.invalid_dry_run_blocked == report_b.invalid_dry_run_blocked


# ------------------------------------------------------------------------------
# TEST 13: Fingerprint Propagation
# ------------------------------------------------------------------------------
def test_13_fingerprint_propagation(system_report):
    fps = system_report.fingerprints
    assert "step1_narrative" in fps
    assert "step2_storyboard" in fps
    assert "step3_preprocessing" in fps
    assert "step4_editorial" in fps
    assert "step5_sfx" in fps
    assert "step6_qa" in fps
    assert "step7_cadence" in fps
    # All fingerprints must be non-empty 16-character SHA-256 tokens
    for k, v in fps.items():
        assert len(v) == 16, f"Invalid fingerprint format for {k}: {v}"


# ------------------------------------------------------------------------------
# TEST 14: Provenance Propagation
# ------------------------------------------------------------------------------
def test_14_provenance_propagation(checkpoint_engine):
    story_plan = checkpoint_engine._build_synthetic_story_plan("prov_test")
    storyboard = checkpoint_engine._build_synthetic_storyboard(story_plan)
    assert storyboard.metadata.get("evidence_provenance") == "NOVEL_CANON"
    assert len(story_plan.evidence_points) == 2
    assert story_plan.evidence_points[0].source_id == "hp1_ch07_sorting"


# ------------------------------------------------------------------------------
# TEST 15: Novel Story Isolation
# ------------------------------------------------------------------------------
def test_15_novel_story_isolation(checkpoint_engine):
    # Remotion editorial engine must raise ValueError if candidate_type="novel_story"
    story_plan = checkpoint_engine._build_synthetic_story_plan("ns_test")
    storyboard = checkpoint_engine._build_synthetic_storyboard(story_plan)
    assets = checkpoint_engine._build_synthetic_preprocessed_assets(storyboard)

    with pytest.raises(ValueError, match="Novel Story pipeline is isolated"):
        checkpoint_engine.remotion_engine.build_editorial_timeline(
            storyboard_plan=storyboard,
            preprocessed_assets=assets,
            candidate_type="novel_story",
        )


# ------------------------------------------------------------------------------
# TEST 16: Invalid Package Blocks Readiness
# ------------------------------------------------------------------------------
def test_16_invalid_package_blocks_readiness(checkpoint_engine):
    report = checkpoint_engine.execute_dry_run("test_blocker")
    c_inv = next(c for c in report.contract_results if c.boundary_id == "step6_invalid_adversarial_test")
    assert c_inv.status == StepContractStatus.PASS
    assert report.invalid_dry_run_blocked is True


# ------------------------------------------------------------------------------
# TEST 17: No Production Side Effects
# ------------------------------------------------------------------------------
def test_17_no_production_side_effects(system_report):
    assert system_report.no_production_side_effects is True


# ------------------------------------------------------------------------------
# TEST 18: No YouTube Calls
# ------------------------------------------------------------------------------
def test_18_no_youtube_calls(checkpoint_engine):
    # Verify dry-run engine has no references to YouTube upload/scheduling methods
    assert not hasattr(checkpoint_engine, "upload_to_youtube")
    assert not hasattr(checkpoint_engine, "schedule_youtube_short")


# ------------------------------------------------------------------------------
# TEST 19: No Drive Production Mutation
# ------------------------------------------------------------------------------
def test_19_no_drive_production_mutation(checkpoint_engine):
    # Verify dry-run engine has no references to Drive write/upload methods
    assert not hasattr(checkpoint_engine, "upload_to_drive")
    assert not hasattr(checkpoint_engine, "move_to_ready_vault")


# ------------------------------------------------------------------------------
# TEST 20: AL AMR Isolation
# ------------------------------------------------------------------------------
def test_20_al_amr_isolation():
    proj_path = str(PROJECT_ROOT).lower()
    assert "yt automation" not in proj_path, "FATAL: AL AMR workspace referenced in PROJECT_ROOT!"


# ------------------------------------------------------------------------------
# TEST 21: Configuration & Path Assertions
# ------------------------------------------------------------------------------
def test_21_configuration_assertions():
    assert EXPECTED_GOOGLE_ACCOUNT == "jishan760@gmail.com" or EXPECTED_GOOGLE_ACCOUNT == "jishanh760@gmail.com"
    assert EXPECTED_DRIVE_ROOT_ID == "11K6v7PjLsnb8fVCsAm00YGmamvv4ygzC"
    assert EXPECTED_YOUTUBE_CHANNEL_ID == "UCsghEXDa3EzxI4d93cjT-bQ"
    assert AUTOMATION_ID == "harry_potter"


# ------------------------------------------------------------------------------
# TEST 22: Checkpoint Report Generation
# ------------------------------------------------------------------------------
def test_22_checkpoint_report_generation(system_report):
    report_dict = system_report.to_dict()
    assert report_dict["overall_status"] == "PASS"
    assert report_dict["valid_dry_run_passed"] is True
    assert report_dict["invalid_dry_run_blocked"] is True
    assert report_dict["determinism_verified"] is True
    assert report_dict["isolation_verified"] is True
    assert len(report_dict["contract_results"]) >= 6
    assert len(report_dict["fingerprints"]) == 7
