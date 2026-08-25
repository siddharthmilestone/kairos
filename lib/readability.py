"""Deterministic readability scoring for markdown content.

Computes Flesch Reading Ease and Flesch-Kincaid Grade Level over the prose in a
markdown document, using a heuristic syllable counter. Markdown syntax, fenced
code blocks, and tables are stripped first so they don't distort the scores — a
block of code or a pipe-delimited table has no meaningful "sentence length" and
would otherwise wreck the numbers.

Pure stdlib, no third-party deps, no network. Used to gate generated content to
a target reading grade (see TARGET_GRADE_MAX / within_target).
"""
from __future__ import annotations

import re

TARGET_GRADE_MAX = 12

# --- markdown stripping ------------------------------------------------------

_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_FENCED_CODE_TILDE = re.compile(r"~~~.*?~~~", re.DOTALL)
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")   # [text](url) -> text, images dropped to alt
_INLINE_CODE = re.compile(r"`([^`]*)`")


def _is_table_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    # A markdown table row is pipe-delimited; a separator row is only |-:  chars.
    if s.startswith("|") or ("|" in s and s.count("|") >= 2):
        return True
    return False


def strip_markdown(md: str) -> str:
    """Remove markdown formatting, returning readable sentence text.

    Drops fenced code blocks and table rows entirely; converts links to their
    anchor text; strips heading marks, emphasis, blockquote and list markers,
    inline code backticks and stray table pipes. Whitespace is collapsed.
    """
    if not md:
        return ""
    text = md
    # Remove fenced code blocks wholesale (they aren't prose).
    text = _FENCED_CODE.sub(" ", text)
    text = _FENCED_CODE_TILDE.sub(" ", text)
    # Links -> anchor text (before we start deleting punctuation).
    text = _LINK.sub(r"\1", text)
    # Inline code -> its contents without backticks.
    text = _INLINE_CODE.sub(r"\1", text)

    out_lines = []
    for line in text.split("\n"):
        if _is_table_line(line):
            continue
        s = line
        # Heading marks, blockquotes, list markers at line start.
        s = re.sub(r"^\s{0,3}#{1,6}\s*", "", s)
        s = re.sub(r"^\s*>+\s?", "", s)
        s = re.sub(r"^\s*[-*+]\s+", "", s)          # unordered list
        s = re.sub(r"^\s*\d+[.)]\s+", "", s)        # ordered list
        # Horizontal rules.
        if re.match(r"^\s*([-*_])\1{2,}\s*$", s):
            continue
        out_lines.append(s)
    text = "\n".join(out_lines)

    # Emphasis / bold markers and stray formatting chars.
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"[*_`]", "", text)
    text = text.replace("|", " ")
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


# --- syllable counting -------------------------------------------------------

_VOWELS = "aeiouy"


def count_syllables(word: str) -> int:
    """Heuristic syllable count for an English word. Minimum 1 for any alphabetic word."""
    w = re.sub(r"[^a-z]", "", (word or "").lower())
    if not w:
        return 0
    count = 0
    prev_vowel = False
    for ch in w:
        is_vowel = ch in _VOWELS
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Silent trailing 'e' (but not 'le' after a consonant, e.g. "table").
    if w.endswith("e") and not w.endswith("le"):
        count -= 1
    if w.endswith("le") and len(w) > 2 and w[-3] not in _VOWELS:
        count += 1
    return max(1, count)


# --- analysis ----------------------------------------------------------------

_WORD = re.compile(r"\b[\w']+\b")
_SENT_SPLIT = re.compile(r"[.!?]+")


def _count_sentences(text: str) -> int:
    if not text.strip():
        return 0
    parts = [p for p in _SENT_SPLIT.split(text) if p.strip()]
    return max(1, len(parts))


def _grade_label(grade_int: int) -> str:
    if grade_int <= 8:
        return f"Easy (grade {grade_int})"
    if grade_int <= 12:
        return f"Standard (grade {grade_int})"
    if grade_int <= 15:
        return f"Fairly hard (grade {grade_int})"
    return f"Difficult (grade {grade_int})"


def analyze(md: str) -> dict:
    """Analyze markdown content and return readability metrics.

    Returns a dict with words, sentences, syllables, reading_ease (Flesch),
    grade (Flesch-Kincaid), grade_label, and avg_sentence_len. Empty text
    yields all zeros with grade_label "n/a".
    """
    text = strip_markdown(md)
    words = _WORD.findall(text)
    n_words = len(words)
    n_sentences = _count_sentences(text)

    if n_words == 0 or n_sentences == 0:
        return {
            "words": 0,
            "sentences": 0,
            "syllables": 0,
            "reading_ease": 0.0,
            "grade": 0.0,
            "grade_label": "n/a",
            "avg_sentence_len": 0.0,
        }

    n_syllables = sum(count_syllables(w) for w in words)
    wps = n_words / n_sentences          # words per sentence
    spw = n_syllables / n_words          # syllables per word

    reading_ease = round(206.835 - 1.015 * wps - 84.6 * spw, 1)
    grade = round(0.39 * wps + 11.8 * spw - 15.59, 1)
    grade_int = int(round(grade))

    return {
        "words": n_words,
        "sentences": n_sentences,
        "syllables": n_syllables,
        "reading_ease": reading_ease,
        "grade": grade,
        "grade_label": _grade_label(grade_int),
        "avg_sentence_len": round(wps, 1),
    }


def within_target(md: str) -> bool:
    """True when the content is non-empty and its grade is within TARGET_GRADE_MAX."""
    m = analyze(md)
    if m["words"] == 0:
        return False
    return m["grade"] <= TARGET_GRADE_MAX
