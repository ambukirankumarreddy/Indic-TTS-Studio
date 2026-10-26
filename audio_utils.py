"""Audio helpers: trimming, resampling, speed/pitch, loudness, ducking, saving."""

from __future__ import annotations

import os
from typing import Optional

import numpy as np


def trim_and_fade(audio: np.ndarray, sr: int, margin_s: float = 0.06, fade_s: float = 0.015) -> np.ndarray:
    """Trim leading/trailing near-silence, then short fades to avoid clicks at joins."""
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
        audio = audio.astype(np.float32, copy=True)
        audio[:f] *= ramp
        audio[-f:] *= ramp[::-1]
    return audio


def resample(audio: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to or audio.size == 0:
        return audio.astype(np.float32)
    import soxr
    return soxr.resample(audio.astype(np.float32), sr_from, sr_to).astype(np.float32)


def change_speed(audio: np.ndarray, sr: int, factor: float) -> np.ndarray:
    """Time-stretch without changing pitch. factor > 1 = faster."""
    if abs(factor - 1.0) < 0.02 or audio.size < sr // 10:
        return audio
    import librosa
    return librosa.effects.time_stretch(audio.astype(np.float32), rate=float(factor)).astype(np.float32)


def change_pitch(audio: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    if abs(semitones) < 0.25 or audio.size < sr // 10:
        return audio
    import librosa
    return librosa.effects.pitch_shift(audio.astype(np.float32), sr=sr, n_steps=float(semitones)).astype(np.float32)


def silence(sr: int, seconds: float) -> np.ndarray:
    return np.zeros(max(0, int(sr * seconds)), dtype=np.float32)


def normalize_peak(audio: np.ndarray, peak_db: float = -1.0) -> np.ndarray:
    p = float(np.max(np.abs(audio))) if audio.size else 0.0
    if p <= 0:
        return audio
    return (audio * (10 ** (peak_db / 20) / p)).astype(np.float32)


def rms_db(audio: np.ndarray) -> float:
    if audio.size == 0:
        return -120.0
    r = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    return 20 * np.log10(max(r, 1e-9))


def match_loudness(audio: np.ndarray, target_db: float = -20.0) -> np.ndarray:
    """Bring speech to a consistent level (so mixed engines/speakers sound even)."""
    voiced = audio[np.abs(audio) > 0.01]
    if voiced.size < 100:
        return audio
    gain = 10 ** ((target_db - rms_db(voiced)) / 20)
    out = audio * gain
    p = float(np.max(np.abs(out)))
    if p > 0.98:
        out = out * (0.98 / p)
    return out.astype(np.float32)


def load_audio(path: str, sr: Optional[int] = None) -> tuple:
    import soundfile as sf
    a, file_sr = sf.read(path, dtype="float32", always_2d=False)
    if a.ndim > 1:
        a = a.mean(axis=1)
    if sr and sr != file_sr:
        a = resample(a, file_sr, sr)
        file_sr = sr
    return a.astype(np.float32), file_sr


def save_audio(audio: np.ndarray, sr: int, path: str) -> str:
    """Save as .wav or .mp3 (decided by extension)."""
    import soundfile as sf
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    audio = np.clip(audio.astype(np.float32), -1.0, 1.0)
    if path.lower().endswith(".mp3"):
        sf.write(path, audio, sr, format="MP3")
    else:
        sf.write(path, audio, sr, subtype="PCM_16")
    return os.path.abspath(path)


def waveform_peaks(audio: np.ndarray, buckets: int = 400) -> np.ndarray:
    """Downsample to per-bucket peak values for drawing a waveform."""
    if audio.size == 0:
        return np.zeros(buckets, dtype=np.float32)
    n = max(1, audio.size // buckets)
    usable = audio[: n * (audio.size // n)]
    peaks = np.abs(usable.reshape(-1, n)).max(axis=1)
    if peaks.size > buckets:
        peaks = peaks[:buckets]
    m = float(peaks.max()) or 1.0
    return (peaks / m).astype(np.float32)


# ---------------------------------------------------------------------------
# Music ducking (approach adapted from srt-voiceover-studio, MIT)
# ---------------------------------------------------------------------------
def ducking_envelope(voice: np.ndarray, sr: int, duck_db: float = -12.0,
                     fade_ms: float = 300.0, hold_ms: float = 200.0) -> np.ndarray:
    """Gain envelope (linear) that dips where the voice is actually audible.
    Ramps down before the first syllable and holds briefly after the last."""
    hop = max(1, int(sr * 0.01))                         # 10 ms frames
    frames = int(np.ceil(voice.size / hop))
    padded = np.zeros(frames * hop, dtype=np.float32)
    padded[: voice.size] = np.abs(voice)
    energy = padded.reshape(frames, hop).max(axis=1)
    active = energy > 0.02
    # hold + pre-roll so the music is already down when speech starts
    hold = int(hold_ms / 10)
    pre = int(fade_ms / 10)
    act = active.copy()
    idx = np.where(active)[0]
    for i in idx:
        act[max(0, i - pre): i + hold + 1] = True
    target = np.where(act, 10 ** (duck_db / 20), 1.0).astype(np.float32)
    # smooth with a moving average of fade length
    k = max(1, int(fade_ms / 10))
    kernel = np.ones(k, dtype=np.float32) / k
    smooth = np.convolve(target, kernel, mode="same")
    env = np.repeat(smooth, hop)[: voice.size]
    return env.astype(np.float32)


def fit_music(music: np.ndarray, length: int, sr: int, fade_s: float = 2.0) -> np.ndarray:
    """Loop or trim music to exactly `length` samples with a fade out."""
    if music.size == 0:
        return np.zeros(length, dtype=np.float32)
    reps = int(np.ceil(length / music.size))
    out = np.tile(music, reps)[:length].astype(np.float32)
    f = min(int(sr * fade_s), length // 2)
    if f > 0:
        out[-f:] *= np.linspace(1.0, 0.0, f, dtype=np.float32)
    return out


def mix_with_music(voice: np.ndarray, music: np.ndarray, sr: int, music_db: float = -18.0,
                   duck_db: float = -12.0, fade_ms: float = 300.0) -> np.ndarray:
    m = fit_music(music, voice.size, sr)
    # bring music to its resting level relative to full scale
    m = m * (10 ** ((music_db - rms_db(m)) / 20)) if m.any() else m
    env = ducking_envelope(voice, sr, duck_db=duck_db, fade_ms=fade_ms)
    out = voice + m * env
    return normalize_peak(out, -1.0) if np.max(np.abs(out)) > 0.89 else out.astype(np.float32)
