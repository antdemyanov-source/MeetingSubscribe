# MeetingScribe — Design Spec

## Overview

Desktop Windows application that records any audio stream (system sound + microphone), transcribes recordings locally using Whisper, and generates structured meeting summaries via Claude API.

**Target user:** Professional who records work meetings, English lessons, and therapy sessions. Needs concise summaries with key insights, action items, and follow-ups.

## Architecture

Python application running in the Windows system tray. Four core modules:

### 1. Audio Capture

- **System audio:** WASAPI Loopback via `pyaudiowpatch` — captures everything going to speakers/headphones
- **Microphone:** `sounddevice` — captures user's voice
- **Mixing:** Both streams mixed into a single WAV file using `numpy`
- **Format:** WAV (uncompressed) during recording, converted to OGG/Opus after transcription for long-term storage

### 2. Transcriber

- **Engine:** `faster-whisper` (CTranslate2-optimized Whisper implementation)
- **Model:** `turbo` (large-v3-turbo) — near large-v3 quality, 3-4x faster
- **Runtime:** CPU mode (~6 GB RAM)
- **Language:** Set by user at recording start (Russian default, English, Auto). Primary language is passed as hint; model can still recognize segments in other languages (handles code-switching in English lessons)
- **Output:** Timestamped transcript in Markdown format

### 3. Summarizer

- **Engine:** Claude API (Anthropic SDK)
- **Input:** Full transcript text
- **Prompt:** Adapted per meeting type (see Prompt Templates below)
- **Output:** Structured Markdown summary

### 4. UI (System Tray)

- **Tray icon:** `pystray` + `Pillow` — persistent icon in system tray
- **Popup window:** `tkinter` — appears on tray icon click
- **Controls:**
  - Language dropdown: Русский (default) / English / Авто
  - Meeting type dropdown: Рабочая встреча / Урок английского / Сессия с психологом
  - Start/Stop button
  - Audio level indicator (visual bar showing capture is active)
  - Status text: "Записываю... 00:12:34" / "Транскрибирую..." / "Генерирую саммари..." / "Готово"

## Data Flow

```
User clicks Start
  → WASAPI Loopback capture begins
  → Microphone capture begins
  → Both streams mixed → WAV file
  → UI shows audio level + elapsed time

User clicks Stop
  → Recording saved as WAV
  → faster-whisper transcribes (CPU, turbo model) → transcript.md
  → Claude API generates summary (type-adapted prompt) → summary.md
  → meta.json written (duration, language, type, date)
  → WAV converted to OGG/Opus, WAV deleted
  → System notification: "Готово"
```

## File Storage

```
C:\AI\MeetingScribe\
  recordings\
    2026\
      04\
        2026-04-22_14-30_work_meeting\
          audio.ogg          # compressed audio for long-term storage
          transcript.md      # full timestamped transcript
          summary.md         # structured summary with insights
          meta.json          # metadata: duration, language, type, date
```

- Each recording gets its own folder named `YYYY-MM-DD_HH-MM_<type>`
- Organized by year/month for navigation
- WAV is temporary — deleted after OGG conversion

## Summary Template (summary.md)

```markdown
# Встреча: [auto-detected topic]
**Дата:** 2026-04-22 14:30
**Длительность:** 45 мин
**Язык:** Русский
**Тип:** Рабочая встреча

## Краткое содержание
2-3 sentences about the meeting.

## Ключевые инсайты
- Insight 1
- Insight 2

## Решения и договорённости
- Decisions and who is responsible

## Задачи (Action Items)
- [ ] Task — owner — deadline

## Важные цитаты
> Verbatim quotes worth remembering
```

## Prompt Templates by Meeting Type

### Work Meeting (Рабочая встреча)
Focus: decisions, action items, owners, deadlines, blockers.

### English Lesson (Урок английского)
Focus: new vocabulary, grammar mistakes and corrections, progress notes, teacher recommendations, homework.

### Therapy Session (Сессия с психологом)
Focus: key personal insights, therapist recommendations, topics for further exploration, emotional patterns discussed.

## Technology Stack

| Component | Library | Purpose |
|-----------|---------|---------|
| System tray | pystray + Pillow | Tray icon and menu |
| Popup UI | tkinter | Recording controls and status |
| System audio | pyaudiowpatch | WASAPI Loopback capture |
| Microphone | sounddevice | Mic capture |
| Audio mixing | numpy | Mix two streams |
| Audio I/O | soundfile | WAV read/write |
| Audio conversion | ffmpeg (subprocess) | WAV → OGG/Opus |
| Transcription | faster-whisper | Local Whisper turbo model |
| Summarization | anthropic SDK | Claude API |
| Config | json | Settings storage |

## Configuration

Settings stored in `C:\AI\MeetingScribe\config.json`:

```json
{
  "recordings_dir": "C:\\AI\\MeetingScribe\\recordings",
  "default_language": "ru",
  "default_meeting_type": "work",
  "whisper_model": "turbo",
  "whisper_device": "cpu",
  "anthropic_api_key": "sk-...",
  "audio_sample_rate": 44100,
  "keep_wav": false
}
```

## Constraints

- **RAM:** ~6 GB for Whisper turbo model, laptop has 16 GB total — sufficient
- **GPU:** 2 GB VRAM, insufficient for Whisper — CPU mode only
- **Disk:** WAV ~100 MB/hour (temporary), OGG ~10 MB/hour (permanent)
- **Processing time:** ~8-12 min per hour of audio for transcription (CPU)
- **API cost:** ~$0.01-0.05 per meeting summary via Claude API
