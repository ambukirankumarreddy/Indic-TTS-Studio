"""Text processing: number reading, pronunciation dictionary, chunking, dialogue scripts."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DICT_PATH = os.path.join(APP_DIR, "pronunciation_dictionary.json")

# ---------------------------------------------------------------------------
# Hindi number words (num2words has no Hindi support)
# ---------------------------------------------------------------------------
_HI_0_99 = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस "
    "पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस "
    "सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरेपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ "
    "इकसठ बासठ तिरेसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर "
    "पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी "
    "सत्तासी अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()
assert len(_HI_0_99) == 100

HINDI_LIKE = {"Hindi", "Chhattisgarhi", "Maithili", "Magahi", "Bhojpuri", "Dogri"}
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def hindi_number(n: int) -> str:
    if n < 0:
        return "ऋण " + hindi_number(-n)
    if n < 100:
        return _HI_0_99[n]
    parts = []
    for value, word in ((10 ** 9, "अरब"), (10 ** 7, "करोड़"), (10 ** 5, "लाख"), (1000, "हज़ार"), (100, "सौ")):
        if n >= value:
            q, n = divmod(n, value)
            parts.append(f"{hindi_number(q)} {word}")
    if n:
        parts.append(_HI_0_99[n])
    return " ".join(parts)


def _hindi_digits(s: str) -> str:
    return " ".join(_HI_0_99[int(c)] for c in s if c.isdigit())


def _english_number(n_str: str) -> str:
    from num2words import num2words
    try:
        return num2words(float(n_str) if "." in n_str else int(n_str), lang="en_IN")
    except Exception:
        return n_str


def normalize_numbers(text: str, language: str) -> str:
    """Spell out numbers, %, ₹ for Hindi-like languages and English. Others are left as-is."""
    text = text.translate(DEVANAGARI_DIGITS)
    is_hi = language in HINDI_LIKE
    is_en = language.startswith("English")
    if not (is_hi or is_en):
        return text

    def num_words(raw: str) -> str:
        raw = raw.replace(",", "")
        if is_en:
            return _english_number(raw)
        if "." in raw:
            whole, frac = raw.split(".", 1)
            return f"{hindi_number(int(whole or 0))} दशमलव {_hindi_digits(frac)}"
        if len(raw) > 1 and raw.startswith("0"):
            return _hindi_digits(raw)          # e.g. PIN / phone style
        if len(raw) > 12:
            return _hindi_digits(raw)
        return hindi_number(int(raw))

    num = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
    # ₹ 500 / Rs. 500
    text = re.sub(rf"(?:₹|Rs\.?|INR)\s*({num})",
                  lambda m: num_words(m.group(1)) + (" rupees" if is_en else " रुपये"), text)
    text = re.sub(rf"({num})\s*%",
                  lambda m: num_words(m.group(1)) + (" percent" if is_en else " प्रतिशत"), text)
    text = re.sub(num, lambda m: num_words(m.group(0)), text)
    return text


# ---------------------------------------------------------------------------
# Pronunciation dictionary
# ---------------------------------------------------------------------------
@dataclass
class DictEntry:
    word: str
    say_as: str
    language: str = "All"
    case_sensitive: bool = False


def load_dictionary() -> List[DictEntry]:
    if not os.path.isfile(DICT_PATH):
        defaults = [DictEntry("AI", "ए आई", "Hindi", True), DictEntry("TTS", "टी टी एस", "Hindi", True),
                    DictEntry("Dr.", "डॉक्टर", "Hindi", True)]
        save_dictionary(defaults)
        return defaults
    try:
        with open(DICT_PATH, encoding="utf-8") as f:
            return [DictEntry(**d) for d in json.load(f)]
    except Exception:
        return []


def save_dictionary(entries: List[DictEntry]) -> None:
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump([e.__dict__ for e in entries], f, ensure_ascii=False, indent=2)


def apply_dictionary(text: str, language: str, entries: Optional[List[DictEntry]] = None) -> str:
    entries = load_dictionary() if entries is None else entries
    # Longest words first so "Dr. Sharma" beats "Dr"
    for e in sorted(entries, key=lambda e: -len(e.word)):
        if not e.word or (e.language not in ("All", language)):
            continue
        flags = 0 if e.case_sensitive else re.IGNORECASE
        # word boundaries that also work for Devanagari (\w covers it in Python 3)
        pattern = rf"(?<!\w){re.escape(e.word)}(?!\w)"
        text = re.sub(pattern, e.say_as, text, flags=flags)
    return text


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
SENTENCE_END = ".?!\u0964\u0965"


def split_text_into_chunks(text: str, max_chars: int = 200) -> List[str]:
    """Split on sentence boundaries (incl. Devanagari danda) into chunks <= max_chars."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[\.\?\!\u0964\u0965])\s+", text) if s.strip()]
    chunks: List[str] = []
    current = ""
    for sent in sentences:
        while len(sent) > max_chars:
            cut = sent.rfind(",", 0, max_chars)
            if cut < max_chars // 3:
                cut = sent.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            head, sent = sent[:cut + 1].strip(), sent[cut + 1:].strip()
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if not sent:
            continue
        if current and len(current) + 1 + len(sent) > max_chars:
            chunks.append(current)
            current = sent
        else:
            current = f"{current} {sent}".strip()
    if current:
        chunks.append(current)
    return chunks


def ends_sentence(chunk: str) -> bool:
    return chunk.rstrip()[-1:] in SENTENCE_END + "\"\u201d'"


def prepare_text(text: str, language: str, use_dictionary: bool = True, read_numbers: bool = True) -> str:
    if use_dictionary:
        text = apply_dictionary(text, language)
    if read_numbers:
        text = normalize_numbers(text, language)
    return text


# ---------------------------------------------------------------------------
# Dialogue scripts:  "[Rohit] text"  or  "[speaker:1] text"  or  "Rohit: text"
# ---------------------------------------------------------------------------
_TAG = re.compile(r"^\s*\[(?:speaker\s*:\s*)?([^\]]+)\]\s*(.*)$", re.IGNORECASE)
_COLON = re.compile(r"^\s*([A-Za-z\u0900-\u097F][\w\u0900-\u097F ]{0,24})\s*:\s+(.+)$")


def parse_dialogue(script: str) -> List[Tuple[str, str]]:
    """Return [(speaker, line_text)]. Lines without a tag continue the previous speaker."""
    out: List[Tuple[str, str]] = []
    speaker = "Narrator"
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _TAG.match(line) or _COLON.match(line)
        if m:
            speaker = m.group(1).strip()
            line = m.group(2).strip()
            if not line:
                continue
        if out and out[-1][0] == speaker and not m:
            out[-1] = (speaker, out[-1][1] + " " + line)
        else:
            out.append((speaker, line))
    return out


def dialogue_speakers(script: str) -> List[str]:
    seen: Dict[str, None] = {}
    for spk, _ in parse_dialogue(script):
        seen.setdefault(spk, None)
    return list(seen)
