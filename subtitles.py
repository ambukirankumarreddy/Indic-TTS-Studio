"""SRT subtitles -> one timed voiceover track, with optional ducked background music.

Timing approach adapted from srt-voiceover-studio (MIT, github.com/khan57/srt-voiceover-studio):
every line is placed on a silent canvas at its exact timestamp (so lines can't drift),
and lines that overrun their slot are time-compressed (pitch preserved) up to a cap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

import audio_utils as au
from engines import SynthSettings, Voice
from studio_service import Job, synthesize_text


@dataclass
class Cue:
    index: int
    start: float   # seconds
    end: float
    text: str


_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


def _t(s: str) -> float:
    m = _TIME.search(s)
    if not m:
        raise ValueError(f"Bad timestamp: {s}")
    h, mi, se, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000


def read_srt(path: str) -> List[Cue]:
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            t = raw.decode(enc)
            if "\ufffd" not in t:
                text = t
                break
        except UnicodeError:
            continue
    if text is None:
        raise ValueError("Could not read the subtitle file. Please re-save it as UTF-8.")
    return parse_srt(text)


def parse_srt(text: str) -> List[Cue]:
    cues: List[Cue] = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        a, b = lines[ti].split("-->")
        body = " ".join(lines[ti + 1:])
        body = re.sub(r"<[^>]+>|\{[^}]+\}", "", body).strip()   # strip formatting tags
        if not body:
            continue
        start, end = _t(a), _t(b)
        if end <= start:
            continue
        cues.append(Cue(len(cues) + 1, start, end, body))
    cues.sort(key=lambda c: c.start)
    if not cues:
        raise ValueError("No subtitle lines found in this file.")
    return cues


def render_voiceover(cues: List[Cue], voice: Voice, settings: SynthSettings,
                     max_compress: float = 1.5, music: Optional[np.ndarray] = None,
                     music_sr: int = 0, music_db: float = -18.0, duck_db: float = -12.0,
                     fade_ms: float = 300.0, progress: Optional[Callable[[str, float], None]] = None,
                     job: Optional[Job] = None, sr: int = 24000) -> Tuple[np.ndarray, int, dict]:
    clips: List[Tuple[float, np.ndarray]] = []
    stats = {"voiced": 0, "compressed": 0, "overrun": 0, "failed": 0, "max_factor": 1.0}
    for i, cue in enumerate(cues):
        if job:
            job.check()
        if progress:
            progress(f"Line {i + 1}/{len(cues)}: {cue.text[:40]}", i / len(cues))
        try:
            a, a_sr = synthesize_text(voice, cue.text, settings, job=job)
        except Exception:
            stats["failed"] += 1        # a failed line stays silent instead of aborting
            continue
        a = au.match_loudness(au.resample(a, a_sr, sr))
        nxt = cues[i + 1].start if i + 1 < len(cues) else cue.end + 2.0
        slot = max(0.3, nxt - cue.start)
        dur = a.size / sr
        if dur > slot:
            factor = min(dur / slot, max_compress)
            a = au.change_speed(a, sr, factor)
            stats["compressed"] += 1
            stats["max_factor"] = max(stats["max_factor"], factor)
            if a.size / sr > slot + 0.05:
                stats["overrun"] += 1
        clips.append((cue.start, a))
        stats["voiced"] += 1

    if not clips:
        raise RuntimeError("Every line failed to synthesise. Check the voice/engine and try again.")
    total = max(int(round(s * sr)) + c.size for s, c in clips)
    total = max(total, int(cues[-1].end * sr))
    canvas = np.zeros(total + int(0.5 * sr), dtype=np.float32)
    for start, c in clips:
        o = int(round(start * sr))
        canvas[o:o + c.size] += c

    if music is not None and music.size:
        if progress:
            progress("Mixing background music with ducking...", 0.98)
        m = au.resample(music, music_sr, sr)
        canvas = au.mix_with_music(canvas, m, sr, music_db=music_db, duck_db=duck_db, fade_ms=fade_ms)
    else:
        canvas = au.normalize_peak(canvas, -1.0) if np.max(np.abs(canvas)) > 0.89 else canvas
    return canvas, sr, stats
