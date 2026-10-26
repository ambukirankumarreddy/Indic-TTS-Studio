"""OpenBMB VoxCPM2 engine (local GPU, multilingual TTS with optional voice cloning)."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

import numpy as np

from .base import Engine, SynthSettings, Voice, ProgressFn

MODEL_ID = "openbmb/VoxCPM2"
LICENSE = "Apache-2.0 (VoxCPM, OpenBMB)"


class VoxCPMEngine(Engine):
    id = "voxcpm"
    name = "VoxCPM2 (local GPU, cloning)"
    description = ("Expressive multilingual local TTS. Optional voice cloning from a short "
                   "reference clip. Needs a GPU for good speed; first use downloads the model.")
    license_summary = LICENSE
    supports_cloning = True
    native_speed = False
    native_pitch = False
    max_chunk_chars = 300

    def __init__(self):
        super().__init__()
        self.model = None
        self.sr = 48000

    def install_size_hint(self, voice=None) -> str:
        return "Several GB (downloaded from Hugging Face on first use)"

    def is_installed(self, voice=None) -> bool:
        try:
            import voxcpm  # noqa: F401
            from huggingface_hub import try_to_load_from_cache
            return isinstance(try_to_load_from_cache(MODEL_ID, "config.json"), str)
        except Exception:
            return False

    def is_loaded(self) -> bool:
        return self.model is not None

    def load(self, progress: ProgressFn = None) -> None:
        with self._lock:
            if self.model is not None:
                return
            from voxcpm import VoxCPM
            if progress:
                progress("Loading VoxCPM2 (first time downloads the model)...", -1)
            # Denoiser is optional and pulls an extra model; keep it off by default.
            self.model = VoxCPM.from_pretrained(MODEL_ID, load_denoiser=False)
            self.sr = int(getattr(self.model.tts_model, "sample_rate", 48000))

    def voices(self, language: Optional[str] = None) -> List[Voice]:
        return [
            Voice(id="default", name="Default voice", language="Multilingual",
                  engine_id=self.id, license=LICENSE, recommended=True, native=True,
                  notes="Model's built-in voice"),
            Voice(id="clone", name="Cloned voice (reference clip)", language="Multilingual",
                  engine_id=self.id, license=LICENSE, native=True,
                  notes="Pick a reference clip you have the right to use",
                  extra={"cloning": True}),
        ]

    def languages(self) -> List[str]:
        return ["Multilingual"]

    def synthesize(self, text: str, voice: Voice, settings: SynthSettings) -> Tuple[np.ndarray, int]:
        self.load()
        kwargs = {"text": text, "cfg_value": 2.0, "inference_timesteps": 10}
        if voice.extra.get("cloning"):
            ref = settings.reference_audio
            if not ref or not os.path.isfile(ref):
                raise RuntimeError("Select a reference audio clip to use the cloned voice.")
            kwargs["reference_wav_path"] = ref
            if settings.reference_text.strip():
                kwargs["prompt_wav_path"] = ref
                kwargs["prompt_text"] = settings.reference_text.strip()
        with self._lock:
            audio = self.model.generate(**kwargs)
        audio = np.asarray(audio, dtype=np.float32).squeeze()
        return audio, self.sr
