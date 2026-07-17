"""
audio_config.py
================

Audio + speech runtime constants for Spring Demo.

Imported as `import audio_config as config` from audio_utils.py and
speech_utils.py so they can keep their original `config.XXX` references
without colliding with DEMO1's Supabase config.py.

These values are intentionally Pi-specific. If a different Pi or USB
device set is used in the future, just update SPEAKER_USB_ID / MIC_USB_ID
and VOSK_FALLBACK_MODEL_PATHS.
"""

from __future__ import annotations

import os
from pathlib import Path


# ============================================================
# USB device IDs (vendor:product, lowercase, no colon spaces)
# ============================================================
# Detected by /proc/asound/cardN/usbid so card numbers can shift.

# Jieli Technology UACDemoV1.0
SPEAKER_USB_ID = "4c4a:4155"

# C-Media USB PnP Sound Device
MIC_USB_ID = "1620:0b21"


# ============================================================
# ALSA device strings (filled in at runtime by audio_utils.detect)
# ============================================================
# audio_utils.py mutates these once detection succeeds.

AUDIO_DEVICE = "plughw:3,0"   # speaker fallback
MIC_DEVICE = "plughw:4,0"     # mic fallback


# ============================================================
# Recording format
# ============================================================

DTYPE = "int16"
CHANNELS = 1


# ============================================================
# Vosk speech-to-text
# ============================================================

VOSK_SAMPLE_RATE = 16000

# Where to look for the unzipped Vosk model folder.
# First match wins. Add more paths if needed.
_EVENT_DIR = Path(__file__).resolve().parent

VOSK_FALLBACK_MODEL_PATHS = [
    str(_EVENT_DIR / "vosk-model-small-en-us-0.15"),
    str(_EVENT_DIR / "models" / "vosk-model-small-en-us-0.15"),
    "/opt/bigbang/events/Spring Demo/vosk-model-small-en-us-0.15",
    "/opt/bigbang/models/vosk-model-small-en-us-0.15",
    "/usr/share/vosk/vosk-model-small-en-us-0.15",
    os.path.expanduser("~/vosk-model-small-en-us-0.15"),
]


# ============================================================
# Recording loop tuning (for speech_utils.record_until_silence)
# ============================================================

# Lower = more sensitive to quiet voices. 500 is a good Pi default.
SILENCE_THRESHOLD = 500

# How many seconds of silence end the recording.
SILENCE_DURATION = 1.5

# Hard cap on a single utterance (seconds).
MAX_RECORD_SECONDS = 12


# ============================================================
# Speaker volume / mic capture defaults applied at startup
# ============================================================

SPEAKER_VOLUME_PERCENT = 80
MIC_VOLUME_PERCENT = 100
ENABLE_MIC_AGC = True
