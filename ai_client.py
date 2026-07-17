"""
ai_client.py
================

Spring Demo AI client — talks to Poe's OpenAI-compatible API.

Three responsibilities:

    1. chat_completion(...) -> (answer_text, stats)
       Classic one-shot call: waits for the WHOLE answer. Kept as the
       fallback path when streaming is disabled or fails.

    2. chat_completion_stream(...) -> yields text pieces as they arrive
       Streaming call: the answer trickles in word-by-word, so the bot
       can start working on sentence 1 while the rest is still being
       written. Use iter_sentences() to chop the stream into sentences.

    3. tts_speak(...) -> mp3 bytes
       Turns one piece of text into spoken audio.

Speed features:
    - One shared keep-alive HTTP session is reused for every call, so
      we pay the connection-setup cost (TLS handshake) once instead of
      three times per turn. warmup() opens it at startup.
    - Set keep_alive=False on any call to go back to plain requests.

Key design:
    - No openai client library. Plain `requests` only.
    - api_key is passed in by the caller. NEVER read from disk, NEVER
      written to disk. Held in process memory only.
    - This module reads NO settings itself; callers pass model names,
      timeouts, and switches in. (User settings live in bot_config.py.)
"""

from __future__ import annotations

import json
import re
import time
from typing import Generator, Iterable, Tuple

import requests


CHAT_PATH = "/chat/completions"
TTS_PATH = "/chat/completions"

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 90


# ============================================================
# Shared keep-alive HTTP session
# ============================================================

_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    """
    One process-wide session. Reusing it keeps the TLS connection to
    api.poe.com warm, which saves roughly 0.3-0.8 s per call on a Pi.
    """
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=4,
            pool_maxsize=4,
            max_retries=0,
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _SESSION = s
    return _SESSION


def _post(url, headers, payload, timeout, stream=False, keep_alive=True):
    if keep_alive:
        return _get_session().post(
            url, headers=headers, json=payload, timeout=timeout, stream=stream
        )
    return requests.post(
        url, headers=headers, json=payload, timeout=timeout, stream=stream
    )


def _get(url, timeout, keep_alive=True):
    if keep_alive:
        return _get_session().get(url, timeout=timeout)
    return requests.get(url, timeout=timeout)


def warmup(base_url: str, api_key: str = "", timeout: int = 8) -> None:
    """
    Fire one tiny request at startup so DNS + TCP + TLS are already done
    before the student's first question. Best-effort: never raises.
    """
    try:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        _get_session().get(base_url.rstrip("/") + "/", headers=headers, timeout=timeout)
    except Exception:
        pass


def _headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _messages(system_prompt: str, user_text: str) -> list:
    msgs = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": user_text})
    return msgs


# ============================================================
# Chat completion — classic one-shot (fallback path)
# ============================================================

def chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_text: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = 30,
    keep_alive: bool = True,
) -> Tuple[str, dict]:
    """
    Send one chat turn and wait for the WHOLE answer.

    Returns (answer_text, stats_dict).
    Raises Exception on HTTP errors with a short, kid-safe message.
    """

    if not api_key:
        raise Exception("AI key missing")

    url = base_url.rstrip("/") + CHAT_PATH

    payload = {
        "model": model,
        "messages": _messages(system_prompt, user_text),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    t0 = time.time()
    resp = _post(url, _headers(api_key), payload, timeout, keep_alive=keep_alive)
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

    answer = clean_for_speech(answer)

    usage = data.get("usage", {})
    stats = {
        "time": elapsed,
        "model": data.get("model", model),
        "total_tokens": usage.get("total_tokens", 0),
    }

    return answer, stats


# ============================================================
# Chat completion — streaming (fast path)
# ============================================================

def chat_completion_stream(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_text: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: int = 30,
    keep_alive: bool = True,
) -> Generator[str, None, None]:
    """
    Same chat turn, but yields text PIECES as the model writes them
    (Server-Sent Events). Feed this into iter_sentences().

    Raises Exception on HTTP errors (caller can fall back to
    chat_completion).
    """

    if not api_key:
        raise Exception("AI key missing")

    url = base_url.rstrip("/") + CHAT_PATH

    payload = {
        "model": model,
        "messages": _messages(system_prompt, user_text),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    resp = _post(
        url, _headers(api_key), payload, timeout, stream=True, keep_alive=keep_alive
    )

    if resp.status_code >= 400:
        # Read the error body, then bail out so the caller can fall back.
        try:
            detail = resp.text[:200]
        except Exception:
            detail = f"HTTP {resp.status_code}"
        raise Exception(f"AI stream HTTP {resp.status_code}: {detail}")

    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue
        line = raw.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except Exception:
            continue
        try:
            delta = chunk["choices"][0].get("delta", {}) or {}
            piece = delta.get("content") or ""
        except Exception:
            piece = ""
        if piece:
            yield piece


# ============================================================
# Sentence chopping
# ============================================================

# A sentence ends at . ! or ? followed by whitespace (or end of text).
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def iter_sentences(
    token_stream: Iterable[str],
    max_chars: int = 220,
) -> Generator[str, None, None]:
    """
    Turn a stream of text pieces into complete sentences.

    Yields a sentence as soon as it is finished, so TTS can start on
    sentence 1 while the model is still writing sentence 2.

    max_chars is a safety net: if the model writes a very long run-on
    without punctuation, we split at the last comma or space instead of
    waiting forever.
    """

    buf = ""

    for piece in token_stream:
        if not piece:
            continue
        buf += piece

        while True:
            m = _SENTENCE_END.search(buf)
            if m:
                sentence = buf[: m.end()].strip()
                buf = buf[m.end():]
                if sentence:
                    yield sentence
                continue

            if len(buf) > max_chars:
                # Split at the last comma or space BEFORE the cap, so a
                # run-on never produces an oversized TTS chunk.
                window = buf[:max_chars]
                cut = max(window.rfind(", "), window.rfind(" "))
                if cut > 40:
                    sentence = buf[:cut].strip()
                    buf = buf[cut:]
                    if sentence:
                        yield sentence
                    continue

            break

    tail = buf.strip()
    if tail:
        yield tail


# ============================================================
# Text-to-speech (TTS)
# ============================================================
#
# Poe's TTS bots are exposed through the same OpenAI-compatible
# /chat/completions endpoint. We pass the bot name as `model` and the
# text as the only user message. The response contains an audio URL,
# which we then download.

def tts_speak(
    base_url: str,
    api_key: str,
    tts_model: str,
    text: str,
    voice: str = "tessa",
    timeout: int = 60,
    keep_alive: bool = True,
) -> bytes:
    """
    Generate spoken audio for `text`. Returns raw mp3 bytes.

    Raises Exception on failure.
    """

    if not api_key:
        raise Exception("AI key missing")
    if not text:
        raise Exception("nothing to speak")

    url = base_url.rstrip("/") + TTS_PATH

    payload = {
        "model": tts_model,
        "messages": [
            {"role": "user", "content": text},
        ],
        "parameters": {"voice": voice},
    }

    resp = _post(url, _headers(api_key), payload, timeout, keep_alive=keep_alive)

    if resp.status_code >= 400:
        raise Exception(f"TTS HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
    except Exception:
        raise Exception(f"TTS bad JSON: {resp.text[:200]}")

    audio_url = _find_audio_url(data)
    if not audio_url:
        raise Exception(f"TTS returned no audio URL: {str(data)[:200]}")

    audio = _get(audio_url, timeout, keep_alive=keep_alive)
    if audio.status_code >= 400:
        raise Exception(f"TTS audio download HTTP {audio.status_code}")

    return audio.content


def _find_audio_url(data) -> str:
    """Extract audio URL from a Poe/OpenAI-compatible response."""

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


# ============================================================
# Text cleaning (strip markdown so TTS sounds natural)
# ============================================================

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


def clean_for_speech(text: str) -> str:
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
