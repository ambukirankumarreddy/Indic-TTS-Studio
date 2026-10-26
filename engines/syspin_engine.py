"""SYSPIN (IISc Bangalore) VITS voices - the models used by tts-multilingual-project / VoiceAPI."""

from __future__ import annotations

import importlib.util
import os
from collections import OrderedDict
from typing import List, Optional, Tuple

import numpy as np

from .base import Engine, SynthSettings, Voice, ProgressFn, MODELS_DIR

# key, language, gender, HF repo, model file
# (Bhojpuri and Gujarati are full Coqui checkpoints that need the Coqui TTS package - not included)
SYSPIN_VOICES = [
    ("hi_female", "Hindi", "Female", "SYSPIN/tts_vits_coquiai_HindiFemale", "hi_female_vits_30hrs.pt"),
    ("hi_male", "Hindi", "Male", "SYSPIN/tts_vits_coquiai_HindiMale", "hi_male_vits_30hrs.pt"),
    ("bn_female", "Bengali", "Female", "SYSPIN/tts_vits_coquiai_BengaliFemale", "bn_female_vits_30hrs.pt"),
    ("bn_male", "Bengali", "Male", "SYSPIN/tts_vits_coquiai_BengaliMale", "bn_male_vits_30hrs.pt"),
    ("mr_female", "Marathi", "Female", "SYSPIN/tts_vits_coquiai_MarathiFemale", "mr_female_vits_30hrs.pt"),
    ("mr_male", "Marathi", "Male", "SYSPIN/tts_vits_coquiai_MarathiMale", "mr_male_vits_30hrs.pt"),
    ("te_female", "Telugu", "Female", "SYSPIN/tts_vits_coquiai_TeluguFemale", "te_female_vits_30hrs.pt"),
    ("te_male", "Telugu", "Male", "SYSPIN/tts_vits_coquiai_TeluguMale", "te_male_vits_30hrs.pt"),
    ("kn_female", "Kannada", "Female", "SYSPIN/tts_vits_coquiai_KannadaFemale", "kn_female_vits_30hrs.pt"),
    ("kn_male", "Kannada", "Male", "SYSPIN/tts_vits_coquiai_KannadaMale", "kn_male_vits_30hrs.pt"),
    ("hne_female", "Chhattisgarhi", "Female", "SYSPIN/tts_vits_coquiai_ChhattisgarhiFemale", "ch_female_vits_30hrs.pt"),
    ("hne_male", "Chhattisgarhi", "Male", "SYSPIN/tts_vits_coquiai_ChhattisgarhiMale", "ch_male_vits_30hrs.pt"),
    ("mai_female", "Maithili", "Female", "SYSPIN/tts_vits_coquiai_MaithiliFemale", "mt_female_vits_30hrs.pt"),
    ("mai_male", "Maithili", "Male", "SYSPIN/tts_vits_coquiai_MaithiliMale", "mt_male_vits_30hrs.pt"),
    ("mag_female", "Magahi", "Female", "SYSPIN/tts_vits_coquiai_MagahiFemale", "mg_female_vits_30hrs.pt"),
    ("mag_male", "Magahi", "Male", "SYSPIN/tts_vits_coquiai_MagahiMale", "mg_male_vits_30hrs.pt"),
    ("en_female", "English (Indian)", "Female", "SYSPIN/tts_vits_coquiai_EnglishFemale", "en_female_vits_30hrs.pt"),
    ("en_male", "English (Indian)", "Male", "SYSPIN/tts_vits_coquiai_EnglishMale", "en_male_vits_30hrs.pt"),
]
LICENSE = "CC BY 4.0 (credit: SYSPIN, IISc Bangalore)"
SR = 22050


class SyspinEngine(Engine):
    id = "syspin"
    name = "SYSPIN VITS"
    description = "Male + female voices for 9 languages incl. Chhattisgarhi, Maithili, Magahi. Offline, CPU."
    license_summary = LICENSE
    max_chunk_chars = 250

    def __init__(self):
        super().__init__()
        self._loaded: "OrderedDict[str, tuple]" = OrderedDict()   # small LRU of (net, tokenizer)

    def _dir(self, voice: Voice) -> str:
        return os.path.join(MODELS_DIR, "syspin", voice.id)

    def voices(self, language: Optional[str] = None) -> List[Voice]:
        out = []
        for key, lang, gender, repo, fname in SYSPIN_VOICES:
            if language and lang != language:
                continue
            out.append(Voice(id=key, name=f"{lang} {gender}", language=lang, engine_id=self.id,
                             gender=gender, license=LICENSE, extra={"repo": repo, "file": fname}))
        return out

    def install_size_hint(self, voice=None) -> str:
        return "~335 MB per voice"

    def is_installed(self, voice: Optional[Voice] = None) -> bool:
        if voice is None:
            return any(self.is_installed(v) for v in self.voices())
        d = self._dir(voice)
        return all(os.path.isfile(os.path.join(d, f)) for f in ("extra.py", "chars.txt", voice.extra["file"]))

    def install(self, voice: Optional[Voice] = None, progress: ProgressFn = None) -> None:
        from huggingface_hub import hf_hub_download
        targets = [voice] if voice else self.voices()[:2]
        for v in targets:
            if self.is_installed(v):
                continue
            for f in ("extra.py", "chars.txt", v.extra["file"]):
                if progress:
                    progress(f"Downloading SYSPIN {v.name}: {f} (model file is ~333 MB)...", -1)
                hf_hub_download(v.extra["repo"], f, local_dir=self._dir(v))

    def _get(self, voice: Voice):
        import torch
        with self._lock:
            if voice.id in self._loaded:
                self._loaded.move_to_end(voice.id)
                return self._loaded[voice.id]
            if not self.is_installed(voice):
                self.install(voice)
            d = self._dir(voice)
            spec = importlib.util.spec_from_file_location(f"syspin_extra_{voice.id}", os.path.join(d, "extra.py"))
            extra = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(extra)
            with open(os.path.join(d, "chars.txt"), encoding="utf-8") as f:
                letters = f.read().strip("\n")
            cfg = extra.VitsConfig(text_cleaner="multilingual_cleaners", characters=extra.CharactersConfig(
                characters_class=extra.VitsCharacters, pad="<PAD>", eos="<EOS>", bos="<BOS>",
                blank="<BLNK>", characters=letters, punctuations="!¡'(),-.:;¿? ", phonemes=None))
            tok, _ = extra.TTSTokenizer.init_from_config(cfg)
            # The traced models hard-code CPU tensors internally, so they must run on CPU.
            net = torch.jit.load(os.path.join(d, voice.extra["file"]), map_location="cpu")
            net.eval()
            self._loaded[voice.id] = (net, tok, set(letters))
            while len(self._loaded) > 2:
                self._loaded.popitem(last=False)
            return self._loaded[voice.id]

    def synthesize(self, text: str, voice: Voice, settings: SynthSettings) -> Tuple[np.ndarray, int]:
        import torch
        net, tok, letters = self._get(voice)
        if voice.language.startswith("English"):
            text = text.lower()   # SYSPIN English models only know lowercase letters
        ids = tok.text_to_ids(text)
        if len(ids) < 3:
            return np.zeros(int(SR * 0.2), dtype=np.float32), SR
        x = torch.from_numpy(np.array(ids)).unsqueeze(0)
        with self._lock, torch.no_grad():
            y = net(x)
        return y.squeeze().float().cpu().numpy().astype(np.float32), SR
