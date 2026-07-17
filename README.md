# Spring Demo — Speech-to-Speech Bot (Orange Pi)

> **Handover doc + progress tracker.** If you're picking this project up fresh,
> read this file top to bottom — it's the whole story.

---

## 1. What this is

A tap-to-talk robot buddy for students aged 10–12, built for a live event kiosk.
It runs on an **Orange Pi** with a **3.5" screen** showing an animated face.

The kid taps the face, asks a question out loud, and the bot answers out loud:

```
tap face → 🎤 listen (Vosk, offline) → 🧠 think (Claude via Poe, cloud)
         → 🔊 speak (Sonic TTS via Poe, cloud) → mpg123 → speaker
```

**Face states:** `idle` → `listening` → `thinking` → `talking` → back to `idle`
(`sleeping` after 60 s of no taps).

---

## 2. ⭐ Customizing the bot: edit `bot_config.py` ONLY

**`bot_config.py` is the single user file.** Everything you might want to
change — personality, AI models, voice, speed switches, listening sensitivity,
volumes, screen messages, safety filter — lives there in plain English with
comments. You should never need to open any other file to customize the bot.

Quick tour of its sections:

| Section | Examples of what you can change |
|---|---|
| Personality | `BOT_NAME`, `STUDENT_AGE_RANGE`, `BOT_CITY`, `EXTRA_INSTRUCTIONS` |
| AI models | `LLM_MODEL`, `TTS_MODEL`, `TTS_VOICE`, `AI_BASE_URL` |
| Reply style | `MAX_RESPONSE_SENTENCES`, `MAX_TOKENS`, `TEMPERATURE` |
| Speed | `STREAM_LLM`, `SENTENCE_TTS`, `KEEP_ALIVE`, `PRECACHE_PHRASES`, `THINKING_FILLER` |
| Listening | `SILENCE_DURATION`, `SILENCE_THRESHOLD`, `USE_VOSK_ENDPOINTING` |
| Volume | speaker/mic percent, mic AGC |
| Screen | `IDLE_TO_SLEEP_SECONDS`, all status messages |
| Safety | `BLOCKED_KEYWORDS`, redirect + calm-down texts |
| Debug | `DEBUG_MODE` (prints per-stage timings) |

> `event.json` still works on top: its `status_text` and `system_addon`
> override per event, so organizers can customize without touching code.

---

## 3. File map (after the 2026-07-17 cleanup)

| File | Role | Edit? |
|---|---|---|
| **`bot_config.py`** | ⭐ THE user settings file | **Yes — edit this one** |
| `main.py` | App entry + turn pipeline (listen → think → speak) | No |
| `ai_client.py` | Poe API: streaming chat, sentence chopper, TTS, keep-alive session | No |
| `speech_utils.py` | Mic recording + Vosk STT (with endpointing) | No |
| `settings.py` | Thin shim: builds the system prompt + safety filter from bot_config | No |
| `audio_config.py` | Thin shim: hardware plumbing (ALSA, USB IDs, Vosk paths) | No |
| `face_widget.py` | The animated face | No |
| `audio_utils.py` | ALSA/USB audio setup helpers | No |
| `config.py`, `event_runtime.py`, `supabase_helper.py`, `device_utils.py` | Supabase key-fetch plumbing (shared Big Bang pattern) | No |
| `event.json` | Per-event status text + extra persona | Per event |
| `Spring6_working/` | Frozen backup of the pre-cleanup version | Archive |

**Security rule:** the Poe API key comes from Supabase RPC `get_event_api_key`
at runtime and lives in memory only. Never hardcode or commit keys.

---

## 4. How it works now (the fast pipeline)

One turn, with all speed switches on (the default):

```
tap → listen (Vosk endpointing stops ~0.9 s after speech ends)
    → Claude STREAMS the answer word-by-word
    → sentence 1 goes to TTS the moment it's finished
    → sentence 1 plays while sentences 2+ are still generating
    → face: listening → thinking → talking (at first audio) → idle
```

- **Keep-alive session:** one warm HTTP connection for all Poe calls
  (no more 3 fresh TLS handshakes per turn), pre-warmed at startup.
- **Pre-cached phrases:** the calm-down message's audio is generated once
  at startup, so guardrail responses play instantly.
- **Fallback:** if streaming fails, the turn silently uses the classic
  whole-answer path. If one sentence's TTS fails, it's skipped.
- Set `DEBUG_MODE = True` in `bot_config.py` to print per-stage timings
  (listen / llm_first_token / first_audio / total) to the console.

---

## 5. How to run (on the Pi)

```bash
./run.sh
```

Needs: Vosk model folder (`vosk-model-small-en-us-0.15`), `mpg123`,
`/etc/bigbang.env` (or equivalent) with Supabase URL + anon key + event code.

---

## 6. Kid safety

`bot_config.py` → `BLOCKED_KEYWORDS`: trips → soft redirect prompt;
`MAX_INAPPROPRIATE_ATTEMPTS` trips → pre-cached calm-down message plays
instantly and the counter resets. Keep this working through all changes.

---

## 7. Progress tracker

### ✅ Done
- [x] Working v2 pipeline: tap → listen → think → speak, face in sync
- [x] Latency diagnosis (2026-07-17): ~6–10 s dead air, fully sequential stages
- [x] Research check (2026-07-17): streaming pipeline confirmed as industry
      best practice (ElevenLabs/AssemblyAI/OpenAI guidance)
- [x] **Cleanup + single user file** (2026-07-17): `bot_config.py` created;
      `settings.py`/`audio_config.py` reduced to thin shims; dead code removed
      (hidden TALK button, hidden answer ticker, unused imports); duplicated
      text-cleaning merged; confusing `config` alias renamed
- [x] **Keep-alive session + startup warm-up** (`ai_client.py`)
- [x] **Streaming LLM → sentence-chunked TTS pipeline** (`ai_client.py`, `main.py`)
- [x] **Pre-cached fixed phrases** (`main.py`)
- [x] **Vosk endpointing + `SILENCE_DURATION` 1.5 → 0.9 s**
- [x] **Reply caps**: 150 → 90 tokens, 3 → 2 sentences
- [x] Unit-tested sentence splitter + config wiring on PC (all pass)

### 🔜 Next
- [ ] Test on the Orange Pi with real hardware; set `DEBUG_MODE = True`
      and record real timings here
- [ ] Decide on `Spring6_working/` (keep as frozen backup or archive it)
- [ ] Create GitHub repo and push (see session log)

### 💡 Later / ideas
- [ ] Optional `THINKING_FILLER` ("Hmm, let me think!") — code is built,
      just flip the switch in `bot_config.py`
- [ ] Single realtime speech-to-speech model (OpenAI Realtime / Gemini Live,
      ~0.5–1 s). Trade-offs: higher cost, needs direct API key (Poe has no
      realtime audio), loses offline STT, guardrail must move to transcripts

---

## 8. Session log

| Date | What happened |
|---|---|
| 2026-07-17 | Project reviewed. Latency problem diagnosed (~6–10 s dead air). 4-step streaming plan proposed. Working rules agreed: plan → confirm → build; GitHub repo + regular push/pull; this README as handover. |
| 2026-07-17 | **Build day 1 (approved):** full cleanup + `bot_config.py` single user file; keep-alive + warm-up; streaming LLM → sentence-TTS pipeline; phrase pre-caching; Vosk endpointing; reply caps. Found + fixed a sentence-splitter edge bug via unit tests. All files compile; logic tests pass on PC. **Next: test on the Pi, then set up GitHub repo.** |

_(Add a row every work session — date, what changed, what's next.)_
