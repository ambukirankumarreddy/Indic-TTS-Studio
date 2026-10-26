"""Common engine interface, voice/settings types and model download helpers."""

from __future__ import annotations

import os
import tarfile
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(APP_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Keep every Hugging Face model inside the app folder so the software is self-contained.
os.environ.setdefault("HF_HOME", os.path.join(MODELS_DIR, "hf"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
# Offline mode: set env OFFLINE=1 or create an empty file models/.offline
if os.environ.get("OFFLINE") == "1" or os.path.isfile(os.path.join(MODELS_DIR, ".offline")):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def is_offline() -> bool:
    return os.environ.get("HF_HUB_OFFLINE") == "1"

ProgressFn = Optional[Callable[[str, float], None]]  # (message, fraction 0..1 or -1 if unknown)


@dataclass
class Voice:
    id: str                      # unique within engine
    name: str                    # display name
    language: str                # display language, e.g. "Hindi"
    engine_id: str
    gender: str = ""             # "Male" / "Female" / ""
    license: str = ""            # short license label shown as a badge
    recommended: bool = False
    native: bool = True          # False for e.g. multilingual Edge voices reading Hindi
    notes: str = ""
    extra: Dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.engine_id}:{self.id}"

    @property
    def label(self) -> str:
        parts = [("★ " if self.recommended else "") + self.name]
        if self.gender:
            parts.append(self.gender)
        if not self.native:
            parts.append("non-native")
        return " · ".join(parts)


@dataclass
class SynthSettings:
    speed: float = 1.0           # 0.5 .. 2.0
    pitch: float = 0.0           # semitones, -6 .. +6
    emotion: str = "Neutral"     # Parler only
    expressivity: str = "Slightly Expressive"   # Parler only
    quality: str = "Very High Quality (Studio)" # Parler only
    caption: str = ""            # Parler: manual caption override
    seed: Optional[int] = None
    reference_audio: str = ""    # path to reference clip (cloning engines only)
    reference_text: str = ""     # transcript of the reference clip (optional)
    language_code: str = ""      # engine-specific language hint (e.g. "hi", "en")


class Engine:
    """Base class. Subclasses implement the abstract methods."""

    id: str = "base"
    name: str = "Base"
    description: str = ""
    online: bool = False
    license_summary: str = ""
    supports_emotion: bool = False
    native_speed: bool = False    # engine applies speed itself
    native_pitch: bool = False    # engine applies pitch itself
    supports_cloning: bool = False  # accepts a reference clip (SynthSettings.reference_audio)
    max_chunk_chars: int = 400

    def __init__(self):
        self._lock = threading.RLock()

    # --- lifecycle -------------------------------------------------------
    def is_installed(self, voice: Optional[Voice] = None) -> bool:
        return True

    def install(self, voice: Optional[Voice] = None, progress: ProgressFn = None) -> None:
        pass

    def is_loaded(self) -> bool:
        return True

    def load(self, progress: ProgressFn = None) -> None:
        pass

    def install_size_hint(self, voice: Optional[Voice] = None) -> str:
        return ""

    # --- catalogue -------------------------------------------------------
    def languages(self) -> List[str]:
        return sorted({v.language for v in self.voices()})

    def voices(self, language: Optional[str] = None) -> List[Voice]:
        raise NotImplementedError

    def get_voice(self, voice_id: str) -> Optional[Voice]:
        for v in self.voices():
            if v.id == voice_id:
                return v
        return None

    # --- synthesis -------------------------------------------------------
    def synthesize(self, text: str, voice: Voice, settings: SynthSettings) -> Tuple[np.ndarray, int]:
        """Return mono float32 audio in [-1, 1] and its sample rate."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def download_file(url: str, dest: str, progress: ProgressFn = None, label: str = "") -> str:
    import requests

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if progress:
                    frac = done / total if total else -1
                    progress(f"Downloading {label or os.path.basename(dest)}: "
                             f"{done / 1e6:.0f}/{total / 1e6:.0f} MB", frac)
    os.replace(tmp, dest)
    return dest


def download_and_extract_tar(url: str, target_dir: str, progress: ProgressFn = None, label: str = "") -> None:
    """Download a .tar.bz2 archive into MODELS_DIR and extract it."""
    archive = os.path.join(MODELS_DIR, os.path.basename(url))
    download_file(url, archive, progress, label)
    if progress:
        progress(f"Extracting {label}...", -1)
    with tarfile.open(archive, "r:bz2") as tar:
        # Guard against path traversal in archives
        base = os.path.abspath(MODELS_DIR)
        for m in tar.getmembers():
            p = os.path.abspath(os.path.join(MODELS_DIR, m.name))
            if not p.startswith(base):
                raise RuntimeError(f"Unsafe path in archive: {m.name}")
        tar.extractall(MODELS_DIR)
    os.remove(archive)
    if not os.path.isdir(target_dir):
        raise RuntimeError(f"Archive did not contain expected folder: {target_dir}")
