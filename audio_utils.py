from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from typing import Any

import sounddevice as sd

import audio_config as config


# ============================================================
# Audio Utilities
# ============================================================
#
# Hardware from current Orange Pi Zero 3 setup:
#
# Speaker:
#   Jieli Technology UACDemoV1.0
#   USB ID: 4C4A:4155
#
# Microphone:
#   C-Media USB PnP Sound Device
#   USB ID: 08BB:2902
#
# Important:
# - ALSA card numbers can change on reboot.
# - Do NOT hardcode card 3/card 4.
# - Detect cards by /proc/asound/card*/usbid.
# ============================================================


@dataclass
class AudioDevices:
    speaker_card: int | None = None
    mic_card: int | None = None
    speaker_device: str = ""
    mic_device: str = ""
    sounddevice_mic_index: int | None = None
    speaker_found: bool = False
    mic_found: bool = False


# Runtime cache
_detected_devices = AudioDevices()


# ============================================================
# Command Helpers
# ============================================================

def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def run_cmd(
    cmd: list[str],
    timeout: int = 5,
    check: bool = False,
) -> subprocess.CompletedProcess | None:
    """
    Run a command safely.

    Returns CompletedProcess or None.
    Does not raise unless check=True and subprocess itself raises.
    """

    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=check,
        )
    except Exception:
        return None


