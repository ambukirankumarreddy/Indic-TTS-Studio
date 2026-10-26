"""Reusable widgets: cards, badges, voice picker, settings panel, player bar, status bar."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Callable, Dict, List, Optional

import customtkinter as ctk
import tkinter as tk

from config import EMOTIONS, EXPRESSIVITY_OPTIONS, AUDIO_QUALITY_OPTIONS
from engines import Engine, SynthSettings, Voice, all_engines, get_engine
from . import theme as T

SAMPLE_TEXT = {
    "Hindi": "नमस्ते! मैं आपकी आवाज़ हूँ। आज का दिन बहुत सुंदर है।",
    "Bengali": "নমস্কার! আজকের দিনটা খুব সুন্দর।",
    "Marathi": "नमस्कार! आजचा दिवस खूप छान आहे.",
    "Tamil": "வணக்கம்! இன்று மிகவும் அழகான நாள்.",
    "Telugu": "నమస్కారం! ఈ రోజు చాలా అందమైన రోజు.",
    "Kannada": "ನಮಸ್ಕಾರ! ಇಂದು ತುಂಬಾ ಸುಂದರವಾದ ದಿನ.",
    "Malayalam": "നമസ്കാരം! ഇന്ന് വളരെ മനോഹരമായ ദിവസമാണ്.",
    "Gujarati": "નમસ્તે! આજનો દિવસ ખૂબ સુંદર છે.",
    "Punjabi": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਅੱਜ ਦਾ ਦਿਨ ਬਹੁਤ ਸੋਹਣਾ ਹੈ।",
    "Odia": "ନମସ୍କାର! ଆଜି ବହୁତ ସୁନ୍ଦର ଦିନ।",
    "Assamese": "নমস্কাৰ! আজিৰ দিনটো বৰ ধুনীয়া।",
    "Urdu": "السلام علیکم! آج کا دن بہت خوبصورت ہے۔",
    "Nepali": "नमस्ते! आजको दिन धेरै राम्रो छ।",
}
ENGLISH_SAMPLE = "Hello! This is how I sound. Have a wonderful day."


def sample_for(language: str) -> str:
    if language in SAMPLE_TEXT:
        return SAMPLE_TEXT[language]
    if language.lower().startswith("english"):
        return ENGLISH_SAMPLE
    return SAMPLE_TEXT["Hindi"]


# ---------------------------------------------------------------------------
# Catalogue helpers
# ---------------------------------------------------------------------------
_LANGS: Optional[List[str]] = None


def all_languages() -> List[str]:
    global _LANGS
    if _LANGS is None:
        s = set()
        for e in all_engines():
            try:
                s.update(e.languages())
            except Exception:
                pass
        s.discard("Any language")
        first = [l for l in ("Hindi", "English", "English (Indian)") if l in s]
        _LANGS = first + sorted(s - set(first))
    return _LANGS


def engines_for(language: str) -> List[Engine]:
    out = []
    for e in all_engines():
        try:
            if language in e.languages():
                out.append(e)
        except Exception:
            pass
    return out


def open_in_explorer(path: str):
    if os.path.isfile(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif os.path.isdir(path):
        os.startfile(path)


# ---------------------------------------------------------------------------
# Basic building blocks
# ---------------------------------------------------------------------------
class Card(ctk.CTkFrame):
    def __init__(self, master, title: str = "", subtitle: str = "", **kw):
        kw.setdefault("fg_color", T.CARD)
        kw.setdefault("corner_radius", 14)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", T.BORDER)
        super().__init__(master, **kw)
        self.grid_columnconfigure(0, weight=1)
        r = 0
        if title:
            ctk.CTkLabel(self, text=title, font=T.font(14, "bold"), text_color=T.TEXT,
                         anchor="w").grid(row=r, column=0, sticky="ew", padx=16, pady=(14, 0))
            r += 1
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=T.font(12), text_color=T.MUTED, anchor="w",
                         justify="left", wraplength=520).grid(row=r, column=0, sticky="ew", padx=16)
            r += 1
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=r, column=0, sticky="nsew", padx=16, pady=(10, 16))
        self.grid_rowconfigure(r, weight=1)
        self.body.grid_columnconfigure(0, weight=1)


class Badge(ctk.CTkLabel):
    def __init__(self, master, text="", bg=T.CARD_2, fg=T.MUTED, **kw):
        super().__init__(master, text=f" {text} ", fg_color=bg, text_color=fg, corner_radius=8,
                         font=T.font(11, "bold"), height=22, **kw)

    def set(self, text, bg=None, fg=None):
        self.configure(text=f" {text} ")
        if bg:
            self.configure(fg_color=bg)
        if fg:
            self.configure(text_color=fg)


def option_menu(master, values, command=None, width=200, variable=None):
    return ctk.CTkOptionMenu(
        master, values=values or ["—"], command=command, width=width, height=34,
        dynamic_resizing=False, variable=variable, corner_radius=10,
        fg_color=T.INPUT, button_color=T.CARD_2, button_hover_color=T.HOVER,
        dropdown_fg_color=T.CARD_2, dropdown_hover_color=T.ACCENT_SOFT,
        text_color=T.TEXT, font=T.font(13), dropdown_font=T.font(13, family=T.FONT_INDIC))


def primary_button(master, text, command, height=46, **kw):
    return ctk.CTkButton(master, text=text, command=command, height=height, corner_radius=12,
                         fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER, text_color="#ffffff",
                         font=T.font(15, "bold"), **kw)


def ghost_button(master, text, command, width=None, height=32, danger=False, **kw):
    if width:
        kw["width"] = width
    return ctk.CTkButton(master, text=text, command=command, height=height, corner_radius=10,
                         fg_color=T.CARD_2, hover_color=T.HOVER, border_width=1,
                         border_color=T.BORDER, text_color=T.DANGER if danger else T.TEXT,
                         font=T.font(12, "bold"), **kw)


def label(master, text, size=12, color=T.MUTED, weight="normal", **kw):
    return ctk.CTkLabel(master, text=text, font=T.font(size, weight), text_color=color,
                        anchor="w", justify="left", **kw)


def indic_textbox(master, height=200, size=16):
    return ctk.CTkTextbox(master, height=height, wrap="word", corner_radius=12, border_width=1,
                          border_color=T.BORDER, fg_color=T.INPUT, text_color=T.TEXT,
                          font=T.font(size, family=T.FONT_INDIC), border_spacing=10)


def switch(master, text, value=True):
    var = tk.BooleanVar(value=value)
    sw = ctk.CTkSwitch(master, text=text, variable=var, progress_color=T.ACCENT,
                       button_color="#ffffff", button_hover_color="#e5e5e5",
                       font=T.font(12), text_color=T.TEXT)
    return sw, var


class LabeledSlider(ctk.CTkFrame):
    def __init__(self, master, text, from_, to, value, steps, fmt="{:.2f}", command=None):
        super().__init__(master, fg_color="transparent")
        self.fmt = fmt
        self.grid_columnconfigure(0, weight=1)
        label(self, text, 12, T.MUTED).grid(row=0, column=0, sticky="w")
        self.val_label = label(self, "", 12, T.TEXT, "bold")
        self.val_label.grid(row=0, column=1, sticky="e")
        self.slider = ctk.CTkSlider(self, from_=from_, to=to, number_of_steps=steps,
                                    command=self._changed, progress_color=T.ACCENT,
                                    button_color=T.ACCENT, button_hover_color=T.ACCENT_HOVER,
                                    fg_color=T.CARD_2, height=16)
        self.slider.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 0))
        self._cmd = command
        self.set(value)

    def _changed(self, v):
        self.val_label.configure(text=self.fmt.format(float(v)))
        if self._cmd:
            self._cmd(float(v))

    def set(self, v):
        self.slider.set(v)
        self.val_label.configure(text=self.fmt.format(float(v)))

    def get(self) -> float:
        return float(self.slider.get())


# ---------------------------------------------------------------------------
# Voice picker: Language -> Engine -> Voice, with license / online / install badges
# ---------------------------------------------------------------------------
class VoicePicker(ctk.CTkFrame):
    def __init__(self, master, app, pref_key: str, compact: bool = False,
                 on_change: Optional[Callable[[Voice, Engine], None]] = None,
                 settings_provider: Optional[Callable[[], SynthSettings]] = None,
                 default_language: str = "Hindi"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.pref_key = pref_key
        self.compact = compact
        self.on_change = on_change
        self.settings_provider = settings_provider
        self._engine_map: Dict[str, Engine] = {}
        self._voice_map: Dict[str, Voice] = {}
        self.grid_columnconfigure(0, weight=1)

        langs = all_languages()
        w = 150 if compact else 300
        self.lang_menu = option_menu(self, langs, self._on_lang, width=w)
        self.engine_menu = option_menu(self, [], self._on_engine, width=w)
        self.voice_menu = option_menu(self, [], self._on_voice, width=(200 if compact else w))

        if compact:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.grid(row=0, column=0, sticky="ew")
            for i, m in enumerate((self.lang_menu, self.engine_menu, self.voice_menu)):
                m.grid(in_=row, row=0, column=i, padx=(0, 6))
            self.badges = ctk.CTkFrame(self, fg_color="transparent")
            self.badges.grid(row=1, column=0, sticky="w", pady=(6, 0))
        else:
            r = 0
            for text, m in (("Language", self.lang_menu), ("Engine", self.engine_menu),
                            ("Voice", self.voice_menu)):
                label(self, text, 11, T.DIM, "bold").grid(row=r, column=0, sticky="w", pady=(6, 2))
                m.grid(row=r + 1, column=0, sticky="ew")
                r += 2
            self.badges = ctk.CTkFrame(self, fg_color="transparent")
            self.badges.grid(row=r, column=0, sticky="w", pady=(10, 0))
            self.note = label(self, "", 11, T.MUTED, wraplength=300)
            self.note.grid(row=r + 1, column=0, sticky="ew", pady=(6, 0))
            btns = ctk.CTkFrame(self, fg_color="transparent")
            btns.grid(row=r + 2, column=0, sticky="ew", pady=(8, 0))
            btns.grid_columnconfigure((0, 1), weight=1)
            self.preview_btn = ghost_button(btns, "▶  Preview voice", self.preview)
            self.preview_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            self.install_btn = ghost_button(btns, "⬇  Download", self.install)
            self.install_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self.lic_badge = Badge(self.badges)
        self.lic_badge.grid(row=0, column=0, padx=(0, 6))
        self.net_badge = Badge(self.badges)
        self.net_badge.grid(row=0, column=1, padx=(0, 6))
        self.state_badge = Badge(self.badges)
        self.state_badge.grid(row=0, column=2)

        saved = app.prefs.get(f"voice.{pref_key}", "")
        self._restore(saved, default_language)

    # -- population ---------------------------------------------------------
    def _restore(self, key: str, default_language: str):
        from engines import find_voice
        v = find_voice(key) if key else None
        lang = app_lang = (v.language if v and v.language != "Any language" else None)
        if not lang:
            lang = self.app.prefs.get(f"lang.{self.pref_key}", default_language)
        if lang not in all_languages():
            lang = all_languages()[0]
        self.lang_menu.set(lang)
        self._fill_engines(lang, prefer=v.engine_id if v else self.app.prefs.get(f"engine.{self.pref_key}"))
        if v:
            for lbl, vv in self._voice_map.items():
                if vv.key == v.key:
                    self.voice_menu.set(lbl)
                    break
        self._refresh_badges()

    def _fill_engines(self, lang: str, prefer: Optional[str] = None):
        engines = engines_for(lang)
        self._engine_map = {}
        for e in engines:
            n = len(e.voices(lang))
            self._engine_map[f"{e.name}{'  ·  online' if e.online else ''}  ({n})"] = e
        labels = list(self._engine_map) or ["—"]
        self.engine_menu.configure(values=labels)
        pick = None
        if prefer:
            pick = next((l for l, e in self._engine_map.items() if e.id == prefer), None)
        if not pick:
            order = ["edge", "parler", "piper", "kokoro", "syspin"]
            pick = sorted(labels, key=lambda l: order.index(self._engine_map[l].id)
                          if l in self._engine_map and self._engine_map[l].id in order else 99)[0]
        self.engine_menu.set(pick)
        self._fill_voices()

    def _fill_voices(self):
        e = self.engine
        lang = self.lang_menu.get()
        self._voice_map = {}
        if e:
            vs = sorted(e.voices(lang), key=lambda v: (not v.recommended, not v.native, v.name))
            for v in vs:
                lbl = v.label
                while lbl in self._voice_map:
                    lbl += " "
                self._voice_map[lbl] = v
        labels = list(self._voice_map) or ["—"]
        self.voice_menu.configure(values=labels)
        self.voice_menu.set(labels[0])

    # -- events -------------------------------------------------------------
    def _on_lang(self, lang):
        self.app.prefs[f"lang.{self.pref_key}"] = lang
        cur = self.engine.id if self.engine else None
        self._fill_engines(lang, prefer=cur)
        self._changed()

    def _on_engine(self, _):
        if self.engine:
            self.app.prefs[f"engine.{self.pref_key}"] = self.engine.id
        self._fill_voices()
        self._changed()

    def _on_voice(self, _):
        self._changed()

    def _changed(self):
        v = self.voice
        if v:
            self.app.prefs[f"voice.{self.pref_key}"] = v.key
            self.app.save_prefs()
        self._refresh_badges()
        if self.on_change and v:
            self.on_change(v, self.engine)

    def _refresh_badges(self):
        v, e = self.voice, self.engine
        if not v or not e:
            return
        lic = v.license or e.license_summary
        short = lic.split("(")[0].strip()[:34]
        bg, fg = T.license_colors(lic)
        self.lic_badge.set("⚖ " + short, bg, fg)
        if e.online:
            self.net_badge.set("☁ Online", "#132a45", T.INFO)
        else:
            self.net_badge.set("⌂ Offline", T.CARD_2, T.MUTED)
        installed = e.is_installed(v)
        if installed:
            self.state_badge.set("✓ Ready", "#0f3326", T.SUCCESS)
        else:
            self.state_badge.set("⬇ " + (e.install_size_hint(v) or "Download needed")[:30],
                                 "#3a2c10", T.WARN)
        if not self.compact:
            notes = [v.notes] if v.notes else []
            notes.append(e.description)
            notes.append("License: " + lic)
            self.note.configure(text="\n".join(n for n in notes if n))
            self.install_btn.configure(state="disabled" if installed else "normal",
                                       text="✓  Installed" if installed else "⬇  Download")

    # -- public -------------------------------------------------------------
    @property
    def engine(self) -> Optional[Engine]:
        return self._engine_map.get(self.engine_menu.get())

    @property
    def voice(self) -> Optional[Voice]:
        return self._voice_map.get(self.voice_menu.get())

    @property
    def language(self) -> str:
        return self.lang_menu.get()

    def refresh(self):
        self._refresh_badges()

    def select_other_gender(self):
        cur_v = self.voice
        if not cur_v or not cur_v.gender:
            labels = list(self._voice_map.keys())
            if len(labels) > 1:
                self.voice_menu.set(labels[1])
                self._changed()
            return
        target = "Male" if cur_v.gender.lower() == "female" else "Female"
        for lbl, v in self._voice_map.items():
            if v.gender and v.gender.lower() == target.lower():
                self.voice_menu.set(lbl)
                self._changed()
                return

    def install(self):
        v, e = self.voice, self.engine
        if not v or not e:
            return

        def work(job, progress):
            e.install(v, progress)
            return None
        self.app.run_job(f"Downloading {e.name} · {v.name}", work,
                         on_done=lambda _: self._refresh_badges())

    def preview(self):
        v = self.voice
        if not v:
            return
        settings = self.settings_provider() if self.settings_provider else SynthSettings()
        self.app.preview_voice(v, self.language, settings, on_done=self._refresh_badges)


# ---------------------------------------------------------------------------
# Synthesis settings
# ---------------------------------------------------------------------------
class SettingsPanel(ctk.CTkFrame):
    def __init__(self, master, compact=False):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.speed = LabeledSlider(self, "Speed", 0.5, 2.0, 1.0, 30, "{:.2f}×")
        self.speed.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.pitch = LabeledSlider(self, "Pitch", -6, 6, 0, 24, "{:+.1f} st")
        self.pitch.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        self.hint = label(self, "", 11, T.DIM, wraplength=300)
        self.hint.grid(row=2, column=0, sticky="ew")

        self.parler = ctk.CTkFrame(self, fg_color=T.CARD_2, corner_radius=12)
        self.parler.grid_columnconfigure(0, weight=1)
        label(self.parler, "✦  Expressive controls (Parler)", 12, T.TEXT, "bold").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        self.emotion = option_menu(self.parler, EMOTIONS, width=260)
        self.emotion.set("Neutral")
        self._row(self.parler, 1, "Emotion", self.emotion)
        self.expr = option_menu(self.parler, [k for k, _ in EXPRESSIVITY_OPTIONS], width=260)
        self.expr.set("Expressive")
        self._row(self.parler, 3, "Expressivity", self.expr)
        self.quality = option_menu(self.parler, [k for k, _ in AUDIO_QUALITY_OPTIONS], width=260)
        self.quality.set(AUDIO_QUALITY_OPTIONS[0][0])
        self._row(self.parler, 5, "Recording quality", self.quality)
        self.seed = ctk.CTkEntry(self.parler, placeholder_text="Random", height=32, corner_radius=10,
                                 fg_color=T.INPUT, border_color=T.BORDER)
        self._row(self.parler, 7, "Seed (same seed = same voice character)", self.seed)
        self.caption = ctk.CTkEntry(self.parler, placeholder_text="Optional: write your own voice description",
                                    height=32, corner_radius=10, fg_color=T.INPUT, border_color=T.BORDER)
        self._row(self.parler, 9, "Custom caption (overrides the above)", self.caption, last=True)

    def _row(self, parent, r, text, widget, last=False):
        label(parent, text, 11, T.DIM, "bold").grid(row=r, column=0, sticky="w", padx=12, pady=(4, 2))
        widget.grid(row=r + 1, column=0, sticky="ew", padx=12, pady=(0, 12 if last else 2))

    def set_engine(self, engine: Optional[Engine]):
        if engine and engine.supports_emotion:
            self.parler.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        else:
            self.parler.grid_forget()
        if engine is None:
            self.hint.configure(text="")
        elif engine.native_speed and engine.native_pitch:
            self.hint.configure(text="Speed and pitch are applied by the engine itself.")
        else:
            self.hint.configure(text="Pitch (and speed where needed) is applied after synthesis.")

    def get(self) -> SynthSettings:
        seed_txt = self.seed.get().strip()
        seed = int(seed_txt) if seed_txt.isdigit() else None
        return SynthSettings(speed=round(self.speed.get(), 2), pitch=round(self.pitch.get(), 1),
                             emotion=self.emotion.get(), expressivity=self.expr.get(),
                             quality=self.quality.get(), caption=self.caption.get().strip(),
                             seed=seed)


# ---------------------------------------------------------------------------
# Status bar (progress + cancel)
# ---------------------------------------------------------------------------
class StatusBar(ctk.CTkFrame):
    def __init__(self, master, on_cancel):
        super().__init__(master, fg_color="transparent", height=34)
        self.grid_columnconfigure(1, weight=1)
        self.dot = ctk.CTkLabel(self, text="●", text_color=T.SUCCESS, font=T.font(12), width=16)
        self.dot.grid(row=0, column=0, padx=(0, 6))
        self.msg = label(self, "Ready", 12, T.MUTED)
        self.msg.grid(row=0, column=1, sticky="ew")
        self.bar = ctk.CTkProgressBar(self, width=220, height=8, progress_color=T.ACCENT,
                                      fg_color=T.CARD_2, corner_radius=4)
        self.bar.set(0)
        self.cancel_btn = ghost_button(self, "Cancel", on_cancel, width=80, height=28, danger=True)
        self._indet = False
        self._t0 = 0.0

    def start(self, text):
        self._t0 = time.monotonic()
        self.dot.configure(text_color=T.WARN)
        self.msg.configure(text=text, text_color=T.TEXT)
        self.bar.grid(row=0, column=2, padx=10)
        self.cancel_btn.grid(row=0, column=3)
        self.update_progress(text, -1)

    def update_progress(self, text, frac):
        el = time.monotonic() - self._t0
        self.msg.configure(text=f"{text}   ·  {el:.0f}s")
        if frac is None or frac < 0:
            if not self._indet:
                self.bar.configure(mode="indeterminate")
                self.bar.start()
                self._indet = True
        else:
            if self._indet:
                self.bar.stop()
                self.bar.configure(mode="determinate")
                self._indet = False
            self.bar.set(max(0.0, min(1.0, frac)))

    def done(self, text, ok=True):
        if self._indet:
            self.bar.stop()
            self.bar.configure(mode="determinate")
            self._indet = False
        self.bar.grid_forget()
        self.cancel_btn.grid_forget()
        self.dot.configure(text_color=T.SUCCESS if ok else T.DANGER)
        self.msg.configure(text=text, text_color=T.MUTED if ok else T.DANGER)


# ---------------------------------------------------------------------------
# Player bar with waveform
# ---------------------------------------------------------------------------
class PlayerBar(ctk.CTkFrame):
    BARS_GAP = 3

    def __init__(self, master, app):
        super().__init__(master, fg_color=T.CARD, corner_radius=16, border_width=1,
                         border_color=T.BORDER, height=96)
        self.app = app
        self.path: Optional[str] = None
        self.peaks = None
        self.duration = 0.0
        self._play_t0 = 0.0
        self._playing = False
        self._bar_ids: List[int] = []
        self._played_upto = 0
        self.grid_columnconfigure(1, weight=1)

        self.play_btn = ctk.CTkButton(self, text="▶", width=52, height=52, corner_radius=26,
                                      fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                                      font=T.font(20, "bold"), command=self.toggle)
        self.play_btn.grid(row=0, column=0, rowspan=2, padx=(16, 14), pady=14)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=1, sticky="ew", pady=(12, 0))
        top.grid_columnconfigure(0, weight=1)
        self.title = ctk.CTkLabel(top, text="Nothing loaded yet — generate something!",
                                  font=T.font(13, "bold", T.FONT_INDIC), text_color=T.TEXT, anchor="w")
        self.title.grid(row=0, column=0, sticky="ew")
        self.time_lbl = label(top, "0:00 / 0:00", 12, T.MUTED)
        self.time_lbl.grid(row=0, column=1, padx=(10, 0))

        self.canvas = tk.Canvas(self, height=40, bg=T.CARD, highlightthickness=0, bd=0)
        self.canvas.grid(row=1, column=1, sticky="ew", pady=(4, 12))
        self.canvas.bind("<Configure>", lambda e: self._draw_waveform())
        self.canvas.bind("<Button-1>", lambda e: self.play())

        side = ctk.CTkFrame(self, fg_color="transparent")
        side.grid(row=0, column=2, rowspan=2, padx=(12, 16))
        self.export_btn = ghost_button(side, "⇩ Export", self.export, width=96)
        self.export_btn.grid(row=0, column=0, pady=(0, 6))
        self.folder_btn = ghost_button(side, "↗ Show file", self.show_file, width=96)
        self.folder_btn.grid(row=1, column=0)
        self._set_enabled(False)
        self._tick()

    def _set_enabled(self, on):
        st = "normal" if on else "disabled"
        for b in (self.play_btn, self.export_btn, self.folder_btn):
            b.configure(state=st)

    def load(self, path: str, title: str = "", meta: str = "", autoplay: bool = True):
        import audio_utils as au
        self.stop()
        try:
            audio, sr = au.load_audio(path)
        except Exception as e:
            self.title.configure(text=f"Could not open audio: {e}")
            return
        self.path = path
        self.duration = len(audio) / float(sr)
        self.peaks = au.waveform_peaks(audio, 600)
        t = (title or os.path.basename(path)).replace("\n", " ")
        self.title.configure(text=(t[:90] + "…") if len(t) > 90 else t)
        self._set_enabled(True)
        self._draw_waveform()
        self._update_time(0)
        if autoplay:
            self.play()

    def _draw_waveform(self):
        c = self.canvas
        c.delete("all")
        self._bar_ids = []
        self._played_upto = 0
        w = max(10, c.winfo_width())
        h = max(10, c.winfo_height())
        if self.peaks is None:
            for i in range(0, w, self.BARS_GAP + 2):
                c.create_line(i, h / 2, i, h / 2 + 1, fill=T.BORDER, width=2)
            return
        n = max(1, w // (self.BARS_GAP + 2))
        import numpy as np
        idx = np.linspace(0, len(self.peaks) - 1, n).astype(int)
        vals = self.peaks[idx]
        for i, v in enumerate(vals):
            x = i * (self.BARS_GAP + 2) + 1
            bh = max(2.0, float(v) * (h - 4))
            self._bar_ids.append(c.create_line(x, (h - bh) / 2, x, (h + bh) / 2,
                                               fill=T.DIM, width=2, capstyle="round"))

    def _paint_progress(self, frac):
        k = int(len(self._bar_ids) * frac)
        if k == self._played_upto:
            return
        lo, hi = sorted((k, self._played_upto))
        color = T.ACCENT if k > self._played_upto else T.DIM
        for i in range(lo, hi):
            self.canvas.itemconfigure(self._bar_ids[i], fill=color)
        self._played_upto = k

    def _update_time(self, el):
        f = lambda s: f"{int(s // 60)}:{int(s % 60):02d}"
        self.time_lbl.configure(text=f"{f(el)} / {f(self.duration)}")

    def _tick(self):
        if self._playing:
            el = time.monotonic() - self._play_t0
            if el >= self.duration + 0.3 or not self.app.player.is_playing:
                self._finished()
            else:
                self._paint_progress(min(1.0, el / max(self.duration, 0.01)))
                self._update_time(min(el, self.duration))
        self.after(50, self._tick)

    def toggle(self):
        if self._playing:
            self.stop()
        else:
            self.play()

    def play(self):
        if not self.path:
            return
        self.app.player.play(self.path)
        self._play_t0 = time.monotonic()
        self._playing = True
        self._paint_progress(0)
        self.play_btn.configure(text="■")

    def stop(self):
        if self._playing:
            self.app.player.stop()
        self._finished()

    def _finished(self):
        self._playing = False
        self.play_btn.configure(text="▶")
        self._paint_progress(0)
        self._update_time(0)

    def release(self, path: str):
        """Stop and unload if `path` is the loaded file (so it can be deleted)."""
        if self.path and os.path.normcase(os.path.abspath(self.path)) == os.path.normcase(os.path.abspath(path)):
            self.stop()
            self.app.player.unload()
            self.path = None
            self.peaks = None
            self.title.configure(text="Nothing loaded")
            self._set_enabled(False)
            self._draw_waveform()

    def export(self):
        if not self.path:
            return
        from tkinter import filedialog
        import audio_utils as au
        base = os.path.splitext(os.path.basename(self.path))[0]
        dest = filedialog.asksaveasfilename(
            title="Export audio", initialfile=base, defaultextension=".mp3",
            filetypes=[("MP3 audio", "*.mp3"), ("WAV audio", "*.wav")])
        if not dest:
            return
        try:
            a, sr = au.load_audio(self.path)
            au.save_audio(a, sr, dest)
            self.app.status.done(f"Exported → {dest}")
        except Exception as e:
            self.app.show_error("Export failed", str(e))

    def show_file(self):
        if self.path:
            open_in_explorer(self.path)
