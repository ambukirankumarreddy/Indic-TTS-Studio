"""Piper and Kokoro voices, both run through sherpa-onnx (Apache-2.0)."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from .base import Engine, SynthSettings, Voice, ProgressFn, MODELS_DIR, download_and_extract_tar

SHERPA_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/"

# ---------------------------------------------------------------------------
# Piper (fast VITS voices) - voices from rhasspy/piper-voices, packaged by sherpa-onnx
# ---------------------------------------------------------------------------
PIPER_VOICES = [
    # id, display name, language, gender, archive folder, license label
    ("hi_rohan", "Rohan", "Hindi", "Male", "vits-piper-hi_IN-rohan-medium",
     "IIT Madras IndicTTS licence (check before commercial use)"),
    ("hi_pratham", "Pratham", "Hindi", "Male", "vits-piper-hi_IN-pratham-medium",
     "CC BY-NC-SA 4.0 (non-commercial)"),
    ("hi_priyamvada", "Priyamvada", "Hindi", "Female", "vits-piper-hi_IN-priyamvada-medium",
     "CC BY-NC-SA 4.0 (non-commercial)"),
]


class PiperEngine(Engine):
    id = "piper"
    name = "Piper"
    description = "Very fast, fully offline Hindi voices. Runs on CPU in about a second."
    license_summary = "Varies per voice"
    native_speed = True
    max_chunk_chars = 400

    def __init__(self):
        super().__init__()
        self._tts: Dict[str, object] = {}

    def _dir(self, voice: Voice) -> str:
        return os.path.join(MODELS_DIR, voice.extra["folder"])

    def voices(self, language: Optional[str] = None) -> List[Voice]:
        out = []
        for vid, name, lang, gender, folder, lic in PIPER_VOICES:
            if language and lang != language:
                continue
            out.append(Voice(id=vid, name=name, language=lang, engine_id=self.id, gender=gender,
                             license=lic, recommended=(vid == "hi_rohan"),
                             extra={"folder": folder}))
        return out

    def install_size_hint(self, voice=None) -> str:
        return "~64 MB per voice"

    def is_installed(self, voice: Optional[Voice] = None) -> bool:
        if voice is None:
            return any(self.is_installed(v) for v in self.voices())
        d = self._dir(voice)
        return os.path.isdir(d) and any(f.endswith(".onnx") for f in os.listdir(d))

    def install(self, voice: Optional[Voice] = None, progress: ProgressFn = None) -> None:
        targets = [voice] if voice else self.voices()
        for v in targets:
            if not self.is_installed(v):
                folder = v.extra["folder"]
                download_and_extract_tar(SHERPA_URL + folder + ".tar.bz2", self._dir(v), progress, v.name)

    def _get(self, voice: Voice):
        import sherpa_onnx
        with self._lock:
            if voice.id not in self._tts:
                if not self.is_installed(voice):
                    self.install(voice)
                d = self._dir(voice)
                onnx = [f for f in os.listdir(d) if f.endswith(".onnx")][0]
                cfg = sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=os.path.join(d, onnx), tokens=os.path.join(d, "tokens.txt"),
                        data_dir=os.path.join(d, "espeak-ng-data")),
                    num_threads=4, provider="cpu"))
                self._tts[voice.id] = sherpa_onnx.OfflineTts(cfg)
            return self._tts[voice.id]

    def synthesize(self, text: str, voice: Voice, settings: SynthSettings) -> Tuple[np.ndarray, int]:
        tts = self._get(voice)
        a = tts.generate(text, sid=0, speed=float(settings.speed))
        return np.asarray(a.samples, dtype=np.float32), int(a.sample_rate)


# ---------------------------------------------------------------------------
# Kokoro-82M (v1.0 multi-lang, int8) - the engine VoxSherpa uses
# ---------------------------------------------------------------------------
KOKORO_FOLDER = "kokoro-int8-multi-lang-v1_0"
# Speaker ids read from the model's own metadata (speaker_names)
KOKORO_VOICES = [
    # sid, voice code, display name, language, gender, espeak lang
    (31, "hf_alpha", "Alpha", "Hindi", "Female", "hi"),
    (32, "hf_beta", "Beta", "Hindi", "Female", "hi"),
    (33, "hm_omega", "Omega", "Hindi", "Male", "hi"),
    (34, "hm_psi", "Psi", "Hindi", "Male", "hi"),
    (3, "af_heart", "Heart (US)", "English", "Female", "en-us"),
    (2, "af_bella", "Bella (US)", "English", "Female", "en-us"),
    (16, "am_michael", "Michael (US)", "English", "Male", "en-us"),
    (14, "am_fenrir", "Fenrir (US)", "English", "Male", "en-us"),
    (21, "bf_emma", "Emma (UK)", "English", "Female", "en-gb"),
    (26, "bm_george", "George (UK)", "English", "Male", "en-gb"),
]


class KokoroEngine(Engine):
    id = "kokoro"
    name = "Kokoro-82M"
    description = "High-quality small model. 4 Hindi voices + US/UK English voices. Offline, CPU."
    license_summary = "Apache-2.0"
    native_speed = True
    max_chunk_chars = 350

    def __init__(self):
        super().__init__()
        self._tts: Dict[str, object] = {}   # one instance per espeak language

    @property
    def _dir(self) -> str:
        return os.path.join(MODELS_DIR, KOKORO_FOLDER)

    def voices(self, language: Optional[str] = None) -> List[Voice]:
        out = []
        for sid, code, name, lang, gender, el in KOKORO_VOICES:
            if language and lang != language:
                continue
            out.append(Voice(id=code, name=name, language=lang, engine_id=self.id, gender=gender,
                             license=self.license_summary, recommended=code in ("hf_alpha", "hm_omega", "af_heart"),
                             extra={"sid": sid, "lang": el}))
        return out

    def install_size_hint(self, voice=None) -> str:
        return "~126 MB (all voices)"

    def is_installed(self, voice=None) -> bool:
        return os.path.isfile(os.path.join(self._dir, "model.int8.onnx"))

    def install(self, voice=None, progress: ProgressFn = None) -> None:
        if not self.is_installed():
            download_and_extract_tar(SHERPA_URL + KOKORO_FOLDER + ".tar.bz2", self._dir, progress, "Kokoro")

    def _get(self, lang: str):
        import sherpa_onnx
        with self._lock:
            if lang not in self._tts:
                if not self.is_installed():
                    self.install()
                d = self._dir
                lex = ",".join(os.path.join(d, f) for f in sorted(os.listdir(d))
                               if f.startswith("lexicon") and f.endswith(".txt"))
                k = sherpa_onnx.OfflineTtsKokoroModelConfig(
                    model=os.path.join(d, "model.int8.onnx"), voices=os.path.join(d, "voices.bin"),
                    tokens=os.path.join(d, "tokens.txt"), data_dir=os.path.join(d, "espeak-ng-data"),
                    lexicon=lex)
                k.lang = lang
                self._tts[lang] = sherpa_onnx.OfflineTts(sherpa_onnx.OfflineTtsConfig(
                    model=sherpa_onnx.OfflineTtsModelConfig(kokoro=k, num_threads=4, provider="cpu")))
            return self._tts[lang]

    def synthesize(self, text: str, voice: Voice, settings: SynthSettings) -> Tuple[np.ndarray, int]:
        tts = self._get(voice.extra["lang"])
        a = tts.generate(text, sid=int(voice.extra["sid"]), speed=float(settings.speed))
        return np.asarray(a.samples, dtype=np.float32), int(a.sample_rate)
