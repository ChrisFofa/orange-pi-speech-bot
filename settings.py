"""
settings.py
================

INTERNAL PLUMBING — do not edit settings here.

All user-editable values (persona, reply style, safety filter, status
text, timings) live in `bot_config.py` — the one file you edit.

This file only:
  1. Re-exports those values under the names main.py expects, and
  2. Holds the two small FUNCTIONS that use them:
     build_system_prompt() and is_blocked().
"""

from __future__ import annotations

import bot_config as _bc


# ============================================================
# Re-exported values (edit them in bot_config.py, not here)
# ============================================================

PERSONA_NAME = _bc.BOT_NAME
STUDENT_AGE_RANGE = _bc.STUDENT_AGE_RANGE

MAX_TOKENS = _bc.MAX_TOKENS
MAX_RESPONSE_SENTENCES = _bc.MAX_RESPONSE_SENTENCES
DEFAULT_TEMPERATURE = _bc.TEMPERATURE

MAX_INAPPROPRIATE_ATTEMPTS = _bc.MAX_INAPPROPRIATE_ATTEMPTS
BLOCKED_KEYWORDS = _bc.BLOCKED_KEYWORDS
REDIRECT_PROMPT = _bc.REDIRECT_PROMPT
CALMDOWN_TEXT = _bc.CALMDOWN_TEXT

DEFAULT_STATUS = _bc.STATUS_TEXT

IDLE_TO_SLEEP_SECONDS = _bc.IDLE_TO_SLEEP_SECONDS


# ============================================================
# System prompt (built at startup so bot_config edits apply)
# ============================================================

def build_system_prompt(system_addon: str = "") -> str:
    """
    Combine the base persona from bot_config.py with:
      - bot_config.EXTRA_INSTRUCTIONS (owner-level flavor), and
      - the `system_addon` field from event.json (event-level flavor).
    """
    base = (
        f"You are {_bc.BOT_NAME}, a friendly speech-to-speech study buddy for "
        f"{_bc.STUDENT_AGE_RANGE} year old students in {_bc.BOT_CITY}. "
        "Your reply will be spoken out loud, so write the way you would say it. "
        f"Keep every reply to {_bc.MAX_RESPONSE_SENTENCES} short sentences or fewer. "
        "Never use markdown formatting, asterisks, bullet points, headings, or code blocks. "
        "Use simple words a 10 year old can follow. "
        "Use metric units only. "
        "Never ask for personal details (name, school, address, phone, email, password). "
        "If the student asks for personal data or anything unsafe, gently redirect them "
        "back to a science, math, or hands-on curiosity question."
    )

    parts = [base]

    extra = (_bc.EXTRA_INSTRUCTIONS or "").strip()
    if extra:
        parts.append(extra)

    addon = (system_addon or "").strip()
    if addon:
        parts.append(addon)

    return "\n\n".join(parts)


# ============================================================
# Content filter — soft redirect, not lockout
# ============================================================

def is_blocked(user_text: str) -> bool:
    """
    Return True if the utterance contains a blocked keyword/phrase.
    Matching is case-insensitive substring; cheap and good enough for
    a kiosk.
    """
    if not user_text:
        return False
    low = user_text.lower()
    for kw in _bc.BLOCKED_KEYWORDS:
        if kw in low:
            return True
    return False
