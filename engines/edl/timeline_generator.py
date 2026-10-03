"""
STORY FORGE — Visual EDL Master Generator (Parts 15, 16, 20, 25)
================================================================
Master orchestrator producing the complete, verified, arbitrated Visual EDL
before rendering. Computes cryptographic lineage and produces EDL preview reports.
"""

import logging
import hashlib
import time
from typing import Dict, List, Any, Optional

from engines.edl.models import (
    LockedNarrationInput,
    VisualBeat,
    EvaluatedCandidate,
    EDLEntry,
    VisualEDL,
    EDLLineage,
    CoverageState,
    CoverageRequirement,
    SearchDiagnosticRecord,
)
from engines.edl.beat_compiler import VisualBeatCompiler
from engines.edl.deep_search import DeepMovieSearcher
from engines.edl.candidate_evaluator import CandidateEvidenceEvaluator
from engines.edl.arbitration import CandidateArbitrator

logger = logging.getLogger("VisualEDLGenerator")


class VisualEDLGenerator:
    """
    Coordinates the full Phase 4 pipeline to generate a verified Visual EDL.
    Hard Invariant: Rendering is NOT part of this layer.
    """

    def __init__(
        self,
        beat_compiler: Optional[VisualBeatCompiler] = None,
        searcher: Optional[DeepMovieSearcher] = None,
        evaluator: Optional[CandidateEvidenceEvaluator] = None,
        arbitrator: Optional[CandidateArbitrator] = None,
    ):
        self.beat_compiler = beat_compiler or VisualBeatCompiler()
        self.searcher = searcher or DeepMovieSearcher()
        self.evaluator = evaluator or CandidateEvidenceEvaluator()
        self.arbitrator = arbitrator or CandidateArbitrator()

    def generate_edl(
        self,
        narration_input: LockedNarrationInput,
        target_movie_id: Optional[int] = None,
        candidate_timelines_by_beat: Optional[Dict[str, Any]] = None,
    ) -> VisualEDL:
        """
        Executes end-to-end EDL compilation, deep search, perception/physical
        evidence evaluation, global arbitration, and lineage binding.
        """
        t0 = time.time()
        c_id = narration_input.content_id

        # 1. Compile Locked Narration into Visual Beats (Part 2 & 3)
        beats = self.beat_compiler.compile_beats(narration_input)
        beat_hash = hashlib.sha256("".join(b.compute_beat_hash() for b in beats).encode()).hexdigest()

        # 2. Deep Movie Search & Candidate Pooling (Part 4, 6, 23, 24)
        evaluated_candidates_by_beat: Dict[str, List[EvaluatedCandidate]] = {}
        all_diagnostics: List[SearchDiagnosticRecord] = []
        cand_hasher = hashlib.sha256()

        for beat in beats:
            raw_cands, diag = self.searcher.search_beat_candidates(
                beat=beat, target_movie_id=target_movie_id
            )
            all_diagnostics.append(diag)

            # 3. Evaluate Candidates through Phase 2 & Phase 3 (Part 8, 9, 10, 11, 12, 13, 18)
            beat_eval_cands: List[EvaluatedCandidate] = []
            timelines = (candidate_timelines_by_beat or {}).get(beat.beat_id, {})

            for rc in raw_cands:
                tl = timelines.get(rc.candidate_id) if isinstance(timelines, dict) else timelines
                evaluated = self.evaluator.evaluate_candidate(
                    candidate=rc,
                    beat=beat,
                    timeline=tl,
                )
                beat_eval_cands.append(evaluated)
                cand_hasher.update(evaluated.evidence_hash.encode())

            evaluated_candidates_by_beat[beat.beat_id] = beat_eval_cands

        candidate_hash = cand_hasher.hexdigest()

        # 4. Global Multi-Beat Candidate Arbitration & Anti-Loop (Part 7, 14, 17, 19)
        entries, anti_loop = self.arbitrator.arbitrate_timeline(
            beats=beats,
            evaluated_candidates_by_beat=evaluated_candidates_by_beat,
        )

        # 5. Narration Coverage Accounting (Part 16)
        total_duration = narration_input.exact_narration_duration
        direct_cov = sum(e.narration_duration for e in entries if e.coverage_state == CoverageState.VERIFIED_DIRECT)
        optional_cov = sum(e.narration_duration for e in entries if e.coverage_state in (CoverageState.VERIFIED_CONTEXT, CoverageState.VISUAL_OPTIONAL))
        unfulfilled_cov = sum(e.narration_duration for e in entries if e.coverage_state == CoverageState.UNFULFILLED)
        cov_pct = round((direct_cov + optional_cov) / total_duration, 4) if total_duration > 0 else 0.0

        # Check for unfulfilled DIRECT beats (Fail-Closed)
        is_complete = True
        failure_reason = None
        unfulfilled_beats = [e.beat_id for e in entries if e.coverage_state == CoverageState.UNFULFILLED]
        if unfulfilled_beats:
            is_complete = False
            failure_reason = f"INSUFFICIENT_VISUAL_COVERAGE: Direct beats unfulfilled: {unfulfilled_beats}"
        elif not anti_loop.passed:
            is_complete = False
            failure_reason = f"ANTI_LOOP_VIOLATION: {anti_loop.explanation}"

        # 6. Cryptographic Lineage Binding (Part 25)
        perception_hash = hashlib.sha256(str(len(entries)).encode()).hexdigest()
        evidence_hash = hashlib.sha256("".join(e.evidence_hash for e in entries).encode()).hexdigest()
        crop_feasibility_hash = hashlib.sha256("".join(e.crop_feasibility.value for e in entries).encode()).hexdigest()
        arbitration_hash = hashlib.sha256(str(anti_loop.passed).encode()).hexdigest()

        master_h = hashlib.sha256()
        master_h.update(c_id.encode())
        master_h.update(narration_input.script_hash.encode())
        master_h.update(narration_input.narration_hash.encode())
        master_h.update(beat_hash.encode())
        master_h.update(candidate_hash.encode())
        master_h.update(evidence_hash.encode())
        master_h.update(crop_feasibility_hash.encode())
        master_h.update(arbitration_hash.encode())
        master_edl_hash = master_h.hexdigest()

        lineage = EDLLineage(
            content_id=c_id,
            script_hash=narration_input.script_hash,
            narration_hash=narration_input.narration_hash,
            beat_hash=beat_hash,
            candidate_hash=candidate_hash,
            perception_hash=perception_hash,
            evidence_hash=evidence_hash,
            crop_feasibility_hash=crop_feasibility_hash,
            arbitration_hash=arbitration_hash,
            edl_hash=master_edl_hash,
        )

        edl_id = f"edl_{c_id[:12]}_{master_edl_hash[:8]}"

        edl = VisualEDL(
            edl_id=edl_id,
            content_id=c_id,
            total_narration_duration=round(total_duration, 2),
            directly_covered_duration=round(direct_cov, 2),
            optional_duration=round(optional_cov, 2),
            unfulfilled_duration=round(unfulfilled_cov, 2),
            coverage_percentage=cov_pct,
            entries=entries,
            anti_loop_audit=anti_loop,
            diagnostics=all_diagnostics,
            lineage=lineage,
            is_complete=is_complete,
            failure_reason=failure_reason,
        )

        logger.info(f"Generated VisualEDL {edl_id}: Coverage {cov_pct * 100:.1f}%, Complete={is_complete}")
        return edl

    @staticmethod
    def generate_edl_preview_report(edl: VisualEDL, beats_map: Optional[Dict[str, VisualBeat]] = None) -> str:
        """
        Produces a detailed markdown preview report of the complete Visual EDL (Part 20).
        Does NOT trigger video rendering.
        """
        lines = [
            f"# STORY FORGE — Visual EDL Preview Report",
            f"**EDL ID**: `{edl.edl_id}`  ",
            f"**Content ID**: `{edl.content_id}`  ",
            f"**Total Narration Duration**: `{edl.total_narration_duration:.2f}s`  ",
            f"**Coverage Percentage**: `{edl.coverage_percentage * 100:.1f}%` ({edl.directly_covered_duration:.2f}s Direct, {edl.optional_duration:.2f}s Optional, {edl.unfulfilled_duration:.2f}s Unfulfilled)  ",
            f"**Status**: `{'COMPLETE & VERIFIED' if edl.is_complete else 'INCOMPLETE'}`  ",
            f"**Lineage Master Hash**: `{edl.lineage.edl_hash}`  ",
            "",
            "---",
            "",
            "## Timeline Beat Breakdown",
            "",
        ]

        for idx, entry in enumerate(edl.entries, 1):
            beat_info = beats_map.get(entry.beat_id) if beats_map else None
            txt = beat_info.text_span if beat_info else entry.beat_id
            lines.extend([
                f"### Beat {idx:02d} (`{entry.beat_id}`) — [{entry.narration_start:.2f}s → {entry.narration_end:.2f}s]",
                f"- **Narration Text**: *\"{txt}\"*",
                f"- **Coverage State**: `{entry.coverage_state.value}`",
                f"- **Selected Footage**: `HP{entry.source_movie_id}` [{entry.source_clip_start:.2f}s → {entry.source_clip_end:.2f}s] (Clip Duration: {entry.clip_duration:.2f}s)",
                f"- **Evidence Verified**: `{entry.evidence_class}` — Action: `{entry.verified_action or 'NONE'}` | Entities: `{', '.join(entry.verified_entities) or 'NONE'}`",
                f"- **9:16 Crop Feasibility**: `{entry.crop_feasibility.value}`",
                f"- **Candidate Rank / Confidence**: Rank {entry.candidate_rank} ({entry.confidence * 100:.1f}%)",
                f"- **Reuse Status**: `{entry.reuse_group or 'NONE (Unique Footage)'}`",
                f"- **Evidence Hash**: `{entry.evidence_hash[:16]}...`",
                "",
            ])

        lines.extend([
            "---",
            "",
            "## Anti-Loop Audit",
            f"- **Anti-Loop Status**: `{'PASSED' if edl.anti_loop_audit.passed else 'FAILED'}`",
            f"- **Unique Intervals**: `{edl.anti_loop_audit.unique_footage_intervals}` / `{edl.anti_loop_audit.total_entries}`",
            f"- **Repeated Source Count**: `{edl.anti_loop_audit.repeated_source_count}`",
            f"- **Stream Loops Detected**: `{edl.anti_loop_audit.stream_loops_detected}`",
            "",
            "## Lineage Fingerprints",
            f"- `script_hash`: `{edl.lineage.script_hash[:16]}...`",
            f"- `narration_hash`: `{edl.lineage.narration_hash[:16]}...`",
            f"- `beat_hash`: `{edl.lineage.beat_hash[:16]}...`",
            f"- `candidate_hash`: `{edl.lineage.candidate_hash[:16]}...`",
            f"- `evidence_hash`: `{edl.lineage.evidence_hash[:16]}...`",
            f"- `crop_feasibility_hash`: `{edl.lineage.crop_feasibility_hash[:16]}...`",
            f"- `master_edl_hash`: `{edl.lineage.edl_hash}`",
        ])

        return "\n".join(lines)
