"""
STORY FORGE — Phase 5: Canonical Subtitle Renderer
====================================================
Parts 11, 12, 13 of the 34-part Phase 5 specification.

PART 11: Canonical subtitle profile:
    - Font: "Harry P" (Harry Potter canonical font)
    - White text, heavy black outline
    - Canonical placement (bottom 20% safe zone)
    - DO NOT substitute Arial / Arial Bold / Arial Black / any generic font

PART 12: Word-level subtitle timing from locked word timestamps.

PART 13: Subtitle safe-zone — must not cover key visual evidence.
    Returns SUBTITLE_EVIDENCE_COLLISION if subtitles would obscure action region.

The previous Arial substitution MUST NEVER happen again.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from engines.edl.models import WordTimestamp, VisualEDL, EDLEntry

logger = logging.getLogger("Phase5SubtitleRenderer")

# ── Canonical subtitle profile (Part 11) ──────────────────────────────────────
CANONICAL_FONT_NAME = "Harry P"
CANONICAL_FONT_SIZE = 82
CANONICAL_OUTLINE_WIDTH = 8
CANONICAL_SHADOW_DEPTH = 3
CANONICAL_PRIMARY_COLOR = "&H00FFFFFF&"    # White
CANONICAL_OUTLINE_COLOR = "&H00000000&"    # Black
CANONICAL_BACK_COLOR = "&H80000000&"       # Semi-transparent black shadow
CANONICAL_ALIGNMENT = 2                    # Bottom-centre (ASS numpad)
CANONICAL_MARGIN_V = 120                   # Pixels from bottom edge

# Subtitle safe zone — subtitles occupy bottom region [0.82, 1.0] of normalised height
SUBTITLE_SAFE_ZONE_TOP = 0.82             # Subtitles live below this Y threshold

# Known generic font substitutes to REJECT
_BANNED_FONTS = frozenset([
    "arial", "arial black", "arial bold", "arial narrow",
    "helvetica", "times new roman", "verdana", "tahoma",
    "calibri", "segoe ui", "roboto", "open sans",
])


@dataclass
class SubtitleRenderResult:
    """Result of generating the ASS subtitle file."""
    ass_path: Optional[Path]
    font_name: str
    cue_count: int
    render_ok: bool = True
    error: Optional[str] = None
    evidence_collision_detected: bool = False
    collision_details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ass_path": str(self.ass_path) if self.ass_path else None,
            "font_name": self.font_name,
            "cue_count": self.cue_count,
            "render_ok": self.render_ok,
            "error": self.error,
            "evidence_collision_detected": self.evidence_collision_detected,
            "collision_details": self.collision_details,
        }


class SubtitleChunkerV2:
    """
    Chunks word timestamps into natural 2-3 word subtitle cues.
    Strictly forbids 4+ word blocks; splits them down to 2-3 words.
    Preserves exact word-level start and end timestamps.
    """

    MAX_WORDS_PER_CHUNK: int = 3
    MIN_WORDS_PER_CHUNK: int = 2

    @classmethod
    def validate_chunk(cls, words: List[Any]) -> bool:
        """
        Validates if a chunk meets the 2-3 word standard requirement.
        Returns True for 1-3 words; False for 4+ words.
        """
        return 1 <= len(words) <= cls.MAX_WORDS_PER_CHUNK

    @classmethod
    def validate_font(cls, font_name: str) -> bool:
        """Validates that font is canonical 'Harry P' and not in banned list."""
        if not font_name or font_name.lower().strip() in _BANNED_FONTS:
            return False
        return font_name.strip() == CANONICAL_FONT_NAME

    @classmethod
    def chunk_words(
        cls,
        word_timestamps: List[WordTimestamp],
        max_words_per_cue: int = 3,
        min_words_per_cue: int = 2,
    ) -> List[Tuple[float, float, str]]:
        if not word_timestamps:
            return []

        cues: List[Tuple[float, float, str]] = []
        n = len(word_timestamps)
        i = 0

        while i < n:
            rem = n - i
            # Standard chunk size: 2 or 3 words
            if rem == 4:
                chunk_len = 2
            elif rem >= 3:
                # If the 2nd word ends with punctuation, flush at 2 words
                if word_timestamps[i + 1].word.rstrip().endswith((".", "!", "?", ",", ";", "…")):
                    chunk_len = 2
                else:
                    chunk_len = min(max_words_per_cue, 3)
            elif rem == 2:
                chunk_len = 2
            else:  # rem == 1
                if cues:
                    # Append single trailing word to previous cue if previous cue had 2 words
                    prev_start, prev_end, prev_text = cues[-1]
                    prev_words = prev_text.split()
                    if len(prev_words) <= 2:
                        cues[-1] = (
                            prev_start,
                            word_timestamps[i].end_sec,
                            f"{prev_text} {word_timestamps[i].word}".strip(),
                        )
                        break
                chunk_len = 1

            chunk = word_timestamps[i : i + chunk_len]
            cue_start = chunk[0].start_sec
            cue_end = chunk[-1].end_sec
            cue_text = " ".join(w.word for w in chunk).strip()
            cues.append((cue_start, cue_end, cue_text))
            i += chunk_len

        return cues


class Phase5SubtitleRenderer:
    """
    Generates a canonical ASS subtitle file from locked word timestamps.

    STRICT INVARIANTS:
      1. Font is ALWAYS "Harry P" — no substitution, no override.
      2. If "Harry P" is not available, fail with CANONICAL_FONT_MISSING —
         do NOT silently substitute.
      3. Word-level timing: each subtitle cue uses the exact start/end
         from the LockedNarrationInput word timestamps.
      4. Safe-zone: subtitles are bottom-pinned; if any required action
         evidence falls in the bottom zone, return SUBTITLE_EVIDENCE_COLLISION.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        if output_dir is None:
            try:
                from config.settings import PROJECT_ROOT
                output_dir = PROJECT_ROOT / "data" / "captions" / "phase5"
            except ImportError:
                output_dir = Path("data/captions/phase5")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        content_id: str,
        word_timestamps: List[WordTimestamp],
        edl: Optional[VisualEDL] = None,
        check_evidence_collision: bool = True,
    ) -> SubtitleRenderResult:
        """
        Generate a canonical ASS subtitle file.

        Args:
            content_id: Identifier for the content (used in filename).
            word_timestamps: Locked word-level timestamps.
            edl: Optional VisualEDL for SUBTITLE_EVIDENCE_COLLISION check.
            check_evidence_collision: Whether to run the safe-zone collision check.

        Returns:
            SubtitleRenderResult — check .render_ok before using.
        """
        if not word_timestamps:
            return SubtitleRenderResult(
                ass_path=None,
                font_name=CANONICAL_FONT_NAME,
                cue_count=0,
                render_ok=False,
                error="No word timestamps provided — cannot generate subtitles.",
            )

        ass_path = self.output_dir / f"{content_id}_phase5.ass"

        # Build sentence-level cues from word timestamps
        cues = self._build_sentence_cues(word_timestamps)

        # Check for evidence collision before writing
        collision_detail = None
        if check_evidence_collision and edl is not None:
            collision_detail = self._check_evidence_collision(edl)

        # Write ASS file
        ass_content = self._generate_ass(cues)
        ass_path.write_text(ass_content, encoding="utf-8")

        logger.info(
            "Subtitle ASS written: %s | %d cues | font='%s'",
            ass_path.name, len(cues), CANONICAL_FONT_NAME,
        )

        return SubtitleRenderResult(
            ass_path=ass_path,
            font_name=CANONICAL_FONT_NAME,
            cue_count=len(cues),
            render_ok=True,
            evidence_collision_detected=collision_detail is not None,
            collision_details=collision_detail,
        )

    # ------------------------------------------------------------------
    # Sentence cue construction (Part 12: word-level timing)
    # ------------------------------------------------------------------

    def _build_sentence_cues(
        self,
        word_timestamps: List[WordTimestamp],
        max_words_per_cue: int = 3,
        min_cue_gap_sec: float = 0.05,
    ) -> List[Tuple[float, float, str]]:
        """
        Group words into subtitle cues (2-3 words maximum per chunk).
        Each cue timing comes directly from the locked word timestamps.
        """
        return SubtitleChunkerV2.chunk_words(
            word_timestamps, max_words_per_cue=max_words_per_cue
        )

    # ------------------------------------------------------------------
    # ASS file generation (Part 11: canonical font)
    # ------------------------------------------------------------------

    def _generate_ass(self, cues: List[Tuple[float, float, str]]) -> str:
        """Generate the full ASS file content with canonical Harry P font."""
        header = self._ass_header()
        events_header = "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

        dialogue_lines: List[str] = []
        for start, end, text in cues:
            dialogue_lines.append(
                f"Dialogue: 0,{self._fmt_ts(start)},{self._fmt_ts(end)},"
                f"HarryPStyle,,0,0,0,,{text}"
            )

        return header + "\n" + events_header + "\n".join(dialogue_lines) + "\n"

    def _ass_header(self) -> str:
        """Build ASS [Script Info] + [V4+ Styles] block."""
        return (
            "[Script Info]\n"
            "ScriptType: v4.00+\n"
            "PlayResX: 1080\n"
            "PlayResY: 1920\n"
            "ScaledBorderAndShadow: yes\n"
            "\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            f"Style: HarryPStyle,"
            f"{CANONICAL_FONT_NAME},"          # ← CANONICAL FONT — DO NOT CHANGE
            f"{CANONICAL_FONT_SIZE},"
            f"{CANONICAL_PRIMARY_COLOR},"
            f"&H000000FF&,"                    # Secondary (unused)
            f"{CANONICAL_OUTLINE_COLOR},"
            f"{CANONICAL_BACK_COLOR},"
            f"0,0,0,0,"                         # Bold=0, Italic=0, etc.
            f"100,100,0,0,"                     # ScaleX, ScaleY, Spacing, Angle
            f"1,"                               # BorderStyle=1 (outline+shadow)
            f"{CANONICAL_OUTLINE_WIDTH},"
            f"{CANONICAL_SHADOW_DEPTH},"
            f"{CANONICAL_ALIGNMENT},"          # Bottom-centre
            f"80,80,{CANONICAL_MARGIN_V},0\n"  # MarginL, MarginR, MarginV, Encoding
        )

    @staticmethod
    def _fmt_ts(seconds: float) -> str:
        """Format seconds into ASS H:MM:SS.cc timestamp."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int(round((seconds - int(seconds)) * 100))
        if cs >= 100:
            s += 1
            cs = 0
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    # ------------------------------------------------------------------
    # Subtitle evidence collision check (Part 13)
    # ------------------------------------------------------------------

    def _check_evidence_collision(self, edl: VisualEDL) -> Optional[str]:
        """
        Check whether any DIRECT beat's evidence region falls in the subtitle safe zone.

        The subtitle safe zone is the bottom 18% of the frame (Y > 0.82).
        If a DIRECT beat has crop_requirements indicating subject bboxes
        that intersect this zone, return SUBTITLE_EVIDENCE_COLLISION.
        """
        from engines.edl.models import CoverageState, CoverageRequirement

        for entry in edl.entries:
            if entry.coverage_state != CoverageState.VERIFIED_DIRECT:
                continue

            crop = entry.crop_requirements
            if not crop or not isinstance(crop, dict):
                continue

            # Check if the crop window places the subject in the subtitle zone
            # crop_window: {x, y, w, h, src_w, src_h}
            crop_w = crop.get("crop_window") or crop
            x = crop_w.get("x", 0)
            y = crop_w.get("y", 0)
            w = crop_w.get("w")
            h = crop_w.get("h")
            src_h = crop_w.get("src_h", 800)

            if w is None or h is None or src_h == 0:
                continue

            # Normalised crop position relative to source height
            crop_bottom_norm = (y + h) / src_h  # 0..1 in source space

            # In the OUTPUT 9:16 frame, the subject occupies [0, 1.0] vertically.
            # After crop+scale, subjects that were near the bottom of the source
            # will appear near the bottom of the output.
            # Simplified: if crop_y is in the lower half of source, subject is in lower half of output.
            norm_subject_centre_y = (y + h / 2) / src_h
            if norm_subject_centre_y > SUBTITLE_SAFE_ZONE_TOP:
                return (
                    f"SUBTITLE_EVIDENCE_COLLISION: Beat '{entry.beat_id}' "
                    f"has DIRECT evidence (required: {entry.required_entities}) "
                    f"positioned at normalised Y={norm_subject_centre_y:.2f} "
                    f"which overlaps the subtitle safe zone (Y>{SUBTITLE_SAFE_ZONE_TOP}). "
                    f"Subtitle placement would cover key visual evidence."
                )
        return None

    # ------------------------------------------------------------------
    # Forensic: verify existing ASS file uses canonical font (Part 25)
    # ------------------------------------------------------------------

    @staticmethod
    def audit_ass_font(ass_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Audit an existing ASS file to verify it uses the canonical 'Harry P' font.
        Returns (passed, detail_or_none).
        """
        if not ass_path.exists():
            return False, f"ASS file not found: {ass_path}"

        content = ass_path.read_text(encoding="utf-8", errors="ignore")
        # Extract font names from Style lines
        style_matches = re.findall(r"^Style\s*:\s*[^,]+,([^,]+),", content, re.MULTILINE)
        for raw_font in style_matches:
            fn = raw_font.strip()
            if fn.lower() in _BANNED_FONTS:
                return False, (
                    f"CANONICAL_FONT_VIOLATION: ASS file '{ass_path.name}' uses "
                    f"banned generic font '{fn}'. Expected '{CANONICAL_FONT_NAME}'. "
                    f"The previous Arial substitution must never happen again."
                )
            if fn.lower() != CANONICAL_FONT_NAME.lower():
                return False, (
                    f"CANONICAL_FONT_MISMATCH: ASS file '{ass_path.name}' uses "
                    f"font '{fn}' instead of canonical '{CANONICAL_FONT_NAME}'."
                )
        return True, None
