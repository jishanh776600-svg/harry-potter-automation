"""
Caption Engine.
Uses Faster-Whisper to generate accurate word-level timestamps.
Renders stylized ASS subtitle streams placed in safe zones with dynamic word highlighting
and semantic punch-word emphasis.
"""
import re
import uuid
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from faster_whisper import WhisperModel
from config.settings import CAPTIONS_DIR
from config.constants import VIDEO_WIDTH, VIDEO_HEIGHT

logger = logging.getLogger(__name__)


SUBTITLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "harry_potter": {
        "profile_id": "harry_potter_canonical_v1",
        "font_name": "Harry P",
        "default_size": 84,
        "default_color": "&H00FFFFFF",
        "default_outline_color": "&H00000000",
        "default_outline": 4.5,
        "default_shadow": 0.0,
        "pop_size": 92,
        "pop_color": "&H002AE5FF",
        "pop_outline_color": "&H00000000",
        "pop_outline": 5.0,
        "pop_shadow": 0.0,
        "alignment": 2,
        "margin_l": 80,
        "margin_r": 80,
        "margin_v": 520,
    },
    "generic": {
        "profile_id": "generic_arial_black_v1",
        "font_name": "Arial Black",
        "default_size": 86,
        "default_color": "&H00FFFFFF",
        "default_outline_color": "&H00000000",
        "default_outline": 8.0,
        "default_shadow": 4.0,
        "pop_size": 90,
        "pop_color": "&H0000D7FF",
        "pop_outline_color": "&H00000000",
        "pop_outline": 9.0,
        "pop_shadow": 5.0,
        "alignment": 2,
        "margin_l": 60,
        "margin_r": 60,
        "margin_v": 500,
    },
}


def compute_subtitle_fingerprint(profile_name: str = "harry_potter") -> str:
    """Computes a deterministic cryptographic fingerprint of the subtitle profile styling."""
    prof = SUBTITLE_PROFILES.get(profile_name, SUBTITLE_PROFILES["harry_potter"])
    raw = (
        f"{prof['profile_id']}:{prof['font_name']}:{prof['default_size']}:{prof['default_outline']}:"
        f"{prof['pop_size']}:{prof['pop_outline']}:{prof['margin_v']}:{prof['alignment']}"
    )
    import hashlib
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


class CaptionEngine:
    """Extracts word-level timestamps and produces modern, vertical Shorts subtitles."""

    def __init__(self, model_size: str = "base"):
        self.captions_dir = CAPTIONS_DIR
        self.captions_dir.mkdir(parents=True, exist_ok=True)
        self.model_size = model_size
        self._model = None

    def _get_whisper_model(self) -> WhisperModel:
        if self._model is None:
            logger.info(f"Loading faster-whisper model ({self.model_size}) on CPU...")
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe_words(self, audio_path: Path) -> List[Dict[str, Any]]:
        """Extracts word-level timestamp entries."""
        model = self._get_whisper_model()
        segments, _ = model.transcribe(str(audio_path), word_timestamps=True, language="en")

        words = []
        for segment in segments:
            if segment.words:
                for w in segment.words:
                    clean_w = w.word.strip()
                    if clean_w:
                        words.append({
                            "word": clean_w,
                            "start": round(w.start, 2),
                            "end": round(w.end, 2)
                        })
            else:
                text_words = segment.text.strip().split()
                dur = (segment.end - segment.start) / max(len(text_words), 1)
                for idx, tw in enumerate(text_words):
                    if tw.strip():
                        words.append({
                            "word": tw.strip(),
                            "start": round(segment.start + (idx * dur), 2),
                            "end": round(segment.start + ((idx + 1) * dur), 2)
                        })
        return words

    @classmethod
    def build_ass_header(cls, profile_name: str = "harry_potter") -> str:
        """Constructs canonical ASS header for specified subtitle profile."""
        prof = SUBTITLE_PROFILES.get(profile_name, SUBTITLE_PROFILES["harry_potter"])
        fn = prof["font_name"]
        ds = prof["default_size"]
        dc = prof["default_color"]
        do = prof["default_outline"]
        ps = prof["pop_size"]
        pc = prof["pop_color"]
        po = prof["pop_outline"]
        mv = prof["margin_v"]
        ml = prof["margin_l"]
        mr = prof["margin_r"]
        sh_def = prof["default_shadow"]
        sh_pop = prof["pop_shadow"]
        align = prof["alignment"]

        return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: HP_Default,{fn},{ds},{dc},{dc},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{do},{sh_def},{align},{ml},{mr},{mv},1
