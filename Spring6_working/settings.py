"""
settings.py
================

Spring Demo — child safety + conversation policy constants.

Loaded once at startup by main.py. The system prompt is built by
combining SYSTEM_BASE with the `system_addon` field from event.json.

Mascots have been intentionally removed from this version.
"""

from __future__ import annotations

# ============================================================
# Audience / persona
# ============================================================

STUDENT_AGE_RANGE = "10-12"

PERSONA_NAME = "Spring Demo"

# Hard caps. The system prompt also asks the model to keep things short,
# but max_tokens at the API level is the real ceiling.
MAX_TOKENS = 150
MAX_RESPONSE_SENTENCES = 3
DEFAULT_TEMPERATURE = 0.7


# ============================================================
# System prompt (built once at startup)
# ============================================================

SYSTEM_BASE = (
    "You are Spring Demo, a friendly speech-to-speech study buddy for "
    f"{STUDENT_AGE_RANGE} year old students in Hong Kong. "
    "Your reply will be spoken out loud, so write the way you would say it. "
    f"Keep every reply to {MAX_RESPONSE_SENTENCES} short sentences or fewer. "
    "Never use markdown formatting, asterisks, bullet points, headings, or code blocks. "
    "Use simple words a 10 year old can follow. "
    "Use metric units only. "
    "Never ask for personal details (name, school, address, phone, email, password). "
    "If the student asks for personal data or anything unsafe, gently redirect them "
    "back to a science, math, or hands-on curiosity question."
)


def build_system_prompt(system_addon: str = "") -> str:
    """
    Combine SYSTEM_BASE with the system_addon from event.json.
    """
    addon = (system_addon or "").strip()
    if addon:
        return SYSTEM_BASE + "\n\n" + addon
    return SYSTEM_BASE


# ============================================================
# Content filter — soft redirect, not lockout
# ============================================================
#
# When a user utterance trips one of these keywords we substitute a
# safe redirect prompt for the model instead of refusing to respond.
# After MAX_INAPPROPRIATE_ATTEMPTS in a single session the screen
# shows a calming reset and the bot returns to idle.

MAX_INAPPROPRIATE_ATTEMPTS = 2

BLOCKED_KEYWORDS = [
    # Personal data probes (kid -> bot)
    "what is your password",
    "tell me your password",
    "give me your password",
    "your phone number",
    "your address",
    "your home",
    "your real name",
    # Adult / unsafe content
    "kill", "murder", "suicide",
    "weapon", "gun", "bomb", "knife",
    "drug", "drugs", "cocaine", "heroin", "weed",
    "alcohol", "vodka", "beer", "whiskey",
    "sex", "porn", "naked", "nude",
    "blood", "gore",
    "hate", "racist",
    # Cheating-on-test asks
    "give me the answers to my test",
    "do my homework for me",
]

REDIRECT_PROMPT = (
    "The student asked something off-topic or unsafe. Without repeating their "
    "question, gently redirect them in 2 short spoken sentences toward a "
    "fun science, math, art, technology, or hands-on observation question "
    "they could explore right now. End with one inviting question."
)

CALMDOWN_TEXT = (
    "Let's take a breath and try a different question. Tap me when you're "
    "ready to explore something cool together."
)


def is_blocked(user_text: str) -> bool:
    """
    Return True if the utterance contains a blocked keyword/phrase.
    Matching is case-insensitive substring; cheap and good enough for
    a kiosk.
    """
    if not user_text:
        return False
    low = user_text.lower()
    for kw in BLOCKED_KEYWORDS:
        if kw in low:
            return True
    return False


# ============================================================
# UI status strings (overridable from event.json status_text)
# ============================================================

DEFAULT_STATUS = {
    "starting": "Starting Spring Demo...",
    "setup_audio": "Getting my ears and voice ready...",
    "loading_speech": "Loading my listening brain...",
    "ready": "Tap my face to ask a question.",
    "listening": "Listening...",
    "thinking": "Thinking...",
    "talking": "Sharing an answer...",
    "after_answer": "Tap my face to ask another.",
    "sleeping": "Tap my face to wake me up.",
    "no_speech": "I didn't catch that. Tap my face and try again.",
    "api_missing": "AI key not ready. Ask the teacher to check setup.",
    "setup_error": "Setup error. Ask the teacher to check setup.",
    "offline": "I need Wi-Fi for my cloud brain. Please check the internet.",
    "redirect": "Let's try something different.",
    "generic_error": "Something went wrong. Tap my face to try again.",
}


# ============================================================
# Idle behavior
# ============================================================

IDLE_TO_SLEEP_SECONDS = 60
