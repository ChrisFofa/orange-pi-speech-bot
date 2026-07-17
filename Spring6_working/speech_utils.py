from __future__ import annotations

import json
import os
import queue
import re
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model

import audio_config as config
import audio_utils


# ============================================================
# Speech Utilities
# ============================================================
#
# STT:
# - Vosk local/offline speech recognition.
# - Vosk recognizer uses 16 kHz.
# - USB microphone may run at 16 kHz, 44.1 kHz, or 48 kHz.
# - If mic rate differs, audio is resampled before sending to Vosk.
#
# Important:
# - LLM/TTS require internet.
# - STT can still work offline.
# ============================================================


@dataclass
class SpeechRuntime:
    vosk_model: Model | None = None
    vosk_model_path: str = ""
    mic_sample_rate: int | None = None
    mic_device_index: int | None = None
    last_peak_level: int = 0
    last_transcript: str = ""
    ready: bool = False


runtime = SpeechRuntime()


# ============================================================
# Vosk Model Loading
# ============================================================

def find_vosk_model_path() -> str:
    """
    Find a valid Vosk model directory.

    Uses config.VOSK_FALLBACK_MODEL_PATHS.
    """

    paths = getattr(config, "VOSK_FALLBACK_MODEL_PATHS", [])

    for path in paths:
        if not path:
            continue

        expanded = os.path.abspath(os.path.expanduser(path))

        if os.path.isdir(expanded):
            # Basic check for Vosk model files/folders.
            if (
                os.path.isdir(os.path.join(expanded, "am"))
                or os.path.exists(os.path.join(expanded, "conf", "model.conf"))
                or os.path.exists(os.path.join(expanded, "ivector"))
            ):
                return expanded

            # Some model layouts may not match exactly; still allow directory.
            return expanded

    return ""


def load_vosk_model(force_reload: bool = False) -> Model:
    """
    Load Vosk model.

    Raises:
      FileNotFoundError if no model exists.
      RuntimeError for model load failure.
    """

    if runtime.vosk_model is not None and not force_reload:
        return runtime.vosk_model

    model_path = find_vosk_model_path()

    if not model_path:
        searched = "\n".join(
            f"  - {os.path.abspath(os.path.expanduser(p))}"
            for p in getattr(config, "VOSK_FALLBACK_MODEL_PATHS", [])
        )

        raise FileNotFoundError(
            "No Vosk model found. Searched:\n" + searched
        )

    try:
        print(f"Loading Vosk model from {model_path}")
        runtime.vosk_model = Model(model_path)
        runtime.vosk_model_path = model_path
        runtime.ready = True
        return runtime.vosk_model

    except Exception as e:
        runtime.ready = False
        raise RuntimeError(f"Failed to load Vosk model from {model_path}: {e}") from e


def is_speech_ready() -> bool:
    return runtime.vosk_model is not None and runtime.ready


# ============================================================
# Microphone Setup
# ============================================================

def detect_microphone() -> tuple[int | None, int]:
    """
    Detect sounddevice mic index and sample rate.

    Returns:
      (device_index, sample_rate)
    """

    device_index = audio_utils.get_mic_device_index()
    sample_rate = audio_utils.detect_mic_sample_rate(device_index)

    runtime.mic_device_index = device_index
    runtime.mic_sample_rate = sample_rate

    return device_index, sample_rate


def ensure_microphone_ready() -> tuple[int | None, int]:
    """
    Ensure mic index/sample rate are available.
    """

    if runtime.mic_sample_rate is None:
        return detect_microphone()

    return runtime.mic_device_index, runtime.mic_sample_rate


# ============================================================
# Audio Resampling
# ============================================================

def resample_audio(
    audio_data: np.ndarray,
    orig_rate: int,
    target_rate: int,
) -> np.ndarray:
    """
    Resample int16 mono audio using linear interpolation.

    This is lightweight and good enough for speech recognition.
    """

    if orig_rate == target_rate:
        return audio_data

    if len(audio_data) == 0:
        return audio_data

    ratio = target_rate / orig_rate
    new_length = max(1, int(len(audio_data) * ratio))

    old_indices = np.arange(len(audio_data))
    new_indices = np.linspace(0, len(audio_data) - 1, new_length)

    resampled = np.interp(
        new_indices,
        old_indices,
        audio_data.astype(np.float32),
    )

    return resampled.astype(np.int16)


# ============================================================
# Recording / Transcription
# ============================================================

