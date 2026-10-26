"""Studio pages: Studio, Dialogue, Audiobook, Subtitles, Batch, Library, Dictionary, Engines."""

from __future__ import annotations

import csv
import os
import subprocess
import time
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Dict, List, Optional

import customtkinter as ctk
import numpy as np

import audio_utils as au
import studio_service as svc
import text_pipeline as tp
from engines import SynthSettings, all_engines, get_engine
from . import theme as T
from .widgets import (Badge, Card, LabeledSlider, SettingsPanel, VoicePicker, all_languages,
                      ghost_button, indic_textbox, label, open_in_explorer, option_menu,
                      primary_button, sample_for, switch)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Base page
# ---------------------------------------------------------------------------
class Page(ctk.CTkFrame):
    title = ""
    subtitle = ""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text=self.title, font=T.font(24, "bold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text=self.subtitle, font=T.font(13), text_color=T.MUTED,
                     anchor="w").grid(row=1, column=0, sticky="w")
        self.head_actions = ctk.CTkFrame(head, fg_color="transparent")
        self.head_actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def two_columns(self, right_width=372):
        left = ctk.CTkFrame(self.content, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        left.grid_columnconfigure(0, weight=1)
        right = ctk.CTkScrollableFrame(self.content, width=right_width, fg_color="transparent",
                                       scrollbar_button_color=T.CARD_2,
                                       scrollbar_button_hover_color=T.HOVER)
        right.grid(row=0, column=1, sticky="ns")
        right.grid_columnconfigure(0, weight=1)
        return left, right

    def voice_and_style(self, parent, pref_key, row=0):
        """Voice card + style card + format selector. Returns (picker, settings, fmt_var)."""
        vcard = Card(parent, "Voice")
        vcard.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        settings_holder = {}
        picker = VoicePicker(vcard.body, self.app, pref_key,
                             on_change=lambda v, e: settings_holder["s"].set_engine(e),
                             settings_provider=lambda: settings_holder["s"].get())
        picker.grid(row=0, column=0, sticky="ew")
        scard = Card(parent, "Style")
        scard.grid(row=row + 1, column=0, sticky="ew", pady=(0, 12))
        settings = SettingsPanel(scard.body)
        settings.grid(row=0, column=0, sticky="ew")
        settings_holder["s"] = settings
        settings.set_engine(picker.engine)
        fmt = self.format_selector(parent, pref_key, row + 2)
        return picker, settings, fmt

    def format_selector(self, parent, pref_key, row, default="WAV"):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        f.grid_columnconfigure(1, weight=1)
        label(f, "Save as", 12, T.MUTED).grid(row=0, column=0, padx=(2, 10))
        var = ctk.StringVar(value=self.app.prefs.get(f"fmt.{pref_key}", default))
        seg = ctk.CTkSegmentedButton(f, values=["WAV", "MP3"], variable=var, height=32,
                                     selected_color=T.ACCENT, selected_hover_color=T.ACCENT_HOVER,
                                     unselected_color=T.CARD_2, unselected_hover_color=T.HOVER,
                                     fg_color=T.CARD_2, font=T.font(12, "bold"),
                                     command=lambda v: self._save_pref(f"fmt.{pref_key}", v))
        seg.grid(row=0, column=1, sticky="ew")
        return var

    def _save_pref(self, k, v):
        self.app.prefs[k] = v
        self.app.save_prefs()

    def require_voice(self, picker):
        v = picker.voice
        if not v:
            messagebox.showwarning("No voice", "Please choose a voice first.")
        return v


# ---------------------------------------------------------------------------
# Studio
# ---------------------------------------------------------------------------
class StudioPage(Page):
    title = "Studio"
    subtitle = "Type or paste text, pick a voice, and generate natural speech."

    def __init__(self, master, app):
        super().__init__(master, app)
        left, right = self.two_columns()
        left.grid_rowconfigure(0, weight=1)

        card = Card(left, "Script", "Any length — long text is split at sentence boundaries automatically.")
        card.grid(row=0, column=0, sticky="nsew")
        card.body.grid_rowconfigure(1, weight=1)
        bar = ctk.CTkFrame(card.body, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ghost_button(bar, "✦ Sample", self.sample, width=90).grid(row=0, column=0, padx=(0, 6))
        ghost_button(bar, "⎘ Paste", self.paste, width=80).grid(row=0, column=1, padx=(0, 6))
        ghost_button(bar, "✕ Clear", lambda: self.text.delete("1.0", "end"), width=80).grid(row=0, column=2)
        bar.grid_columnconfigure(3, weight=1)
        self.dict_sw, self.use_dict = switch(bar, "Pronunciation dictionary", app.prefs.get("use_dict", True))
        self.dict_sw.grid(row=0, column=4, padx=(0, 14))
        self.num_sw, self.read_nums = switch(bar, "Read numbers as words", app.prefs.get("read_nums", True))
        self.num_sw.grid(row=0, column=5)

        self.text = indic_textbox(card.body, height=300, size=17)
        self.text.grid(row=1, column=0, sticky="nsew")
        self.text.insert("1.0", app.prefs.get("studio_text", sample_for("Hindi")))
        self.text.bind("<KeyRelease>", lambda e: self._count())
        self.text.bind("<Control-Return>", lambda e: (self.generate(), "break")[1])
        foot = ctk.CTkFrame(card.body, fg_color="transparent")
        foot.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        foot.grid_columnconfigure(0, weight=1)
        self.count_lbl = label(foot, "", 12, T.MUTED)
        self.count_lbl.grid(row=0, column=0, sticky="w")
        label(foot, "Ctrl+Enter to generate", 11, T.DIM).grid(row=0, column=1, sticky="e")

        self.picker, self.settings, self.fmt = self.voice_and_style(right, "studio")
        self.picker.on_change = lambda v, e: (self.settings.set_engine(e), self._count())
        self.gen_btn = primary_button(right, "✦  Generate speech", self.generate)
        self.gen_btn.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        app.register_busy(self.gen_btn)
        self._count()

    def sample(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", sample_for(self.picker.language))
        self._count()

    def paste(self):
        try:
            self.text.insert("insert", self.clipboard_get())
        except Exception:
            pass
        self._count()

    def _count(self):
        t = self.text.get("1.0", "end").strip()
        e = self.picker.engine
        parts = len(tp.split_text_into_chunks(t, e.max_chunk_chars)) if (t and e) else 0
        words = len(t.split())
        self.count_lbl.configure(text=f"{len(t):,} characters · {words:,} words · {parts} part(s)"
                                      f" · ≈ {words / 2.3 / 60:.1f} min of audio")

    def generate(self):
        text = self.text.get("1.0", "end").strip()
        v = self.require_voice(self.picker)
        if not v or not text:
            if not text:
                messagebox.showwarning("No text", "Please type some text first.")
            return
        s, lang = self.settings.get(), self.picker.language
        ud, rn, ext = self.use_dict.get(), self.read_nums.get(), self.fmt.get().lower()
        self.app.prefs.update(studio_text=text[:5000], use_dict=ud, read_nums=rn)
        self.app.save_prefs()

        def work(job, progress):
            t0 = time.time()
            self.app.ensure_ready(v, progress)
            a, sr = svc.synthesize_text(v, text, s, lang, progress, job, ud, rn)
            return svc.save_result(a, sr, v.name, text, f"{v.name} ({get_engine(v.engine_id).name})",
                                   "Studio", ext, time.time() - t0)
        self.app.run_job(f"Generating with {v.name}", work, on_done=self.app.play_item)


# ---------------------------------------------------------------------------
# Dialogue
# ---------------------------------------------------------------------------
DIALOGUE_SAMPLE = """[Rohit] नमस्ते प्रिया! आज मौसम कितना अच्छा है।
[Priya] हाँ रोहित, चलो शाम को पार्क चलते हैं।
[Rohit] ठीक है, मैं पाँच बजे तैयार रहूँगा।
[Priya] बढ़िया! मिलते हैं।"""

SPEAKER_COLORS = [T.ACCENT, T.TEAL, T.SUCCESS, T.WARN, T.INFO, "#f472b6", "#a3e635", "#fb923c"]


class DialoguePage(Page):
    title = "Dialogue"
    subtitle = "Multi-speaker conversations. Write [Name] text or Name: text — one line per turn."

    def __init__(self, master, app):
        super().__init__(master, app)
        self.content.grid_columnconfigure(0, weight=5)
        self.content.grid_columnconfigure(1, weight=6)
        self.casts: Dict[str, dict] = {}

        card = Card(self.content, "Script")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        card.body.grid_rowconfigure(0, weight=1)
        self.text = indic_textbox(card.body, height=300, size=16)
        self.text.grid(row=0, column=0, sticky="nsew")
        self.text.insert("1.0", app.prefs.get("dialogue_text", DIALOGUE_SAMPLE))
        row = ctk.CTkFrame(card.body, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ghost_button(row, "⟳  Detect speakers", self.detect, width=150).grid(row=0, column=0)
        ghost_button(row, "✦ Example", self.example, width=90).grid(row=0, column=1, padx=6)
        self.info = label(row, "", 12, T.MUTED)
        self.info.grid(row=0, column=2, padx=6)

        right = Card(self.content, "Cast", "Give every speaker a voice. You can mix engines freely.")
        right.grid(row=0, column=1, sticky="nsew")
        right.body.grid_rowconfigure(0, weight=1)
        self.cast_frame = ctk.CTkScrollableFrame(right.body, fg_color="transparent",
                                                 scrollbar_button_color=T.CARD_2)
        self.cast_frame.grid(row=0, column=0, sticky="nsew")
        self.cast_frame.grid_columnconfigure(0, weight=1)
        bottom = ctk.CTkFrame(right.body, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        self.gap = LabeledSlider(bottom, "Pause between turns", 0.0, 2.0,
                                 app.prefs.get("dialogue_gap", 0.5), 40, "{:.2f} s")
        self.gap.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.fmt = self.format_selector(bottom, "dialogue", 1)
        self.gen_btn = primary_button(bottom, "✦  Generate conversation", self.generate)
        self.gen_btn.grid(row=2, column=0, sticky="ew")
        app.register_busy(self.gen_btn)
        self.detect()

    def example(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", DIALOGUE_SAMPLE)
        self.detect()

    def detect(self):
        script = self.text.get("1.0", "end")
        speakers = tp.dialogue_speakers(script)
        lines = tp.parse_dialogue(script)
        self.info.configure(text=f"{len(lines)} turns · {len(speakers)} speakers")
        for name in list(self.casts):
            if name not in speakers:
                self.casts.pop(name)["frame"].destroy()
        for i, name in enumerate(speakers):
            if name in self.casts:
                self.casts[name]["frame"].grid(row=i, column=0, sticky="ew", pady=(0, 10))
                continue
            f = ctk.CTkFrame(self.cast_frame, fg_color=T.CARD_2, corner_radius=12)
            f.grid(row=i, column=0, sticky="ew", pady=(0, 10))
            f.grid_columnconfigure(1, weight=1)
            color = SPEAKER_COLORS[i % len(SPEAKER_COLORS)]
            ctk.CTkLabel(f, text=f"  {name}  ", fg_color=color, text_color="#0e1016", corner_radius=8,
                         font=T.font(12, "bold", T.FONT_INDIC), height=24).grid(
                row=0, column=0, sticky="w", padx=12, pady=(10, 6))
            speed = LabeledSlider(f, "Speed", 0.5, 2.0, 1.0, 30, "{:.2f}×")
            speed.grid(row=0, column=1, sticky="ew", padx=(20, 12), pady=(8, 4))
            key = f"dialogue.{name}"
            had_pref = f"voice.{key}" in self.app.prefs
            picker = VoicePicker(f, self.app, key, compact=True)
            picker.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 12))
            if not had_pref and i % 2 == 1:
                picker.select_other_gender()
            self.casts[name] = {"frame": f, "picker": picker, "speed": speed}

    def generate(self):
        script = self.text.get("1.0", "end").strip()
        self.detect()
        lines = tp.parse_dialogue(script)
        if not lines:
            messagebox.showwarning("Empty script", "Write at least one line like:  [Rohit] नमस्ते!")
            return
        voice_map, settings_map = {}, {}
        for name, c in self.casts.items():
            v = c["picker"].voice
            if not v:
                messagebox.showwarning("Missing voice", f"Choose a voice for {name}.")
                return
            voice_map[name] = v
            settings_map[name] = SynthSettings(speed=round(c["speed"].get(), 2))
        gap, ext = self.gap.get(), self.fmt.get().lower()
        self.app.prefs.update(dialogue_text=script[:5000], dialogue_gap=gap)
        self.app.save_prefs()

        def work(job, progress):
            t0 = time.time()
            for v in {v.key: v for v in voice_map.values()}.values():
                self.app.ensure_ready(v, progress)
            a, sr = svc.synthesize_dialogue(lines, voice_map, settings_map, gap, progress, job)
            desc = ", ".join(f"{n}={v.name}" for n, v in voice_map.items())
            return svc.save_result(a, sr, "dialogue", script, desc, "Dialogue", ext, time.time() - t0)
        self.app.run_job("Generating conversation", work, on_done=self.app.play_item)


# ---------------------------------------------------------------------------
# Audiobook
# ---------------------------------------------------------------------------
class AudiobookPage(Page):
    title = "Audiobook"
    subtitle = "Turn a TXT, DOCX or PDF into chapter-by-chapter audio. Legacy KrutiDev PDFs are converted."

    def __init__(self, master, app):
        super().__init__(master, app)
        left, right = self.two_columns()
        left.grid_rowconfigure(1, weight=1)
        self.chapters: List = []
        self.checks: List[ctk.BooleanVar] = []
        self.book_name = "book"

        top = Card(left, "Book")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        r = ctk.CTkFrame(top.body, fg_color="transparent")
        r.grid(row=0, column=0, sticky="ew")
        r.grid_columnconfigure(1, weight=1)
        ghost_button(r, "⇪  Import file…", self.import_file, width=140, height=36).grid(row=0, column=0)
        self.file_lbl = label(r, "No file loaded", 13, T.TEXT)
        self.file_lbl.grid(row=0, column=1, sticky="ew", padx=12)
        self.note = label(top.body, "", 11, T.WARN, wraplength=640)
        self.note.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        mid = ctk.CTkFrame(left, fg_color="transparent")
        mid.grid(row=1, column=0, sticky="nsew")
        mid.grid_columnconfigure(0, weight=2)
        mid.grid_columnconfigure(1, weight=3)
        mid.grid_rowconfigure(0, weight=1)
        chap_card = Card(mid, "Chapters")
        chap_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        chap_card.body.grid_rowconfigure(1, weight=1)
        sel = ctk.CTkFrame(chap_card.body, fg_color="transparent")
        sel.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ghost_button(sel, "All", lambda: self._select(True), width=60, height=26).grid(row=0, column=0)
        ghost_button(sel, "None", lambda: self._select(False), width=60, height=26).grid(row=0, column=1, padx=6)
        self.chap_list = ctk.CTkScrollableFrame(chap_card.body, fg_color="transparent",
                                                scrollbar_button_color=T.CARD_2)
        self.chap_list.grid(row=1, column=0, sticky="nsew")
        self.chap_list.grid_columnconfigure(0, weight=1)
        prev_card = Card(mid, "Preview (editable)")
        prev_card.grid(row=0, column=1, sticky="nsew")
        prev_card.body.grid_rowconfigure(0, weight=1)
        self.preview = indic_textbox(prev_card.body, height=200, size=15)
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview.bind("<KeyRelease>", lambda e: self._store_edit())
        self.current = -1

        self.picker, self.settings, self.fmt = self.voice_and_style(right, "audiobook")
        opt = Card(right, "Output")
        opt.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.each_sw, self.each = switch(opt.body, "One file per chapter", True)
        self.each_sw.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.comb_sw, self.combined = switch(opt.body, "One combined file", True)
        self.comb_sw.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self.pause = LabeledSlider(opt.body, "Pause between chapters", 0.5, 5.0, 2.0, 18, "{:.1f} s")
        self.pause.grid(row=2, column=0, sticky="ew")
        self.gen_btn = primary_button(right, "✦  Create audiobook", self.generate)
        self.gen_btn.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        app.register_busy(self.gen_btn)
        self._show_empty()

    def _show_empty(self):
        label(self.chap_list, "Import a book to see its chapters.\nHeadings like “Chapter 1”, "
                              "“अध्याय 2” or “भाग 3” are detected automatically.", 12, T.DIM).grid(
            row=0, column=0, sticky="ew", pady=20)

    def import_file(self):
        path = filedialog.askopenfilename(title="Choose a book",
                                          filetypes=[("Documents", "*.txt *.docx *.pdf *.md"),
                                                     ("All files", "*.*")])
        if not path:
            return
        import documents

        def work(job, progress):
            progress("Reading document…", -1)
            d = documents.read_document(path)
            return d, documents.split_chapters(d["text"])

        def done(res):
            d, chapters = res
            self.book_name = os.path.splitext(os.path.basename(path))[0]
            self.file_lbl.configure(text=f"{os.path.basename(path)}  ·  {len(d['text']):,} characters")
            self.note.configure(text=d.get("note", ""))
            self.chapters = chapters
            self._fill()
        self.app.run_job("Importing book", work, on_done=done, done_text="Book imported")

    def _fill(self):
        for w in self.chap_list.winfo_children():
            w.destroy()
        self.checks = []
        if not self.chapters:
            label(self.chap_list, "No readable text found in this file.", 12, T.WARN).grid(row=0, column=0)
            return
        for i, ch in enumerate(self.chapters):
            var = ctk.BooleanVar(value=True)
            self.checks.append(var)
            row = ctk.CTkFrame(self.chap_list, fg_color=T.CARD_2, corner_radius=10)
            row.grid(row=i, column=0, sticky="ew", pady=3)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkCheckBox(row, text="", variable=var, width=24, fg_color=T.ACCENT,
                            hover_color=T.ACCENT_HOVER, border_color=T.BORDER).grid(row=0, column=0, padx=(8, 0), pady=6)
            b = ctk.CTkButton(row, text=f"{i + 1:02d}  {ch.title[:40]}", anchor="w", fg_color="transparent",
                              hover_color=T.HOVER, text_color=T.TEXT, font=T.font(12, "normal", T.FONT_INDIC),
                              command=lambda k=i: self._open(k), height=28)
            b.grid(row=0, column=1, sticky="ew")
            label(row, f"{len(ch.text):,}", 11, T.DIM).grid(row=0, column=2, padx=8)
        self._open(0)

    def _open(self, i):
        self.current = i
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", self.chapters[i].text)

    def _store_edit(self):
        if 0 <= self.current < len(self.chapters):
            self.chapters[self.current].text = self.preview.get("1.0", "end").strip()

    def _select(self, on):
        for v in self.checks:
            v.set(on)

    def generate(self):
        sel = [(i, c) for i, c in enumerate(self.chapters) if i < len(self.checks) and self.checks[i].get()]
        v = self.require_voice(self.picker)
        if not v:
            return
        if not sel:
            messagebox.showwarning("Nothing selected", "Import a book and tick at least one chapter.")
            return
        each, comb = self.each.get(), self.combined.get()
        if not each and not comb:
            messagebox.showwarning("No output", "Turn on per-chapter files, the combined file, or both.")
            return
        s, lang, ext, pause = self.settings.get(), self.picker.language, self.fmt.get().lower(), self.pause.get()
        book = self.book_name
        folder = os.path.join(svc.OUTPUT_DIR, "audiobooks",
                              f"{book[:30]}_{datetime.now():%Y%m%d_%H%M%S}")
        vdesc = f"{v.name} ({get_engine(v.engine_id).name})"

        def work(job, progress):
            t0 = time.time()
            self.app.ensure_ready(v, progress)
            os.makedirs(folder, exist_ok=True)
            parts, last, n = [], None, len(sel)
            for k, (i, ch) in enumerate(sel):
                def p(msg, f, k=k, ch=ch):
                    progress(f"Chapter {k + 1}/{n} · {ch.title[:30]} · {msg}", (k + max(f, 0)) / n)
                a, sr = svc.synthesize_text(v, ch.text, s, lang, p, job)
                if each:
                    path = os.path.join(folder, f"{i + 1:02d}_{_safe(ch.title)}.{ext}")
                    last = svc.save_result(a, sr, book, ch.text, vdesc, "Audiobook", ext,
                                           extra={"chapter": ch.title}, path=path)
                if comb:
                    parts.append((a, sr))
            if comb and parts:
                sr0 = parts[0][1]
                joined = []
                for j, (a, sr) in enumerate(parts):
                    joined.append(au.resample(a, sr, sr0))
                    if j < len(parts) - 1:
                        joined.append(au.silence(sr0, pause))
                full = np.concatenate(joined)
                last = svc.save_result(full, sr0, book, f"{book} — {len(parts)} chapters", vdesc,
                                       "Audiobook", ext, time.time() - t0,
                                       path=os.path.join(folder, f"{_safe(book)}_full.{ext}"))
            return last

        def done(item):
            if item:
                self.app.play_item(item, autoplay=False)
            open_in_explorer(folder)
        self.app.run_job(f"Creating audiobook ({len(sel)} chapters)", work, on_done=done)


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_ " else "_" for c in s).strip()[:40] or "part"


# ---------------------------------------------------------------------------
# Subtitles -> voiceover
# ---------------------------------------------------------------------------
SRT_SAMPLE = """1
00:00:00,500 --> 00:00:03,000
नमस्ते, हमारे चैनल में आपका स्वागत है।

2
00:00:03,500 --> 00:00:07,000
आज हम सीखेंगे कि अच्छी आवाज़ कैसे बनाई जाती है।
"""


class SubtitlesPage(Page):
    title = "Subtitles → Voiceover"
    subtitle = "Load an .srt file and get speech timed to every cue, with optional background music ducking."

    def __init__(self, master, app):
        super().__init__(master, app)
        left, right = self.two_columns()
        left.grid_rowconfigure(0, weight=1)
        self.music_path: Optional[str] = None

        card = Card(left, "Subtitles (.srt)", "Load a file or paste SRT text below. You can edit lines before generating.")
        card.grid(row=0, column=0, sticky="nsew", pady=(0, 12))
        card.body.grid_rowconfigure(1, weight=1)
        r = ctk.CTkFrame(card.body, fg_color="transparent")
        r.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        r.grid_columnconfigure(2, weight=1)
        ghost_button(r, "⇪  Load .srt…", self.load_srt, width=120, height=34).grid(row=0, column=0)
        ghost_button(r, "✦ Example", self.example, width=90, height=34).grid(row=0, column=1, padx=6)
        self.info = label(r, "", 12, T.MUTED)
        self.info.grid(row=0, column=2, sticky="e")
        self.text = indic_textbox(card.body, height=260, size=14)
        self.text.grid(row=1, column=0, sticky="nsew")
        self.text.insert("1.0", app.prefs.get("srt_text", SRT_SAMPLE))
        self.text.bind("<KeyRelease>", lambda e: self._update_info())

        mus = Card(left, "Background music (optional)")
        mus.grid(row=1, column=0, sticky="ew")
        m = ctk.CTkFrame(mus.body, fg_color="transparent")
        m.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        m.grid_columnconfigure(1, weight=1)
        ghost_button(m, "♫  Choose music…", self.choose_music, width=140).grid(row=0, column=0)
        self.music_lbl = label(m, "None", 12, T.TEXT)
        self.music_lbl.grid(row=0, column=1, sticky="ew", padx=10)
        ghost_button(m, "✕", self.clear_music, width=36).grid(row=0, column=2)
        sl = ctk.CTkFrame(mus.body, fg_color="transparent")
        sl.grid(row=1, column=0, sticky="ew")
        sl.grid_columnconfigure((0, 1, 2), weight=1, uniform="s")
        self.music_db = LabeledSlider(sl, "Music level", -36, 0, -18, 36, "{:.0f} dB")
        self.music_db.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.duck_db = LabeledSlider(sl, "Duck under speech", -30, 0, -12, 30, "{:.0f} dB")
        self.duck_db.grid(row=0, column=1, sticky="ew", padx=10)
        self.fade = LabeledSlider(sl, "Duck fade", 50, 1000, 300, 19, "{:.0f} ms")
        self.fade.grid(row=0, column=2, sticky="ew", padx=(10, 0))

        self.picker, self.settings, self.fmt = self.voice_and_style(right, "subtitles")
        tcard = Card(right, "Timing")
        tcard.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.compress = LabeledSlider(tcard.body, "Max speed-up to fit a cue", 1.0, 2.0, 1.5, 20, "{:.2f}×")
        self.compress.grid(row=0, column=0, sticky="ew")
        label(tcard.body, "If a line is longer than its cue, it is sped up by at most this much; "
                          "anything still too long overlaps slightly.", 11, T.DIM, wraplength=300).grid(
            row=1, column=0, sticky="ew", pady=(6, 0))
        self.gen_btn = primary_button(right, "✦  Render voiceover", self.generate)
        self.gen_btn.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        app.register_busy(self.gen_btn)
        self._update_info()

    def example(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", SRT_SAMPLE)
        self._update_info()

    def load_srt(self):
        import subtitles as st
        path = filedialog.askopenfilename(title="Choose subtitles", filetypes=[("SubRip", "*.srt"), ("All", "*.*")])
        if not path:
            return
        for enc in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                with open(path, encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeError:
                continue
        else:
            messagebox.showerror("Could not read", "Please save the .srt as UTF-8.")
            return
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self._update_info()

    def _update_info(self):
        import subtitles as st
        try:
            cues = st.parse_srt(self.text.get("1.0", "end"))
        except Exception:
            cues = []
        if cues:
            end = max(c.end for c in cues)
            self.info.configure(text=f"{len(cues)} cues · {int(end // 60)}:{int(end % 60):02d} long")
        else:
            self.info.configure(text="No cues found")

    def choose_music(self):
        p = filedialog.askopenfilename(title="Background music",
                                       filetypes=[("Audio", "*.mp3 *.wav *.flac *.ogg"), ("All", "*.*")])
        if p:
            self.music_path = p
            self.music_lbl.configure(text=os.path.basename(p))

    def clear_music(self):
        self.music_path = None
        self.music_lbl.configure(text="None")

    def generate(self):
        import subtitles as st
        raw = self.text.get("1.0", "end")
        cues = st.parse_srt(raw)
        v = self.require_voice(self.picker)
        if not v:
            return
        if not cues:
            messagebox.showwarning("No cues", "No subtitle cues found. Check the SRT format.")
            return
        s, ext = self.settings.get(), self.fmt.get().lower()
        mc, mdb, ddb, fade = self.compress.get(), self.music_db.get(), self.duck_db.get(), self.fade.get()
        music_path = self.music_path
        self.app.prefs["srt_text"] = raw[:20000]
        self.app.save_prefs()

        def work(job, progress):
            t0 = time.time()
            self.app.ensure_ready(v, progress)
            music, msr = (None, 0)
            if music_path:
                progress("Loading music…", -1)
                music, msr = au.load_audio(music_path)
            a, sr, stats = st.render_voiceover(cues, v, s, mc, music, msr, mdb, ddb, fade, progress, job)
            item = svc.save_result(a, sr, "voiceover", " ".join(c.text for c in cues), v.name,
                                   "Subtitles", ext, time.time() - t0, extra={"stats": stats})
            return item, stats

        def done(res):
            item, stats = res
            self.app.play_item(item)
            self.app.status.done(f"Voiced {stats['voiced']} cues · sped up {stats['compressed']} · "
                                 f"overran {stats['overrun']} · failed {stats['failed']}",
                                 ok=stats["failed"] == 0)
        self.app.run_job("Rendering voiceover", work, on_done=done)


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------
class BatchPage(Page):
    title = "Batch"
    subtitle = "Many short clips at once — one line becomes one audio file."

    def __init__(self, master, app):
        super().__init__(master, app)
        left, right = self.two_columns()
        left.grid_rowconfigure(0, weight=1)
        card = Card(left, "Lines", "Each non-empty line is generated as its own file. Load a .txt or .csv (first column).")
        card.grid(row=0, column=0, sticky="nsew")
        card.body.grid_rowconfigure(1, weight=1)
        r = ctk.CTkFrame(card.body, fg_color="transparent")
        r.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        r.grid_columnconfigure(1, weight=1)
        ghost_button(r, "⇪  Load file…", self.load, width=120, height=34).grid(row=0, column=0)
        self.info = label(r, "", 12, T.MUTED)
        self.info.grid(row=0, column=1, sticky="e")
        self.text = indic_textbox(card.body, height=300, size=15)
        self.text.grid(row=1, column=0, sticky="nsew")
        self.text.insert("1.0", app.prefs.get("batch_text", "स्टेशन पर आपका स्वागत है।\n"
                                                           "कृपया अपने सामान का ध्यान रखें।\n"
                                                           "गाड़ी प्लेटफ़ॉर्म नंबर 3 पर आ रही है।"))
        self.text.bind("<KeyRelease>", lambda e: self._info())

        self.picker, self.settings, self.fmt = self.voice_and_style(right, "batch")
        opt = Card(right, "Output")
        opt.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        self.merge_sw, self.merge = switch(opt.body, "Also merge all lines into one file", False)
        self.merge_sw.grid(row=0, column=0, sticky="w")
        self.gen_btn = primary_button(right, "✦  Generate all", self.generate)
        self.gen_btn.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        app.register_busy(self.gen_btn)
        self._info()

    def _lines(self):
        return [l.strip() for l in self.text.get("1.0", "end").splitlines() if l.strip()]

    def _info(self):
        self.info.configure(text=f"{len(self._lines())} lines")

    def load(self):
        p = filedialog.askopenfilename(filetypes=[("Text / CSV", "*.txt *.csv"), ("All", "*.*")])
        if not p:
            return
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            if p.lower().endswith(".csv"):
                lines = [row[0] for row in csv.reader(f) if row and row[0].strip()]
            else:
                lines = [l for l in f.read().splitlines() if l.strip()]
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "\n".join(lines))
        self._info()

    def generate(self):
        lines = self._lines()
        v = self.require_voice(self.picker)
        if not v:
            return
        if not lines:
            messagebox.showwarning("No lines", "Add at least one line of text.")
            return
        s, lang, ext, merge = self.settings.get(), self.picker.language, self.fmt.get().lower(), self.merge.get()
        self.app.prefs["batch_text"] = "\n".join(lines)[:20000]
        self.app.save_prefs()
        folder = os.path.join(svc.OUTPUT_DIR, f"batch_{datetime.now():%Y%m%d_%H%M%S}")

        def work(job, progress):
            self.app.ensure_ready(v, progress)
            os.makedirs(folder, exist_ok=True)
            n, ok, failed, last, parts = len(lines), 0, 0, None, []
            for i, line in enumerate(lines):
                job.check()
                progress(f"Line {i + 1}/{n}", i / n)
                try:
                    a, sr = svc.synthesize_text(v, line, s, lang, None, job)
                    last = svc.save_result(a, sr, "batch", line, v.name, "Batch", ext,
                                           path=os.path.join(folder, f"{i + 1:03d}_{_safe(line[:24])}.{ext}"))
                    if merge:
                        parts.append((a, sr))
                    ok += 1
                except svc.Cancelled:
                    raise
                except Exception as e:
                    print(f"[batch] line {i + 1} failed: {e}")
                    failed += 1
            if merge and parts:
                sr0 = parts[0][1]
                seq = []
                for a, sr in parts:
                    seq += [au.resample(a, sr, sr0), au.silence(sr0, 0.6)]
                last = svc.save_result(np.concatenate(seq), sr0, "batch_all", "\n".join(lines), v.name,
                                       "Batch", ext, path=os.path.join(folder, f"all_lines.{ext}"))
            return last, ok, failed

        def done(res):
            last, ok, failed = res
            if last:
                self.app.play_item(last, autoplay=False)
            self.app.status.done(f"Batch finished: {ok} ok, {failed} failed → {folder}", ok=failed == 0)
            open_in_explorer(folder)
        self.app.run_job(f"Batch · {len(lines)} lines", work, on_done=done)


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------
class LibraryPage(Page):
    title = "Library"
    subtitle = "Everything you have generated. Click ▶ to load it into the player."
    PAGE_SIZE = 40

    def __init__(self, master, app):
        super().__init__(master, app)
        self.kind = ctk.StringVar(value="All")
        seg = ctk.CTkSegmentedButton(self.head_actions, values=["All", "Studio", "Dialogue", "Audiobook",
                                                                "Subtitles", "Batch"],
                                     variable=self.kind, command=lambda v: self.refresh(),
                                     selected_color=T.ACCENT, selected_hover_color=T.ACCENT_HOVER,
                                     unselected_color=T.CARD_2, unselected_hover_color=T.HOVER,
                                     fg_color=T.CARD_2, font=T.font(12, "bold"), height=32)
        seg.grid(row=0, column=0, padx=(0, 10))
        self.search = ctk.CTkEntry(self.head_actions, placeholder_text="Search text or voice…", width=220,
                                   height=32, corner_radius=10, fg_color=T.INPUT, border_color=T.BORDER,
                                   font=T.font(12, family=T.FONT_INDIC))
        self.search.grid(row=0, column=1)
        self.search.bind("<KeyRelease>", lambda e: self.refresh())
        self.list = ctk.CTkScrollableFrame(self.content, fg_color="transparent", scrollbar_button_color=T.CARD_2)
        self.list.grid(row=0, column=0, sticky="nsew")
        self.list.grid_columnconfigure(0, weight=1)
        self.limit = self.PAGE_SIZE

    def on_show(self):
        self.refresh()

    def mark_dirty(self):
        pass

    def refresh(self):
        for w in self.list.winfo_children():
            w.destroy()
        q = self.search.get().strip().lower()
        kind = self.kind.get()
        items = [h for h in svc.get_history()
                 if h.get("wav_path") and os.path.isfile(h["wav_path"])
                 and (kind == "All" or h.get("kind", "Studio") == kind)
                 and (not q or q in h.get("text", "").lower() or q in h.get("voice", "").lower())]
        if not items:
            label(self.list, "Nothing here yet. Generate something in Studio!", 14, T.DIM).grid(
                row=0, column=0, pady=40)
            return
        for i, h in enumerate(items[: self.limit]):
            self._row(i, h)
        if len(items) > self.limit:
            ghost_button(self.list, f"Show more ({len(items) - self.limit} left)", self._more).grid(
                row=self.limit, column=0, pady=10)

    def _more(self):
        self.limit += self.PAGE_SIZE
        self.refresh()

    def _row(self, i, h):
        f = ctk.CTkFrame(self.list, fg_color=T.CARD, corner_radius=12, border_width=1, border_color=T.BORDER)
        f.grid(row=i, column=0, sticky="ew", pady=4, padx=(0, 6))
        f.grid_columnconfigure(2, weight=1)
        ctk.CTkButton(f, text="▶", width=40, height=40, corner_radius=20, fg_color=T.ACCENT_SOFT,
                      hover_color=T.ACCENT, text_color=T.TEXT, font=T.font(14, "bold"),
                      command=lambda: self.app.play_item(h)).grid(row=0, column=0, rowspan=2, padx=12, pady=10)
        kind = h.get("kind", "Studio")
        Badge(f, kind, T.CARD_2, T.KIND_COLORS.get(kind, T.MUTED)).grid(row=0, column=1, rowspan=2, padx=(0, 12))
        txt = h.get("text", "").replace("\n", " ")
        ctk.CTkLabel(f, text=(txt[:110] + "…") if len(txt) > 110 else txt, anchor="w",
                     font=T.font(13, family=T.FONT_INDIC), text_color=T.TEXT).grid(
            row=0, column=2, sticky="ew", pady=(10, 0))
        dur = h.get("audio_duration", 0)
        ts = h.get("timestamp", "").replace("T", "  ")
        meta = f"{h.get('voice', '')}   ·   {int(dur // 60)}:{int(dur % 60):02d}   ·   {ts}   ·   {h.get('filename', '')}"
        label(f, meta, 11, T.MUTED).grid(row=1, column=2, sticky="ew", pady=(0, 10))
        ghost_button(f, "↗", lambda: open_in_explorer(h["wav_path"]), width=36).grid(row=0, column=3, rowspan=2, padx=4)
        ghost_button(f, "✕", lambda: self._delete(h), width=36, danger=True).grid(
            row=0, column=4, rowspan=2, padx=(4, 12))

    def _delete(self, h):
        if not messagebox.askyesno("Delete", f"Delete this file?\n\n{h.get('filename')}"):
            return
        self.app.player_bar.release(h["wav_path"])
        try:
            svc.delete_history_item(h["wav_path"])
        except Exception as e:
            messagebox.showerror("Could not delete", str(e))
        self.refresh()


# ---------------------------------------------------------------------------
# Pronunciation dictionary
# ---------------------------------------------------------------------------
class DictionaryPage(Page):
    title = "Pronunciation"
    subtitle = "Teach the studio how to say abbreviations, names and English words. Applies to every engine."

    def __init__(self, master, app):
        super().__init__(master, app)
        self.content.grid_columnconfigure(0, weight=3)
        self.content.grid_columnconfigure(1, weight=2)
        self.rows: List[dict] = []

        card = Card(self.content, "Words")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        card.body.grid_rowconfigure(1, weight=1)
        hdr = ctk.CTkFrame(card.body, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for c, (t, w) in enumerate((("Written", 170), ("Say as", 230), ("Language", 140), ("Exact case", 80))):
            label(hdr, t, 11, T.DIM, "bold", width=w).grid(row=0, column=c, padx=4, sticky="w")
        self.table = ctk.CTkScrollableFrame(card.body, fg_color="transparent", scrollbar_button_color=T.CARD_2)
        self.table.grid(row=1, column=0, sticky="nsew")
        btns = ctk.CTkFrame(card.body, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        btns.grid_columnconfigure(1, weight=1)
        ghost_button(btns, "+  Add word", lambda: self._add_row(tp.DictEntry("", "", "All", False)),
                     width=120, height=36).grid(row=0, column=0)
        primary_button(btns, "Save dictionary", self.save, height=36, width=160).grid(row=0, column=2)
        for e in tp.load_dictionary():
            self._add_row(e)

        test = Card(self.content, "Try it", "See exactly what text will be sent to the voice.")
        test.grid(row=0, column=1, sticky="nsew")
        self.t_lang = option_menu(test.body, all_languages(), width=200)
        self.t_lang.set("Hindi")
        self.t_lang.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.t_in = indic_textbox(test.body, height=120, size=15)
        self.t_in.grid(row=1, column=0, sticky="ew")
        self.t_in.insert("1.0", "Dr. शर्मा ने कहा कि AI और TTS की कीमत ₹2500 है, यानी 15% छूट।")
        ghost_button(test.body, "→  Show spoken text", self.try_it, height=36).grid(row=2, column=0, sticky="ew", pady=10)
        self.t_out = indic_textbox(test.body, height=120, size=15)
        self.t_out.grid(row=3, column=0, sticky="ew")

    def _add_row(self, e):
        r = len(self.rows)
        f = ctk.CTkFrame(self.table, fg_color="transparent")
        f.grid(row=r, column=0, sticky="ew", pady=2)
        kw = dict(height=32, corner_radius=8, fg_color=T.INPUT, border_color=T.BORDER,
                  font=T.font(13, family=T.FONT_INDIC))
        w = ctk.CTkEntry(f, width=170, **kw)
        w.insert(0, e.word)
        w.grid(row=0, column=0, padx=4)
        s = ctk.CTkEntry(f, width=230, **kw)
        s.insert(0, e.say_as)
        s.grid(row=0, column=1, padx=4)
        lang = option_menu(f, ["All"] + all_languages(), width=140)
        lang.set(e.language or "All")
        lang.grid(row=0, column=2, padx=4)
        cs = ctk.BooleanVar(value=e.case_sensitive)
        ctk.CTkCheckBox(f, text="", variable=cs, width=80, fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                        border_color=T.BORDER).grid(row=0, column=3, padx=4)
        row = {"frame": f, "word": w, "say": s, "lang": lang, "cs": cs}
        ghost_button(f, "✕", lambda: self._remove(row), width=32, danger=True).grid(row=0, column=4, padx=4)
        self.rows.append(row)

    def _remove(self, row):
        row["frame"].destroy()
        self.rows.remove(row)

    def _entries(self):
        return [tp.DictEntry(r["word"].get().strip(), r["say"].get().strip(), r["lang"].get(), r["cs"].get())
                for r in self.rows if r["word"].get().strip()]

    def save(self):
        tp.save_dictionary(self._entries())
        self.app.status.done(f"Dictionary saved · {len(self._entries())} words")

    def try_it(self):
        lang = self.t_lang.get()
        txt = self.t_in.get("1.0", "end").strip()
        out = tp.apply_dictionary(txt, lang, self._entries())
        out = tp.normalize_numbers(out, lang)
        self.t_out.delete("1.0", "end")
        self.t_out.insert("1.0", out)


# ---------------------------------------------------------------------------
# Engines & licenses
# ---------------------------------------------------------------------------
class EnginesPage(Page):
    title = "Engines & Licenses"
    subtitle = "What each engine is good at, what it costs to install, and how you may use its voices."

    def __init__(self, master, app):
        super().__init__(master, app)
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent", scrollbar_button_color=T.CARD_2)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure((0, 1), weight=1, uniform="e")
        self.status_labels: Dict[str, ctk.CTkLabel] = {}
        engines = all_engines()
        for i, e in enumerate(engines):
            self._engine_card(scroll, e).grid(row=i // 2, column=i % 2, sticky="nsew", padx=6, pady=6)
        r = (len(engines) + 1) // 2
        self._license_card(scroll, engines).grid(row=r, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        self._credits_card(scroll).grid(row=r + 1, column=0, columnspan=2, sticky="ew", padx=6, pady=6)

    def on_show(self):
        for e in all_engines():
            self._update_status(e)

    def _engine_card(self, parent, e):
        c = Card(parent)
        b = c.body
        top = ctk.CTkFrame(b, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(top, text=e.name, font=T.font(16, "bold"), text_color=T.TEXT, anchor="w").grid(
            row=0, column=0, sticky="w")
        Badge(top, "☁ Online" if e.online else "⌂ Offline",
              "#132a45" if e.online else T.CARD_2, T.INFO if e.online else T.MUTED).grid(row=0, column=1, padx=4)
        bg, fg = T.license_colors(e.license_summary)
        label(b, e.description, 12, T.MUTED, wraplength=440).grid(row=1, column=0, sticky="ew", pady=(6, 6))
        try:
            vs = e.voices()
            langs = e.languages()
        except Exception:
            vs, langs = [], []
        label(b, f"{len(vs)} voices · {len(langs)} languages: {', '.join(langs[:8])}{'…' if len(langs) > 8 else ''}",
              11, T.DIM, wraplength=440).grid(row=2, column=0, sticky="ew")
        lic = ctk.CTkFrame(b, fg_color="transparent")
        lic.grid(row=3, column=0, sticky="w", pady=(8, 0))
        for j, l in enumerate(sorted({v.license for v in vs if v.license}) or [e.license_summary]):
            bb, ff = T.license_colors(l)
            Badge(lic, "⚖ " + l[:60], bb, ff).grid(row=j, column=0, sticky="w", pady=2)
        st = label(b, "", 12, T.TEXT)
        st.grid(row=4, column=0, sticky="ew", pady=(10, 6))
        self.status_labels[e.id] = st
        act = ctk.CTkFrame(b, fg_color="transparent")
        act.grid(row=5, column=0, sticky="ew")
        if e.id == "parler":
            ghost_button(act, "Load model now", lambda: self._load(e), width=140).grid(row=0, column=0)
            sw, var = switch(act, "FP16 (less VRAM, slightly lower quality)", self.app.prefs.get("parler_fp16", False))
            sw.configure(command=lambda: self._fp16(e, var.get()))
            sw.grid(row=0, column=1, padx=12)
            ghost_button(act, "Hugging Face login…", self._hf_login, width=160).grid(row=1, column=0, pady=(8, 0))
        elif e.id == "kokoro":
            ghost_button(act, f"Download ({e.install_size_hint()})", lambda: self._install(e, None),
                         width=200).grid(row=0, column=0)
        elif e.id == "piper":
            ghost_button(act, "Download all Piper voices", lambda: self._install_all(e), width=200).grid(row=0, column=0)
        elif e.id == "edge":
            ghost_button(act, "Refresh voice list", lambda: self._refresh_edge(e), width=160).grid(row=0, column=0)
        elif e.id == "syspin":
            label(act, "Each voice downloads automatically the first time you use it.", 11, T.DIM).grid(row=0, column=0)
        self._update_status(e)
        return c

    def _update_status(self, e):
        lbl = self.status_labels.get(e.id)
        if not lbl:
            return
        try:
            if e.id == "parler":
                txt = ("● Loaded on " + e.device + (" (FP16)" if e.use_fp16 else " (FP32)")) if e.is_loaded() else \
                      ("● Downloaded — loads on first use (≈1 min)" if e.is_installed() else "○ Not downloaded (~3.8 GB)")
            elif e.id == "edge":
                txt = "● Ready — needs internet while generating"
            else:
                vs = e.voices()
                n = sum(1 for v in vs if e.is_installed(v))
                txt = f"● {n} of {len(vs)} voices downloaded" if n else "○ Nothing downloaded yet"
        except Exception as ex:
            txt = f"Status unavailable: {ex}"
        lbl.configure(text=txt, text_color=T.SUCCESS if txt.startswith("●") else T.MUTED)

    def _load(self, e):
        def work(job, progress):
            e.load(progress)
        self.app.run_job("Loading Indic Parler-TTS", work, on_done=lambda _: self._update_status(e))

    def _fp16(self, e, on):
        self.app.prefs["parler_fp16"] = bool(on)
        self.app.save_prefs()
        e.use_fp16 = bool(on)
        if e.is_loaded():
            with e._lock:
                e.model = None
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
        self._update_status(e)

    def _install(self, e, v):
        self.app.run_job(f"Downloading {e.name}", lambda job, p: e.install(v, p),
                         on_done=lambda _: self._update_status(e))

    def _install_all(self, e):
        def work(job, progress):
            for v in e.voices():
                job.check()
                if not e.is_installed(v):
                    e.install(v, progress)
        self.app.run_job(f"Downloading {e.name} voices", work, on_done=lambda _: self._update_status(e))

    def _refresh_edge(self, e):
        import engines.edge_engine as ee

        def work(job, progress):
            progress("Fetching Microsoft voice list…", -1)
            if os.path.isfile(ee.CACHE):
                os.remove(ee.CACHE)
            e._voices = None
            return len(e.voices())
        self.app.run_job("Refreshing Edge voices", work,
                         on_done=lambda n: self.app.status.done(f"Edge voice list refreshed · {n} voices"))

    def _hf_login(self):
        bat = os.path.join(APP_DIR, "login_huggingface.bat")
        if os.path.isfile(bat):
            subprocess.Popen(["cmd", "/c", "start", "", bat], cwd=APP_DIR)

    def _license_card(self, parent, engines):
        c = Card(parent, "Licenses at a glance",
                 "Not legal advice. Check the original licence before selling or publishing audio commercially.")
        rows = [
            ("Indic Parler-TTS", "Apache-2.0", "Yes, with attribution"),
            ("Kokoro-82M", "Apache-2.0", "Yes, with attribution"),
            ("SYSPIN VITS", "CC BY 4.0", "Yes — credit SYSPIN / IISc Bangalore"),
            ("Piper · Pratham, Priyamvada", "CC BY-NC-SA 4.0", "No — non-commercial only"),
            ("Piper · Rohan", "IIT Madras IndicTTS licence", "Check licence terms first"),
            ("Microsoft Edge voices", "Microsoft service terms (online)", "Unclear — review terms first"),
        ]
        for i, (a, b_, cc) in enumerate(rows):
            bg, fg = T.license_colors(b_)
            label(c.body, a, 13, T.TEXT, "bold").grid(row=i, column=0, sticky="w", pady=4)
            Badge(c.body, b_, bg, fg).grid(row=i, column=1, sticky="w", padx=16)
            label(c.body, cc, 12, fg).grid(row=i, column=2, sticky="w")
        c.body.grid_columnconfigure(2, weight=1)
        return c

    def _credits_card(self, parent):
        c = Card(parent, "Credits")
        txt = ("AI4Bharat Indic Parler-TTS · k2-fsa sherpa-onnx (Apache-2.0) · Piper voices (rhasspy) · "
               "Kokoro-82M (hexgrad) · edge-tts (LGPL-3.0) · SYSPIN TTS models (IISc Bangalore, CC BY 4.0) · "
               "lipi by aparsoft (MIT) for KrutiDev → Unicode · music ducking approach adapted from "
               "srt-voiceover-studio by khan57 (MIT) · num2words (LGPL).")
        label(c.body, txt, 12, T.MUTED, wraplength=1000).grid(row=0, column=0, sticky="ew")
        return c


PAGES = {
    "studio": StudioPage, "dialogue": DialoguePage, "audiobook": AudiobookPage,
    "subtitles": SubtitlesPage, "batch": BatchPage, "library": LibraryPage,
    "dictionary": DictionaryPage, "engines": EnginesPage,
}