def run_shell(
    command: str,
    timeout: int = 5,
) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["bash", "-lc", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return None


# ============================================================
# ALSA Card Detection
# ============================================================

def list_asound_usb_ids() -> dict[int, str]:
    """
    Return mapping of ALSA card number -> USB ID.

    Example:
    {
        3: "4c4a:4155",
        4: "08bb:2902"
    }
    """

    cards: dict[int, str] = {}

    result = run_shell(
        'for c in /proc/asound/card*/usbid; do '
        '[ -f "$c" ] && echo "$c $(cat "$c")"; '
        'done',
        timeout=5,
    )

    if not result or not result.stdout:
        return cards

    for line in result.stdout.splitlines():
        line = line.strip()

        match = re.search(r"/proc/asound/card(\d+)/usbid\s+([0-9A-Fa-f]{4}:[0-9A-Fa-f]{4})", line)

        if match:
            card_num = int(match.group(1))
            usb_id = match.group(2).lower()
            cards[card_num] = usb_id

    return cards


def find_alsa_card_by_usb_id(usb_id: str) -> int | None:
    """
    Find ALSA card number by USB vendor:product ID.

    Example:
      find_alsa_card_by_usb_id("4C4A:4155")
    """

    target = (usb_id or "").strip().lower()

    if not target:
        return None

    cards = list_asound_usb_ids()

    for card, found_usb_id in cards.items():
        if found_usb_id.lower() == target:
            return card

    return None


def get_card_name(card_num: int) -> str:
    path = f"/proc/asound/card{card_num}/id"

    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def get_card_long_name(card_num: int) -> str:
    path = f"/proc/asound/card{card_num}/usblongname"

    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


# ============================================================
# ALSA Mixer Helpers
# ============================================================

def amixer_sset(card: int, control: str, value: str, timeout: int = 5) -> bool:
    result = run_cmd(
        ["amixer", "-c", str(card), "sset", control, value],
        timeout=timeout,
    )

    return bool(result and result.returncode == 0)


def amixer_sget(card: int, control: str, timeout: int = 5) -> str:
    result = run_cmd(
        ["amixer", "-c", str(card), "sget", control],
        timeout=timeout,
    )

    if result and result.stdout:
        return result.stdout

    return ""


def configure_speaker_mixer(card: int) -> None:
    """
    Configure speaker volume.

    Current speaker uses:
      PCM Playback Volume
      PCM Playback Switch
    """

    volume = max(0, min(100, int(getattr(config, "SPEAKER_VOLUME_PERCENT", 90))))

    # Main known control.
    amixer_sset(card, "PCM", f"{volume}%")
    amixer_sset(card, "PCM", "unmute")

    # Fallback controls for other USB audio adapters.
    amixer_sset(card, "Speaker", f"{volume}%")
    amixer_sset(card, "Speaker", "unmute")
    amixer_sset(card, "Master", f"{volume}%")
    amixer_sset(card, "Master", "unmute")


def configure_microphone_mixer(card: int) -> None:
    """
    Configure microphone capture.

    Current microphone uses:
      Mic Capture Volume
      Mic Capture Switch
      Auto Gain Control
    """

    volume = max(0, min(100, int(getattr(config, "MIC_VOLUME_PERCENT", 87))))

    # Main known control.
    amixer_sset(card, "Mic", f"{volume}%")
    amixer_sset(card, "Mic", "cap")

    # Fallback controls.
    amixer_sset(card, "Capture", f"{volume}%")
    amixer_sset(card, "Capture", "cap")

    if getattr(config, "MIC_AUTO_GAIN", True):
        amixer_sset(card, "Auto Gain Control", "on")
    else:
        amixer_sset(card, "Auto Gain Control", "off")


# ============================================================
# Audio Configuration
# ============================================================

def configure_audio() -> AudioDevices:
    """
    Detect and configure speaker/mic.

    Updates:
      config.AUDIO_DEVICE
      config.MIC_DEVICE

    Returns:
      AudioDevices dataclass
    """

    global _detected_devices

    speaker_card = find_alsa_card_by_usb_id(config.SPEAKER_USB_ID)
    mic_card = find_alsa_card_by_usb_id(config.MIC_USB_ID)

    devices = AudioDevices()

    if speaker_card is not None:
        devices.speaker_card = speaker_card
        devices.speaker_device = f"plughw:{speaker_card},0"
        devices.speaker_found = True

        config.AUDIO_DEVICE = devices.speaker_device

        configure_speaker_mixer(speaker_card)

        print(
            "Speaker detected:",
            f"card={speaker_card}",
            f"device={devices.speaker_device}",
            f"name={get_card_name(speaker_card)}",
        )
    else:
        devices.speaker_card = None
        devices.speaker_device = getattr(config, "AUDIO_DEVICE", "")
        devices.speaker_found = False

        print("Speaker USB ID not found. Using default playback device.")

    if mic_card is not None:
        devices.mic_card = mic_card
        devices.mic_device = f"plughw:{mic_card},0"
        devices.mic_found = True

        config.MIC_DEVICE = devices.mic_device

        configure_microphone_mixer(mic_card)

        print(
            "Microphone detected:",
            f"card={mic_card}",
            f"alsa={devices.mic_device}",
            f"name={get_card_name(mic_card)}",
        )
    else:
        devices.mic_card = None
        devices.mic_device = getattr(config, "MIC_DEVICE", "")
        devices.mic_found = False

        print("Microphone USB ID not found. Using sounddevice default input.")

    devices.sounddevice_mic_index = get_mic_device_index()

    _detected_devices = devices
    return devices


def get_detected_devices() -> AudioDevices:
    return _detected_devices


# ============================================================
# USB Power
# ============================================================

def disable_usb_autosuspend() -> None:
    """
    Try to disable USB autosuspend.

    This may require root permissions.
    Failure is ignored because the kiosk should still run.
    """

    result = run_cmd(
        ["find", "/sys/bus/usb/devices", "-name", "power"],
        timeout=5,
    )

    if not result or not result.stdout:
        return

    for usb_path in result.stdout.strip().splitlines():
        usb_path = usb_path.strip()

        if not usb_path:
            continue

        control_file = os.path.join(usb_path, "control")

        if not os.path.exists(control_file):
            continue

        try:
            with open(control_file, "w", encoding="utf-8") as f:
                f.write("on")
        except Exception:
            pass


# ============================================================
# SoundDevice Microphone Helpers
# ============================================================

def query_sound_devices() -> list[dict[str, Any]]:
    try:
        devices = sd.query_devices()
        return [dict(d) for d in devices]
    except Exception:
        return []


def print_sound_devices() -> None:
    try:
        print(sd.query_devices())
    except Exception as e:
        print("Could not query sound devices:", e)


def get_mic_device_index() -> int | None:
    """
    Find a microphone device index for sounddevice.

    Priority:
    1. C-Media / USB PnP / USB input device
    2. Any input device
    """

    try:
        devices = sd.query_devices()

        # Prefer known USB microphone.
        for i, d in enumerate(devices):
            name = str(d.get("name", "")).lower()
            max_inputs = int(d.get("max_input_channels", 0))

            if max_inputs <= 0:
                continue

            if (
                "c-media" in name
                or "usb pnp" in name
                or "usb audio" in name
                or "usb" in name
            ):
                return i

        # Fallback to first input device.
        for i, d in enumerate(devices):
            max_inputs = int(d.get("max_input_channels", 0))

            if max_inputs > 0:
                return i

    except Exception as e:
        print("Microphone query error:", e)

    return None


def detect_mic_sample_rate(device_index: int | None) -> int:
    """
    Detect supported mic sample rate.

    Vosk prefers 16000 Hz, but some USB mics work more reliably
    at 44100/48000 and then we resample in software.
    """

    rates_to_try = [16000, 44100, 48000, 22050, 32000, 8000]

    for rate in rates_to_try:
        try:
            with sd.RawInputStream(
                samplerate=rate,
                blocksize=1024,
                dtype=config.DTYPE,
                channels=config.CHANNELS,
                device=device_index,
            ):
                pass

            return rate

        except Exception:
            continue

    try:
        if device_index is not None:
            info = sd.query_devices(device_index)
            return int(info.get("default_samplerate", 44100))
    except Exception:
        pass

    return 44100


# ============================================================
# Audio Format Detection
# ============================================================

def detect_audio_format(data: bytes) -> str:
    if not data or len(data) < 12:
        return "unknown"

    # MP3 can start with ID3 or frame sync.
    if data[:3] == b"ID3":
        return "mp3"

    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "mp3"

    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"

    if data[:4] == b"OggS":
        return "ogg"

    # Poe/ElevenLabs usually returns MP3 if unknown.
    return "mp3"


def extension_for_audio_format(fmt: str) -> str:
    fmt = (fmt or "").lower()

    if fmt == "wav":
        return ".wav"

    if fmt == "ogg":
        return ".ogg"

    if fmt == "mp3":
        return ".mp3"

    return ".mp3"


# ============================================================
# Playback
# ============================================================

def play_audio_file(path: str, fmt: str = "") -> bool:
    """
    Play an audio file using ALSA tools.

    WAV:
      aplay

    MP3:
      mpg123

    OGG:
      ogg123

    Uses config.AUDIO_DEVICE if available.
    """

    if not path or not os.path.exists(path):
        return False

    fmt = (fmt or "").lower().strip()

    if not fmt:
        ext = os.path.splitext(path)[1].lower()

        if ext == ".wav":
            fmt = "wav"
        elif ext == ".ogg":
            fmt = "ogg"
        else:
            fmt = "mp3"

    audio_device = getattr(config, "AUDIO_DEVICE", "")

    try:
        if fmt == "wav":
            if not command_exists("aplay"):
                print("aplay not found.")
                return False

            cmd = ["aplay", "-q"]

            if audio_device:
                cmd.extend(["-D", audio_device])

            cmd.append(path)

        elif fmt == "ogg":
            if not command_exists("ogg123"):
                print("ogg123 not found.")
                return False

            cmd = ["ogg123", "-q"]

            # ogg123 ALSA device support can vary, so keep simple first.
            # If default audio routing fails, use MP3/WAV TTS output instead.
            cmd.append(path)

        else:
            if not command_exists("mpg123"):
                print("mpg123 not found.")
                return False

            cmd = ["mpg123", "-q"]

            if audio_device:
                cmd.extend(["-o", "alsa", "-a", audio_device])

            cmd.append(path)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        if result.returncode != 0:
            if result.stderr:
                print("Playback stderr:", result.stderr.strip())
            return False

        return True

    except Exception as e:
        print("Playback error:", e)
        return False


def play_audio_bytes(audio_bytes: bytes, fmt: str = "") -> bool:
    """
    Save audio bytes to a temp file and play it.
    """

    if not audio_bytes:
        return False

    if not fmt:
        fmt = detect_audio_format(audio_bytes)

    ext = extension_for_audio_format(fmt)

    audio_path = ""

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(audio_bytes)
            audio_path = f.name

        return play_audio_file(audio_path, fmt)

    finally:
        if audio_path:
            try:
                os.unlink(audio_path)
            except Exception:
                pass


# ============================================================
# Audio Warmup
# ============================================================

def create_silent_wav(path: str, seconds: float = 0.35, sample_rate: int = 44100) -> None:
    """
    Create a short silent WAV file.
    """

    samples = max(1, int(sample_rate * seconds))

    with wave.open(path, "w") as wavf:
        wavf.setnchannels(1)
        wavf.setsampwidth(2)
        wavf.setframerate(sample_rate)

        # Write in chunks to avoid creating a huge Python list.
        chunk = struct.pack("<h", 0) * min(samples, 4096)
        remaining = samples

        while remaining > 0:
            count = min(remaining, 4096)
            wavf.writeframes(struct.pack("<h", 0) * count)
            remaining -= count


def warmup_audio() -> None:
    """
    Warm up the USB speaker to reduce first-play pop/click.
    """

    disable_usb_autosuspend()

    wav_path = ""

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name

        create_silent_wav(wav_path, seconds=0.35, sample_rate=44100)
        play_audio_file(wav_path, "wav")
        time.sleep(0.1)

    except Exception:
        pass

    finally:
        if wav_path:
            try:
                os.unlink(wav_path)
            except Exception:
                pass


# ============================================================
# Diagnostics
# ============================================================

def get_audio_diagnostics() -> str:
    """
    Return a text diagnostic summary.
    """

    lines: list[str] = []

    lines.append("========== AUDIO DIAGNOSTICS ==========")
    lines.append(f"SPEAKER_USB_ID={config.SPEAKER_USB_ID}")
    lines.append(f"MIC_USB_ID={config.MIC_USB_ID}")
    lines.append("")

    lines.append("ALSA USB IDs:")
    cards = list_asound_usb_ids()

    if cards:
        for card, usb_id in sorted(cards.items()):
            lines.append(
                f"  card {card}: {usb_id} "
                f"id={get_card_name(card)} "
                f"name={get_card_long_name(card)}"
            )
    else:
        lines.append("  none found")

    lines.append("")
    lines.append(f"config.AUDIO_DEVICE={getattr(config, 'AUDIO_DEVICE', '')}")
    lines.append(f"config.MIC_DEVICE={getattr(config, 'MIC_DEVICE', '')}")

    lines.append("")
    lines.append("Tools:")
    for tool in ["aplay", "arecord", "amixer", "mpg123", "ogg123"]:
        lines.append(f"  {tool}: {'yes' if command_exists(tool) else 'no'}")

    lines.append("")
    lines.append("sounddevice devices:")

    try:
        lines.append(str(sd.query_devices()))
    except Exception as e:
        lines.append(f"  error: {e}")

    lines.append("=======================================")

    return "\n".join(lines)


def print_audio_diagnostics() -> None:
    print(get_audio_diagnostics())


def quick_speaker_test() -> bool:
    """
    Play short silence through configured speaker.
    Useful as a no-annoying-sound test.
    """

    warmup_audio()
    return True