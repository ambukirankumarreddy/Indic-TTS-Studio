"""Core synthesis service shared by all studio features."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

import audio_utils as au
import text_pipeline as tp
from engines import Engine, SynthSettings, Voice, get_engine

APP_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(APP_DIR, "generated_audio")
HISTORY_FILE = os.path.join(OUTPUT_DIR, "history.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)

Progress = Optional[Callable[[str, float], None]]


class Cancelled(Exception):
    pass


@dataclass
class Job:
    """Cancellation token passed through long operations."""
    cancel_event: threading.Event

    @staticmethod
    def new() -> "Job":
        return Job(threading.Event())

    def check(self):
        if self.cancel_event.is_set():
            raise Cancelled()


def _engine_for(voice: Voice) -> Engine:
    e = get_engine(voice.engine_id)
    if e is None:
        raise RuntimeError(f"Unknown engine: {voice.engine_id}")
    return e


def synthesize_text(voice: Voice, text: str, settings: SynthSettings, language: Optional[str] = None,
                    progress: Progress = None, job: Optional[Job] = None,
                    use_dictionary: bool = True, read_numbers: bool = True,
                    sentence_pause: float = 0.45, comma_pause: float = 0.18) -> Tuple[np.ndarray, int]:
    """Text of any length -> one audio array. Handles chunking, speed/pitch, joins."""
    engine = _engine_for(voice)
    language = language or voice.language
    text = tp.prepare_text(text, language, use_dictionary, read_numbers)
    chunks = tp.split_text_into_chunks(text, engine.max_chunk_chars)
    if not chunks:
        raise ValueError("There is no text to speak.")

    if not engine.is_installed(voice):
        if progress:
            progress(f"Downloading {engine.name} voice ({engine.install_size_hint(voice)})...", -1)
        engine.install(voice, progress)

    if settings.seed is None:
        settings = SynthSettings(**{**settings.__dict__, "seed": int(time.time()) % (2 ** 31)})

    pieces: List[np.ndarray] = []
    sr_out: Optional[int] = None
    for i, chunk in enumerate(chunks):
        if job:
            job.check()
        if progress:
            progress(f"{engine.name}: part {i + 1} of {len(chunks)}", i / len(chunks))
        audio, sr = engine.synthesize(chunk, voice, settings)
        if sr_out is None:
            sr_out = sr
        audio = au.resample(audio, sr, sr_out)
        if not engine.native_speed:
            audio = au.change_speed(audio, sr_out, settings.speed)
        if not engine.native_pitch:
            audio = au.change_pitch(audio, sr_out, settings.pitch)
        audio = au.trim_and_fade(audio, sr_out)
        pieces.append(audio)
        if i < len(chunks) - 1:
            pieces.append(au.silence(sr_out, sentence_pause if tp.ends_sentence(chunk) else comma_pause))
    if progress:
        progress("Finishing...", 1.0)
    return np.concatenate(pieces).astype(np.float32), int(sr_out)


# ---------------------------------------------------------------------------
# Dialogue
# ---------------------------------------------------------------------------
def synthesize_dialogue(lines: List[Tuple[str, str]], voice_map: Dict[str, Voice],
                        settings_map: Dict[str, SynthSettings], gap: float = 0.5,
                        progress: Progress = None, job: Optional[Job] = None,
                        sr_out: int = 24000) -> Tuple[np.ndarray, int]:
    pieces: List[np.ndarray] = []
    for i, (speaker, text) in enumerate(lines):
        if job:
            job.check()
        voice = voice_map[speaker]
        if progress:
            progress(f"Line {i + 1}/{len(lines)} · {speaker} ({voice.name})", i / len(lines))
        a, sr = synthesize_text(voice, text, settings_map.get(speaker, SynthSettings()), job=job)
        a = au.match_loudness(au.resample(a, sr, sr_out))
        pieces.append(a)
        if i < len(lines) - 1:
            pieces.append(au.silence(sr_out, gap))
    return np.concatenate(pieces), sr_out


# ---------------------------------------------------------------------------
# Library / history
# ---------------------------------------------------------------------------
def output_path(prefix: str, ext: str = "wav", folder: Optional[str] = None) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in prefix)[:40] or "audio"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(folder or OUTPUT_DIR, f"{safe}_{stamp}.{ext}")


def save_result(audio: np.ndarray, sr: int, prefix: str, text: str, voice_desc: str,
                kind: str = "Studio", ext: str = "wav", gen_time: float = 0.0,
                extra: Optional[dict] = None, path: Optional[str] = None) -> dict:
    path = au.save_audio(audio, sr, path or output_path(prefix, ext))
    item = {
        "wav_path": path, "filename": os.path.basename(path), "kind": kind,
        "text": text[:500], "voice": voice_desc, "sampling_rate": sr,
        "audio_duration": len(audio) / float(sr), "generation_time": gen_time,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    if extra:
        item.update(extra)
    history = get_history()
    history.insert(0, item)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[:500], f, ensure_ascii=False, indent=2)
    return item


def get_history() -> List[dict]:
    if not os.path.isfile(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def delete_history_item(path: str, delete_file: bool = True) -> None:
    history = [h for h in get_history() if h.get("wav_path") != path]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    if delete_file and os.path.isfile(path):
        os.remove(path)
