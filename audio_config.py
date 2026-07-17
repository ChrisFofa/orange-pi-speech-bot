"""
audio_config.py
================

INTERNAL PLUMBING — do not edit settings here.

All user-editable values live in `bot_config.py` (the one file you edit).
This file only:
  1. Re-exports those values so the audio code can read them, and
  2. Holds low-level hardware constants (ALSA device strings, sample
     format) that `audio_utils.py` mutates at runtime when it detects
     the USB sound cards.
"""

from __future__ import annotations

import os
from pathlib import Path

import bot_config as _bc


# ============================================================
# User-editable values (from bot_config.py)
# ============================================================

SPEAKER_USB_ID = _bc.SPEAKER_USB_ID
MIC_USB_ID = _bc.MIC_USB_ID

SILENCE_THRESHOLD = _bc.SILENCE_THRESHOLD
SILENCE_DURATION = _bc.SILENCE_DURATION
MAX_RECORD_SECONDS = _bc.MAX_RECORD_SECONDS
USE_VOSK_ENDPOINTING = _bc.USE_VOSK_ENDPOINTING

VOSK_SAMPLE_RATE = _bc.VOSK_SAMPLE_RATE

SPEAKER_VOLUME_PERCENT = _bc.SPEAKER_VOLUME_PERCENT
MIC_VOLUME_PERCENT = _bc.MIC_VOLUME_PERCENT
ENABLE_MIC_AGC = _bc.ENABLE_MIC_AGC

DEBUG_MODE = _bc.DEBUG_MODE

MAX_BOT_TEXT_LENGTH = _bc.MAX_BOT_TEXT_LENGTH
MAX_USER_TEXT_LENGTH = _bc.MAX_USER_TEXT_LENGTH


# ============================================================
# Low-level hardware constants (not user settings)
# ============================================================

# ALSA device strings. audio_utils.py mutates these once USB detection
# succeeds at startup; until then these fallbacks are used.
AUDIO_DEVICE = "plughw:3,0"   # speaker fallback
MIC_DEVICE = "plughw:4,0"     # mic fallback

# Recording format.
DTYPE = "int16"
CHANNELS = 1


# ============================================================
# Vosk model search paths (built from bot_config.VOSK_MODEL_FOLDER)
# ============================================================

_EVENT_DIR = Path(__file__).resolve().parent
_MODEL = _bc.VOSK_MODEL_FOLDER

VOSK_FALLBACK_MODEL_PATHS = [
    str(_EVENT_DIR / _MODEL),
    str(_EVENT_DIR / "models" / _MODEL),
    f"/opt/bigbang/events/Spring Demo/{_MODEL}",
    f"/opt/bigbang/models/{_MODEL}",
    f"/usr/share/vosk/{_MODEL}",
    os.path.expanduser(f"~/{_MODEL}"),
]
