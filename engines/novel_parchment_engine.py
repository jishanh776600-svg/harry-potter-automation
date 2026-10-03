"""
STORY FORGE Canonical Novel Parchment & Book Artwork Engine
===========================================================
Generates authentic, high-definition aged Hogwarts parchment quote cards
for novel-only scenes, book-vs-movie differences, and unfilmed lore beats.

Key Features:
1. 1080x1920 (9:16 vertical) resolution.
2. Authentic aged parchment texture, ornate borders, HarryP title font, Georgia serif body.
3. Book & Chapter citation ("BOOK 7: CHAPTER 36 • THE FLAW IN THE PLAN").
4. J.K. Rowling canonical excerpt quotation.
5. Subtle Ken Burns slow zoom (zoompan) motion @ 30 FPS.
6. Zero audio streams (-an) guaranteed.
"""

import os
import re
import json
import logging
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

from config.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

PARCHMENT_DIR = PROJECT_ROOT / "data" / "parchment"
PARCHMENT_DIR.mkdir(parents=True, exist_ok=True)
CLIPS_DIR = PROJECT_ROOT / "data" / "clips"
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

FONT_HARRY = PROJECT_ROOT / "assets" / "fonts" / "HarryP.ttf"
FONT_MAGIC = PROJECT_ROOT / "assets" / "fonts" / "MagicSchoolOne.ttf"


