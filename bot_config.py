"""
================================================================================
 bot_config.py — THE ONE FILE YOU EDIT
================================================================================

Everything you might want to change about how the bot looks, sounds,
listens, and thinks lives right here — in plain English.

You should NEVER need to open any other file to customize the bot.

Rules for editing:
  1. Only change the value AFTER the "=" sign.
  2. True / False must keep the capital first letter.
  3. Text goes inside "quotes". Numbers have no quotes.
  4. If the bot breaks after an edit, change your last edit back.

Sections:
  1. Personality        — who the bot is
  2. AI models          — which cloud brains it uses
  3. Reply style        — how long / creative answers are
  4. Speed              — latency switches (the fast pipeline)
  5. Listening          — how it hears the student
  6. Volume             — speaker and mic levels
  7. Screen             — face timing and status messages
  8. Safety             — kid-safety filter
  9. Debug              — extra logging
 10. Advanced           — do not touch unless you know why
================================================================================
"""

from __future__ import annotations


# ==============================================================================
# 1. PERSONALITY — who the bot is
# ==============================================================================

# The bot's name (used in its system prompt).
BOT_NAME = "Spring Demo"

# Age range of the students it talks to.
STUDENT_AGE_RANGE = "10-12"

# City / region — answers are localized for these students.
BOT_CITY = "Hong Kong"

# Extra instructions added to the bot's personality.
# Example: "You love dinosaurs and use fun space examples."
# Leave empty ("") for none. Note: event.json "system_addon" is appended
# after this, so event organizers can add their own flavor per event.
EXTRA_INSTRUCTIONS = ""


# ==============================================================================
# 2. AI MODELS — which cloud brains it uses
# ==============================================================================

# The API endpoint. Poe gives one key that unlocks many models.
AI_BASE_URL = "https://api.poe.com/v1"

# The thinking brain (text in, text out).
LLM_MODEL = "Claude-3.5-Haiku"

# The speaking voice engine (text in, audio out).
TTS_MODEL = "Sonic-3.0"

# Which voice the TTS engine uses.
TTS_VOICE = "tessa"

# How long (seconds) to wait for the AI before giving up.
LLM_TIMEOUT = 30
TTS_TIMEOUT = 60


# ==============================================================================
# 3. REPLY STYLE — how the bot answers
# ==============================================================================

# Maximum sentences per spoken reply. Short = snappy + kid-friendly.
MAX_RESPONSE_SENTENCES = 2

# Hard cap on reply length (AI tokens). Lower = faster + shorter.
MAX_TOKENS = 90

# Creativity dial: 0.0 = very predictable, 1.0 = very playful. 0.7 is a
# good balance for a study buddy.
TEMPERATURE = 0.7


# ==============================================================================
# 4. SPEED — the fast pipeline switches (all True = fastest)
# ==============================================================================

# Stream the AI's answer word-by-word instead of waiting for the whole
# reply. Recommended: True.
STREAM_LLM = True

# Start speaking sentence 1 while sentences 2+ are still being written.
# Works together with STREAM_LLM. Recommended: True.
SENTENCE_TTS = True

# Reuse one internet connection for all AI calls instead of dialing a
# fresh one 3 times per turn. Recommended: True.
KEEP_ALIVE = True

# Open the connection once at startup so the first question is fast too.
WARMUP_ON_START = True

# Pre-make the audio for fixed phrases (like the calm-down message) at
# startup, so they play instantly with zero waiting. Recommended: True.
PRECACHE_PHRASES = True

# If the answer is taking a while, play a short "Hmm, let me think!"
# filler so the student knows the bot heard them. Off by default.
THINKING_FILLER = False
THINKING_FILLER_TEXT = "Hmm, let me think about that!"

# Seconds of waiting before the filler plays (only if enabled above).
THINKING_FILLER_DELAY = 2.0


# ==============================================================================
# 5. LISTENING — how it hears the student
# ==============================================================================

# Seconds of quiet that mean "the student finished talking".
# Lower = faster reply, but too low can cut off slow talkers.
# 0.8–1.0 is a good range for kids. (Was 1.5 in the old version.)
SILENCE_DURATION = 0.9

# Microphone loudness needed to count as speech. Lower = hears quieter
# voices, but may react to background noise. 500 is a good Pi default.
SILENCE_THRESHOLD = 500

# Hard cap on one question (seconds).
MAX_RECORD_SECONDS = 12

# Let Vosk's built-in "end of sentence" detection stop recording early
# (smarter than pure silence timing). Recommended: True.
USE_VOSK_ENDPOINTING = True

# Folder name of the Vosk speech model (offline listening brain).
VOSK_MODEL_FOLDER = "vosk-model-small-en-us-0.15"

# Vosk always works at this sample rate. Do not change.
VOSK_SAMPLE_RATE = 16000


# ==============================================================================
# 6. VOLUME
# ==============================================================================

SPEAKER_VOLUME_PERCENT = 80
MIC_VOLUME_PERCENT = 100

# Automatic gain control: boosts quiet voices. Recommended: True.
ENABLE_MIC_AGC = True


# ==============================================================================
# 7. SCREEN — face timing and status messages
# ==============================================================================

# Seconds with no taps before the face goes to sleep.
IDLE_TO_SLEEP_SECONDS = 60

# Status messages shown on screen. event.json can override these per event.
STATUS_TEXT = {
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


# ==============================================================================
# 8. SAFETY — kid-safety filter
# ==============================================================================

# If the student says one of these, the bot gently redirects instead of
# answering. Matching is case-insensitive. Add or remove freely.
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

# How many blocked attempts in a session trigger the calm-down message.
MAX_INAPPROPRIATE_ATTEMPTS = 2

# What the bot is secretly asked to do after a blocked question.
REDIRECT_PROMPT = (
    "The student asked something off-topic or unsafe. Without repeating their "
    "question, gently redirect them in 2 short spoken sentences toward a "
    "fun science, math, art, technology, or hands-on observation question "
    "they could explore right now. End with one inviting question."
)

# What the bot says out loud after too many blocked attempts.
CALMDOWN_TEXT = (
    "Let's take a breath and try a different question. Tap me when you're "
    "ready to explore something cool together."
)


# ==============================================================================
# 9. DEBUG
# ==============================================================================

# True = print per-stage timings (listen / think / speak) to the console.
# Useful for measuring speed on the Pi. Off for the event.
DEBUG_MODE = False


# ==============================================================================
# 10. ADVANCED — do not touch unless you know why
# ==============================================================================

# USB hardware IDs (vendor:product) so the right mic/speaker is found even
# if card numbers change. Check with: cat /proc/asound/card*/usbid
SPEAKER_USB_ID = "4c4a:4155"   # Jieli Technology UACDemoV1.0
MIC_USB_ID = "1620:0b21"       # C-Media USB PnP Sound Device

# Text length guards (characters) for the AI input/output.
MAX_USER_TEXT_LENGTH = 500
MAX_BOT_TEXT_LENGTH = 1200
