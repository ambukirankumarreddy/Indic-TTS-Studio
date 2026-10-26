"""Document import for audiobooks: TXT, DOCX, PDF (incl. legacy KrutiDev/Chanakya Hindi via lipi)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List


@dataclass
class Chapter:
    title: str
    text: str


def read_document(path: str) -> dict:
    """Returns {'text': str, 'note': str}."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        for enc in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                with open(path, encoding=enc) as f:
                    return {"text": f.read(), "note": ""}
            except UnicodeError:
                continue
        raise ValueError("Could not read the text file. Please save it as UTF-8.")
    if ext == ".docx":
        import docx
        d = docx.Document(path)
        return {"text": "\n".join(p.text for p in d.paragraphs), "note": ""}
    if ext == ".pdf":
        return _read_pdf(path)
    raise ValueError(f"Unsupported file type: {ext}. Use .txt, .docx or .pdf")


def _read_pdf(path: str) -> dict:
    # lipi detects KrutiDev/Chanakya-encoded PDFs and converts them to Unicode
    try:
        from lipi.extractor import extract_unicode_text
        r = extract_unicode_text(path)
        text = _lipi_text(r)
        font = r.get("detected_font_type") or r.get("font_type") or ""
        note = ""
        if font and font not in ("unicode", "none", "auto"):
            note = (f"Detected legacy Hindi font ({font}) and converted it to Unicode. "
                    "Conversion is ~85-92% accurate - please proofread before generating.")
        if text.strip():
            return {"text": text, "note": note}
    except Exception:
        pass
    from pypdf import PdfReader
    reader = PdfReader(path)
    return {"text": "\n".join((p.extract_text() or "") for p in reader.pages), "note": ""}


def _lipi_text(r) -> str:
    if isinstance(r, str):
        return r
    for k in ("text", "cleaned_text", "unicode_text", "full_text"):
        if isinstance(r.get(k), str):
            return r[k]
    pages = r.get("pages")
    if isinstance(pages, list):
        return "\n".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in pages)
    return ""


_HEADING = re.compile(
    r"^\s*((chapter|part|section)\s+[\w\dIVXLC]+|अध्याय\s*[\w\d\u0966-\u096F]+|भाग\s*[\w\d\u0966-\u096F]+|"
    r"पाठ\s*[\w\d\u0966-\u096F]+)\b.*$", re.IGNORECASE)


def split_chapters(text: str, max_chars: int = 6000) -> List[Chapter]:
    """Split by detected chapter headings; otherwise into ~max_chars parts at paragraph breaks."""
    lines = text.splitlines()
    chapters: List[Chapter] = []
    title, buf = "Introduction", []
    found = False
    for line in lines:
        if _HEADING.match(line) and len(line.strip()) < 80:
            found = True
            if "".join(buf).strip():
                chapters.append(Chapter(title, "\n".join(buf).strip()))
            title, buf = line.strip(), []
        else:
            buf.append(line)
    if "".join(buf).strip():
        chapters.append(Chapter(title, "\n".join(buf).strip()))
    if found and len(chapters) > 1:
        return chapters

    # No headings: split into parts at paragraph boundaries
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()] or [text.strip()]
    parts, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > max_chars:
            parts.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}".strip()
    if cur:
        parts.append(cur)
    return [Chapter(f"Part {i + 1}", t) for i, t in enumerate(parts)]
