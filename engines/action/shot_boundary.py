"""
STORY FORGE — Shot Boundary & Multi-Shot Continuity Analyzer
============================================================
Detects shot transitions / cuts in video footage and evaluates whether
an action spanning across cuts meets physical continuity standards.
Fails closed with ACTION_NOT_VERIFIED_ACROSS_CUT if physical proof was occluded
by a camera cut.
"""

from __future__ import annotations
import logging
from typing import List, Dict, Tuple, Optional, Any
import cv2
import numpy as np

from engines.action.models import ActionFailureReason

logger = logging.getLogger("ShotBoundaryAnalyzer")


class ShotCut:
    def __init__(self, frame_index: int, timestamp_sec: float, correlation: float):
        self.frame_index = frame_index
        self.timestamp_sec = timestamp_sec
        self.correlation = correlation


class ShotBoundaryAnalyzer:
    """
    Detects hard cuts and evaluates multi-shot action continuity.
    """

    def __init__(self, cut_hist_threshold: float = 0.52):
        self.cut_hist_threshold = cut_hist_threshold

    def detect_cuts(
        self,
        frames: List[np.ndarray],
        timestamps: Optional[List[float]] = None,
        fps: float = 24.0,
    ) -> List[ShotCut]:
        """
        Detects hard camera cuts by computing consecutive frame HSV histogram correlations.
        """
        cuts: List[ShotCut] = []
        if len(frames) < 2:
            return cuts

        prev_hist = None
        for i, frame in enumerate(frames):
            ts = timestamps[i] if (timestamps and i < len(timestamps)) else (i / fps)
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV) if len(frame.shape) == 3 else frame
            hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)

            if prev_hist is not None:
                corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
                if corr < self.cut_hist_threshold:
                    cuts.append(ShotCut(frame_index=i, timestamp_sec=round(ts, 3), correlation=round(corr, 3)))
            prev_hist = hist

        return cuts

    def verify_action_across_cuts(
        self,
        cuts: List[ShotCut],
        action_interval: Tuple[float, float],
        has_direct_requirement: bool,
        contact_timestamp: Optional[float] = None,
        identity_persisted_across_cut: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluates whether an action spanning across one or more cuts can be certified.
        
        Rule: If an assertion requires direct visual proof, and the critical contact/transition
        moment coincides with an abrupt cut, it must fail closed with ACTION_NOT_VERIFIED_ACROSS_CUT.
        """
        act_start, act_end = action_interval
        cuts_in_interval = [c for c in cuts if act_start <= c.timestamp_sec <= act_end]

        if not cuts_in_interval:
            return {
                "continuous": True,
                "cuts_detected": 0,
                "failure_reason": None,
                "explanation": "Continuous single shot across action interval.",
            }

        logger.info(f"Detected {len(cuts_in_interval)} cut(s) in action interval [{act_start:.2f}, {act_end:.2f}s]")

        # Check if critical contact occurred right at the cut
        if contact_timestamp is not None:
            for cut in cuts_in_interval:
                time_diff = abs(cut.timestamp_sec - contact_timestamp)
                if time_diff < 0.20:
                    # Contact was occluded by the cut!
                    return {
                        "continuous": False,
                        "cuts_detected": len(cuts_in_interval),
                        "failure_reason": ActionFailureReason.ACTION_NOT_VERIFIED_ACROSS_CUT,
                        "explanation": (
                            f"ACTION_NOT_VERIFIED_ACROSS_CUT: Crucial action impact at t={contact_timestamp:.2f}s "
                            f"coincided with hard camera cut at t={cut.timestamp_sec:.2f}s. "
                            f"Physical contact was not directly observed."
                        ),
                    }

        # If direct visual verification is mandatory, cuts generally disrupt physical proof
        # unless full identity continuity and physical progression are unbroken
        if has_direct_requirement and not identity_persisted_across_cut:
            return {
                "continuous": False,
                "cuts_detected": len(cuts_in_interval),
                "failure_reason": ActionFailureReason.ACTION_NOT_VERIFIED_ACROSS_CUT,
                "explanation": (
                    f"ACTION_NOT_VERIFIED_ACROSS_CUT: Action crossed {len(cuts_in_interval)} shot boundary cut(s) "
                    f"without confirmed cross-cut entity continuity."
                ),
            }

        return {
            "continuous": True,
            "cuts_detected": len(cuts_in_interval),
            "failure_reason": None,
            "explanation": f"Multi-shot sequence verified with confirmed continuity across {len(cuts_in_interval)} cut(s).",
        }
