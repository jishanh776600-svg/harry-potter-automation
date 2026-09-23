"""
STORY FORGE End-to-End Dry Run & System Checkpoint Models (Step 8)
================================================================================
Defines canonical contracts for the Step 8 end-to-end dry run verification:
  - StepContractStatus: PASS, FAIL, WARNING, NOT_TESTED
  - ContractVerificationResult: Diagnostic record for each stage-to-stage handover
  - DryRunSystemReport: Complete auditable end-to-end verification report
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any


class StepContractStatus(str, Enum):
    """Execution status for an inter-step data contract boundary."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NOT_TESTED = "NOT_TESTED"


@dataclass
class ContractVerificationResult:
    """Diagnostic audit record for an inter-step boundary transition."""
    boundary_id: str                      # e.g., "step1_to_step2"
    source_step: str                      # e.g., "Step 1 (Narrative Engine)"
    target_step: str                      # e.g., "Step 2 (Storyboard Planner)"
    status: StepContractStatus
    input_fingerprint: str
    output_fingerprint: str
    is_schema_compliant: bool
    diagnostic_message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, StepContractStatus) else str(self.status)
        return d


@dataclass
class DryRunSystemReport:
    """
    Comprehensive end-to-end dry-run audit report.
    Validates complete Step 1 -> Step 7 chain without triggering production.
    """
    dry_run_id: str
    timestamp: str
    overall_status: StepContractStatus
    valid_dry_run_passed: bool
    invalid_dry_run_blocked: bool
    determinism_verified: bool
    isolation_verified: bool
    no_production_side_effects: bool
    contract_results: List[ContractVerificationResult] = field(default_factory=list)
    fingerprints: Dict[str, str] = field(default_factory=dict)
    cadence_simulations: Dict[str, str] = field(default_factory=dict)
    isolation_audit: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dry_run_id": self.dry_run_id,
            "timestamp": self.timestamp,
            "overall_status": self.overall_status.value if isinstance(self.overall_status, StepContractStatus) else str(self.overall_status),
            "valid_dry_run_passed": self.valid_dry_run_passed,
            "invalid_dry_run_blocked": self.invalid_dry_run_blocked,
            "determinism_verified": self.determinism_verified,
            "isolation_verified": self.isolation_verified,
            "no_production_side_effects": self.no_production_side_effects,
            "contract_results": [c.to_dict() for c in self.contract_results],
            "fingerprints": self.fingerprints,
            "cadence_simulations": self.cadence_simulations,
            "isolation_audit": self.isolation_audit,
            "metadata": self.metadata,
        }
