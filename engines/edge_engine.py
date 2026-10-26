"""Microsoft Edge neural voices via edge-tts (online, no API key)."""

from __future__ import annotations

import asyncio
import io
import json
import os
import time
from typing import List, Optional, Tuple

import numpy as np

from .base import Engine, SynthSettings, Voice, ProgressFn, MODELS_DIR

CACHE = os.path.join(MODELS_DIR, "edge_voices.json")
LOCALE_LANG = {
    "hi-IN": "Hindi", "bn-IN": "Bengali", "en-IN": "English (Indian)", "gu-IN": "Gujarati",
    "kn-IN": "Kannada", "ml-IN": "Malayalam", "mr-IN": "Marathi", "ta-IN": "Tamil",
    "te-IN": "Telugu", "ur-IN": "Urdu",
}
ANY = "Any language"
LICENSE = "Microsoft service terms (online; review before commercial use)"


class EdgeEngine(Engine):
    id = "edge"
    name = "Edge Neural (online)"
    description = "Very natural Microsoft voices for 10 Indian languages. Needs internet; no account."
    online = True
    license_summary = LICENSE
    native_speed = True
    native_pitch = True
    max_chunk_chars = 1500

    def __init__(self):
        super().__init__()
        self._voices: Optional[List[Voice]] = None

    def is_installed(self, voice=None) -> bool:
        return True

    def install_size_hint(self, voice=None) -> str:
        return "No download (online)"

    def _fetch_list(self) -> list:
        import edge_tts
        if os.path.isfile(CACHE) and time.time() - os.path.getmtime(CACHE) < 7 * 86400:
            with open(CACHE, encoding="utf-8") as f:
                return json.load(f)
        try:
            data = asyncio.run(edge_tts.list_voices())
            with open(CACHE, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return data
        except Exception:
            if os.path.isfile(CACHE):
                with open(CACHE, encoding="utf-8") as f:
                    return json.load(f)
            # Offline and no cache: fall back to the two native Hindi voices
            return [{"ShortName": "hi-IN-SwaraNeural", "Locale": "hi-IN", "Gender": "Female"},
                    {"ShortName": "hi-IN-MadhurNeural", "Locale": "hi-IN", "Gender": "Male"}]

    def voices(self, language: Optional[str] = None) -> List[Voice]:
        if self._voices is None:
            vs = []
            for v in self._fetch_list():
                sn, loc = v["ShortName"], v["Locale"]
                short = sn.split("-")[-1].replace("Neural", "")
                if loc in LOCALE_LANG:
                    vs.append(Voice(id=sn, name=short, language=LOCALE_LANG[loc], engine_id=self.id,
                                    gender=v.get("Gender", ""), license=LICENSE,
                                    recommended=sn in ("hi-IN-SwaraNeural", "hi-IN-MadhurNeural")))
                elif "Multilingual" in sn:
                    vs.append(Voice(id=sn, name=short.replace("Multilingual", "") + f" ({loc})",
                                    language=ANY, engine_id=self.id, gender=v.get("Gender", ""),
                                    license=LICENSE, native=False,
                                    notes="Multilingual voice: reads other languages with its own accent"))
            self._voices = vs
        if not language:
            return list(self._voices)
        return [v for v in self._voices if v.language == language or v.language == ANY]

    def languages(self) -> List[str]:
        return sorted({v.language for v in self.voices() if v.language != ANY})

    def synthesize(self, text: str, voice: Voice, settings: SynthSettings) -> Tuple[np.ndarray, int]:
        import edge_tts
        import soundfile as sf

        rate = f"{int(round((settings.speed - 1.0) * 100)):+d}%"
        pitch = f"{int(round(settings.pitch * 10)):+d}Hz"   # ~10 Hz per semitone for speech

        async def _run() -> bytes:
            buf = bytearray()
            comm = edge_tts.Communicate(text, voice.id, rate=rate, pitch=pitch)
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    buf.extend(ch["data"])
            return bytes(buf)

        last = None
        for attempt in range(3):
            try:
                data = asyncio.run(_run())
                if not data:
                    raise RuntimeError("Edge returned no audio. If the text is Hindi, pick a Hindi or "
                                       "multilingual voice; English-only voices produce silence.")
                a, sr = sf.read(io.BytesIO(data), dtype="float32")
                if a.ndim > 1:
                    a = a.mean(axis=1)
                return a.astype(np.float32), int(sr)
            except Exception as e:
                last = e
                time.sleep(1.0 + attempt)
        raise RuntimeError(f"Edge TTS failed (check your internet connection): {last}")
