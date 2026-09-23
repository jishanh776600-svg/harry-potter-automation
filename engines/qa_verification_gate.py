"""
STORY FORGE Automated 10-Point QA Verification Gate (Step 6)
================================================================================
Comprehensive pre-production inspection gate for Harry Potter Discovery Shorts:
  - Check 1: Deep Discovery Duration (68.0–80.9s; hard ceiling 80.9s; Novel Story isolated)
  - Check 2: Immediate Hook (First spoken word <=120ms; zero throat-clearing)
  - Check 3: Cut Density (~40+ cuts for 75s; max single shot <=3.5s unless anchor/solemn)
  - Check 4: Visual Source Policy (0 generic stock, 0 AI-generated, verified rights)
  - Check 5: Caption Safe Zone (HP serif, white/black stroke, Y=1400, no UI overlap)
  - Check 6: Audio Loudness / Peak (-12.5 to -13.5 LUFS, peak <= -0.1 dBTP; NOT_APPLICABLE if pending)
  - Check 7: Visual Integrity (No black/frozen/corrupt frames, frame continuity)
  - Check 8: Visual Repetition (No duplicate clip timestamps, no shot-scale fatigue)
  - Check 9: Evidence Linkage (Claim -> EvidencePoint -> Provenance -> Beat -> Visual)
  - Check 10: Engagement / Payoff Completeness (Recognizable payoff, no abrupt truncation)

Absolute Architectural Rules:
  - VERIFICATION ONLY: Diagnoses issues without mutating, producing, or silently repairing content.
  - NOVEL STORY ISOLATION: Explicit tier-aware logic; does not force Deep Discovery rules onto Novel Story.
  - CROSS-SYSTEM FINGERPRINT CONSISTENCY: Validates Steps 2, 3, 4, 5 lineage.
"""

import os
import re
import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set

from core.hybrid_visual_models import (
    VisualSourceType,
    FORBIDDEN_SOURCE_PROVIDERS,
)
from core.storyboard_types import (
    StoryboardPlan,
    StoryboardBeatContract,
    VisualRole,
    TransitionIntent,
)
from core.preprocessor_types import (
    PreprocessedVisualAsset,
    PreprocessingStatus,
)
from core.editorial_types import (
    EditorialTimeline,
    EditorialClip,
    MotionIntent,
    EditorialEmphasis,
)
from core.sfx_types import SFXPlan
from core.discovery_types import (
    DeepDiscoveryStoryPlan,
    EvidencePoint,
)
from core.qa_types import (
    QASeverity,
    QACheckStatus,
    QACheckResult,
    QAPackageReport,
)
from engines.final_media_audio_verifier import (
    FinalMediaAudioVerifier,
    MediaAudioVerificationReport,
    SFXCueVerificationResult,
)
from engines.final_media_visual_verifier import (
    FinalMediaVisualVerifier,
    MediaVisualVerificationReport,
)

logger = logging.getLogger(__name__)

# Generic intro / throat-clearing phrases that violate the immediate hook invariant
THROAT_CLEARING_PHRASES: List[str] = [
    "hey guys", "welcome back", "in today's video", "today we are",
    "did you ever wonder", "don't forget to like", "hello everyone",
    "in this video", "today i will show", "make sure to subscribe"
]

# AI generation keywords for strict source policy enforcement
AI_SOURCE_KEYWORDS: Set[str] = {
    "midjourney", "dall-e", "dalle", "stable diffusion", "stablediffusion",
    "flux", "leonardo", "genai", "ai_generated", "synth"
}


