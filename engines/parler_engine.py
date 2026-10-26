"""AI4Bharat Indic Parler-TTS engine (expressive, caption-controlled, GPU)."""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from config import LANGUAGES_DATA, MODEL_ID, EXPRESSIVITY_OPTIONS, AUDIO_QUALITY_OPTIONS
from .base import Engine, SynthSettings, Voice, ProgressFn

EMOTION_WORDS = {
    "Happy": "happy", "Sad": "sad", "Anger": "angry", "Narration": "narrative",
    "Conversation": "conversational", "Surprise": "surprised", "Command": "commanding",
    "Disgust": "disgusted", "Fear": "fearful", "News": "news-reading",
}


def _speed_phrase(speed: float) -> str:
    if speed <= 0.7:
        return "very slowly"
    if speed <= 0.85:
        return "slowly"
    if speed <= 0.95:
        return "at a slightly slow pace"
    if speed < 1.08:
        return "at a moderate pace"
    if speed < 1.25:
        return "at a slightly fast pace"
    if speed < 1.5:
        return "fast"
    return "very fast"


def _pitch_phrase(semitones: float) -> str:
    if semitones <= -4:
        return "a very low pitch"
    if semitones <= -1.5:
        return "a slightly low pitch"
    if semitones < 1.5:
        return "a moderate pitch"
    if semitones < 4:
        return "a slightly high pitch"
    return "a high pitch"


def build_caption(speaker: Optional[str], s: SynthSettings) -> str:
    """Caption in the style of the model card examples."""
    subject = speaker or "A speaker"
    first = f"{subject} speaks {_speed_phrase(s.speed)} with {_pitch_phrase(s.pitch)}."
    expr = dict(EXPRESSIVITY_OPTIONS).get(s.expressivity, "slightly expressive")
    emo = EMOTION_WORDS.get(s.emotion or "Neutral")
    second = f"The delivery is {expr}, with a {emo} tone." if emo else f"The delivery is {expr}."
    quality = dict(AUDIO_QUALITY_OPTIONS).get(
        s.quality, "The recording is very clear audio, close-sounding, with no background noise.")
    return f"{first} {second} {quality}"


class ParlerEngine(Engine):
    id = "parler"
    name = "Indic Parler-TTS"
    description = "Most expressive. Emotions, 69 named speakers, 18 languages. Needs GPU; slower."
    license_summary = "Apache-2.0"
    supports_emotion = True
    native_speed = True     # via caption
    native_pitch = True     # via caption
    max_chunk_chars = 200

    def __init__(self):
        super().__init__()
        self.model = None
        self.tokenizer = None
        self.desc_tokenizer = None
        self.sr = 44100
        self.device = "cpu"
        self.use_fp16 = False

    def install_size_hint(self, voice=None) -> str:
        return "~3.8 GB (Hugging Face login + access approval required)"

    def is_installed(self, voice=None) -> bool:
        try:
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
            import torch
            from transformers import AutoTokenizer
            from parler_tts import ParlerTTSForConditionalGeneration

            self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if (self.use_fp16 and self.device != "cpu") else torch.float32
            if progress:
                progress("Loading Indic Parler-TTS (first time downloads ~3.8 GB)...", -1)
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
                model = ParlerTTSForConditionalGeneration.from_pretrained(
                    MODEL_ID, torch_dtype=dtype, low_cpu_mem_usage=True).to(self.device)
            except Exception as e:
                msg = str(e)
                if "gated" in msg.lower() or "401" in msg:
                    raise RuntimeError(
                        "Indic Parler-TTS is gated on Hugging Face. Accept the terms at "
                        "https://huggingface.co/ai4bharat/indic-parler-tts and run "
                        "login_huggingface.bat, then try again.") from e
                raise
            model.eval()
            self.desc_tokenizer = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
            self.sr = int(getattr(model.config, "sampling_rate", 44100))
            self.model = model

    def voices(self, language: Optional[str] = None) -> List[Voice]:
        out = []
        for lang, info in LANGUAGES_DATA.items():
            if language and lang != language:
                continue
            rec = set(info.get("recommended", []))
            out.append(Voice(id=f"{lang}|", name="Random voice", language=lang,
                             engine_id=self.id, license=self.license_summary,
                             notes="Voice varies per generation"))
            for spk in info["speakers"]:
                out.append(Voice(id=f"{lang}|{spk}", name=spk, language=lang, engine_id=self.id,
                                 license=self.license_summary, recommended=spk in rec,
                                 extra={"speaker": spk}))
        return out

    def synthesize(self, text: str, voice: Voice, settings: SynthSettings) -> Tuple[np.ndarray, int]:
        self.load()
        import torch
        speaker = voice.extra.get("speaker") or None
        caption = settings.caption.strip() or build_caption(speaker, settings)
        with self._lock:
            d = self.desc_tokenizer(caption, return_tensors="pt").to(self.device)
            p = self.tokenizer(text, return_tensors="pt").to(self.device)
            if settings.seed is not None:
                torch.manual_seed(settings.seed)
            with torch.inference_mode():
                gen = self.model.generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                                          prompt_input_ids=p.input_ids,
                                          prompt_attention_mask=p.attention_mask)
            audio = gen.float().cpu().numpy().squeeze().astype(np.float32)
        return audio, self.sr