Style: HP_Pop,{fn},{ps},{pc},{pc},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{po},{sh_pop},{align},{ml},{mr},{mv},1
Style: Default,{fn},{ds},{dc},{dc},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{do},{sh_def},{align},{ml},{mr},{mv},1
Style: Punch,{fn},{ps},{pc},{pc},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{po},{sh_pop},{align},{ml},{mr},{mv},1
Style: PartMarker,{fn},42,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.0,0,7,50,50,55,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    @classmethod
    def generate_ass_from_words(
        cls,
        words: List[Dict[str, Any]],
        output_path: Path,
        profile: str = "harry_potter",
        keywords: Optional[Set[str]] = None,
    ) -> Path:
        """
        Renders word timestamps directly into canonical ASS subtitles using the active profile.
        """
        prof = SUBTITLE_PROFILES.get(profile, SUBTITLE_PROFILES["harry_potter"])
        pop_color = prof["pop_color"]
        header = cls.build_ass_header(profile)

        punch_kw = set(keywords) if keywords else {
            "HOGWARTS", "MAGIC", "WAND", "SPELL", "POTTER", "DUMBLEDORE", "VOLDEMORT",
            "GRYFFINDOR", "SLYTHERIN", "SECRET", "DANGER", "CURSE", "PROPHECY", "DISCOVERY",
            "MYSTERY", "SHOCKING", "UNEXPLAINED", "DEADLY", "REVEALED", "TRUE", "POWERFUL",
            "HERMIONE", "RON", "SNAPE", "HAGRID", "MALFOY", "SIRIUS", "DOBBY", "CHOCOLATE",
            "LUPIN", "DEMENTOR", "OLLIVANDER", "BEECHWOOD", "HOLLY", "PHOENIX", "FIRST", "AID"
        }

        # Cluster words into punchy lines (3-4 words per line)
        clusters = []
        chunk = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= 4 or str(w["word"]).endswith((".", ",", "!", "?", ":", "—")):
                clusters.append(list(chunk))
                chunk = []
        if chunk:
            clusters.append(chunk)

        events = []
        for cl in clusters:
            st = float(cl[0]["start"])
            et = float(cl[-1]["end"])
            st_str = f"0:{int(st//60):02d}:{st%60:05.2f}"
            et_str = f"0:{int(et//60):02d}:{et%60:05.2f}"

            tokens = []
            for w in cl:
                clean = re.sub(r"[^\w]", "", str(w["word"])).upper()
                if clean in punch_kw:
                    tokens.append(f"{{\\c{pop_color}\\}}{w['word']}{{\\c&H00FFFFFF\\}}")
                else:
                    tokens.append(w["word"])
            line = " ".join(tokens)
            events.append(f"Dialogue: 0,{st_str},{et_str},HP_Default,,0,0,0,,{line}\n")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + "".join(events))

        logger.info(f"Generated canonical '{profile}' ASS subtitles at {output_path}")
        return output_path

    def generate_ass_subtitles(
        self,
        audio_path: Path,
        output_path: Optional[Path] = None,
        editing_plan: Optional[Any] = None,
        part_marker: Optional[str] = None,
        profile: str = "harry_potter",
    ) -> Path:
        """
        Builds modern ASS subtitle file with karaoke style active-word highlighting
        using the specified canonical subtitle profile (default: 'harry_potter').
        """
        words = self.transcribe_words(audio_path)
        if not output_path:
            output_path = self.captions_dir / f"subs_{uuid.uuid4().hex[:8]}.ass"

        return self.generate_ass_from_words(
            words=words,
            output_path=output_path,
            profile=profile,
        )
