"""Audio playback for the studio (pygame mixer, with winsound / external fallback)."""

import os
import sys
import threading
from typing import Optional


class AudioPlayer:
    def __init__(self):
        self.current_file: Optional[str] = None
        self._has_pygame = False
        self._winsound_playing = False
        try:
            import pygame
            pygame.mixer.init()
            self._has_pygame = True
        except Exception:
            self._has_pygame = False

    @property
    def is_playing(self) -> bool:
        if self._has_pygame:
            try:
                import pygame
                return bool(pygame.mixer.music.get_busy())
            except Exception:
                return False
        return self._winsound_playing

    def play(self, path: str):
        """Start playing `path` (non-blocking)."""
        if not os.path.exists(path):
            print(f"[AudioPlayer] File not found: {path}")
            return
        self.stop()
        self.current_file = path
        if self._has_pygame:
            try:
                import pygame
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                return
            except Exception as e:
                print(f"[AudioPlayer] pygame error: {e}")
        if sys.platform == "win32" and path.lower().endswith(".wav"):
            import winsound

            def _worker():
                self._winsound_playing = True
                try:
                    winsound.PlaySound(path, winsound.SND_FILENAME)
                finally:
                    self._winsound_playing = False
            threading.Thread(target=_worker, daemon=True).start()
        else:
            self.open_external(path)

    def stop(self):
        if self._has_pygame:
            try:
                import pygame
                pygame.mixer.music.stop()
            except Exception:
                pass
        elif sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        self._winsound_playing = False

    def unload(self):
        """Release the file handle so the file can be deleted (Windows)."""
        self.stop()
        if self._has_pygame:
            try:
                import pygame
                pygame.mixer.music.unload()
            except Exception:
                pass
        self.current_file = None

    def open_external(self, filepath: Optional[str] = None):
        target = filepath or self.current_file
        if target and os.path.exists(target):
            try:
                os.startfile(target)
            except Exception as e:
                print(f"[AudioPlayer] Failed to open external player: {e}")
