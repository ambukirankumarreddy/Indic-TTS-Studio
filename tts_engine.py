"""TTS Engine wrapper for ai4bharat/indic-parler-tts."""

import os
import sys
import time
import json
import threading
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime

import numpy as np
from config import MODEL_ID, DEFAULT_OUTPUT_DIR, LANGUAGES_DATA


def _trim_and_fade(audio: "np.ndarray", sr: int, margin_s: float = 0.06, fade_s: float = 0.015) -> "np.ndarray":
    """Trim leading/trailing near-silence so joined chunks don't have long dead gaps,
    then apply a short fade in/out to avoid clicks at the joins."""
    if audio.size == 0:
        return audio
    peak = float(np.max(np.abs(audio)))
    if peak <= 0:
        return audio
    idx = np.where(np.abs(audio) > peak * 0.02)[0]
    if idx.size:
        m = int(sr * margin_s)
        audio = audio[max(0, idx[0] - m): min(audio.size, idx[-1] + m)]
    f = min(int(sr * fade_s), audio.size // 2)
    if f > 0:
        ramp = np.linspace(0.0, 1.0, f, dtype=np.float32)
        audio = audio.copy()
        audio[:f] *= ramp
        audio[-f:] *= ramp[::-1]
    return audio


def split_text_into_chunks(text: str, max_chars: int = 200) -> List[str]:
    """Split text on sentence boundaries (incl. Devanagari danda) into chunks <= max_chars."""
    import re
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[\.\?\!\u0964\u0965])\s+", text) if s.strip()]

    chunks: List[str] = []
    current = ""
    for sent in sentences:
        # Hard-split any single sentence that is still too long, on commas then spaces
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


