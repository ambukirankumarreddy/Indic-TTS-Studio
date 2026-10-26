"""Main window: sidebar navigation, job runner, preferences, player bar."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import traceback
from tkinter import messagebox
from typing import Callable, Dict, Optional

import customtkinter as ctk

import studio_service as svc
from audio_player import AudioPlayer
from engines import SynthSettings, Voice, get_engine
from . import theme as T
from .widgets import PlayerBar, StatusBar, label, open_in_explorer, sample_for

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFS_FILE = os.path.join(APP_DIR, "studio_prefs.json")

NAV = [
    ("studio", "✎", "Studio"),
    ("dialogue", "☰", "Dialogue"),
    ("audiobook", "▤", "Audiobook"),
    ("subtitles", "⧉", "Subtitles → Voice"),
    ("batch", "≡", "Batch"),
    ("library", "♫", "Library"),
    ("dictionary", "Ꭿ", "Pronunciation"),
    ("engines", "⚙", "Engines & Licenses"),
]


class StudioApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=T.BG)
        self.title("Indic TTS Studio")
        self.geometry("1360x880")
        self.minsize(1120, 720)
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.prefs: Dict = self._load_prefs()
        self.player = AudioPlayer()
        self._ui_q: "queue.Queue[Callable]" = queue.Queue()
        self.job: Optional[svc.Job] = None
        self._busy_widgets = []
        self.pages: Dict[str, ctk.CTkFrame] = {}
        self.current_page: Optional[str] = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        main = ctk.CTkFrame(self, fg_color=T.BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        self.page_host = ctk.CTkFrame(main, fg_color=T.BG)
        self.page_host.grid(row=0, column=0, sticky="nsew", padx=24, pady=(18, 6))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

        self.status = StatusBar(main, self.cancel_job)
        self.status.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 6))
        self.player_bar = PlayerBar(main, self)
        self.player_bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 18))

        self.after(30, self._drain_ui_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_page(self.prefs.get("last_page", "studio"))

    # ------------------------------------------------------------------ layout
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=T.SIDEBAR, corner_radius=0, width=236)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        sb.grid_columnconfigure(0, weight=1)

        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 26))
        mark = ctk.CTkLabel(logo, text="◉", width=42, height=42, corner_radius=12,
                            fg_color=T.ACCENT, text_color="#ffffff", font=T.font(20, "bold"))
        mark.grid(row=0, column=0, rowspan=2, padx=(0, 10))
        ctk.CTkLabel(logo, text="Indic TTS Studio", font=T.font(16, "bold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(logo, text="5 engines · 20+ languages", font=T.font(11), text_color=T.MUTED,
                     anchor="w").grid(row=1, column=1, sticky="w")

        label(sb, "CREATE", 10, T.DIM, "bold").grid(row=1, column=0, sticky="w", padx=22, pady=(0, 4))
        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        r = 2
        for key, icon, text in NAV:
            if key == "library":
                label(sb, "MANAGE", 10, T.DIM, "bold").grid(row=r, column=0, sticky="w",
                                                           padx=22, pady=(16, 4))
                r += 1
            b = ctk.CTkButton(sb, text=f"  {icon}    {text}", anchor="w", height=40, corner_radius=10,
                              fg_color="transparent", hover_color=T.HOVER, text_color=T.MUTED,
                              font=T.font(13, "bold"), command=lambda k=key: self.show_page(k))
            b.grid(row=r, column=0, sticky="ew", padx=12, pady=2)
            self.nav_buttons[key] = b
            r += 1

        sb.grid_rowconfigure(r, weight=1)
        foot = ctk.CTkFrame(sb, fg_color=T.CARD, corner_radius=12)
        foot.grid(row=r + 1, column=0, sticky="ew", padx=12, pady=16)
        foot.grid_columnconfigure(0, weight=1)
        label(foot, "Output folder", 11, T.DIM, "bold").grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        ctk.CTkButton(foot, text="Open generated_audio ↗", height=30, corner_radius=8,
                      fg_color=T.CARD_2, hover_color=T.HOVER, font=T.font(12),
                      command=lambda: open_in_explorer(svc.OUTPUT_DIR)).grid(
            row=1, column=0, sticky="ew", padx=10, pady=(4, 10))

    def show_page(self, key: str):
        from . import pages
        if key not in dict((k, 1) for k, _, _ in NAV):
            key = "studio"
        if key not in self.pages:
            cls = pages.PAGES[key]
            try:
                self.pages[key] = cls(self.page_host, self)
            except Exception as e:
                traceback.print_exc()
                self.show_error("Could not open page", f"{e}")
                return
        if self.current_page and self.current_page in self.pages:
            self.pages[self.current_page].grid_forget()
        self.pages[key].grid(row=0, column=0, sticky="nsew")
        if hasattr(self.pages[key], "on_show"):
            self.pages[key].on_show()
        self.current_page = key
        for k, b in self.nav_buttons.items():
            sel = k == key
            b.configure(fg_color=T.ACCENT_SOFT if sel else "transparent",
                        text_color=T.TEXT if sel else T.MUTED)
        self.prefs["last_page"] = key
        self.save_prefs()

    # ------------------------------------------------------------------ prefs
    def _load_prefs(self) -> Dict:
        try:
            with open(PREFS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_prefs(self):
        try:
            with open(PREFS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.prefs, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # ------------------------------------------------------------------ threading
    def call_ui(self, fn: Callable, *args, **kw):
        """Schedule fn on the Tk main thread (safe to call from worker threads)."""
        self._ui_q.put(lambda: fn(*args, **kw))

    def _drain_ui_queue(self):
        try:
            for _ in range(200):
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.after(30, self._drain_ui_queue)

    def register_busy(self, *widgets):
        self._busy_widgets.extend(widgets)

    def _set_busy(self, busy: bool):
        for w in self._busy_widgets:
            try:
                w.configure(state="disabled" if busy else "normal")
            except Exception:
                pass

    def run_job(self, title: str, work: Callable, on_done: Optional[Callable] = None,
                done_text: Optional[str] = None):
        """Run work(job, progress) on a thread; on_done(result) on the UI thread."""
        if self.job is not None:
            messagebox.showinfo("Busy", "Another task is running. Wait for it or press Cancel.")
            return
        job = svc.Job.new()
        self.job = job
        self._set_busy(True)
        self.status.start(title)
        t0 = time.monotonic()

        def progress(msg, frac=-1):
            self.call_ui(self.status.update_progress, msg, frac)

        def finish(result):
            self.job = None
            self._set_busy(False)
            self.status.done(done_text or f"Done in {time.monotonic() - t0:.1f}s")
            if on_done:
                on_done(result)

        def failed(msg, cancelled=False):
            self.job = None
            self._set_busy(False)
            self.status.done("Cancelled" if cancelled else f"Failed: {msg[:120]}", ok=cancelled)
            if not cancelled:
                self.show_error("Something went wrong", msg)

        def runner():
            try:
                res = work(job, progress)
                self.call_ui(finish, res)
            except svc.Cancelled:
                self.call_ui(failed, "", True)
            except Exception as e:
                traceback.print_exc()
                self.call_ui(failed, friendly_error(e))

        threading.Thread(target=runner, daemon=True).start()

    def cancel_job(self):
        if self.job:
            self.job.cancel_event.set()
            self.status.update_progress("Cancelling after the current part…", -1)

    def show_error(self, title: str, msg: str):
        messagebox.showerror(title, msg)

    # ------------------------------------------------------------------ synthesis helpers
    @staticmethod
    def ensure_ready(voice: Voice, progress):
        e = get_engine(voice.engine_id)
        if not e.is_installed(voice):
            progress(f"Downloading {e.name} voice ({e.install_size_hint(voice)})…", -1)
            e.install(voice, progress)
        if not e.is_loaded():
            progress(f"Loading {e.name}… (first load can take a minute)", -1)
            e.load(progress)

    def preview_voice(self, voice: Voice, language: str, settings: SynthSettings, on_done=None):
        text = sample_for(language)
        path = os.path.join(svc.OUTPUT_DIR, "_preview.wav")

        def work(job, progress):
            self.ensure_ready(voice, progress)
            a, sr = svc.synthesize_text(voice, text, settings, language, progress, job)
            self.call_ui(self.player_bar.release, path)
            time.sleep(0.15)
            import audio_utils as au
            au.save_audio(a, sr, path)
            return path

        def done(p):
            self.player_bar.load(p, f"Preview · {voice.name} — {text}")
            if on_done:
                on_done()
        self.run_job(f"Preview · {voice.name}", work, on_done=done)

    def play_item(self, item: dict, autoplay=True):
        title = f"{item.get('kind', '')} · {item.get('voice', '')} — {item.get('text', '')}"
        self.player_bar.load(item["wav_path"], title, autoplay=autoplay)
        lib = self.pages.get("library")
        if lib is not None:
            lib.mark_dirty()

    def _on_close(self):
        if self.job:
            self.job.cancel_event.set()
        self.save_prefs()
        try:
            self.player.unload()
        except Exception:
            pass
        self.destroy()
        os._exit(0)  # don't wait for model threads


def friendly_error(e: Exception) -> str:
    msg = str(e) or e.__class__.__name__
    low = msg.lower()
    if "cuda out of memory" in low or "outofmemory" in low:
        return ("The GPU ran out of memory. Try shorter text, switch Parler to FP16 in "
                "Engines & Licenses, or use another engine.\n\n" + msg)
    if "getaddrinfo" in low or "connection" in low or "timed out" in low:
        return ("Network problem. Edge voices and first-time downloads need internet.\n\n" + msg)
    return msg


def run():
    app = StudioApp()
    app.mainloop()
