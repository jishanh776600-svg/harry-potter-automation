"""
Evidence Reporter & Forensic Report Generator
Produces structured JSON machine-readable evidence records and human-readable forensic reports.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

from py_visual_evidence.schema import ObservationEvidence, EvidenceVerdict


class EvidenceReporter:
    @staticmethod
    def generate_json_artifact(evidence: ObservationEvidence, out_path: Optional[Path] = None) -> str:
        """Serializes ObservationEvidence to machine-readable JSON."""
        data_json = evidence.model_dump_json(indent=2)
        if out_path:
            out_p = Path(out_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "w", encoding="utf-8") as f:
                f.write(data_json)
        return data_json

    @staticmethod
    def generate_forensic_markdown_report(evidence: ObservationEvidence, out_path: Optional[Path] = None) -> str:
        """Generates a human-readable forensic report explaining the evidence decision."""
        verdict_str = evidence.verdict.value
        status_symbol = "PASSED" if evidence.verdict == EvidenceVerdict.PASS else "REJECTED"

        grounded_str = "\n".join(
            [f"  - **{e.entity_name}** ({e.role}): confidence {e.confidence:.2f}, bbox=[x={e.bbox.x:.2f}, y={e.bbox.y:.2f}, w={e.bbox.w:.2f}, h={e.bbox.h:.2f}]"
             for e in evidence.grounded_entities]
        ) or "  *No entities grounded.*"

        action_summary = "N/A"
        if evidence.action_result:
            ar = evidence.action_result
            action_summary = f"{ar.action_name}: detected={ar.detected} (conf={ar.confidence:.2f}, peak={ar.peak_metric_value:.2f}, threshold={ar.threshold_used:.2f})"

        state_summary = "N/A"
        if evidence.state_transition_result:
            st = evidence.state_transition_result
            state_summary = f"detected={st.detected}, initial={st.initial_state_metric:.2f}, final={st.final_state_metric:.2f}, disruption_ratio={st.disruption_ratio:.2f}"

        crop_summary = "N/A"
        if evidence.crop_result:
            cr = evidence.crop_result
            crop_summary = f"aspect={cr.aspect_ratio}, retained_area={cr.retained_subject_ratio:.2f}, safe_zone={cr.inside_safe_zone}, passed={cr.passed}"

        report = f"""# VISUAL EVIDENCE FORENSIC AUDIT REPORT

**Assertion ID**: `{evidence.assertion_id}`  
**Video Clip**: `{evidence.video_path}`  
**Time Range**: `{evidence.time_range[0]:.2f}s` to `{evidence.time_range[1]:.2f}s`  
**Overall Verdict**: **{verdict_str}** ({status_symbol})  
**Confidence**: `{evidence.confidence:.2f}`  
**Timestamp**: `{evidence.timestamp_iso}`  

---

## 1. Executive Forensic Summary
- **Why did this clip {status_symbol.lower()}?**  
  {evidence.rejection_reason if evidence.rejection_reason else "All visual assertions (subject presence, object presence, physical action trajectory, relationship, state transition, and 9:16 safe-zone crop) were successfully verified from observable video evidence."}

---

## 2. Visual Grounding & Spatial Localization
- **Shot Count**: `{evidence.shot_count}` uninterrupted camera shot(s)
- **Grounded Entities**:
{grounded_str}

---

## 3. Physical Action & Kinematics
- **Observed Action**: {action_summary}
- **Spatial Relationship**: `{evidence.relationship_summary}` (Verified: `{evidence.relationship_verified}`)

---

## 4. Physical State Transition
- **State Change Evidence**: {state_summary}

---

## 5. Viewer-Visible 9:16 Crop Validation
- **Crop Verification**: {crop_summary}
- **Causal Sequence Integrity**: `{evidence.causal_order_passed}`

---

## 6. Audit Metrics Snapshot
```json
{json.dumps(evidence.metrics, indent=2)}
```
"""
        if out_path:
            out_p = Path(out_path)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            with open(out_p, "w", encoding="utf-8") as f:
                f.write(report)
        return report
