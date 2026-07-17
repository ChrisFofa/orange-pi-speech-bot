#!/usr/bin/env python3
"""
Spring Demo — main.py
======================

Tap-to-talk speech-to-speech study bot for 10-12 year old students.

Flow per turn:
    1. User taps the face widget (or presses SPACE / TALK button).
    2. face -> "listening".  Vosk records from USB mic until silence.
    3. face -> "thinking".  Send transcript to Claude-3.5-Haiku via Poe.
       This state PERSISTS through the TTS fetch (~2-4 seconds) so the
       mouth does NOT move while we're still waiting for audio.
    4. face -> "talking".   Set ONLY when MP3 bytes are in hand and
       playback is about to start. Mouth animation stays in sync.
    5. face -> "idle".      After 60s with no tap, face -> "sleeping".

Key invariants:
    - face_widget.py is imported UNCHANGED from the original design.
    - The Poe API key is fetched from Supabase via the get_event_api_key
      RPC and held in process memory only. It is never persisted.
    - AI_MODEL, AI_BASE_URL, AI_TTS_MODEL, AI_VOICE are pinned constants.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Force framebuffer Qt platform before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "linuxfb:fb=/dev/fb0:tty=/dev/tty1")
os.environ.setdefault("QT_FONT_DPI", "96")


# ============================================================
# Bigbang env loading (DEMO1 pattern, copy-paste compatible)
# ============================================================

ENV_PATHS = [
    "/etc/bigbang.env",
    "/opt/bigbang/.env",
    "/opt/bigbang/app/.env",
    "/opt/bigbang/config/.env",
    "/boot/bigbang.env",
]


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    return v


def _first_env(keys):
    for k in keys:
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return ""


def _set_aliases(keys, value):
    if not value:
        return
    for k in keys:
        if not os.environ.get(k):
            os.environ[k] = value


def normalize_env_aliases():
    url_keys = [
        "SUPABASE_URL", "supabase_url",
        "NEXT_PUBLIC_SUPABASE_URL", "VITE_SUPABASE_URL",
    ]
    key_keys = [
        "SUPABASE_PUBLISHABLE_KEY", "supabase_publishable_key",
        "SUPABASE_ANON_KEY", "supabase_anon_key",
        "SUPABASE_ANONYMOUS_KEY", "supabase_anonymous_key",
        "SUPABASE_KEY", "supabase_key",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY", "VITE_SUPABASE_ANON_KEY",
    ]
    event_keys = ["EVENT_CODE", "event_code", "BIGBANG_EVENT_CODE", "bigbang_event_code"]

    url = _first_env(url_keys)
    key = _first_env(key_keys)
    event = _first_env(event_keys)
    _set_aliases(url_keys, url)
    _set_aliases(key_keys, key)
    _set_aliases(event_keys, event)


def load_env_files():
    for path in ENV_PATHS:
        p = Path(path)
        if not p.exists():
            continue
        try:
            for raw in p.read_text(errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                k, v = line.split("=", 1)
                k = k.strip()
                v = _strip_quotes(v)
                if k and not os.environ.get(k):
                    os.environ[k] = v
        except Exception:
            pass
    normalize_env_aliases()


load_env_files()

for extra_path in [
    "/opt/bigbang", "/opt/bigbang/app", "/opt/bigbang/lib", "/opt/bigbang/events",
]:
    if extra_path not in sys.path:
        sys.path.insert(0, extra_path)


# ============================================================
# Pinned AI configuration
# ============================================================

AI_BASE_URL = "https://api.poe.com/v1"
AI_MODEL = "Claude-3.5-Haiku"
# AI_TTS_MODEL = "ElevenLabs-v2.5-Turbo"
# AI_VOICE = "Lily"
AI_TTS_MODEL = "Sonic-3.0"
AI_VOICE = "tessa"


# ============================================================
# Local imports (after sys.path setup, after env load)
# ============================================================

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

from face_widget import FaceWidget
import audio_utils
import speech_utils
import ai_client
import audio_config
import settings as cfg


# ============================================================
# Credential fetch (DEMO1 pattern)
# ============================================================

def fetch_api_key() -> str:
    """
    Use event_runtime + supabase_helper to call get_event_api_key.
    Returns the Poe API key as a string. Held only in memory.
    """
    load_env_files()

    try:
        from event_runtime import build_event_context, create_supabase_client
    except Exception as e:
        # Last-ditch fallback for SSH testing only.
        poe_key = os.environ.get("POE_API_KEY") or os.environ.get("poe_api_key")
        if poe_key:
            return poe_key
        raise Exception(f"event_runtime import failed: {str(e)[:120]}")

    ctx = build_event_context(require_supabase=True)
    client = create_supabase_client(ctx)

    api_key = client.rpc("get_event_api_key", {"p_event_code": ctx.event_code})

    # PostgREST may return the scalar wrapped in a list or dict.
    if isinstance(api_key, list) and api_key:
        api_key = api_key[0]
    if isinstance(api_key, dict):
        api_key = api_key.get("api_key") or api_key.get("get_event_api_key")

    if not api_key or not isinstance(api_key, str):
        raise Exception(f"get_event_api_key returned no key for {ctx.event_code}")

    return api_key


# ============================================================
# Worker signals (Qt thread-safe bridge)
# ============================================================

class WorkerSignals(QObject):
    state = pyqtSignal(str)        # face state: idle/listening/thinking/talking/sleeping/error
    status = pyqtSignal(str)       # status label text
    answer = pyqtSignal(str)       # last transcript / answer text
    error = pyqtSignal(str)
    ready = pyqtSignal()           # setup complete, enable UI
    finished_turn = pyqtSignal()   # one full turn done, return to idle


# ============================================================
# Audio playback helper
# ============================================================

def play_mp3_bytes(mp3_bytes: bytes, alsa_device: str) -> None:
    """
    Pipe mp3 bytes into mpg123 -> ALSA. Blocks until playback ends.
    """
    if not mp3_bytes:
        return

    cmd = ["mpg123", "-q"]
    if alsa_device:
        cmd += ["-o", "alsa", "-a", alsa_device]
    cmd += ["-"]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        proc.communicate(input=mp3_bytes, timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()


# ============================================================
# Main screen
# ============================================================

class SpringDemoScreen(QWidget):

    def __init__(self):
        super().__init__()

        self.setStyleSheet("background-color: #1a1a2e; color: #e0e0e0;")

        self.signals = WorkerSignals()
        self.signals.state.connect(self._set_face_state)
        self.signals.status.connect(self._set_status)
        self.signals.answer.connect(self._set_answer)
        self.signals.error.connect(self._on_error)
        self.signals.ready.connect(self._on_ready)
        self.signals.finished_turn.connect(self._on_turn_done)

        # Runtime state
        self.api_key: str = ""              # Poe key held in memory only
        self.system_prompt: str = ""
        self.bad_attempts: int = 0
        self.is_busy: bool = False           # one turn at a time

        # Build event manifest -> grab status_text + system_addon
        self.status_text = dict(cfg.DEFAULT_STATUS)
        self.system_addon = ""
        self._load_event_manifest()

        # ---- Layout ----
        root = QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # The face widget owns the top of the screen.
        self.face = FaceWidget()
        self.face.setMinimumHeight(360)
        self.face.set_state("idle")
        # Tap on the face = start a turn.
        self.face.mousePressEvent = self._on_face_tap
        root.addWidget(self.face, stretch=4)

        # Status bar under the face.
        self.status_lbl = QLabel(self.status_text.get("starting", "Starting..."))
        self.status_lbl.setAlignment(Qt.AlignCenter)
        self.status_lbl.setStyleSheet(
            "color: #ffd966; background: #2a2a3e; padding: 6px; "
            "border-radius: 6px; font-size: 22px; font-weight: bold;"
        )
        self.status_lbl.setWordWrap(True)
        root.addWidget(self.status_lbl, stretch=0)

        # Last-answer ticker (small, in case student wants to read).
        self.answer_lbl = QLabel("")
        self.answer_lbl.hide()
        self.answer_lbl.setAlignment(Qt.AlignCenter)
        self.answer_lbl.setStyleSheet(
            "color: #cdd6f4; background: #16213e; padding: 4px 8px; "
            "border-left: 3px solid #00ff88; border-radius: 4px; font-size: 16px;"
        )
        self.answer_lbl.setWordWrap(True)
        # root.addWidget(self.answer_lbl, stretch=1)  # hidden: text output removed

        # Bottom row: TALK + CLOSE
        row = QHBoxLayout()
        row.setSpacing(12)

        self.talk_btn = QPushButton("TALK")
        self.talk_btn.hide()
        self.talk_btn.setMinimumHeight(72)
        self.talk_btn.setStyleSheet(
            "background:#00d4ff; color:#0a0a1e; border-radius:10px; "
            "font-size:26px; font-weight:bold; padding:8px;"
        )
        self.talk_btn.clicked.connect(self._on_talk)
        # row.addWidget(self.talk_btn, stretch=3)  # removed: tap face instead

        close_btn = QPushButton("CLOSE")
        close_btn.setMinimumHeight(72)
        close_btn.setStyleSheet(
            "background:#cc0000; color:white; border-radius:10px; "
            "font-size:22px; font-weight:bold; padding:8px;"
        )
        close_btn.clicked.connect(self._clean_exit)
        row.addWidget(close_btn, stretch=1)

        root.addLayout(row, stretch=0)
        self.setLayout(root)

        # Idle->sleep timer
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.timeout.connect(self._go_sleep)

    # ----------------------------------------------------------------
    # Event manifest loading (status_text + system_addon)
    # ----------------------------------------------------------------

    def _load_event_manifest(self):
        try:
            here = Path(__file__).resolve().parent
            data = json.loads((here / "event.json").read_text(encoding="utf-8"))
            self.system_addon = (data.get("system_addon") or "").strip()
            st = data.get("status_text") or {}
            for k, v in st.items():
                if isinstance(v, str) and v:
                    self.status_text[k] = v
        except Exception:
            pass

    # ----------------------------------------------------------------
    # Startup orchestration
    # ----------------------------------------------------------------

    def start(self):
        threading.Thread(target=self._setup_worker, daemon=True).start()

    def _setup_worker(self):
        try:
            self.signals.state.emit("idle")
            self.signals.status.emit(self.status_text["setup_audio"])
            audio_utils.configure_audio()
            try:
                audio_utils.disable_usb_autosuspend()
            except Exception:
                pass
            try:
                audio_utils.warmup_audio()
            except Exception:
                pass

            self.signals.status.emit(self.status_text["loading_speech"])
            speech_utils.load_vosk_model()

            self.signals.status.emit("Fetching AI key...")
            self.api_key = fetch_api_key()

            self.system_prompt = cfg.build_system_prompt(self.system_addon)

            self.signals.ready.emit()
        except Exception as e:
            self.signals.error.emit(f"setup_error|{str(e)[:300]}")

    # ----------------------------------------------------------------
    # Conversation turn
    # ----------------------------------------------------------------

    def _start_turn(self):
        if self.is_busy:
            return
        if not self.api_key:
            self._set_status(self.status_text["api_missing"])
            return

        self.is_busy = True
        self.idle_timer.stop()
        threading.Thread(target=self._turn_worker, daemon=True).start()

    def _turn_worker(self):
        try:
            # ---- Listen ----
            self.signals.state.emit("listening")
            self.signals.status.emit(self.status_text["listening"])

            transcript = speech_utils.record_and_transcribe() or ""
            transcript = transcript.strip()

            if not transcript:
                self.signals.status.emit(self.status_text["no_speech"])
                self.signals.state.emit("idle")
                self.signals.finished_turn.emit()
                return

            self.signals.answer.emit(f"You: {transcript}")

            # ---- Guardrail ----
            user_text = transcript
            if cfg.is_blocked(transcript):
                self.bad_attempts += 1
                if self.bad_attempts >= cfg.MAX_INAPPROPRIATE_ATTEMPTS:
                    self.signals.state.emit("idle")
                    self.signals.status.emit(self.status_text["redirect"])
                    self.signals.answer.emit(cfg.CALMDOWN_TEXT)
                    self._speak_safely(cfg.CALMDOWN_TEXT)
                    self.bad_attempts = 0
                    self.signals.finished_turn.emit()
                    return
                # Soft redirect: ask the model to redirect without echoing.
                user_text = cfg.REDIRECT_PROMPT

            # ---- Think ----
            self.signals.state.emit("thinking")
            self.signals.status.emit(self.status_text["thinking"])

            answer, stats = ai_client.chat_completion(
                base_url=AI_BASE_URL,
                api_key=self.api_key,
                model=AI_MODEL,
                system_prompt=self.system_prompt,
                user_text=user_text,
                temperature=cfg.DEFAULT_TEMPERATURE,
                max_tokens=cfg.MAX_TOKENS,
            )

            self.signals.answer.emit(answer)

            # ---- Talk ----
            # NOTE: We do NOT emit state="talking" here. The mouth must stay
            # still during the TTS HTTP fetch (which can take 2-4 seconds).
            # _speak_safely() emits state="talking" only AFTER the MP3 bytes
            # are in hand and immediately before playback starts, so the
            # mouth animation stays in sync with the audio.
            self.signals.status.emit(self.status_text["talking"])
            self._speak_safely(answer)

            self.signals.state.emit("idle")
            self.signals.status.emit(self.status_text["after_answer"])
            self.signals.finished_turn.emit()

        except Exception as e:
            self.signals.error.emit(f"turn_error|{str(e)[:300]}")

    def _speak_safely(self, text: str):
        """
        Run TTS + playback. Failures don't crash the turn.

        Lip-sync strategy:
          1. Face stays in "thinking" while we fetch the TTS MP3 from Poe.
          2. Once we have the MP3 bytes, switch face to "talking" — this is
             the mouth animation start.
          3. Block on playback. mpg123 startup latency (~100-200ms) means
             the mouth begins moving a fraction of a second before audio,
             which is the natural lead for lip-sync (anticipation).
          4. After playback ends, the caller emits "idle".
        """
        try:
            # --- Step 1: fetch TTS (face is "thinking" during this) ---
            mp3 = ai_client.tts_speak(
                base_url=AI_BASE_URL,
                api_key=self.api_key,
                tts_model=AI_TTS_MODEL,
                text=text,
                voice=AI_VOICE,
            )

            if not mp3:
                # Nothing to play — leave face in current state.
                return

            # --- Step 2: switch face to "talking" right before playback ---
            self.signals.state.emit("talking")

            # --- Step 3: block on playback ---
            speaker = getattr(audio_config, "AUDIO_DEVICE", "") or "default"
            play_mp3_bytes(mp3, speaker)

        except Exception as e:
            self.signals.status.emit(f"TTS error: {str(e)[:80]}")

    # ----------------------------------------------------------------
    # Slot handlers (run on Qt main thread)
    # ----------------------------------------------------------------

    def _on_face_tap(self, _event):
        self._on_talk()

    def _on_talk(self):
        self._start_turn()

    def _on_ready(self):
        self.signals.state.emit("idle")
        self.signals.status.emit(self.status_text["ready"])
        self.idle_timer.start(cfg.IDLE_TO_SLEEP_SECONDS * 1000)

    def _on_turn_done(self):
        self.is_busy = False
        self.idle_timer.start(cfg.IDLE_TO_SLEEP_SECONDS * 1000)

    def _on_error(self, packed: str):
        kind, _, msg = packed.partition("|")
        self.signals.state.emit("error")
        if kind == "setup_error":
            self.status_lbl.setText(self.status_text["setup_error"])
        else:
            self.status_lbl.setText(self.status_text["generic_error"])
        self.answer_lbl.setText(msg)
        self.is_busy = False

    def _set_face_state(self, state: str):
        try:
            self.face.set_state(state)
        except Exception:
            pass

    def _set_status(self, text: str):
        self.status_lbl.setText(text)

    def _set_answer(self, text: str):
        self.answer_lbl.setText(text)

    def _go_sleep(self):
        if self.is_busy:
            return
        self.signals.state.emit("sleeping")
        self.signals.status.emit(self.status_text["sleeping"])

    # ----------------------------------------------------------------
    # Exit
    # ----------------------------------------------------------------

    def _clean_exit(self):
        try:
            self.idle_timer.stop()
        except Exception:
            pass
        self.setStyleSheet("background-color: black;")
        for child in self.findChildren(QWidget):
            child.hide()
        self.repaint()
        QApplication.processEvents()
        QTimer.singleShot(100, QApplication.quit)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._clean_exit()
        elif event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_T):
            self._on_talk()


# ============================================================
# Entrypoint
# ============================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    screen = SpringDemoScreen()
    screen.showFullScreen()
    QTimer.singleShot(300, screen.start)
    sys.exit(app.exec_())