class TTSEngine:
    def __init__(self, output_dir: str = DEFAULT_OUTPUT_DIR):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.history_file = os.path.join(self.output_dir, "history.json")

        self.model = None
        self.tokenizer = None
        self.description_tokenizer = None
        self.sampling_rate = 24000  # Default for Parler-TTS

        self.is_loading = False
        self.is_generating = False
        self.device = "cuda" if self._has_cuda() else "cpu"
        self._lock = threading.Lock()

        # Callbacks
        self.on_status_change: Optional[Callable[[str], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

    def _has_cuda(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def log(self, message: str):
        print(f"[TTS Engine] {message}")
        if self.on_log:
            self.on_log(message)

    def set_status(self, status: str):
        if self.on_status_change:
            self.on_status_change(status)

    def is_model_loaded(self) -> bool:
        return self.model is not None

    def load_model(self, device: Optional[str] = None, use_fp16: bool = True, on_complete: Optional[Callable[[bool, str], None]] = None):
        """Loads the Indic Parler-TTS model and both tokenizers asynchronously."""
        def _loader():
            with self._lock:
                if self.model is not None:
                    if on_complete:
                        on_complete(True, "Model is already loaded.")
                    return

                self.is_loading = True
                self.set_status("Loading Indic Parler-TTS model...")
                start_time = time.time()

                try:
                    import torch
                    from transformers import AutoTokenizer
                    from parler_tts import ParlerTTSForConditionalGeneration

                    target_device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
                    self.device = target_device
                    self.log(f"Loading weights onto {target_device}...")

                    # Parler-TTS requires two tokenizers:
                    # 1. Prompt tokenizer (the Indian language text)
                    self.log(f"Fetching prompt tokenizer from {MODEL_ID}...")
                    self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

                    # 2. Main conditional generation model
                    self.log(f"Loading model weights from {MODEL_ID}...")
                    dtype = torch.float16 if (target_device.startswith("cuda") and use_fp16) else torch.float32

                    self.model = ParlerTTSForConditionalGeneration.from_pretrained(
                        MODEL_ID,
                        torch_dtype=dtype,
                        low_cpu_mem_usage=True
                    ).to(target_device)
                    self.model.eval()

                    # 3. Description tokenizer (from the text_encoder of the model)
                    text_encoder_name = self.model.config.text_encoder._name_or_path
                    self.log(f"Fetching description tokenizer ({text_encoder_name})...")
                    self.description_tokenizer = AutoTokenizer.from_pretrained(text_encoder_name)

                    self.sampling_rate = getattr(self.model.config, "sampling_rate", 24000)

                    elapsed = time.time() - start_time
                    success_msg = f"Model loaded successfully on {target_device} in {elapsed:.1f}s (Sampling Rate: {self.sampling_rate}Hz)"
                    self.log(success_msg)
                    self.set_status("Ready")
                    self.is_loading = False

                    if on_complete:
                        on_complete(True, success_msg)

                except Exception as e:
                    self.is_loading = False
                    self.set_status("Load Error")
                    error_msg = f"Failed to load model: {str(e)}"
                    if "gated repo" in str(e).lower() or "401" in str(e):
                        error_msg = (
                            "This model is gated on Hugging Face.\n\n"
                            "1. Open https://huggingface.co/ai4bharat/indic-parler-tts, log in, "
                            "and accept the access conditions.\n"
                            "2. Double-click 'login_huggingface.bat' in the app folder and paste "
                            "your access token.\n"
                            "3. Restart the app and click Load Model again."
                        )
                    self.log(error_msg)
                    if on_complete:
                        on_complete(False, error_msg)

        threading.Thread(target=_loader, daemon=True).start()

    EMOTION_WORDS = {
        "Happy": "happy", "Sad": "sad", "Anger": "angry", "Narration": "narrative",
        "Conversation": "conversational", "Surprise": "surprised", "Command": "commanding",
        "Disgust": "disgusted", "Fear": "fearful", "News": "news-reading",
    }

    def build_description(
        self,
        speaker: Optional[str] = None,
        language: Optional[str] = None,
        emotion: str = "Neutral",
        speed_desc: str = "at a moderate pace",
        pitch_desc: str = "a moderate pitch",
        expressivity_desc: str = "slightly expressive",
        quality_desc: str = "The recording is very clear audio, close-sounding, with no background noise."
    ) -> str:
        """Builds a caption in the same style as the model card examples, e.g.
        'Divya speaks at a moderate pace with a moderate pitch. Her delivery is slightly
        expressive. The recording is very clear audio, close-sounding, with no background noise.'
        """
        named = bool(speaker) and speaker not in ("Random Voice", "Default")
        subject = speaker if named else "A speaker"

        first = f"{subject} speaks {speed_desc} with {pitch_desc}."

        emo_word = self.EMOTION_WORDS.get(emotion or "Neutral")
        if emo_word:
            second = f"The delivery is {expressivity_desc}, with a {emo_word} tone."
        else:
            second = f"The delivery is {expressivity_desc}."

        return f"{first} {second} {quality_desc}"

    def generate(
        self,
        text: str,
        description: str,
        filename_prefix: str = "indic_tts",
        on_progress: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[bool, Optional[Dict[str, Any]], str], None]] = None
    ):
        """Generates speech audio from text and description in a background worker."""
        if not self.is_model_loaded():
            if on_complete:
                on_complete(False, None, "Model is not loaded. Please load the model first.")
            return

        def _worker():
            with self._lock:
                self.is_generating = True
                self.set_status("Synthesizing audio...")
                if on_progress:
                    on_progress("Tokenizing prompt & description...")

                try:
                    import torch
                    import soundfile as sf

                    clean_text = text.strip()
                    clean_desc = description.strip()
                    if not clean_text:
                        raise ValueError("Text prompt cannot be empty.")
                    if not clean_desc:
                        raise ValueError("Description caption cannot be empty.")

                    start_time = time.time()

                    # Tokenize description once (shared by all chunks)
                    desc_inputs = self.description_tokenizer(
                        clean_desc,
                        return_tensors="pt"
                    ).to(self.device)

                    # Parler-TTS degrades on long inputs, so synthesize sentence-sized chunks
                    chunks = split_text_into_chunks(clean_text)
                    pieces = []

                    # Same seed for every chunk -> same sampling path -> more consistent voice
                    seed = int(time.time()) % (2 ** 31)

                    for ci, chunk in enumerate(chunks):
                        if on_progress:
                            on_progress(f"Generating part {ci + 1} of {len(chunks)} on {self.device}...")
                        self.set_status(f"Synthesizing {ci + 1}/{len(chunks)}...")

                        prompt_inputs = self.tokenizer(
                            chunk,
                            return_tensors="pt"
                        ).to(self.device)

                        torch.manual_seed(seed)
                        with torch.inference_mode():
                            generation = self.model.generate(
                                input_ids=desc_inputs.input_ids,
                                attention_mask=desc_inputs.attention_mask,
                                prompt_input_ids=prompt_inputs.input_ids,
                                prompt_attention_mask=prompt_inputs.attention_mask
                            )

                        # Cast to float32: soundfile cannot write float16 arrays
                        piece = generation.float().cpu().numpy().squeeze().astype(np.float32)
                        piece = _trim_and_fade(piece, self.sampling_rate)
                        pieces.append(piece)
                        if ci < len(chunks) - 1:
                            # Longer pause after a full stop, shorter after a comma-split
                            ends_sentence = chunk.rstrip()[-1:] in ".?!\u0964\u0965\"\u201d"
                            gap = 0.45 if ends_sentence else 0.18
                            pieces.append(np.zeros(int(self.sampling_rate * gap), dtype=np.float32))

                    audio_arr = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
                    gen_duration = time.time() - start_time

                    # Calculate audio duration
                    audio_duration_sec = len(audio_arr) / float(self.sampling_rate)
                    rtf = gen_duration / max(0.001, audio_duration_sec)

                    # Save to WAV file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_prefix = "".join([c if c.isalnum() or c in "_-" else "_" for c in filename_prefix])[:20]
                    wav_filename = f"{safe_prefix}_{timestamp}.wav"
                    wav_path = os.path.join(self.output_dir, wav_filename)

                    sf.write(wav_path, audio_arr, self.sampling_rate)

                    result_data = {
                        "wav_path": os.path.abspath(wav_path),
                        "filename": wav_filename,
                        "text": clean_text,
                        "description": clean_desc,
                        "sampling_rate": self.sampling_rate,
                        "audio_duration": audio_duration_sec,
                        "generation_time": gen_duration,
                        "rtf": rtf,
                        "timestamp": datetime.now().isoformat(),
                    }

                    # Append to history
                    self._add_to_history(result_data)

                    self.log(f"Generated {wav_filename} in {gen_duration:.2f}s ({audio_duration_sec:.2f}s audio, RTF: {rtf:.2f})")
                    self.set_status("Ready")
                    self.is_generating = False

                    if on_complete:
                        on_complete(True, result_data, "Generation completed successfully.")

                except Exception as e:
                    self.is_generating = False
                    self.set_status("Generation Error")
                    error_msg = f"Generation failed: {str(e)}"
                    self.log(error_msg)
                    if on_complete:
                        on_complete(False, None, error_msg)

        threading.Thread(target=_worker, daemon=True).start()

    def _add_to_history(self, item: Dict[str, Any]):
        history = self.get_history()
        history.insert(0, item)
        # Limit history to 200 entries
        history = history[:200]
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log(f"Warning: Failed to save history: {e}")

    def get_history(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
