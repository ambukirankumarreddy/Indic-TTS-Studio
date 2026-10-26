"""Modern Desktop GUI for Indic Parler-TTS using CustomTkinter."""

import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import queue
from typing import Optional, Dict, Any, List

import customtkinter as ctk

from config import (
    LANGUAGES_DATA,
    EMOTIONS,
    SPEED_OPTIONS,
    PITCH_OPTIONS,
    EXPRESSIVITY_OPTIONS,
    AUDIO_QUALITY_OPTIONS,
    MODEL_ID,
    DEFAULT_OUTPUT_DIR
)
from tts_engine import TTSEngine
from audio_player import AudioPlayer
from batch_processor import BatchProcessor

# Appearance configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

INDIC_FONT_FAMILY = "Nirmala UI" if sys.platform == "win32" else "Segoe UI"


class IndicTTSApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Indic Parler-TTS Studio — AI Text-to-Speech")
        self.geometry("1240x840")
        self.minsize(1050, 720)

        # Initialize engines
        self.engine = TTSEngine(output_dir=os.path.abspath(DEFAULT_OUTPUT_DIR))
        self.player = AudioPlayer()
        self.batch_processor = BatchProcessor(self.engine)

        self.current_result: Optional[Dict[str, Any]] = None

        # Queue for marshalling worker-thread callbacks onto the Tk main thread
        self._ui_queue: "queue.Queue" = queue.Queue()

        # Build UI layout
        self._create_header()
        self._create_tabs()

        # Connect engine callbacks (thread-safe)
        self.engine.on_status_change = self._ui_safe(self._on_engine_status)
        self.engine.on_log = self._ui_safe(self._on_engine_log)

        self.after(50, self._drain_ui_queue)
        self.after(500, self._initial_setup)

    def _ui_safe(self, fn):
        """Wrap a callback so it is executed on the Tk main thread."""
        def _wrapper(*args, **kwargs):
            self._ui_queue.put((fn, args, kwargs))
        return _wrapper

    def _drain_ui_queue(self):
        try:
            while True:
                fn, args, kwargs = self._ui_queue.get_nowait()
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    print(f"[UI] Callback error: {e}")
        except queue.Empty:
            pass
        self.after(50, self._drain_ui_queue)

    def _initial_setup(self):
        # Update device badge
        cuda_avail = self.engine._has_cuda()
        if cuda_avail:
            import torch
            gpu_name = torch.cuda.get_device_name(0)
            self.lbl_device.configure(text=f"🟢 GPU: {gpu_name} (CUDA)", text_color="#10B981")
        else:
            self.lbl_device.configure(text="🟡 Device: CPU (Slow)", text_color="#F59E0B")

        # Select default language
        self.combo_language.set("Hindi")
        self._on_language_change("Hindi")
        self._refresh_history()

    # -------------------------------------------------------------
    # UI Header
    # -------------------------------------------------------------
    def _create_header(self):
        self.header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#18181B", height=70)
        self.header_frame.pack(fill="x", side="top", padx=0, pady=0)
        self.header_frame.pack_propagate(False)

        # Left title
        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=20, pady=10)

        lbl_title = ctk.CTkLabel(
            title_box,
            text="Indic Parler-TTS Studio",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        lbl_title.pack(anchor="w")

        lbl_subtitle = ctk.CTkLabel(
            title_box,
            text="High-Fidelity Neural Speech for 21 Indian Languages • ai4bharat/indic-parler-tts",
            font=ctk.CTkFont(size=12),
            text_color="#A1A1AA"
        )
        lbl_subtitle.pack(anchor="w")

        # Right badges & Model Load Button
        right_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=20, pady=12)

        self.lbl_device = ctk.CTkLabel(
            right_box,
            text="Checking GPU...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#9CA3AF"
        )
        self.lbl_device.pack(side="left", padx=(0, 15))

        self.lbl_status_badge = ctk.CTkLabel(
            right_box,
            text="Model: Not Loaded",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#374151",
            corner_radius=6,
            padx=12,
            pady=4
        )
        self.lbl_status_badge.pack(side="left", padx=(0, 10))

        self.btn_load_model = ctk.CTkButton(
            right_box,
            text="Load Model",
            command=self._cmd_load_model,
            fg_color="#0284C7",
            hover_color="#0369A1",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=110,
            height=32
        )
        self.btn_load_model.pack(side="left")

    # -------------------------------------------------------------
    # Tab View
    # -------------------------------------------------------------
    def _create_tabs(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=10, fg_color="#1E1E24")
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(10, 15))

        self.tab_studio = self.tabview.add("🎙️ Voice Studio")
        self.tab_batch = self.tabview.add("⚡ Batch Generator")
        self.tab_history = self.tabview.add("📜 History & Recordings")
        self.tab_settings = self.tabview.add("⚙️ Settings & Info")

        self._build_studio_tab()
        self._build_batch_tab()
        self._build_history_tab()
        self._build_settings_tab()

    # -------------------------------------------------------------
    # TAB 1: STUDIO (SINGLE GENERATION)
    # -------------------------------------------------------------
    def _build_studio_tab(self):
        # 2-column layout: Left (Voice attributes), Right (Text input & Audio output)
        container = ctk.CTkFrame(self.tab_studio, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Left Panel (Voice & Style Config)
        left_panel = ctk.CTkScrollableFrame(container, width=440, corner_radius=8, fg_color="#18181B")
        left_panel.pack(side="left", fill="both", padx=(0, 10), pady=0)

        lbl_sec1 = ctk.CTkLabel(left_panel, text="1. Language & Speaker", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_sec1.pack(anchor="w", padx=12, pady=(10, 6))

        # Language dropdown
        lbl_lang = ctk.CTkLabel(left_panel, text="Target Language:", font=ctk.CTkFont(size=12))
        lbl_lang.pack(anchor="w", padx=12, pady=(4, 2))
        self.combo_language = ctk.CTkComboBox(
            left_panel,
            values=list(LANGUAGES_DATA.keys()),
            command=self._on_language_change,
            height=32
        )
        self.combo_language.pack(fill="x", padx=12, pady=(0, 8))

        # Speaker dropdown
        lbl_spk = ctk.CTkLabel(left_panel, text="Speaker Voice (★ = Recommended):", font=ctk.CTkFont(size=12))
        lbl_spk.pack(anchor="w", padx=12, pady=(4, 2))
        self.combo_speaker = ctk.CTkComboBox(
            left_panel,
            values=["Loading..."],
            command=lambda _: self._update_description_preview(),
            height=32
        )
        self.combo_speaker.pack(fill="x", padx=12, pady=(0, 12))

        # Section 2: Emotion & Expression
        lbl_sec2 = ctk.CTkLabel(left_panel, text="2. Emotion & Tone Control", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_sec2.pack(anchor="w", padx=12, pady=(10, 6))

        # Emotion
        lbl_emo = ctk.CTkLabel(left_panel, text="Emotion / Mood:", font=ctk.CTkFont(size=12))
        lbl_emo.pack(anchor="w", padx=12, pady=(4, 2))
        self.combo_emotion = ctk.CTkComboBox(
            left_panel,
            values=EMOTIONS,
            command=lambda _: self._update_description_preview(),
            height=32
        )
        self.combo_emotion.set("Neutral")
        self.combo_emotion.pack(fill="x", padx=12, pady=(0, 8))

        # Speaking Speed
        lbl_speed = ctk.CTkLabel(left_panel, text="Speaking Speed:", font=ctk.CTkFont(size=12))
        lbl_speed.pack(anchor="w", padx=12, pady=(4, 2))
        self.combo_speed = ctk.CTkComboBox(
            left_panel,
            values=[opt[0] for opt in SPEED_OPTIONS],
            command=lambda _: self._update_description_preview(),
            height=32
        )
        self.combo_speed.set("Moderate")
        self.combo_speed.pack(fill="x", padx=12, pady=(0, 8))

        # Pitch
        lbl_pitch = ctk.CTkLabel(left_panel, text="Voice Pitch:", font=ctk.CTkFont(size=12))
        lbl_pitch.pack(anchor="w", padx=12, pady=(4, 2))
        self.combo_pitch = ctk.CTkComboBox(
            left_panel,
            values=[opt[0] for opt in PITCH_OPTIONS],
            command=lambda _: self._update_description_preview(),
            height=32
        )
        self.combo_pitch.set("Moderate")
        self.combo_pitch.pack(fill="x", padx=12, pady=(0, 8))

        # Expressivity
        lbl_exp = ctk.CTkLabel(left_panel, text="Expressivity Dynamic:", font=ctk.CTkFont(size=12))
        lbl_exp.pack(anchor="w", padx=12, pady=(4, 2))
        self.combo_expressivity = ctk.CTkComboBox(
            left_panel,
            values=[opt[0] for opt in EXPRESSIVITY_OPTIONS],
            command=lambda _: self._update_description_preview(),
            height=32
        )
        self.combo_expressivity.set("Slightly Expressive")
        self.combo_expressivity.pack(fill="x", padx=12, pady=(0, 8))

        # Audio Quality / Reverberation
        lbl_qual = ctk.CTkLabel(left_panel, text="Recording Environment & Quality:", font=ctk.CTkFont(size=12))
        lbl_qual.pack(anchor="w", padx=12, pady=(4, 2))
        self.combo_quality = ctk.CTkComboBox(
            left_panel,
            values=[opt[0] for opt in AUDIO_QUALITY_OPTIONS],
            command=lambda _: self._update_description_preview(),
            height=32
        )
        self.combo_quality.set("Very High Quality (Studio)")
        self.combo_quality.pack(fill="x", padx=12, pady=(0, 12))

        # Description Caption Builder & Manual Edit Toggle
        lbl_desc_title = ctk.CTkLabel(left_panel, text="3. Synthesized Prompt Caption", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_desc_title.pack(anchor="w", padx=12, pady=(10, 4))

        self.chk_manual_desc = ctk.CTkCheckBox(
            left_panel,
            text="Unlock & Edit Caption Manually",
            command=self._on_toggle_manual_caption,
            font=ctk.CTkFont(size=12)
        )
        self.chk_manual_desc.pack(anchor="w", padx=12, pady=(0, 6))

        self.txt_description = ctk.CTkTextbox(left_panel, height=85, font=ctk.CTkFont(size=11), wrap="word")
        self.txt_description.pack(fill="x", padx=12, pady=(0, 15))

        # Right Panel (Text Input, Synthesis Button, Audio Player)
        right_panel = ctk.CTkFrame(container, corner_radius=8, fg_color="#18181B")
        right_panel.pack(side="right", fill="both", expand=True, padx=0, pady=0)

        # Header for text area
        text_header = ctk.CTkFrame(right_panel, fg_color="transparent")
        text_header.pack(fill="x", padx=15, pady=(12, 4))

        lbl_text_prompt = ctk.CTkLabel(
            text_header,
            text="Text to Speak (Supports All Indic Scripts)",
            font=ctk.CTkFont(size=15, weight="bold")
        )
        lbl_text_prompt.pack(side="left")

        btn_insert_sample = ctk.CTkButton(
            text_header,
            text="Paste Sample Text",
            command=self._cmd_insert_sample_text,
            width=130,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569"
        )
        btn_insert_sample.pack(side="right", padx=(6, 0))

        btn_clear = ctk.CTkButton(
            text_header,
            text="Clear",
            command=self._cmd_clear_text,
            width=60,
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569"
        )
        btn_clear.pack(side="right")

        # Multiline text input
        self.txt_input = ctk.CTkTextbox(
            right_panel,
            font=ctk.CTkFont(family=INDIC_FONT_FAMILY, size=15),
            wrap="word",
            height=180
        )
        self.txt_input.pack(fill="both", expand=True, padx=15, pady=(4, 8))
        self.txt_input.bind("<KeyRelease>", self._update_char_count)

        # Char/Word Counter bar
        counter_bar = ctk.CTkFrame(right_panel, fg_color="transparent")
        counter_bar.pack(fill="x", padx=15, pady=(0, 8))

        self.lbl_counter = ctk.CTkLabel(
            counter_bar,
            text="0 characters | 0 words",
            font=ctk.CTkFont(size=11),
            text_color="#9CA3AF"
        )
        self.lbl_counter.pack(side="left")

        # Big Synthesize Button
        self.btn_synthesize = ctk.CTkButton(
            right_panel,
            text="🚀  Synthesize Speech",
            command=self._cmd_synthesize,
            font=ctk.CTkFont(size=16, weight="bold"),
            height=46,
            fg_color="#059669",
            hover_color="#047857"
        )
        self.btn_synthesize.pack(fill="x", padx=15, pady=(4, 12))

        # Audio Output Section
        self.audio_card = ctk.CTkFrame(right_panel, fg_color="#27272A", corner_radius=8)
        self.audio_card.pack(fill="x", padx=15, pady=(0, 15))

        audio_header = ctk.CTkFrame(self.audio_card, fg_color="transparent")
        audio_header.pack(fill="x", padx=15, pady=(12, 6))

        lbl_audio_title = ctk.CTkLabel(
            audio_header,
            text="Generated Audio",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        lbl_audio_title.pack(side="left")

        self.lbl_audio_meta = ctk.CTkLabel(
            audio_header,
            text="No audio generated yet",
            font=ctk.CTkFont(size=12),
            text_color="#A1A1AA"
        )
        self.lbl_audio_meta.pack(side="right")

        # Player buttons
        player_bar = ctk.CTkFrame(self.audio_card, fg_color="transparent")
        player_bar.pack(fill="x", padx=15, pady=(4, 12))

        self.btn_play = ctk.CTkButton(
            player_bar,
            text="▶  Play",
            command=self._cmd_play_audio,
            state="disabled",
            width=90,
            height=34,
            fg_color="#2563EB",
            hover_color="#1D4ED8"
        )
        self.btn_play.pack(side="left", padx=(0, 8))

        self.btn_stop = ctk.CTkButton(
            player_bar,
            text="⏹  Stop",
            command=self._cmd_stop_audio,
            state="disabled",
            width=80,
            height=34,
            fg_color="#4B5563",
            hover_color="#374151"
        )
        self.btn_stop.pack(side="left", padx=(0, 8))

        self.btn_external = ctk.CTkButton(
            player_bar,
            text="🔊  Open in Player",
            command=self._cmd_open_external,
            state="disabled",
            width=130,
            height=34,
            fg_color="#374151",
            hover_color="#4B5563"
        )
        self.btn_external.pack(side="left", padx=(0, 8))

        self.btn_save_as = ctk.CTkButton(
            player_bar,
            text="💾  Export WAV...",
            command=self._cmd_save_as,
            state="disabled",
            width=120,
            height=34,
            fg_color="#374151",
            hover_color="#4B5563"
        )
        self.btn_save_as.pack(side="right")

        self.btn_open_folder = ctk.CTkButton(
            player_bar,
            text="📁  Open Folder",
            command=self._cmd_open_folder,
            width=110,
            height=34,
            fg_color="#374151",
            hover_color="#4B5563"
        )
        self.btn_open_folder.pack(side="right", padx=(0, 8))

    # -------------------------------------------------------------
    # TAB 2: BATCH GENERATOR
    # -------------------------------------------------------------
    def _build_batch_tab(self):
        frame = ctk.CTkFrame(self.tab_batch, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Batch source selection
        src_box = ctk.CTkFrame(frame, fg_color="#18181B", corner_radius=8)
        src_box.pack(fill="x", padx=0, pady=(0, 10))

        lbl_batch_src = ctk.CTkLabel(src_box, text="Batch Source", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_batch_src.pack(anchor="w", padx=15, pady=(10, 6))

        btn_row = ctk.CTkFrame(src_box, fg_color="transparent")
        btn_row.pack(fill="x", padx=15, pady=(0, 12))

        btn_load_txt = ctk.CTkButton(
            btn_row,
            text="📄 Load from .TXT (1 line = 1 audio)",
            command=self._cmd_batch_load_txt,
            height=34,
            fg_color="#0284C7",
            hover_color="#0369A1"
        )
        btn_load_txt.pack(side="left", padx=(0, 10))

        btn_load_csv = ctk.CTkButton(
            btn_row,
            text="📊 Load from .CSV (With 'text' column)",
            command=self._cmd_batch_load_csv,
            height=34,
            fg_color="#0284C7",
            hover_color="#0369A1"
        )
        btn_load_csv.pack(side="left")

        self.lbl_batch_loaded_info = ctk.CTkLabel(
            btn_row,
            text="No batch file loaded.",
            font=ctk.CTkFont(size=12),
            text_color="#9CA3AF"
        )
        self.lbl_batch_loaded_info.pack(side="right")

        # Table/List of jobs
        lbl_jobs = ctk.CTkLabel(frame, text="Batch Job Queue", font=ctk.CTkFont(size=14, weight="bold"))
        lbl_jobs.pack(anchor="w", padx=0, pady=(6, 4))

        self.batch_listbox = ctk.CTkTextbox(frame, font=ctk.CTkFont(family=INDIC_FONT_FAMILY, size=12), wrap="none")
        self.batch_listbox.pack(fill="both", expand=True, padx=0, pady=(0, 10))

        # Progress bar & controls
        control_bar = ctk.CTkFrame(frame, fg_color="#18181B", corner_radius=8)
        control_bar.pack(fill="x", padx=0, pady=0)

        progress_row = ctk.CTkFrame(control_bar, fg_color="transparent")
        progress_row.pack(fill="x", padx=15, pady=(10, 4))

        self.batch_progressbar = ctk.CTkProgressBar(progress_row)
        self.batch_progressbar.set(0)
        self.batch_progressbar.pack(fill="x", expand=True, side="left", padx=(0, 15))

        self.lbl_batch_status = ctk.CTkLabel(progress_row, text="Idle", font=ctk.CTkFont(size=12), text_color="#A1A1AA")
        self.lbl_batch_status.pack(side="right")

        btn_actions = ctk.CTkFrame(control_bar, fg_color="transparent")
        btn_actions.pack(fill="x", padx=15, pady=(4, 12))

        self.btn_batch_start = ctk.CTkButton(
            btn_actions,
            text="▶ Start Batch Processing",
            command=self._cmd_batch_start,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=36,
            width=200
        )
        self.btn_batch_start.pack(side="left", padx=(0, 10))

        self.btn_batch_cancel = ctk.CTkButton(
            btn_actions,
            text="⏹ Cancel",
            command=self._cmd_batch_cancel,
            font=ctk.CTkFont(size=13),
            fg_color="#DC2626",
            hover_color="#B91C1C",
            state="disabled",
            height=36,
            width=100
        )
        self.btn_batch_cancel.pack(side="left")

        btn_open_out = ctk.CTkButton(
            btn_actions,
            text="📁 Open Output Folder",
            command=self._cmd_open_folder,
            height=36,
            fg_color="#374151",
            hover_color="#4B5563"
        )
        btn_open_out.pack(side="right")

    # -------------------------------------------------------------
    # TAB 3: HISTORY & RECORDINGS
    # -------------------------------------------------------------
    def _build_history_tab(self):
        frame = ctk.CTkFrame(self.tab_history, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        top_row = ctk.CTkFrame(frame, fg_color="transparent")
        top_row.pack(fill="x", padx=0, pady=(0, 8))

        lbl_hist = ctk.CTkLabel(top_row, text="Generated Speech Library", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_hist.pack(side="left")

        btn_refresh = ctk.CTkButton(
            top_row,
            text="🔄 Refresh",
            command=self._refresh_history,
            width=90,
            height=28,
            fg_color="#374151"
        )
        btn_refresh.pack(side="right", padx=(8, 0))

        btn_open_dir = ctk.CTkButton(
            top_row,
            text="📁 Open Folder",
            command=self._cmd_open_folder,
            width=110,
            height=28,
            fg_color="#374151"
        )
        btn_open_dir.pack(side="right")

        self.history_scroll = ctk.CTkScrollableFrame(frame, fg_color="#18181B", corner_radius=8)
        self.history_scroll.pack(fill="both", expand=True, padx=0, pady=0)

    def _refresh_history(self):
        for widget in self.history_scroll.winfo_children():
            widget.destroy()

        history = self.engine.get_history()
        if not history:
            lbl_empty = ctk.CTkLabel(
                self.history_scroll,
                text="No recordings in history yet. Generate some audio in the Voice Studio!",
                font=ctk.CTkFont(size=13),
                text_color="#9CA3AF"
            )
            lbl_empty.pack(padx=20, pady=40)
            return

        for item in history:
            card = ctk.CTkFrame(self.history_scroll, fg_color="#27272A", corner_radius=6)
            card.pack(fill="x", padx=10, pady=5)

            # Left content
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, padx=12, pady=8)

            txt_preview = item.get("text", "")
            if len(txt_preview) > 90:
                txt_preview = txt_preview[:90] + "..."

            lbl_txt = ctk.CTkLabel(
                info_frame,
                text=txt_preview,
                font=ctk.CTkFont(family=INDIC_FONT_FAMILY, size=13, weight="bold"),
                anchor="w"
            )
            lbl_txt.pack(anchor="w")

            meta_str = f"Duration: {item.get('audio_duration', 0):.1f}s • {item.get('filename', '')} • {item.get('timestamp', '')[:19]}"
            lbl_meta = ctk.CTkLabel(
                info_frame,
                text=meta_str,
                font=ctk.CTkFont(size=11),
                text_color="#A1A1AA",
                anchor="w"
            )
            lbl_meta.pack(anchor="w")

            # Right actions
            btn_frame = ctk.CTkFrame(card, fg_color="transparent")
            btn_frame.pack(side="right", padx=10, pady=8)

            wav_path = item.get("wav_path", "")

            btn_p = ctk.CTkButton(
                btn_frame,
                text="▶ Play",
                width=65,
                height=28,
                fg_color="#2563EB",
                command=lambda p=wav_path: self.player.play(p)
            )
            btn_p.pack(side="left", padx=4)

            btn_o = ctk.CTkButton(
                btn_frame,
                text="🔊 Open",
                width=65,
                height=28,
                fg_color="#374151",
                command=lambda p=wav_path: self.player.open_external(p)
            )
            btn_o.pack(side="left", padx=4)

    # -------------------------------------------------------------
    # TAB 4: SETTINGS & INFO
    # -------------------------------------------------------------
    def _build_settings_tab(self):
        frame = ctk.CTkScrollableFrame(self.tab_settings, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=15, pady=15)

        card1 = ctk.CTkFrame(frame, fg_color="#18181B", corner_radius=8)
        card1.pack(fill="x", padx=0, pady=(0, 15))

        lbl_s1 = ctk.CTkLabel(card1, text="Hardware & Runtime Configuration", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_s1.pack(anchor="w", padx=15, pady=(12, 6))

        self.lbl_system_info = ctk.CTkLabel(
            card1,
            text="Detecting system specs...",
            font=ctk.CTkFont(size=12),
            justify="left",
            anchor="w"
        )
        self.lbl_system_info.pack(fill="x", padx=15, pady=(0, 12))

        # Precision selector
        prec_box = ctk.CTkFrame(card1, fg_color="transparent")
        prec_box.pack(fill="x", padx=15, pady=(0, 15))

        lbl_prec = ctk.CTkLabel(prec_box, text="Inference Precision:", font=ctk.CTkFont(size=12))
        lbl_prec.pack(side="left", padx=(0, 10))

        self.seg_precision = ctk.CTkSegmentedButton(prec_box, values=["FP32 (Best quality)", "FP16 (Faster)"])
        self.seg_precision.set("FP32 (Best quality)")
        self.seg_precision.pack(side="left")

        # Card 2: Model Information
        card2 = ctk.CTkFrame(frame, fg_color="#18181B", corner_radius=8)
        card2.pack(fill="x", padx=0, pady=(0, 15))

        lbl_s2 = ctk.CTkLabel(card2, text="About ai4bharat/indic-parler-tts", font=ctk.CTkFont(size=15, weight="bold"))
        lbl_s2.pack(anchor="w", padx=15, pady=(12, 6))

        about_text = (
            "Indic Parler-TTS is a state-of-the-art conditional text-to-speech model built by AI4Bharat and Hugging Face.\n\n"
            "Key Highlights:\n"
            "• 21 Indian Languages: Hindi, Tamil, Telugu, Bengali, Marathi, Gujarati, Kannada, Malayalam, Odia, Punjabi, Assamese, etc.\n"
            "• 69 Unique Speaker Personas with controllable accents, gender, and regional nuances.\n"
            "• Caption-Guided Synthesis: Control pitch, speaking rate, background noise, reverberation, and emotions via natural language descriptions.\n"
            "• Full Offline Local Inference on your NVIDIA GeForce RTX 4060 GPU with zero external cloud dependencies."
        )

        lbl_about = ctk.CTkLabel(card2, text=about_text, font=ctk.CTkFont(size=12), justify="left", anchor="w")
        lbl_about.pack(fill="x", padx=15, pady=(0, 15))

        self._populate_system_specs()

    def _populate_system_specs(self):
        try:
            import torch
            lines = [
                f"• Python Version: {sys.version.split()[0]}",
                f"• PyTorch Version: {torch.__version__}",
                f"• CUDA Available: {torch.cuda.is_available()}",
            ]
            if torch.cuda.is_available():
                lines.append(f"• Active GPU: {torch.cuda.get_device_name(0)}")
                lines.append(f"• Total VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f} GB")
                lines.append(f"• CUDA Device Capability: {torch.cuda.get_device_capability(0)}")
            self.lbl_system_info.configure(text="\n".join(lines))
        except Exception as e:
            self.lbl_system_info.configure(text=f"Error inspecting hardware: {e}")

    # -------------------------------------------------------------
    # Event Handlers & Commands
    # -------------------------------------------------------------
    def _on_engine_status(self, status: str):
        self.lbl_status_badge.configure(text=f"Status: {status}")
        if status == "Ready":
            self.lbl_status_badge.configure(fg_color="#059669")
            self.btn_load_model.configure(text="Reload Model", state="normal")
            self.btn_synthesize.configure(state="normal", text="🚀  Synthesize Speech")
        elif "Error" in status:
            self.lbl_status_badge.configure(fg_color="#DC2626")
            self.btn_load_model.configure(state="normal")
            self.btn_synthesize.configure(state="normal", text="🚀  Synthesize Speech")
        elif "Loading" in status or "Synthesizing" in status:
            self.lbl_status_badge.configure(fg_color="#D97706")

    def _on_engine_log(self, message: str):
        # Can route to status or console
        pass

    def _cmd_load_model(self):
        self.btn_load_model.configure(state="disabled")
        use_fp16 = "FP16" in self.seg_precision.get()
        target_device = "cuda:0" if self.engine._has_cuda() else "cpu"

        def _on_finish(success: bool, msg: str):
            self.btn_load_model.configure(state="normal")
            if not success:
                messagebox.showerror("Model Load Error", msg)
            else:
                self._update_description_preview()

        self.engine.load_model(device=target_device, use_fp16=use_fp16, on_complete=self._ui_safe(_on_finish))

    def _on_language_change(self, lang_name: str):
        lang_info = LANGUAGES_DATA.get(lang_name, {})
        speakers = lang_info.get("speakers", [])
        recommended = set(lang_info.get("recommended", []))

        # Format with star for recommended
        speaker_choices = ["Random Voice"]
        for spk in speakers:
            prefix = "★ " if spk in recommended else "   "
            speaker_choices.append(f"{prefix}{spk}")

        self.combo_speaker.configure(values=speaker_choices)
        def_spk = lang_info.get("default_speaker", "")
        def_val = f"★ {def_spk}" if def_spk in recommended else def_spk
        self.combo_speaker.set(def_val if def_val in speaker_choices else speaker_choices[0])

        self._update_description_preview()

    def _get_selected_speaker_name(self) -> Optional[str]:
        raw = self.combo_speaker.get().strip()
        if raw.startswith("★ "):
            raw = raw[2:].strip()
        if raw == "Random Voice":
            return None
        return raw

    def _update_description_preview(self):
        if self.chk_manual_desc.get():
            return  # User has custom manual caption enabled

        spk_name = self._get_selected_speaker_name()
        lang_name = self.combo_language.get()
        emotion = self.combo_emotion.get()

        # Find option texts
        speed_map = dict(SPEED_OPTIONS)
        pitch_map = dict(PITCH_OPTIONS)
        exp_map = dict(EXPRESSIVITY_OPTIONS)
        qual_map = dict(AUDIO_QUALITY_OPTIONS)

        speed_desc = speed_map.get(self.combo_speed.get(), "with a moderate speed")
        pitch_desc = pitch_map.get(self.combo_pitch.get(), "moderate pitch")
        exp_desc = exp_map.get(self.combo_expressivity.get(), "slightly expressive and animated")
        qual_desc = qual_map.get(self.combo_quality.get(), "The recording is of very high quality, with no background noise.")

        desc = self.engine.build_description(
            speaker=spk_name,
            language=lang_name,
            emotion=emotion,
            speed_desc=speed_desc,
            pitch_desc=pitch_desc,
            expressivity_desc=exp_desc,
            quality_desc=qual_desc
        )

        self.txt_description.delete("1.0", "end")
        self.txt_description.insert("1.0", desc)

    def _on_toggle_manual_caption(self):
        if not self.chk_manual_desc.get():
            self._update_description_preview()

    def _cmd_insert_sample_text(self):
        lang_name = self.combo_language.get()
        lang_info = LANGUAGES_DATA.get(lang_name, {})
        sample = lang_info.get("sample_text", "Hello, how are you?")
        self.txt_input.delete("1.0", "end")
        self.txt_input.insert("1.0", sample)
        self._update_char_count()

    def _cmd_clear_text(self):
        self.txt_input.delete("1.0", "end")
        self._update_char_count()

    def _update_char_count(self, event=None):
        text = self.txt_input.get("1.0", "end-1c").strip()
        chars = len(text)
        words = len(text.split()) if text else 0
        self.lbl_counter.configure(text=f"{chars} characters | {words} words")

    def _cmd_synthesize(self):
        text = self.txt_input.get("1.0", "end-1c").strip()
        desc = self.txt_description.get("1.0", "end-1c").strip()

        if not text:
            messagebox.showwarning("Empty Text", "Please enter some text to speak.")
            return

        if not self.engine.is_model_loaded():
            confirm = messagebox.askyesno(
                "Model Not Loaded",
                "The Indic-Parler-TTS model has not been loaded into memory yet.\n\nWould you like to load the model now?"
            )
            if confirm:
                self._cmd_load_model()
            return

        self.btn_synthesize.configure(state="disabled", text="⏳  Synthesizing...")
        spk = self._get_selected_speaker_name() or "indic"
        prefix = f"{self.combo_language.get()[:2].lower()}_{spk.lower()}"

        def _on_finish(success: bool, data: Optional[Dict[str, Any]], msg: str):
            self.btn_synthesize.configure(state="normal", text="🚀  Synthesize Speech")
            if not success:
                messagebox.showerror("Synthesis Error", msg)
                return

            self.current_result = data
            self.lbl_audio_meta.configure(
                text=f"{data['filename']} ({data['audio_duration']:.2f}s, generated in {data['generation_time']:.2f}s, RTF: {data['rtf']:.2f})"
            )
            self.btn_play.configure(state="normal")
            self.btn_stop.configure(state="normal")
            self.btn_external.configure(state="normal")
            self.btn_save_as.configure(state="normal")

            # Automatically play generated audio
            self.player.play(data["wav_path"])
            self._refresh_history()

        self.engine.generate(
            text=text,
            description=desc,
            filename_prefix=prefix,
            on_complete=self._ui_safe(_on_finish)
        )

    def _cmd_play_audio(self):
        if self.current_result and "wav_path" in self.current_result:
            self.player.play(self.current_result["wav_path"])

    def _cmd_stop_audio(self):
        self.player.stop()

    def _cmd_open_external(self):
        if self.current_result and "wav_path" in self.current_result:
            self.player.open_external(self.current_result["wav_path"])

    def _cmd_open_folder(self):
        out_dir = os.path.abspath(self.engine.output_dir)
        os.makedirs(out_dir, exist_ok=True)
        os.startfile(out_dir)

    def _cmd_save_as(self):
        if not self.current_result or "wav_path" not in self.current_result:
            return
        src_path = self.current_result["wav_path"]
        target = filedialog.asksaveasfilename(
            defaultextension=".wav",
            filetypes=[("WAV Audio", "*.wav")],
            initialfile=os.path.basename(src_path)
        )
        if target:
            import shutil
            shutil.copy2(src_path, target)
            messagebox.showinfo("Export Successful", f"Audio exported successfully to:\n{target}")

    # -------------------------------------------------------------
    # Batch Processing Handlers
    # -------------------------------------------------------------
    def _cmd_batch_load_txt(self):
        fpath = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not fpath:
            return
        desc = self.txt_description.get("1.0", "end-1c").strip()
        count = self.batch_processor.load_from_txt(fpath, default_description=desc)
        self.lbl_batch_loaded_info.configure(text=f"Loaded {count} lines from {os.path.basename(fpath)}")
        self._refresh_batch_display()

    def _cmd_batch_load_csv(self):
        fpath = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not fpath:
            return
        desc = self.txt_description.get("1.0", "end-1c").strip()
        count = self.batch_processor.load_from_csv(fpath, default_description=desc)
        self.lbl_batch_loaded_info.configure(text=f"Loaded {count} rows from {os.path.basename(fpath)}")
        self._refresh_batch_display()

    def _refresh_batch_display(self):
        self.batch_listbox.delete("1.0", "end")
        for job in self.batch_processor.jobs:
            line = f"[{job.status.upper():10}] #{job.index+1:03d}: {job.text[:60]}... -> {job.filename_prefix}\n"
            self.batch_listbox.insert("end", line)

    def _cmd_batch_start(self):
        if not self.batch_processor.jobs:
            messagebox.showwarning("No Jobs", "Please load a .txt or .csv file first.")
            return

        if not self.engine.is_model_loaded():
            messagebox.showwarning("Model Not Loaded", "Please load the model before starting batch generation.")
            return

        self.btn_batch_start.configure(state="disabled")
        self.btn_batch_cancel.configure(state="normal")

        def _on_item(idx: int, status: str, out_file: Optional[str]):
            self._refresh_batch_display()

        def _on_progress(cur: int, total: int, status_text: str):
            frac = cur / max(1, total)
            self.batch_progressbar.set(frac)
            self.lbl_batch_status.configure(text=status_text)

        def _on_complete(succ: int, fail: int):
            self.btn_batch_start.configure(state="normal")
            self.btn_batch_cancel.configure(state="disabled")
            messagebox.showinfo("Batch Finished", f"Batch complete!\n\nSuccessfully generated: {succ}\nFailed: {fail}")
            self._refresh_history()

        self.batch_processor.on_item_status = self._ui_safe(_on_item)
        self.batch_processor.on_batch_progress = self._ui_safe(_on_progress)
        self.batch_processor.on_batch_complete = self._ui_safe(_on_complete)
        self.batch_processor.start()

    def _cmd_batch_cancel(self):
        self.batch_processor.cancel()
        self.lbl_batch_status.configure(text="Batch cancelled by user.")


def main():
    app = IndicTTSApp()
    app.mainloop()


if __name__ == "__main__":
    main()
