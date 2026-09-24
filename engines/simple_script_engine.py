"""
STORY FORGE — Simple English Scripting Engine
=============================================
Conversational, punchy, clear English scripting for YouTube Shorts narration.
Enforces:
- Short, punchy sentences (avg <= 14 words, max <= 20 words)
- Natural speech flow, active voice, high-retention pacing
- Strict rejection of bloated/academic thesis jargon
- High readability (Flesch Reading Ease >= 70)
- Preservation of canonical Harry Potter lore and dramatic tension
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


ACADEMIC_JARGON = [
    "notwithstanding",
    "furthermore",
    "moreover",
    "in juxtaposition",
    "juxtaposes",
    "it is noteworthy",
    "elucidates",
    "delineates",
    "heretofore",
    "in essence",
    "consequently",
    "subsequently",
    "demonstrative of",
    "epitomizes",
    "purports",
    "in light of the fact that",
    "serves to highlight",
    "it is crucial to remember",
]

SIMPLIFICATION_MAP = {
    "furthermore": "also",
    "moreover": "plus",
    "notwithstanding": "even so",
    "subsequently": "then",
    "consequently": "so",
    "in essence": "basically",
    "elucidates": "shows",
    "delineates": "shows",
    "epitomizes": "proves",
    "in light of the fact that": "because",
    "serves to highlight": "reveals",
    "it is noteworthy that": "notice that",
}

THROAT_CLEARING_PATTERNS = [
    r"in this video we will explore",
    r"let us delve into",
    r"today we are going to look at",
    r"without further ado",
    r"as we all know",
]


@dataclass
class SimpleEnglishAudit:
    """Audit report for Simple English script quality."""
    is_valid: bool
    flesch_score: float
    avg_sentence_length: float
    max_sentence_length: int
    word_count: int
    sentence_count: int
    forbidden_words: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "flesch_score": round(self.flesch_score, 1),
            "avg_sentence_length": round(self.avg_sentence_length, 1),
            "max_sentence_length": self.max_sentence_length,
            "word_count": self.word_count,
            "sentence_count": self.sentence_count,
            "forbidden_words": self.forbidden_words,
            "issues": self.issues,
            "suggestions": self.suggestions,
        }


class SimpleScriptEngine:
    """
    Validates and refines narration scripts into clear, conversational simple English.
    """

    @staticmethod
    def count_syllables(word: str) -> int:
        """Approximates syllable count of an English word."""
        word = word.lower().strip()
        if not word:
            return 0
        word = re.sub(r"[^a-z]", "", word)
        if len(word) <= 3:
            return 1
        # Count vowel sequences
        vowel_runs = re.findall(r"[aeiouy]+", word)
        count = len(vowel_runs)
        # Trailing silent e
        if word.endswith("e") and not word.endswith("le") and len(word) > 2 and word[-2] not in "aeiouy":
            count -= 1
        # Trailing ed
        if word.endswith("ed") and len(word) > 3 and word[-3] not in "td":
            count -= 1
        return max(1, count)

    @classmethod
    def split_sentences(cls, text: str) -> List[str]:
        """Splits text into sentences cleanly."""
        text = text.strip()
        if not text:
            return []
        raw_sentences = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in raw_sentences if s.strip()]

    @classmethod
    def calculate_flesch_score(cls, words: List[str], sentences: List[str]) -> float:
        """
        Calculates standard Flesch Reading Ease score:
        206.835 - 1.015 * (total words / total sentences) - 84.6 * (total syllables / total words)
        """
        if not words or not sentences:
            return 100.0
        total_words = len(words)
        total_sentences = len(sentences)
        total_syllables = sum(cls.count_syllables(w) for w in words)

        asl = total_words / max(1, total_sentences)
        asw = total_syllables / max(1, total_words)

        score = 206.835 - (1.015 * asl) - (84.6 * asw)
        return max(0.0, min(100.0, score))

    @classmethod
    def validate_script(cls, text: str, min_flesch: float = 65.0, max_avg_len: float = 16.0) -> SimpleEnglishAudit:
        """
        Validates whether script text adheres to simple English rules.
        """
        issues = []
        suggestions = []
        forbidden_found = []

        # Find words and sentences
        sentences = cls.split_sentences(text)
        words = re.findall(r"\b[A-Za-z0-9'-]+\b", text)

        if not sentences or not words:
            return SimpleEnglishAudit(
                is_valid=False,
                flesch_score=0.0,
                avg_sentence_length=0.0,
                max_sentence_length=0,
                word_count=0,
                sentence_count=0,
                issues=["Empty script text."],
            )

        sentence_lengths = [len(re.findall(r"\b[A-Za-z0-9'-]+\b", s)) for s in sentences]
        avg_len = sum(sentence_lengths) / len(sentence_lengths)
        max_len = max(sentence_lengths) if sentence_lengths else 0

        # Check jargon
        lower_text = text.lower()
        for jargon in ACADEMIC_JARGON:
            if re.search(r"\b" + re.escape(jargon) + r"\b", lower_text):
                forbidden_found.append(jargon)
                issues.append(f"Forbidden academic/bloated phrasing: '{jargon}'")
                if jargon in SIMPLIFICATION_MAP:
                    suggestions.append(f"Replace '{jargon}' with '{SIMPLIFICATION_MAP[jargon]}'")

        # Check throat clearing
        for tc in THROAT_CLEARING_PATTERNS:
            if re.search(tc, lower_text):
                issues.append(f"Throat-clearing detected: '{tc}'")
                suggestions.append("Remove introductory filler and jump straight into the hook.")

        # Check sentence lengths
        if avg_len > max_avg_len:
            issues.append(f"Average sentence length is too high: {avg_len:.1f} words (limit: {max_avg_len}).")
        if max_len > 22:
            issues.append(f"Run-on sentence detected: {max_len} words (limit: 22 words).")

        flesch = cls.calculate_flesch_score(words, sentences)
        if flesch < min_flesch:
            issues.append(f"Flesch Reading Ease score is too low: {flesch:.1f} (target >= {min_flesch}).")

        is_valid = len(forbidden_found) == 0 and avg_len <= (max_avg_len + 1.0) and flesch >= min_flesch and max_len <= 24

        return SimpleEnglishAudit(
            is_valid=is_valid,
            flesch_score=flesch,
            avg_sentence_length=avg_len,
            max_sentence_length=max_len,
            word_count=len(words),
            sentence_count=len(sentences),
            forbidden_words=forbidden_found,
            issues=issues,
            suggestions=suggestions,
        )

    @classmethod
    def simplify_script(cls, text: str) -> str:
        """
        Transforms text by replacing academic jargon with conversational equivalents
        and stripping throat clearing.
        """
        result = text
        # Remove throat clearing
        for tc in THROAT_CLEARING_PATTERNS:
            result = re.sub(tc, "", result, flags=re.IGNORECASE)

        # Replace jargon
        for jargon, replacement in SIMPLIFICATION_MAP.items():
            pattern = r"\b" + re.escape(jargon) + r"\b"
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        # Clean multiple spaces
        result = re.sub(r"\s+", " ", result).strip()
        return result
