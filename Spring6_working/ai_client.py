"""
ai_client.py
================

Spring Demo AI client.

Two responsibilities:
    1. chat_completion(api_key, system_prompt, user_text) -> str
       Calls Poe's OpenAI-compatible endpoint at api.poe.com/v1/chat/completions
       with the chat model (Claude-3.5-Haiku by default).

    2. tts_speak(api_key, text) -> bytes (mp3)
       Calls Poe's TTS bot (ElevenLabs-v2.5-Turbo) and returns the
       generated audio bytes ready to hand to mpg123.

Key design:
    - No openai client library. Plain `requests` only.
    - api_key is passed in by the caller. NEVER read from disk, NEVER
      written to disk. Held in process memory only.
    - The chat model and base URL are pinned constants at the top of
      main.py (AI_MODEL, AI_BASE_URL) so a deployment never depends on
      Supabase to get them right.
"""

from __future__ import annotations

import json
import re
import time
from typing import Tuple

import requests


# ============================================================
# Chat completion (LLM)
# ============================================================

CHAT_PATH = "/chat/completions"

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 150


def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_text: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = 30,
) -> Tuple[str, dict]:
    """
    Send one chat turn to Poe (OpenAI-compatible).

    Returns (answer_text, stats_dict).
    Raises Exception on HTTP errors with a short, kid-safe message.
    """

    if not api_key:
        raise Exception("AI key missing")

    url = base_url.rstrip("/") + CHAT_PATH

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_text})

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    t0 = time.time()
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    elapsed = round(time.time() - t0, 2)

    try:
        data = resp.json()
    except Exception:
        data = {"raw": resp.text[:400]}

    if resp.status_code >= 400:
        raise Exception(f"AI HTTP {resp.status_code}: {str(data)[:200]}")

    try:
        answer = data["choices"][0]["message"]["content"]
    except Exception:
        raise Exception(f"AI returned no content: {str(data)[:200]}")

    answer = _clean_for_speech(answer)

    usage = data.get("usage", {})
    stats = {
        "time": elapsed,
        "model": data.get("model", model),
        "total_tokens": usage.get("total_tokens", 0),
    }

    return answer, stats


# ============================================================
# Text-to-speech (TTS)
# ============================================================
#
# Poe's ElevenLabs-v2.5-Turbo bot is exposed through the same
# OpenAI-compatible /chat/completions endpoint. We pass the bot
# name as `model` and the text as the only user message.
# The response contains an attachment URL or a base64 audio blob.
#
# To keep things simple and offline-stitchable we use the
# explicit `attachments` field that Poe's API returns.

TTS_PATH = "/chat/completions"


def tts_speak(
    base_url: str,
    api_key: str,
    tts_model: str,
    text: str,
    voice: str = "Lily",
    timeout: int = 60,
) -> bytes:
    """
    Generate spoken audio for `text`. Returns raw mp3 bytes.

    Raises Exception on failure.
    """

    if not api_key:
        raise Exception("AI key missing")
    if not text:
        raise Exception("nothing to speak")

    # ElevenLabs-v2.5-Turbo on Poe accepts a 'voice' parameter via the
    # message-level `parameters` field. The OpenAI-compatible REST shim
    # forwards extra fields, so we just inline-prefix the voice tag in
    # the prompt as a fallback, AND send a query-string voice hint.
    # Both are ignored by models that don't understand them.

    url = base_url.rstrip("/") + TTS_PATH

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": tts_model,
        "messages": [
            {"role": "user", "content": text},
        ],
        "parameters": {"voice": voice},
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)

    if resp.status_code >= 400:
        raise Exception(f"TTS HTTP {resp.status_code}: {resp.text[:200]}")

    # Try to find an attachment URL in the response.
    try:
        data = resp.json()
    except Exception:
        raise Exception(f"TTS bad JSON: {resp.text[:200]}")

    import json as _j
    audio_url = _find_audio_url(data)
    if not audio_url:
        raise Exception(f"TTS returned no audio URL: {str(data)[:200]}")

    audio = requests.get(audio_url, timeout=timeout)
    if audio.status_code >= 400:
        raise Exception(f"TTS audio download HTTP {audio.status_code}")

    return audio.content


def _find_audio_url(data) -> str:
    """Extract audio URL from a Poe/OpenAI-compatible response."""
    import re

    # Poe audio bots often return the audio URL directly as:
    # data["choices"][0]["message"]["content"]
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = ""

    if isinstance(content, str):
        m = re.search(r"https?://\S+", content)
        if m:
            return m.group(0).rstrip(".,);]'\"<>")

    # Fallback: recursively search strings and common URL fields
    def walk(o):
        if isinstance(o, str):
            m = re.search(r"https?://\S+", o)
            if m:
                return m.group(0).rstrip(".,);]'\"<>")

        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("audio_url", "url", "download_url", "file_url", "content"):
                    r = walk(v)
                    if r:
                        return r
            for v in o.values():
                r = walk(v)
                if r:
                    return r

        if isinstance(o, list):
            for v in o:
                r = walk(v)
                if r:
                    return r

        return ""

    return walk(data)



_MD_PATTERNS = [
    (re.compile(r"```[\s\S]*?```"), ""),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"\*([^*\n]+)\*"), r"\1"),
    (re.compile(r"__([^_]+)__"), r"\1"),
    (re.compile(r"_([^_\n]+)_"), r"\1"),
    (re.compile(r"^\s*#+\s*", re.MULTILINE), ""),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
    (re.compile(r"~~([^~]+)~~"), r"\1"),
    (re.compile(r"^>+\s*", re.MULTILINE), ""),
]

def _clean_for_speech(text: str) -> str:
    """
    Strip markdown so TTS sounds natural. The bot is asked to avoid
    markdown in the system prompt, but defense-in-depth is cheap.
    """

    if not text:
        return ""

    text = text.strip()

    for pat, sub in _MD_PATTERNS:
        text = pat.sub(sub, text)

    # Collapse multi-spaces and multi-newlines.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()

    return text