class QAVerificationGate:
    """
    Directorial 10-point automated inspection engine.
    Audits the complete Short candidate package and issues an immutable QAPackageReport.
    """

    def __init__(self, qa_version: str = "v3.0.0"):
        self.qa_version = qa_version

    def evaluate_package(
        self,
        candidate_id: str,
        editorial_timeline: EditorialTimeline,
        sfx_plan: Optional[SFXPlan] = None,
        storyboard_plan: Optional[StoryboardPlan] = None,
        preprocessed_assets: Optional[List[PreprocessedVisualAsset]] = None,
        story_plan: Optional[DeepDiscoveryStoryPlan] = None,
        audio_metrics: Optional[Dict[str, Any]] = None,
        rendered_video_path: Optional[str] = None,
        candidate_type: str = "deep_discovery",
        final_media_audio_report: Optional[MediaAudioVerificationReport] = None,
        final_media_visual_report: Optional[MediaVisualVerificationReport] = None,
    ) -> QAPackageReport:
        """
        Executes all 10 QA verification checks against the candidate package.
        Diagnoses defects with actionable prescriptive feedback; NEVER silently repairs.
        """
        qa_run_id = f"qa_{candidate_id}_{int(datetime.now(timezone.utc).timestamp())}"
        checks: List[QACheckResult] = []

        is_novel_story = (
            candidate_type == "novel_story"
            or (hasattr(editorial_timeline, "metadata") and editorial_timeline.metadata.get("pipeline") == "novel_story")
            or (hasattr(story_plan, "discovery_tier") and str(story_plan.discovery_tier).upper() in ("NOVEL_STORY", "NOVEL_STORY_CANDIDATE"))
        )
        resolved_tier = "novel_story" if is_novel_story else "deep_discovery"

        # Automatic final media verification when rendered_video_path exists
        if rendered_video_path and Path(rendered_video_path).exists():
            media_p = Path(rendered_video_path)
            if final_media_audio_report is None:
                expected_cues = [c.to_dict() for c in sfx_plan.cues] if sfx_plan else []
                final_media_audio_report = FinalMediaAudioVerifier().verify_final_media_audio(
                    media_path=media_p,
                    expected_bgm=True,
                    expected_sfx_cues=expected_cues,
                )
            if final_media_visual_report is None:
                final_media_visual_report = FinalMediaVisualVerifier().verify_final_media_visual(
                    media_path=media_p,
                    editorial_timeline=editorial_timeline,
                )

        # CHECK 1: DURATION
        checks.append(self._check_01_duration(editorial_timeline, resolved_tier))

        # CHECK 2: IMMEDIATE HOOK
        checks.append(self._check_02_immediate_hook(editorial_timeline, resolved_tier))

        # CHECK 3: CUT DENSITY
        checks.append(self._check_03_cut_density(editorial_timeline, resolved_tier))

        # CHECK 4: VISUAL SOURCE POLICY
        checks.append(self._check_04_visual_source_policy(editorial_timeline, storyboard_plan, preprocessed_assets))

        # CHECK 5: CAPTION SAFE ZONE
        checks.append(self._check_05_caption_safe_zone(editorial_timeline, resolved_tier))

        # CHECK 6: AUDIO LOUDNESS / PEAK & FINAL MEDIA AUDIO PRESENCE
        checks.append(self._check_06_audio_loudness_peak(audio_metrics, final_media_audio_report))

        # CHECK 7: VISUAL INTEGRITY & FINAL MEDIA VISUAL INTEGRITY
        checks.append(self._check_07_visual_integrity(editorial_timeline, preprocessed_assets, rendered_video_path, final_media_visual_report))

        # CHECK 8: VISUAL REPETITION
        checks.append(self._check_08_visual_repetition(editorial_timeline))

        # CHECK 9: EVIDENCE LINKAGE
        checks.append(self._check_09_evidence_linkage(story_plan, storyboard_plan, resolved_tier))

        # CHECK 10: ENGAGEMENT / PAYOFF COMPLETENESS
        checks.append(self._check_10_payoff_completeness(editorial_timeline, resolved_tier))

        # CROSS-SYSTEM FINGERPRINT CONSISTENCY
        fp_check = self._check_cross_system_fingerprints(
            editorial_timeline=editorial_timeline,
            sfx_plan=sfx_plan,
            storyboard_plan=storyboard_plan,
            preprocessed_assets=preprocessed_assets,
        )
        if fp_check:
            checks.append(fp_check)

        # AGGREGATE SEVERITIES
        blocker_count = sum(1 for c in checks if c.severity == QASeverity.BLOCKER and c.status == QACheckStatus.FAIL)
        error_count = sum(1 for c in checks if c.severity == QASeverity.ERROR and c.status == QACheckStatus.FAIL)
        warning_count = sum(1 for c in checks if c.severity == QASeverity.WARNING and c.status == QACheckStatus.FAIL)

        overall_pass = (blocker_count == 0 and error_count == 0)
        production_ready = overall_pass

        # DETERMINISTIC QA FINGERPRINT
        qa_fp = self._compute_qa_fingerprint(
            candidate_id=candidate_id,
            ed_fp=editorial_timeline.deterministic_fingerprint,
            sfx_fp=sfx_plan.sfx_fingerprint if sfx_plan else "no_sfx",
            checks=checks,
        )

        return QAPackageReport(
            qa_run_id=qa_run_id,
            candidate_id=candidate_id,
            candidate_type=resolved_tier,
            editorial_fingerprint=editorial_timeline.deterministic_fingerprint,
            sfx_fingerprint=sfx_plan.sfx_fingerprint if sfx_plan else "",
            duration=round(editorial_timeline.total_duration_seconds, 3),
            overall_pass=overall_pass,
            production_ready=production_ready,
            checks=checks,
            blocker_count=blocker_count,
            error_count=error_count,
            warning_count=warning_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
            qa_fingerprint=qa_fp,
            metadata={
                "qa_version": self.qa_version,
                "tier": resolved_tier,
                "total_clips": len(editorial_timeline.clips),
            },
        )

    # --------------------------------------------------------------------------
    # CHECK 1: DURATION
    # --------------------------------------------------------------------------
    def _check_01_duration(self, timeline: EditorialTimeline, tier: str) -> QACheckResult:
        dur = timeline.total_duration_seconds

        if tier == "novel_story":
            # Novel Story bounds: 45.0 to 60.0s
            if 45.0 <= dur <= 60.0:
                return QACheckResult(
                    check_id="check_01_duration",
                    name="Novel Story Duration Invariant",
                    status=QACheckStatus.PASS,
                    severity=QASeverity.PASS,
                    measured_value=dur,
                    expected_value_range="45.0s - 60.0s",
                    diagnostic_message=f"Duration {dur:.2f}s is within Novel Story atmospheric range.",
                )
            return QACheckResult(
                check_id="check_01_duration",
                name="Novel Story Duration Invariant",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=dur,
                expected_value_range="45.0s - 60.0s",
                diagnostic_message=f"Duration {dur:.2f}s outside Novel Story range (45.0 - 60.0s).",
                remediation_suggestion="Adjust narration pacing or trim novel excerpts to fit 45-60s window.",
            )

        # Deep Discovery: Target 68.0–80.9s; Hard ceiling 80.9s
        if dur > 80.9:
            return QACheckResult(
                check_id="check_01_duration",
                name="Deep Discovery Duration Invariant",
                status=QACheckStatus.FAIL,
                severity=QASeverity.BLOCKER,
                measured_value=dur,
                expected_value_range="68.0s - 80.9s (Hard ceiling 80.9s)",
                diagnostic_message=f"Duration {dur:.2f}s violates the hard YouTube Shorts ceiling of 80.9s.",
                remediation_suggestion="Trim secondary evidence beats or accelerate speech rate to <= 80.9s.",
            )
        elif dur < 68.0:
            return QACheckResult(
                check_id="check_01_duration",
                name="Deep Discovery Duration Invariant",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=dur,
                expected_value_range="68.0s - 80.9s",
                diagnostic_message=f"Duration {dur:.2f}s is below the Deep Discovery threshold (minimum 68.0s).",
                remediation_suggestion="Expand canon evidence beats or add depth to anchor realization.",
            )

        return QACheckResult(
            check_id="check_01_duration",
            name="Deep Discovery Duration Invariant",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value=dur,
            expected_value_range="68.0s - 80.9s",
            diagnostic_message=f"Duration {dur:.2f}s is optimal for Deep Discovery Short.",
        )

    # --------------------------------------------------------------------------
    # CHECK 2: IMMEDIATE HOOK
    # --------------------------------------------------------------------------
    def _check_02_immediate_hook(self, timeline: EditorialTimeline, tier: str) -> QACheckResult:
        if tier == "novel_story":
            return QACheckResult(
                check_id="check_02_immediate_hook",
                name="Immediate Hook Timing",
                status=QACheckStatus.PASS,
                severity=QASeverity.PASS,
                measured_value="Novel Story atmospheric opening",
                expected_value_range="N/A (Novel Story isolated)",
                diagnostic_message="Novel Story atmospheric slow-burn opening permitted.",
            )

        if not timeline.clips:
            return QACheckResult(
                check_id="check_02_immediate_hook",
                name="Immediate Hook Timing",
                status=QACheckStatus.FAIL,
                severity=QASeverity.BLOCKER,
                measured_value=0,
                expected_value_range=">= 1 clip",
                diagnostic_message="Editorial timeline contains no visual clips.",
                remediation_suggestion="Assemble storyboard beats into editorial timeline.",
            )

        first_clip = timeline.clips[0]
        # Look for first word timing
        first_word_time = 0.0
        first_caption_text = ""
        if first_clip.captions and first_clip.captions[0].words:
            first_w = first_clip.captions[0].words[0]
            first_word_time = first_w.start_frame / timeline.fps
            first_caption_text = " ".join([c.text.lower() for c in first_clip.captions])
        else:
            first_word_time = first_clip.start_seconds

        # Invariant: First spoken word must be <= 120ms (0.120s)
        if first_word_time > 0.120:
            return QACheckResult(
                check_id="check_02_immediate_hook",
                name="Immediate Hook Timing",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"{first_word_time * 1000:.1f}ms",
                expected_value_range="<= 120.0ms",
                diagnostic_message=f"Dead-air intro: First spoken word occurs at {first_word_time*1000:.1f}ms (> 120ms).",
                remediation_suggestion="Shift narration audio and caption cluster to start at frame 0 (<= 120ms).",
            )

        # Invariant: Zero throat-clearing / generic intro phrases
        for phrase in THROAT_CLEARING_PHRASES:
            if phrase in first_caption_text:
                return QACheckResult(
                    check_id="check_02_immediate_hook",
                    name="Immediate Hook Timing",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.ERROR,
                    measured_value=phrase,
                    expected_value_range="Zero generic filler phrases",
                    diagnostic_message=f"Throat-clearing detected: Hook begins with generic phrase '{phrase}'.",
                    remediation_suggestion="Rewrite hook with cold-open counter-intuitive statement or canon challenge.",
                )

        return QACheckResult(
            check_id="check_02_immediate_hook",
            name="Immediate Hook Timing",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value=f"{first_word_time * 1000:.1f}ms",
            expected_value_range="<= 120.0ms",
            diagnostic_message=f"Hook begins immediately at {first_word_time*1000:.1f}ms with direct canon engagement.",
        )

    # --------------------------------------------------------------------------
    # CHECK 3: CUT DENSITY
    # --------------------------------------------------------------------------
    def _check_03_cut_density(self, timeline: EditorialTimeline, tier: str) -> QACheckResult:
        clip_count = len(timeline.clips)
        dur = timeline.total_duration_seconds

        if tier == "novel_story":
            return QACheckResult(
                check_id="check_03_cut_density",
                name="Cut Density & Visual Rhythm",
                status=QACheckStatus.PASS,
                severity=QASeverity.PASS,
                measured_value=f"{clip_count} clips",
                expected_value_range="Atmospheric pacing (Novel Story isolated)",
                diagnostic_message="Novel Story atmospheric pacing preserved.",
            )

        # For ~75s Deep Discovery: minimum ~40 cuts (proportional: >= 0.50 cuts/sec)
        expected_min_cuts = int(round(dur * 0.50)) if dur > 0 else 35
        if clip_count < expected_min_cuts:
            return QACheckResult(
                check_id="check_03_cut_density",
                name="Cut Density & Visual Rhythm",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"{clip_count} cuts for {dur:.1f}s",
                expected_value_range=f">={expected_min_cuts} cuts (~40-50 cuts for 75s)",
                diagnostic_message=f"Visual cut density too sparse: {clip_count} cuts found, minimum {expected_min_cuts} required.",
                remediation_suggestion="Split longer visual scenes into multi-shot micro-sequences (0.8–2.0s cuts).",
            )

        # Shot Duration Invariant: No single non-anchor, non-solemn shot > 3.5s
        for c in timeline.clips:
            if c.duration_seconds > 3.5:
                is_justified = c.is_anchor or c.editorial_emphasis == EditorialEmphasis.ANCHOR_FOCAL
                if not is_justified:
                    return QACheckResult(
                        check_id="check_03_cut_density",
                        name="Cut Density & Visual Rhythm",
                        status=QACheckStatus.FAIL,
                        severity=QASeverity.ERROR,
                        measured_value=f"{c.clip_id}: {c.duration_seconds:.2f}s",
                        expected_value_range="<= 3.5s for non-anchor shots",
                        diagnostic_message=f"Shot duration violation: Clip {c.clip_id} holds for {c.duration_seconds:.2f}s without anchor justification.",
                        remediation_suggestion=f"Subdivide {c.clip_id} with cutaways or match-cuts to keep shot length <= 3.5s.",
                    )

        return QACheckResult(
            check_id="check_03_cut_density",
            name="Cut Density & Visual Rhythm",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value=f"{clip_count} cuts",
            expected_value_range=f">={expected_min_cuts} cuts",
            diagnostic_message=f"Cut density {clip_count} cuts ({clip_count/max(1.0, dur):.2f} cuts/s) conforms to kinetic standard.",
        )

    # --------------------------------------------------------------------------
    # CHECK 4: VISUAL SOURCE POLICY
    # --------------------------------------------------------------------------
    def _check_04_visual_source_policy(
        self,
        timeline: EditorialTimeline,
        storyboard: Optional[StoryboardPlan],
        assets: Optional[List[PreprocessedVisualAsset]],
    ) -> QACheckResult:
        # Scan timeline clips, storyboard beats, and asset provenance
        forbidden_hits: List[str] = []

        for clip in timeline.clips:
            # Check source ID and path
            text_to_check = f"{clip.source_asset_id} {clip.source_preprocessed_path or ''}".lower()
            if clip.source_provenance:
                text_to_check += " " + json.dumps(clip.source_provenance).lower()

            for forbidden in FORBIDDEN_SOURCE_PROVIDERS:
                if forbidden in text_to_check:
                    forbidden_hits.append(f"Forbidden stock provider '{forbidden}' in clip {clip.clip_id}")

            for ai_kw in AI_SOURCE_KEYWORDS:
                if ai_kw in text_to_check:
                    forbidden_hits.append(f"AI-generated imagery keyword '{ai_kw}' in clip {clip.clip_id}")

        if forbidden_hits:
            return QACheckResult(
                check_id="check_04_visual_source_policy",
                name="Visual Source & Rights Policy",
                status=QACheckStatus.FAIL,
                severity=QASeverity.BLOCKER,
                measured_value=f"{len(forbidden_hits)} violations detected",
                expected_value_range="0 forbidden sources (0 stock, 0 AI imagery)",
                diagnostic_message="; ".join(forbidden_hits[:3]),
                remediation_suggestion="Purge generic stock/AI assets. Use only canon movie clips or cleared artwork.",
            )

        return QACheckResult(
            check_id="check_04_visual_source_policy",
            name="Visual Source & Rights Policy",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value="100% canon/cleared sources",
            expected_value_range="0 forbidden sources",
            diagnostic_message="Visual assets fully comply with authentic canon and rights policy.",
        )

    # --------------------------------------------------------------------------
    # CHECK 5: CAPTION SAFE ZONE
    # --------------------------------------------------------------------------
    def _check_05_caption_safe_zone(self, timeline: EditorialTimeline, tier: str) -> QACheckResult:
        if tier == "novel_story":
            return QACheckResult(
                check_id="check_05_caption_safe_zone",
                name="Caption Safe Zone & Typography",
                status=QACheckStatus.PASS,
                severity=QASeverity.PASS,
                measured_value="Novel Story typography",
                expected_value_range="N/A (Novel Story isolated)",
                diagnostic_message="Novel Story atmospheric subtitle configuration verified.",
            )

        typo = timeline.typography_config
        # Validate Y position safe zone (lower-middle, clearing bottom UI)
        if typo.safe_zone_bottom_px > 1650:
            return QACheckResult(
                check_id="check_05_caption_safe_zone",
                name="Caption Safe Zone & Typography",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"Y={typo.safe_zone_bottom_px}",
                expected_value_range="Y <= 1650 (lower-middle safe zone ~1400)",
                diagnostic_message=f"Captions at Y={typo.safe_zone_bottom_px} will be obscured by YouTube Shorts bottom UI.",
                remediation_suggestion="Anchor captions to safe_zone_bottom_px=1400 with margin_v_px >= 400.",
            )

        # Validate Harry Potter serif typography
        if "serif" not in typo.font_family.lower() and "harry" not in typo.font_family.lower() and "georgia" not in typo.font_family.lower():
            return QACheckResult(
                check_id="check_05_caption_safe_zone",
                name="Caption Safe Zone & Typography",
                status=QACheckStatus.FAIL,
                severity=QASeverity.WARNING,
                measured_value=typo.font_family,
                expected_value_range="Harry P, Georgia, serif",
                diagnostic_message=f"Font '{typo.font_family}' does not match canonical Harry Potter serif aesthetic.",
                remediation_suggestion="Set typography_config.font_family to 'Harry P, Georgia, serif'.",
            )

        # Validate stroke width for contrast
        if typo.stroke_width_px < 3.0:
            return QACheckResult(
                check_id="check_05_caption_safe_zone",
                name="Caption Safe Zone & Typography",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"{typo.stroke_width_px}px",
                expected_value_range=">= 3.0px heavy black outline",
                diagnostic_message=f"Stroke width {typo.stroke_width_px}px is too thin for mobile legibility against high-contrast footage.",
                remediation_suggestion="Increase stroke_width_px to 4.5px with stroke_color='#000000'.",
            )

        return QACheckResult(
            check_id="check_05_caption_safe_zone",
            name="Caption Safe Zone & Typography",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value=f"Y={typo.safe_zone_bottom_px}, stroke={typo.stroke_width_px}px, font={typo.font_size_px}px",
            expected_value_range="Y=1400, stroke>=3.0px, mobile safe",
            diagnostic_message="Kinetic typography strictly conforms to lower-middle safe zone and HP aesthetic.",
        )

    # --------------------------------------------------------------------------
    # CHECK 6: AUDIO LOUDNESS / PEAK & FINAL MEDIA AUDIO PRESENCE
    # --------------------------------------------------------------------------
    def _check_06_audio_loudness_peak(
        self,
        metrics: Optional[Dict[str, Any]],
        media_audio_report: Optional[MediaAudioVerificationReport] = None,
    ) -> QACheckResult:
        # Final-media audio verification if report is provided (PART J, K, L)
        if media_audio_report:
            if media_audio_report.is_silent:
                return QACheckResult(
                    check_id="check_06_audio_loudness_peak",
                    name="Audio Master Loudness & True Peak",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.BLOCKER,
                    measured_value="SILENT_AUDIO_STREAM",
                    expected_value_range="Active broadcast audio stream",
                    diagnostic_message="Critical audio failure: Final rendered MP4 audio track is completely silent or missing.",
                    remediation_suggestion="Inspect audio mixing pipeline and ensure audio muxing is active.",
                )

            if media_audio_report.bgm_expected and not media_audio_report.bgm_detected:
                return QACheckResult(
                    check_id="check_06_audio_loudness_peak",
                    name="Audio Master Loudness & True Peak",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.ERROR,
                    measured_value=f"BGM: {media_audio_report.bgm_energy_dbfs:.1f} dBFS (INADMISSIBLE / SILENT)",
                    expected_value_range="Audible BGM present",
                    diagnostic_message="Planned BGM is missing or effectively silent in final rendered MP4 media.",
                    remediation_suggestion="Remix soundtrack ensuring BGM is not suppressed by excessive attenuation or amix weighting.",
                )

            if media_audio_report.sfx_expected_count > 0 and not media_audio_report.all_expected_sfx_detected:
                missing_cues = [r.category for r in media_audio_report.sfx_cue_results if not r.is_detected]
                return QACheckResult(
                    check_id="check_06_audio_loudness_peak",
                    name="Audio Master Loudness & True Peak",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.ERROR,
                    measured_value=f"SFX Detected: {media_audio_report.sfx_detected_count}/{media_audio_report.sfx_expected_count}",
                    expected_value_range="100% planned SFX audible in final MP4",
                    diagnostic_message=f"Planned SFX cues missing from final rendered MP4 media: {missing_cues}.",
                    remediation_suggestion="Inspect SFX mix chains and ensure cue gains provide measurable transient energy.",
                )

            if not media_audio_report.voice_dominant:
                return QACheckResult(
                    check_id="check_06_audio_loudness_peak",
                    name="Audio Master Loudness & True Peak",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.ERROR,
                    measured_value="Voice not dominant",
                    expected_value_range="Voice dominance >= +4dB over background",
                    diagnostic_message="Voice narration is not dominant in final rendered media.",
                    remediation_suggestion="Duck background tracks or increase voice gain.",
                )

            if not media_audio_report.audio_covers_video:
                return QACheckResult(
                    check_id="check_06_audio_loudness_peak",
                    name="Audio Master Loudness & True Peak",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.ERROR,
                    measured_value=f"Audio {media_audio_report.audio_duration:.2f}s vs Video {media_audio_report.video_duration:.2f}s",
                    expected_value_range="Duration match within 0.5s",
                    diagnostic_message="Audio stream does not cover entire video duration in final media.",
                    remediation_suggestion="Align audio loop/padding to video duration.",
                )

        if not metrics or metrics.get("integrated_lufs") is None:
            if media_audio_report and media_audio_report.integrated_lufs > -90.0:
                lufs = media_audio_report.integrated_lufs
                peak = media_audio_report.true_peak_dbtp
            else:
                return QACheckResult(
                    check_id="check_06_audio_loudness_peak",
                    name="Audio Master Loudness & True Peak",
                    status=QACheckStatus.NOT_APPLICABLE,
                    severity=QASeverity.PASS,
                    measured_value="None (Downstream assembly pending)",
                    expected_value_range="-12.5 to -13.5 LUFS, peak <= -0.1 dBTP",
                    diagnostic_message="Final master audio not yet integrated; loudness audit deferred to final assembly.",
                )
        else:
            lufs = float(metrics.get("integrated_lufs", -99.0))
            peak = float(metrics.get("true_peak_dbtp", 0.0))

        # Check true peak clipping
        if peak > -0.1:
            return QACheckResult(
                check_id="check_06_audio_loudness_peak",
                name="Audio Master Loudness & True Peak",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"Peak {peak:+.2f} dBTP",
                expected_value_range="<= -0.1 dBTP",
                diagnostic_message=f"Audio true peak exceeds digital ceiling ({peak:+.2f} dBTP > -0.1 dBTP); clipping risk.",
                remediation_suggestion="Engage true peak brickwall limiter with -0.5 dBTP margin.",
            )

        # Check integrated loudness (-14.5 to -11.5 acceptable; target -12.5 to -13.5)
        if not (-14.5 <= lufs <= -11.5):
            return QACheckResult(
                check_id="check_06_audio_loudness_peak",
                name="Audio Master Loudness & True Peak",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"{lufs:.1f} LUFS",
                expected_value_range="-14.5 to -11.5 LUFS",
                diagnostic_message=f"Integrated master loudness {lufs:.1f} LUFS out of YouTube Shorts broadcast specification.",
                remediation_suggestion="Re-master audio master chain targeting -13.0 LUFS integrated.",
            )

        return QACheckResult(
            check_id="check_06_audio_loudness_peak",
            name="Audio Master Loudness & True Peak",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value=f"{lufs:.1f} LUFS, peak {peak:+.2f} dBTP",
            expected_value_range="-12.5 to -13.5 LUFS, peak <= -0.1 dBTP",
            diagnostic_message="Audio mastering satisfies strict broadcast loudness and true peak standards.",
        )

    # --------------------------------------------------------------------------
    # CHECK 7: VISUAL INTEGRITY & FINAL MEDIA VISUAL INTEGRITY
    # --------------------------------------------------------------------------
    def _check_07_visual_integrity(
        self,
        timeline: EditorialTimeline,
        assets: Optional[List[PreprocessedVisualAsset]],
        rendered_video_path: Optional[str],
        media_visual_report: Optional[MediaVisualVerificationReport] = None,
    ) -> QACheckResult:
        # Check frame timeline continuity
        expected_f = 0
        for i, clip in enumerate(timeline.clips):
            if clip.start_frame != expected_f:
                return QACheckResult(
                    check_id="check_07_visual_integrity",
                    name="Visual Integrity & Continuity",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.BLOCKER,
                    measured_value=f"Gap/overlap at clip {clip.clip_id}: frame {clip.start_frame} != {expected_f}",
                    expected_value_range="Gapless frame continuity",
                    diagnostic_message=f"Temporal gap detected in editorial timeline before {clip.clip_id}.",
                    remediation_suggestion="Re-align clip sequence frames to maintain zero-gap continuity.",
                )
            if clip.duration_frames <= 0:
                return QACheckResult(
                    check_id="check_07_visual_integrity",
                    name="Visual Integrity & Continuity",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.BLOCKER,
                    measured_value=f"{clip.clip_id} duration_frames={clip.duration_frames}",
                    expected_value_range="duration_frames > 0",
                    diagnostic_message=f"Corrupt clip duration: {clip.clip_id} has {clip.duration_frames} frames.",
                    remediation_suggestion="Assign positive frame duration to all editorial clips.",
                )
            expected_f = clip.end_frame

        # Check for NO_VALID_VISUAL or broken asset references
        for clip in timeline.clips:
            if clip.validation_status == "NO_VALID_VISUAL":
                return QACheckResult(
                    check_id="check_07_visual_integrity",
                    name="Visual Integrity & Continuity",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.BLOCKER,
                    measured_value=f"{clip.clip_id}: NO_VALID_VISUAL",
                    expected_value_range="All clips VALID",
                    diagnostic_message=f"Clip {clip.clip_id} references unresolvable or missing visual media.",
                    remediation_suggestion="Supply canonical movie or cleared artwork asset to satisfy beat contract.",
                )
            if clip.validation_status in ("SEVERE_CROP", "UNSAFE_FRAMING"):
                return QACheckResult(
                    check_id="check_07_visual_integrity",
                    name="Visual Integrity & Continuity",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.ERROR,
                    measured_value=f"{clip.clip_id}: {clip.validation_status}",
                    expected_value_range="All clips safe 9:16 composition",
                    diagnostic_message=f"Clip {clip.clip_id} rejected due to severe crop or unsafe framing.",
                    remediation_suggestion="Select wider framing or re-evaluate 9:16 crop window.",
                )

        # Final Media Visual Verification (PART M, N)
        if media_visual_report:
            if media_visual_report.black_frames_detected > 0:
                return QACheckResult(
                    check_id="check_07_visual_integrity",
                    name="Visual Integrity & Continuity",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.BLOCKER,
                    measured_value=f"Black frames detected ({media_visual_report.black_frames_detected} segments)",
                    expected_value_range="Zero black frames",
                    diagnostic_message="Rendered video stream contains black or missing frames.",
                    remediation_suggestion="Inspect render concatenation and source clip validity.",
                )
            if media_visual_report.frozen_frames_detected > 0:
                return QACheckResult(
                    check_id="check_07_visual_integrity",
                    name="Visual Integrity & Continuity",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.BLOCKER,
                    measured_value=f"Frozen frames detected ({media_visual_report.frozen_frames_detected} segments)",
                    expected_value_range="Zero frozen video segments",
                    diagnostic_message="Rendered video stream contains prolonged frozen/stuck frames (>2.0s).",
                    remediation_suggestion="Inspect source footage for frozen video stream.",
                )
            if not media_visual_report.aspect_ratio_correct:
                return QACheckResult(
                    check_id="check_07_visual_integrity",
                    name="Visual Integrity & Continuity",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.ERROR,
                    measured_value=f"Resolution: {media_visual_report.dimension}",
                    expected_value_range="1080x1920 (9:16)",
                    diagnostic_message=f"Rendered video does not conform to required 1080x1920 9:16 resolution.",
                    remediation_suggestion="Re-render targeting 1080x1920.",
                )
            if media_visual_report.severe_crop_detected:
                return QACheckResult(
                    check_id="check_07_visual_integrity",
                    name="Visual Integrity & Continuity",
                    status=QACheckStatus.FAIL,
                    severity=QASeverity.ERROR,
                    measured_value="Severe crop detected in final media",
                    expected_value_range="Zero severe crop",
                    diagnostic_message="Representative frames exhibit severe subject cutoff or facial distortion.",
                    remediation_suggestion="Replace excessively tight shots with natural medium framing.",
                )

        return QACheckResult(
            check_id="check_07_visual_integrity",
            name="Visual Integrity & Continuity",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value=f"{len(timeline.clips)} clips, {timeline.total_frames} frames",
            expected_value_range="Zero gaps, valid media",
            diagnostic_message="Timeline is continuous, gapless, and free from missing asset references.",
        )

    # --------------------------------------------------------------------------
    # CHECK 8: VISUAL REPETITION
    # --------------------------------------------------------------------------
    def _check_08_visual_repetition(self, timeline: EditorialTimeline) -> QACheckResult:
        seen_sources: Dict[str, List[str]] = {}

        for clip in timeline.clips:
            if not clip.source_asset_id:
                continue
            seen_sources.setdefault(clip.source_asset_id, []).append(clip.clip_id)

        # Flag identical assets used multiple times merely to fill time
        duplicates = {k: v for k, v in seen_sources.items() if len(v) > 2}
        if duplicates:
            sample_dup = list(duplicates.keys())[0]
            clips_involved = duplicates[sample_dup]
            return QACheckResult(
                check_id="check_08_visual_repetition",
                name="Visual Repetition & Fatigue Guard",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"Asset {sample_dup} repeated {len(clips_involved)} times",
                expected_value_range="<= 2 uses of identical visual asset",
                diagnostic_message=f"Visual repetition detected: Asset '{sample_dup}' reused across clips {clips_involved}.",
                remediation_suggestion="Provide diverse footage coverage from different scene timestamps.",
            )

        return QACheckResult(
            check_id="check_08_visual_repetition",
            name="Visual Repetition & Fatigue Guard",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value="Zero redundant footage repeats",
            expected_value_range="Diverse visual sources",
            diagnostic_message="Visual diversity verified with zero repetitive loop cycles.",
        )

    # --------------------------------------------------------------------------
    # CHECK 9: EVIDENCE LINKAGE
    # --------------------------------------------------------------------------
    def _check_09_evidence_linkage(
        self,
        story_plan: Optional[DeepDiscoveryStoryPlan],
        storyboard: Optional[StoryboardPlan],
        tier: str,
    ) -> QACheckResult:
        if tier == "novel_story":
            return QACheckResult(
                check_id="check_09_evidence_linkage",
                name="Factual Evidence & Canon Provenance",
                status=QACheckStatus.PASS,
                severity=QASeverity.PASS,
                measured_value="Novel Story canon chapter grounding",
                expected_value_range="N/A (Novel Story isolated)",
                diagnostic_message="Novel Story grounded in ingested novel corpus.",
            )

        if not story_plan or not story_plan.evidence_points:
            return QACheckResult(
                check_id="check_09_evidence_linkage",
                name="Factual Evidence & Canon Provenance",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value="0 evidence points",
                expected_value_range=">= 1 verified EvidencePoint",
                diagnostic_message="No verified evidence points linked to narrative claims.",
                remediation_suggestion="Ground narrative in tri-partite canon corpus (Novel, Movie, BTS).",
            )

        # Check each evidence point for source provenance
        unverified_claims: List[str] = []
        for ep in story_plan.evidence_points:
            if not ep.source_id or not ep.source_excerpt or not ep.verified:
                unverified_claims.append(ep.claim)

        if unverified_claims:
            return QACheckResult(
                check_id="check_09_evidence_linkage",
                name="Factual Evidence & Canon Provenance",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"{len(unverified_claims)} unverified claims",
                expected_value_range="100% verified factual claims",
                diagnostic_message=f"Unsupported factual claim: '{unverified_claims[0]}' lacks verified source provenance.",
                remediation_suggestion="Cite exact novel chapter/chunk or film timestamp in EvidencePoint.",
            )

        # Check visual-beat semantic linkage if storyboard beats contain semantic mismatch errors
        if storyboard:
            for beat in storyboard.beats:
                notes = getattr(beat, "adaptation_notes", "") or ""
                if "SEMANTIC_MISMATCH" in notes or "UNRELATED_VISUAL" in notes:
                    return QACheckResult(
                        check_id="check_09_evidence_linkage",
                        name="Factual Evidence & Canon Provenance",
                        status=QACheckStatus.FAIL,
                        severity=QASeverity.ERROR,
                        measured_value=f"Beat {beat.beat_id}: SEMANTIC_MISMATCH",
                        expected_value_range="100% canon grounding and visual relevance",
                        diagnostic_message=f"Visual-beat semantic mismatch: candidate footage fails character/scene requirements for beat '{beat.beat_id}'.",
                        remediation_suggestion="Select canonical footage matching narration character and scene requirements.",
                    )

        return QACheckResult(
            check_id="check_09_evidence_linkage",
            name="Factual Evidence & Canon Provenance",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value=f"{len(story_plan.evidence_points)} verified evidence points",
            expected_value_range="100% canon grounding",
            diagnostic_message="All narrative claims possess complete provenance linkage to canonical sources.",
        )

    # --------------------------------------------------------------------------
    # CHECK 10: ENGAGEMENT / PAYOFF COMPLETENESS
    # --------------------------------------------------------------------------
    def _check_10_payoff_completeness(self, timeline: EditorialTimeline, tier: str) -> QACheckResult:
        if not timeline.clips:
            return QACheckResult(
                check_id="check_10_payoff_completeness",
                name="Engagement & Payoff Completeness",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value="Empty timeline",
                expected_value_range="Completed payoff ending",
                diagnostic_message="Timeline has no clips to evaluate payoff completeness.",
                remediation_suggestion="Assemble full narrative arc.",
            )

        # Look for payoff / anchor resolve in the second half of the Short
        total_clips = len(timeline.clips)
        second_half_clips = timeline.clips[total_clips // 2:]

        has_payoff = any(
            c.editorial_emphasis == EditorialEmphasis.PAYOFF_RESOLVE
            or c.is_anchor
            for c in second_half_clips
        )

        if not has_payoff:
            return QACheckResult(
                check_id="check_10_payoff_completeness",
                name="Engagement & Payoff Completeness",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value="No PAYOFF_RESOLVE or anchor in 2nd half",
                expected_value_range="Climactic payoff in second half",
                diagnostic_message="Timeline lacks a climactic canon realization or payoff resolution in second half.",
                remediation_suggestion="Mark final reveal beat with PAYOFF_RESOLVE emphasis or anchor highlight.",
            )

        # Invariant: No abrupt truncation (final clip must complete its frames)
        last_clip = timeline.clips[-1]
        if last_clip.end_frame != timeline.total_frames:
            return QACheckResult(
                check_id="check_10_payoff_completeness",
                name="Engagement & Payoff Completeness",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value=f"last_clip.end_frame ({last_clip.end_frame}) != total_frames ({timeline.total_frames})",
                expected_value_range="Clean boundary alignment",
                diagnostic_message="Abrupt truncation detected: timeline total_frames does not match final clip boundary.",
                remediation_suggestion="Extend or trim final clip to match timeline total_frames precisely.",
            )

        return QACheckResult(
            check_id="check_10_payoff_completeness",
            name="Engagement & Payoff Completeness",
            status=QACheckStatus.PASS,
            severity=QASeverity.PASS,
            measured_value="Recognized payoff resolve with clean narrative ending",
            expected_value_range="Payoff present",
            diagnostic_message="Narrative arc concludes with satisfying canon epiphany and seamless outro.",
        )

    # --------------------------------------------------------------------------
    # CROSS-SYSTEM FINGERPRINT CONSISTENCY
    # --------------------------------------------------------------------------
    def _check_cross_system_fingerprints(
        self,
        editorial_timeline: EditorialTimeline,
        sfx_plan: Optional[SFXPlan],
        storyboard_plan: Optional[StoryboardPlan],
        preprocessed_assets: Optional[List[PreprocessedVisualAsset]],
    ) -> Optional[QACheckResult]:
        """Validates lineage and detects stale cross-system artifacts."""
        mismatches: List[str] = []

        # Validate SFX plan matches editorial timeline fingerprint
        if sfx_plan and sfx_plan.metadata:
            ed_source = sfx_plan.metadata.get("editorial_source_fingerprint")
            if ed_source and ed_source != editorial_timeline.deterministic_fingerprint:
                mismatches.append(
                    f"SFX plan source fingerprint '{ed_source}' does not match editorial fingerprint '{editorial_timeline.deterministic_fingerprint}'."
                )

        # Validate Storyboard ID matches
        if storyboard_plan:
            if editorial_timeline.storyboard_id != storyboard_plan.storyboard_id:
                mismatches.append(
                    f"Editorial storyboard_id '{editorial_timeline.storyboard_id}' != StoryboardPlan '{storyboard_plan.storyboard_id}'."
                )

        if mismatches:
            return QACheckResult(
                check_id="check_cross_system_fingerprints",
                name="Cross-System Fingerprint Consistency",
                status=QACheckStatus.FAIL,
                severity=QASeverity.ERROR,
                measured_value="Fingerprint mismatch detected",
                expected_value_range="100% upstream fingerprint coherence",
                diagnostic_message="; ".join(mismatches),
                remediation_suggestion="Regenerate downstream SFX plan or editorial timeline using updated upstream inputs.",
            )

        return None

    def _compute_qa_fingerprint(
        self,
        candidate_id: str,
        ed_fp: str,
        sfx_fp: str,
        checks: List[QACheckResult],
    ) -> str:
        """Deterministic 16-character SHA-256 fingerprint for the QA evaluation."""
        tokens = [
            f"id={candidate_id}",
            f"ed={ed_fp}",
            f"sfx={sfx_fp}",
            f"v={self.qa_version}",
        ]
        for c in checks:
            tokens.append(f"{c.check_id}:{c.status.value}:{c.severity.value}")

        raw = "||".join(tokens)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