def record_and_transcribe(
    silence_threshold: int | None = None,
    silence_duration: float | None = None,
    max_record_seconds: int | None = None,
    on_level=None,
) -> str | None:
    """
    Record from microphone until silence, then transcribe with Vosk.

    Args:
      silence_threshold:
        Lower = more sensitive. Default config.SILENCE_THRESHOLD.

      silence_duration:
        Seconds of quiet before stopping.

      max_record_seconds:
        Maximum recording length.

      on_level:
        Optional callback called as on_level(level, threshold).
        Useful for UI/debug.

    Returns:
      transcript string or None.
    """

    model = runtime.vosk_model or load_vosk_model()

    device_index, mic_rate = ensure_microphone_ready()

    if mic_rate is None:
        mic_rate = 44100

    silence_threshold = (
        int(silence_threshold)
        if silence_threshold is not None
        else int(config.SILENCE_THRESHOLD)
    )

    silence_duration = (
        float(silence_duration)
        if silence_duration is not None
        else float(config.SILENCE_DURATION)
    )

    max_record_seconds = (
        int(max_record_seconds)
        if max_record_seconds is not None
        else int(config.MAX_RECORD_SECONDS)
    )

    recognizer = KaldiRecognizer(model, int(config.VOSK_SAMPLE_RATE))

    audio_queue: queue.Queue[bytes] = queue.Queue()

    def callback(indata, frames, time_info, status) -> None:
        if status:
            # Do not spam too much; useful during debugging.
            if getattr(config, "DEBUG_MODE", False):
                print("Input status:", status)

        audio_queue.put(bytes(indata))

    frames_collected = 0
    silent_chunks = 0
    peak_level = 0

    chunk_seconds = 0.1
    chunk_samples = max(256, int(mic_rate * chunk_seconds))

    max_silent_chunks = max(1, int(silence_duration / chunk_seconds))
    max_chunks = max(1, int(max_record_seconds / chunk_seconds))

    print(
        f"Listening: device={device_index}, "
        f"mic_rate={mic_rate}, threshold={silence_threshold}"
    )

    try:
        with sd.RawInputStream(
            samplerate=mic_rate,
            blocksize=chunk_samples,
            dtype=config.DTYPE,
            channels=config.CHANNELS,
            device=device_index,
            callback=callback,
        ):
            for _ in range(max_chunks):
                try:
                    data = audio_queue.get(timeout=0.3)
                except queue.Empty:
                    continue

                frames_collected += 1

                audio_chunk = np.frombuffer(data, dtype=np.int16)

                if audio_chunk.size == 0:
                    continue

                level = int(np.abs(audio_chunk).mean())
                peak_level = max(peak_level, level)

                if on_level:
                    try:
                        on_level(level, silence_threshold)
                    except Exception:
                        pass

                if int(mic_rate) != int(config.VOSK_SAMPLE_RATE):
                    resampled = resample_audio(
                        audio_chunk,
                        int(mic_rate),
                        int(config.VOSK_SAMPLE_RATE),
                    )
                    recognizer.AcceptWaveform(resampled.tobytes())
                else:
                    recognizer.AcceptWaveform(data)

                if level < silence_threshold:
                    silent_chunks += 1

                    # Require at least ~1 second of recorded frames before stopping.
                    if silent_chunks >= max_silent_chunks and frames_collected > 10:
                        break
                else:
                    silent_chunks = 0

    except Exception as e:
        print("Recording error:", e)
        runtime.last_peak_level = peak_level
        return None

    runtime.last_peak_level = peak_level

    print(f"Peak level: {peak_level}")

    if frames_collected < 5:
        return None

    try:
        final_result = recognizer.FinalResult()
        result_json = json.loads(final_result)
        text = str(result_json.get("text", "")).strip()

        runtime.last_transcript = text

        if text:
            print(f'Transcript: "{text}"')
            return text

        return None

    except Exception as e:
        print("Transcription parse error:", e)
        return None


# ============================================================
# Text Cleaning
# ============================================================

def clean_for_speech(text: str) -> str:
    """
    Clean LLM output before TTS.

    Removes:
    - emoji
    - markdown symbols
    - excessive whitespace

    Keeps normal punctuation.
    """

    t = text or ""

    # Remove most emoji/symbol pictographs.
    t = re.sub(r"[\U0001F300-\U0001FAFF]", "", t)

    # Remove common markdown formatting.
    t = t.replace("*", "")
    t = t.replace("_", "")
    t = t.replace("#", "")
    t = t.replace("`", "")

    # Remove speaker-label style if model accidentally emits it.
    t = re.sub(r"^\s*[A-Z][A-Za-z]{1,12}\s*:\s*", "", t)

    # Collapse whitespace.
    t = re.sub(r"\s+", " ", t).strip()

    # Limit length for TTS safety.
    max_len = int(getattr(config, "MAX_BOT_TEXT_LENGTH", 1200))

    if max_len > 0 and len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0].strip()
        t += "."

    return t


def clean_user_text(text: str) -> str:
    """
    Clean recognized user text before sending to LLM.
    """

    t = text or ""
    t = re.sub(r"\s+", " ", t).strip()

    max_len = int(getattr(config, "MAX_USER_TEXT_LENGTH", 500))

    if max_len > 0 and len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0].strip()

    return t


# ============================================================
# Diagnostics
# ============================================================

def get_speech_diagnostics() -> str:
    lines: list[str] = []

    lines.append("========== SPEECH DIAGNOSTICS ==========")
    lines.append(f"VOSK_MODEL_PATH={getattr(config, 'VOSK_MODEL_PATH', '')}")
    lines.append(f"runtime.vosk_model_path={runtime.vosk_model_path}")
    lines.append(f"speech_ready={is_speech_ready()}")
    lines.append(f"mic_device_index={runtime.mic_device_index}")
    lines.append(f"mic_sample_rate={runtime.mic_sample_rate}")
    lines.append(f"last_peak_level={runtime.last_peak_level}")
    lines.append(f"last_transcript={runtime.last_transcript}")
    lines.append("Fallback model paths:")

    for p in getattr(config, "VOSK_FALLBACK_MODEL_PATHS", []):
        expanded = os.path.abspath(os.path.expanduser(p))
        exists = os.path.isdir(expanded)
        lines.append(f"  {'yes' if exists else ' no'}  {expanded}")

    lines.append("========================================")

    return "\n".join(lines)


def print_speech_diagnostics() -> None:
    print(get_speech_diagnostics())


# ============================================================
# CLI Test
# ============================================================

def main() -> None:
    """
    Simple command-line test:
      python3 speech_utils.py
    """

    print("Speech utility test")
    print("===================")

    audio_utils.configure_audio()

    print("Loading Vosk...")
    load_vosk_model()

    print("Detecting microphone...")
    device_index, sample_rate = detect_microphone()
    print(f"Mic device index: {device_index}")
    print(f"Mic sample rate: {sample_rate}")

    input("Press ENTER and speak...")

    text = record_and_transcribe()

    if text:
        print("You said:", text)
    else:
        print("No speech detected.")


if __name__ == "__main__":
    main()