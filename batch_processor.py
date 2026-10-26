"""Batch generation manager for Indic-TTS Desktop."""

import os
import csv
import time
import threading
from typing import List, Dict, Any, Optional, Callable
from tts_engine import TTSEngine


class BatchJob:
    def __init__(self, index: int, text: str, description: str, filename_prefix: str):
        self.index = index
        self.text = text
        self.description = description
        self.filename_prefix = filename_prefix
        self.status = "Pending"  # Pending, Processing, Finished, Failed
        self.output_file: Optional[str] = None
        self.error: Optional[str] = None
        self.duration: float = 0.0


class BatchProcessor:
    def __init__(self, engine: TTSEngine):
        self.engine = engine
        self.jobs: List[BatchJob] = []
        self.is_running = False
        self._cancel_flag = False
        self._thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_item_status: Optional[Callable[[int, str, Optional[str]], None]] = None
        self.on_batch_progress: Optional[Callable[[int, int, str], None]] = None
        self.on_batch_complete: Optional[Callable[[int, int], None]] = None

    def load_from_txt(self, filepath: str, default_description: str, prefix: str = "batch") -> int:
        """Loads non-empty lines from a text file as individual jobs."""
        self.jobs = []
        with open(filepath, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        for i, line in enumerate(lines):
            job = BatchJob(
                index=i,
                text=line,
                description=default_description,
                filename_prefix=f"{prefix}_{i+1:03d}"
            )
            self.jobs.append(job)
        return len(self.jobs)

    def load_from_csv(self, filepath: str, default_description: str, text_col: str = "text") -> int:
        """Loads jobs from CSV file. Columns can override description or prefix."""
        self.jobs = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                text = row.get(text_col, "").strip()
                if not text:
                    continue
                # If CSV contains a 'description' column, use it, otherwise use default
                desc = row.get("description", default_description).strip() or default_description
                prefix = row.get("id", f"row_{i+1:03d}")
                job = BatchJob(index=i, text=text, description=desc, filename_prefix=prefix)
                self.jobs.append(job)
        return len(self.jobs)

    def load_from_text_list(self, texts: List[str], default_description: str, prefix: str = "batch") -> int:
        """Loads jobs directly from a list of strings."""
        self.jobs = []
        for i, text in enumerate(texts):
            clean = text.strip()
            if clean:
                job = BatchJob(
                    index=i,
                    text=clean,
                    description=default_description,
                    filename_prefix=f"{prefix}_{i+1:03d}"
                )
                self.jobs.append(job)
        return len(self.jobs)

    def start(self):
        """Starts batch processing in a background thread."""
        if self.is_running:
            return

        self.is_running = True
        self._cancel_flag = False

        def _worker():
            total = len(self.jobs)
            success_count = 0
            fail_count = 0

            for i, job in enumerate(self.jobs):
                if self._cancel_flag:
                    break

                job.status = "Processing"
                if self.on_item_status:
                    self.on_item_status(job.index, "Processing", None)
                if self.on_batch_progress:
                    self.on_batch_progress(i, total, f"Synthesizing item {i+1} of {total}...")

                # Synchronous generation inside batch worker thread
                done_event = threading.Event()
                gen_result = {}

                def _on_complete(success: bool, data: Optional[Dict[str, Any]], message: str):
                    gen_result["success"] = success
                    gen_result["data"] = data
                    gen_result["message"] = message
                    done_event.set()

                self.engine.generate(
                    text=job.text,
                    description=job.description,
                    filename_prefix=job.filename_prefix,
                    on_complete=_on_complete
                )

                done_event.wait()

                if gen_result.get("success"):
                    job.status = "Finished"
                    job.output_file = gen_result["data"]["wav_path"]
                    job.duration = gen_result["data"]["audio_duration"]
                    success_count += 1
                    if self.on_item_status:
                        self.on_item_status(job.index, "Finished", job.output_file)
                else:
                    job.status = "Failed"
                    job.error = gen_result.get("message", "Unknown error")
                    fail_count += 1
                    if self.on_item_status:
                        self.on_item_status(job.index, "Failed", job.error)

            self.is_running = False
            if self.on_batch_progress:
                self.on_batch_progress(total, total, f"Completed: {success_count} succeeded, {fail_count} failed.")
            if self.on_batch_complete:
                self.on_batch_complete(success_count, fail_count)

        self._thread = threading.Thread(target=_worker, daemon=True)
        self._thread.start()

    def cancel(self):
        """Cancels running batch process."""
        self._cancel_flag = True
