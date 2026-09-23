"""
STORY FORGE Automated 10-Point QA Verification Gate Types & Contracts (Step 6)
================================================================================
Defines canonical data models for pre-production verification:
  - QASeverity: BLOCKER, ERROR, WARNING, PASS
  - QACheckStatus: PASS, FAIL, NOT_APPLICABLE
  - QACheckResult: Individual diagnostic inspection report
  - QAPackageReport: Complete directorial audit and production readiness decision
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any


class QASeverity(str, Enum):
    """Severity classification for QA inspection results."""
    BLOCKER = "BLOCKER"   # Absolute veto: immediate rejection, must never enter production
    ERROR = "ERROR"       # Rule failure: short cannot be production ready
    WARNING = "WARNING"   # Advisory/sub-optimal condition: auditable, non-fatal
    PASS = "PASS"         # Invariant fully satisfied


class QACheckStatus(str, Enum):
    """Operational status of an individual QA check."""
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class QACheckResult:
    """
    Structured diagnostic result for a single QA check.
    Guarantees actionable diagnosis without silent auto-repair.
    """
    check_id: str                         # e.g., "check_01_duration"
    name: str                             # Human-readable check title
    status: QACheckStatus
    severity: QASeverity
    measured_value: Any                   # Actual measured property (float, int, str, etc.)
    expected_value_range: Any             # Expected constraint or boundary
    diagnostic_message: str               # Technical explanation of status
    remediation_suggestion: str = ""      # Prescriptive instruction for upstream repair

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, QACheckStatus) else str(self.status),
            "severity": self.severity.value if isinstance(self.severity, QASeverity) else str(self.severity),
            "measured_value": self.measured_value,
            "expected_value_range": self.expected_value_range,
            "diagnostic_message": self.diagnostic_message,
            "remediation_suggestion": self.remediation_suggestion,
        }


@dataclass
class QAPackageReport:
    """
    Comprehensive verification report evaluating a complete Short candidate package.
    Frame-locked, cross-system auditable, and deterministically fingerprinted.
    """
    qa_run_id: str
    candidate_id: str
    candidate_type: str                   # "deep_discovery" or "novel_story"
    editorial_fingerprint: str
    sfx_fingerprint: str
    duration: float
    overall_pass: bool
    production_ready: bool
    checks: List[QACheckResult] = field(default_factory=list)
    blocker_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    timestamp: str = ""
    qa_fingerprint: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "qa_run_id": self.qa_run_id,
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type,
            "editorial_fingerprint": self.editorial_fingerprint,
            "sfx_fingerprint": self.sfx_fingerprint,
            "duration": self.duration,
            "overall_pass": self.overall_pass,
            "production_ready": self.production_ready,
            "checks": [c.to_dict() for c in self.checks],
            "blocker_count": self.blocker_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "timestamp": self.timestamp,
            "qa_fingerprint": self.qa_fingerprint,
            "metadata": self.metadata,
        }