class NovelParchmentEngine:
    """
    Renders truthful aged parchment cards and Ken Burns MP4 video clips
    for canonical novel scenes that were never filmed in the movies.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or PARCHMENT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int, draw: ImageDraw.ImageDraw) -> List[str]:
        """Wraps text into lines that fit within max_width pixels."""
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]
            if line_w <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        if current_line:
            lines.append(" ".join(current_line))
        return lines

    def render_parchment_image(
        self,
        book_title: str,
        chapter_title: str,
        quote_text: str,
        book_number: Optional[int] = None,
        chapter_number: Optional[int] = None,
        output_image_path: Optional[Path] = None
    ) -> Path:
        """
        Creates a high-resolution 1080x1920 aged parchment graphic.
        """
        w, h = 1080, 1920
        img = Image.new("RGB", (w, h), color=(16, 14, 20)) # Gothic dark backdrop
        draw = ImageDraw.Draw(img)

        # Parchment rectangle dimensions
        p_margin_x = 70
        p_margin_y = 300
        p_w = w - (2 * p_margin_x)
        p_h = 1320

        # Draw aged parchment card with ornate vintage double borders
        parchment_color = (235, 220, 185) # Authentic parchment tone
        draw.rectangle([p_margin_x, p_margin_y, p_margin_x + p_w, p_margin_y + p_h], fill=parchment_color)
        draw.rectangle([p_margin_x + 10, p_margin_y + 10, p_margin_x + p_w - 10, p_margin_y + p_h - 10], outline=(120, 85, 45), width=4)
        draw.rectangle([p_margin_x + 18, p_margin_y + 18, p_margin_x + p_w - 18, p_margin_y + p_h - 18], outline=(165, 125, 75), width=2)

        # Corner decorations (vintage brackets)
        corner_len = 35
        # Top-left
        draw.line([(p_margin_x + 28, p_margin_y + 28), (p_margin_x + 28 + corner_len, p_margin_y + 28)], fill=(120, 85, 45), width=3)
        draw.line([(p_margin_x + 28, p_margin_y + 28), (p_margin_x + 28, p_margin_y + 28 + corner_len)], fill=(120, 85, 45), width=3)
        # Top-right
        draw.line([(p_margin_x + p_w - 28, p_margin_y + 28), (p_margin_x + p_w - 28 - corner_len, p_margin_y + 28)], fill=(120, 85, 45), width=3)
        draw.line([(p_margin_x + p_w - 28, p_margin_y + 28), (p_margin_x + p_w - 28, p_margin_y + 28 + corner_len)], fill=(120, 85, 45), width=3)
        # Bottom-left
        draw.line([(p_margin_x + 28, p_margin_y + p_h - 28), (p_margin_x + 28 + corner_len, p_margin_y + p_h - 28)], fill=(120, 85, 45), width=3)
        draw.line([(p_margin_x + 28, p_margin_y + p_h - 28), (p_margin_x + 28, p_margin_y + 28 - corner_len)], fill=(120, 85, 45), width=3)
        # Bottom-right
        draw.line([(p_margin_x + p_w - 28, p_margin_y + p_h - 28), (p_margin_x + p_w - 28 - corner_len, p_margin_y + p_h - 28)], fill=(120, 85, 45), width=3)
        draw.line([(p_margin_x + p_w - 28, p_margin_y + p_h - 28), (p_margin_x + p_w - 28, p_margin_y + 28 + corner_len)], fill=(120, 85, 45), width=3)

        # Fonts
        if FONT_HARRY.exists():
            header_font = ImageFont.truetype(str(FONT_HARRY), 84)
        else:
            header_font = ImageFont.truetype("georgiab.ttf", 60)

        sub_font = ImageFont.truetype("arialbd.ttf", 30)
        body_font = ImageFont.truetype("georgiab.ttf", 44)
        italic_font = ImageFont.truetype("georgiai.ttf", 38)

        # 1. Header: THE CANON NOVEL
        header_text = "THE CANON NOVEL"
        draw.text((w // 2, p_margin_y + 75), header_text, fill=(75, 40, 15), font=header_font, anchor="mm")

        # 2. Subheader: BOOK & CHAPTER
        b_label = f"BOOK {book_number}" if book_number else (book_title.upper() if book_title else "CANON NOVEL")
        c_label = f"CH {chapter_number}: {chapter_title.upper()}" if chapter_number else (chapter_title.upper() if chapter_title else "ORIGINAL TEXT")
        sub_text = f"{b_label} • {c_label}"
        if len(sub_text) > 48:
            sub_text = f"{b_label} • {c_label[:40]}..."
        draw.text((w // 2, p_margin_y + 165), sub_text, fill=(125, 85, 45), font=sub_font, anchor="mm")

        # 3. Divider line
        draw.line([(p_margin_x + 60, p_margin_y + 205), (w - p_margin_x - 60, p_margin_y + 205)], fill=(150, 110, 60), width=3)

        # 4. Book Excerpt / Quote
        clean_quote = quote_text.strip()
        if not (clean_quote.startswith("“") or clean_quote.startswith('"')):
            clean_quote = f"“{clean_quote}"
        if not (clean_quote.endswith("”") or clean_quote.endswith('"')):
            clean_quote = f"{clean_quote}”"

        max_text_w = p_w - 120
        # If quote contains multiple paragraphs / newlines, split them
        paragraphs = clean_quote.split("\n")
        all_wrapped_lines = []
        for p in paragraphs:
            p_strip = p.strip()
            if not p_strip:
                all_wrapped_lines.append("")
                continue
            wrapped = self._wrap_text(p_strip, body_font, max_text_w, draw)
            all_wrapped_lines.extend(wrapped)

        # Layout wrapped text vertically
        line_height = 64
        curr_y = p_margin_y + 280
        for line in all_wrapped_lines:
            if line == "":
                curr_y += 24
                continue
            draw.text((w // 2, curr_y), line, fill=(35, 20, 10), font=body_font, anchor="mm")
            curr_y += line_height

        # 5. Footer citation
        footer_text = "— J.K. ROWLING • ORIGINAL TEXT"
        draw.text((w // 2, p_margin_y + p_h - 75), footer_text, fill=(110, 75, 40), font=italic_font, anchor="mm")

        if output_image_path is None:
            q_hash = hashlib.md5(quote_text.encode("utf-8")).hexdigest()[:10]
            output_image_path = self.output_dir / f"parchment_{q_hash}.jpg"

        img.save(output_image_path, quality=95)
        logger.info(f"Rendered parchment image: {output_image_path} ({output_image_path.stat().st_size} bytes)")
        return output_image_path

    def render_parchment_clip(
        self,
        book_title: str,
        chapter_title: str,
        quote_text: str,
        duration_seconds: float = 2.5,
        book_number: Optional[int] = None,
        chapter_number: Optional[int] = None,
        output_clip_path: Optional[Path] = None,
        zoom_speed: float = 0.0015
    ) -> Path:
        """
        Renders a subtle Ken Burns zoompan MP4 video clip (1080x1920 @ 30fps)
        from the rendered parchment card.
        Guarantees ZERO audio streams (-an).
        """
        q_hash = hashlib.md5(quote_text.encode("utf-8")).hexdigest()[:10]
        img_path = self.output_dir / f"parchment_{q_hash}.jpg"
        self.render_parchment_image(
            book_title=book_title,
            chapter_title=chapter_title,
            quote_text=quote_text,
            book_number=book_number,
            chapter_number=chapter_number,
            output_image_path=img_path
        )

        if output_clip_path is None:
            output_clip_path = CLIPS_DIR / f"parchment_clip_{q_hash}.mp4"

        # Calculate total frames for zoompan
        total_frames = int(duration_seconds * 30)
        # Ken Burns slow zoom: starts at 1.0, gently zooms to ~1.06
        filter_kb = (
            f"zoompan=z='min(zoom+{zoom_speed:.4f},1.08)':d={total_frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
            f"format=yuv420p"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(img_path),
            "-t", str(round(duration_seconds, 3)),
            "-vf", filter_kb,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-an",  # ABSOLUTE INVARIANT: NO AUDIO
            str(output_clip_path)
        ]

        logger.info(f"Rendering Ken Burns parchment clip ({duration_seconds:.2f}s) -> {output_clip_path.name}...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg parchment clip rendering failed: {res.stderr[-300:]}")

        # Probe to ensure 0 audio streams
        probe_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            str(output_clip_path)
        ]
        probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if probe_res.stdout.strip():
            output_clip_path.unlink(missing_ok=True)
            raise RuntimeError(f"Parchment clip {output_clip_path.name} unexpectedly contains audio!")

        logger.info(f"Parchment clip successfully rendered: {output_clip_path.name} ({output_clip_path.stat().st_size} bytes)")
        return output_clip_path
