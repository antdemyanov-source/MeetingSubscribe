# MeetingScribe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows system-tray app that records system audio + microphone, transcribes via local Whisper, and generates meeting summaries via Claude API.

**Architecture:** Python app with 4 modules: audio capture (pyaudiowpatch WASAPI loopback + mic), transcription (faster-whisper turbo on CPU), summarization (Claude API with type-specific prompts), and UI (pystray tray icon + tkinter popup). Processing pipeline runs automatically after recording stops.

**Tech Stack:** Python 3.11+, pyaudiowpatch, numpy, soundfile, faster-whisper, anthropic SDK, pystray, Pillow, tkinter, ffmpeg (system)

---

## File Structure

```
C:\AI\MeetingScribe\
  meetingscribe\
    __init__.py              # package init, version
    __main__.py              # entry point: python -m meetingscribe
    config.py                # load/save config.json with defaults
    storage.py               # recording folder creation, path management
    audio_capture.py         # WASAPI loopback + mic capture, mixing, level meter
    transcriber.py           # faster-whisper wrapper, markdown output
    summarizer.py            # Claude API wrapper, 3 prompt templates
    pipeline.py              # orchestration: transcribe → summarize → convert
    ui\
      __init__.py
      app.py                 # main app class, wires tray + popup + pipeline
      tray.py                # system tray icon with pystray
      popup.py               # tkinter popup window with controls
  tests\
    __init__.py
    test_config.py
    test_storage.py
    test_summarizer.py
    test_pipeline.py
  requirements.txt
  config.json
  run.pyw                    # double-click launcher (no console window)
```

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `meetingscribe/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create project directories**

```bash
cd /c/AI/MeetingScribe
mkdir -p meetingscribe/ui tests
```

- [ ] **Step 2: Create requirements.txt**

Create `requirements.txt`:

```
pyaudiowpatch>=0.2.12
numpy>=1.24.0
soundfile>=0.12.1
faster-whisper>=1.0.0
anthropic>=0.39.0
pystray>=0.19.5
Pillow>=10.0.0
pytest>=7.0.0
```

- [ ] **Step 3: Create virtual environment and install dependencies**

```bash
cd /c/AI/MeetingScribe
python -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
```

Expected: all packages install successfully. `pyaudiowpatch` may need Visual C++ Build Tools — if it fails, install from https://visualstudio.microsoft.com/visual-cpp-build-tools/

- [ ] **Step 4: Verify ffmpeg is available**

```bash
ffmpeg -version
```

Expected: version info printed. If not installed, download from https://ffmpeg.org/download.html and add to PATH.

- [ ] **Step 5: Create package init files**

Create `meetingscribe/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `meetingscribe/ui/__init__.py`:

```python
```

Create `tests/__init__.py`:

```python
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt meetingscribe/__init__.py meetingscribe/ui/__init__.py tests/__init__.py
git commit -m "feat: project setup with dependencies"
```

---

## Task 2: Config Module

**Files:**
- Create: `meetingscribe/config.py`
- Create: `tests/test_config.py`
- Create: `config.json`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:

```python
import json
from pathlib import Path
from meetingscribe.config import Config


def test_default_config_values():
    config = Config()
    assert config.default_language == "ru"
    assert config.default_meeting_type == "work"
    assert config.whisper_model == "turbo"
    assert config.whisper_device == "cpu"
    assert config.anthropic_api_key == ""
    assert config.anthropic_model == "claude-sonnet-4-6"
    assert config.audio_sample_rate == 44100
    assert config.keep_wav is False


def test_load_from_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "default_language": "en",
        "anthropic_api_key": "sk-test-123",
    }), encoding="utf-8")

    config = Config.load(config_path)
    assert config.default_language == "en"
    assert config.anthropic_api_key == "sk-test-123"
    assert config.whisper_model == "turbo"  # default preserved


def test_load_missing_file_returns_defaults(tmp_path):
    config = Config.load(tmp_path / "nonexistent.json")
    assert config.default_language == "ru"


def test_save_and_reload(tmp_path):
    config_path = tmp_path / "config.json"
    config = Config(anthropic_api_key="sk-saved")
    config.save(config_path)

    loaded = Config.load(config_path)
    assert loaded.anthropic_api_key == "sk-saved"


def test_load_ignores_unknown_keys(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "unknown_field": "value",
        "default_language": "en",
    }), encoding="utf-8")

    config = Config.load(config_path)
    assert config.default_language == "en"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /c/AI/MeetingScribe
source venv/Scripts/activate
python -m pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'meetingscribe.config'`

- [ ] **Step 3: Implement config module**

Create `meetingscribe/config.py`:

```python
import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


@dataclass
class Config:
    recordings_dir: str = ""
    default_language: str = "ru"
    default_meeting_type: str = "work"
    whisper_model: str = "turbo"
    whisper_device: str = "cpu"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    audio_sample_rate: int = 44100
    keep_wav: bool = False

    def __post_init__(self):
        if not self.recordings_dir:
            self.recordings_dir = str(Path(__file__).parent.parent / "recordings")

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> "Config":
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            valid_keys = {field.name for field in fields(cls)}
            filtered = {k: v for k, v in data.items() if k in valid_keys}
            return cls(**filtered)
        return cls()

    def save(self, path: Path = DEFAULT_CONFIG_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_config.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Create default config.json**

Create `config.json`:

```json
{
  "recordings_dir": "C:\\AI\\MeetingScribe\\recordings",
  "default_language": "ru",
  "default_meeting_type": "work",
  "whisper_model": "turbo",
  "whisper_device": "cpu",
  "anthropic_api_key": "",
  "anthropic_model": "claude-sonnet-4-6",
  "audio_sample_rate": 44100,
  "keep_wav": false
}
```

- [ ] **Step 6: Commit**

```bash
git add meetingscribe/config.py tests/test_config.py config.json
git commit -m "feat: config module with load/save and defaults"
```

---

## Task 3: Storage Module

**Files:**
- Create: `meetingscribe/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_storage.py`:

```python
from datetime import datetime
from meetingscribe.storage import create_recording_paths, MEETING_TYPE_FOLDER


def test_creates_correct_folder_structure(tmp_path):
    dt = datetime(2026, 4, 22, 14, 30)
    paths = create_recording_paths(str(tmp_path), "work", start_time=dt)

    assert paths.folder == tmp_path / "2026" / "04" / "2026-04-22_14-30_work_meeting"
    assert paths.folder.exists()


def test_file_paths_inside_folder(tmp_path):
    dt = datetime(2026, 4, 22, 14, 30)
    paths = create_recording_paths(str(tmp_path), "work", start_time=dt)

    assert paths.wav == paths.folder / "audio.wav"
    assert paths.ogg == paths.folder / "audio.ogg"
    assert paths.transcript == paths.folder / "transcript.md"
    assert paths.summary == paths.folder / "summary.md"
    assert paths.meta == paths.folder / "meta.json"


def test_english_lesson_type(tmp_path):
    dt = datetime(2026, 3, 15, 10, 0)
    paths = create_recording_paths(str(tmp_path), "english", start_time=dt)

    assert paths.folder.name == "2026-03-15_10-00_english_lesson"
    assert paths.folder.parent.name == "03"
    assert paths.folder.parent.parent.name == "2026"


def test_therapy_session_type(tmp_path):
    dt = datetime(2026, 1, 5, 18, 45)
    paths = create_recording_paths(str(tmp_path), "therapy", start_time=dt)

    assert paths.folder.name == "2026-01-05_18-45_therapy_session"


def test_all_meeting_types_mapped():
    assert "work" in MEETING_TYPE_FOLDER
    assert "english" in MEETING_TYPE_FOLDER
    assert "therapy" in MEETING_TYPE_FOLDER


def test_uses_current_time_when_not_specified(tmp_path):
    paths = create_recording_paths(str(tmp_path), "work")
    assert paths.folder.exists()
    assert "work_meeting" in paths.folder.name
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_storage.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement storage module**

Create `meetingscribe/storage.py`:

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MEETING_TYPE_FOLDER = {
    "work": "work_meeting",
    "english": "english_lesson",
    "therapy": "therapy_session",
}


@dataclass
class RecordingPaths:
    folder: Path
    wav: Path
    ogg: Path
    transcript: Path
    summary: Path
    meta: Path


def create_recording_paths(
    base_dir: str, meeting_type: str, start_time: datetime | None = None
) -> RecordingPaths:
    if start_time is None:
        start_time = datetime.now()

    type_folder = MEETING_TYPE_FOLDER.get(meeting_type, meeting_type)
    date_str = start_time.strftime("%Y-%m-%d_%H-%M")

    folder = (
        Path(base_dir)
        / start_time.strftime("%Y")
        / start_time.strftime("%m")
        / f"{date_str}_{type_folder}"
    )
    folder.mkdir(parents=True, exist_ok=True)

    return RecordingPaths(
        folder=folder,
        wav=folder / "audio.wav",
        ogg=folder / "audio.ogg",
        transcript=folder / "transcript.md",
        summary=folder / "summary.md",
        meta=folder / "meta.json",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_storage.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add meetingscribe/storage.py tests/test_storage.py
git commit -m "feat: storage module with folder hierarchy and path management"
```

---

## Task 4: Audio Capture Module

**Files:**
- Create: `meetingscribe/audio_capture.py`

This module depends on system audio hardware and cannot be unit-tested. Includes a manual test at the end.

- [ ] **Step 1: Implement AudioCapture class**

Create `meetingscribe/audio_capture.py`:

```python
import threading
import numpy as np
import pyaudiowpatch as pyaudio
import soundfile as sf
from pathlib import Path


class AudioCapture:
    def __init__(self, sample_rate: int = 44100):
        self.target_sample_rate = sample_rate
        self.is_recording = False
        self.audio_level = 0.0
        self._pa: pyaudio.PyAudio | None = None
        self._loopback_stream = None
        self._mic_stream = None
        self._loopback_frames: list[np.ndarray] = []
        self._mic_frames: list[np.ndarray] = []
        self._loopback_channels = 2
        self._actual_rate = sample_rate
        self._lock = threading.Lock()

    def _loopback_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16)
        with self._lock:
            self._loopback_frames.append(data.copy())
        rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))
        self.audio_level = min(1.0, rms / 3276.8)
        return (in_data, pyaudio.paContinue)

    def _mic_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16)
        with self._lock:
            self._mic_frames.append(data.copy())
        return (in_data, pyaudio.paContinue)

    def _find_loopback_device(self):
        wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = self._pa.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )
        for loopback in self._pa.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                return loopback
        return None

    def start(self):
        self._pa = pyaudio.PyAudio()
        self._loopback_frames = []
        self._mic_frames = []
        self.audio_level = 0.0

        loopback_device = self._find_loopback_device()
        if loopback_device is None:
            self._pa.terminate()
            raise RuntimeError(
                "Не найдено устройство loopback. Проверьте аудиовыход."
            )

        self._loopback_channels = int(loopback_device["maxInputChannels"])
        self._actual_rate = int(loopback_device["defaultSampleRate"])

        self._loopback_stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._loopback_channels,
            rate=self._actual_rate,
            frames_per_buffer=1024,
            input=True,
            input_device_index=loopback_device["index"],
            stream_callback=self._loopback_callback,
        )

        try:
            mic_info = self._pa.get_default_input_device_info()
            self._mic_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self._actual_rate,
                frames_per_buffer=1024,
                input=True,
                input_device_index=mic_info["index"],
                stream_callback=self._mic_callback,
            )
        except (OSError, pyaudio.PyAudioError):
            self._mic_stream = None

        self.is_recording = True

    def stop(self, output_path: Path) -> int:
        self.is_recording = False

        if self._loopback_stream:
            self._loopback_stream.stop_stream()
            self._loopback_stream.close()
            self._loopback_stream = None
        if self._mic_stream:
            self._mic_stream.stop_stream()
            self._mic_stream.close()
            self._mic_stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None

        with self._lock:
            loopback_data = (
                np.concatenate(self._loopback_frames)
                if self._loopback_frames
                else np.array([], dtype=np.int16)
            )
            mic_data = (
                np.concatenate(self._mic_frames)
                if self._mic_frames
                else np.array([], dtype=np.int16)
            )

        channels = self._loopback_channels

        if len(loopback_data) > 0:
            loopback_data = loopback_data.reshape(-1, channels).astype(np.float32)
        else:
            loopback_data = np.zeros((0, channels), dtype=np.float32)

        if len(mic_data) > 0:
            mic_mono = mic_data.reshape(-1, 1).astype(np.float32)
            mic_data = np.repeat(mic_mono, channels, axis=1)
        else:
            mic_data = np.zeros((0, channels), dtype=np.float32)

        max_len = max(len(loopback_data), len(mic_data))
        if max_len == 0:
            sf.write(str(output_path), np.zeros((1, channels), dtype=np.int16), self._actual_rate)
            return 0

        if len(loopback_data) < max_len:
            pad = np.zeros((max_len - len(loopback_data), channels), dtype=np.float32)
            loopback_data = np.concatenate([loopback_data, pad])
        if len(mic_data) < max_len:
            pad = np.zeros((max_len - len(mic_data), channels), dtype=np.float32)
            mic_data = np.concatenate([mic_data, pad])

        mixed = (loopback_data + mic_data) / 2.0
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), mixed, self._actual_rate)

        return int(len(mixed) / self._actual_rate)
```

- [ ] **Step 2: Manual test — verify audio capture works**

Create a temporary test script and run it:

```bash
cd /c/AI/MeetingScribe
source venv/Scripts/activate
python -c "
from meetingscribe.audio_capture import AudioCapture
from pathlib import Path
import time

cap = AudioCapture()
print('Starting capture... play some audio and speak into mic')
cap.start()
for i in range(50):
    time.sleep(0.1)
    print(f'Level: {\"#\" * int(cap.audio_level * 40):<40} {cap.audio_level:.2f}', end='\r')
print()
duration = cap.stop(Path('test_recording.wav'))
print(f'Done. Duration: {duration}s. File: test_recording.wav')
"
```

Expected: `test_recording.wav` created, plays back with both system audio and mic audio. Level indicator shows activity during playback.

- [ ] **Step 3: Clean up test file and commit**

```bash
rm -f test_recording.wav
git add meetingscribe/audio_capture.py
git commit -m "feat: audio capture with WASAPI loopback + microphone mixing"
```

---

## Task 5: Transcriber Module

**Files:**
- Create: `meetingscribe/transcriber.py`

- [ ] **Step 1: Implement transcriber**

Create `meetingscribe/transcriber.py`:

```python
from pathlib import Path
from datetime import datetime


def _format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


LANGUAGE_NAMES = {
    "ru": "Русский",
    "en": "English",
    "auto": "Авто",
}


def transcribe(
    audio_path: Path,
    output_path: Path,
    language: str = "ru",
    model_size: str = "turbo",
    device: str = "cpu",
) -> str:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type="int8")

    lang_param = None if language == "auto" else language
    segments, info = model.transcribe(
        str(audio_path),
        language=lang_param,
        beam_size=5,
        word_timestamps=True,
    )

    detected_lang = info.language
    duration = info.duration

    lines = []
    lines.append("# Транскрипция\n")
    lines.append(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Длительность:** {_format_timestamp(duration)}")
    lines.append(f"**Язык:** {LANGUAGE_NAMES.get(detected_lang, detected_lang)}\n")
    lines.append("---\n")

    full_text_parts = []
    for segment in segments:
        timestamp = _format_timestamp(segment.start)
        text = segment.text.strip()
        lines.append(f"[{timestamp}] {text}\n")
        full_text_parts.append(text)

    transcript_md = "\n".join(lines)
    output_path.write_text(transcript_md, encoding="utf-8")

    return "\n".join(full_text_parts)
```

- [ ] **Step 2: Manual test with a real audio file**

```bash
cd /c/AI/MeetingScribe
source venv/Scripts/activate
python -c "
from meetingscribe.transcriber import transcribe
from pathlib import Path

# Record a short test clip first, or use any WAV file
# This will download the model on first run (~3 GB)
print('Loading model (first run downloads ~3 GB)...')
text = transcribe(
    Path('test_recording.wav'),  # use a real WAV file
    Path('test_transcript.md'),
    language='ru',
)
print(f'Transcript length: {len(text)} chars')
print(text[:500])
"
```

Expected: model downloads on first run, then transcribes the file. `test_transcript.md` created with timestamped transcript.

- [ ] **Step 3: Clean up and commit**

```bash
rm -f test_transcript.md
git add meetingscribe/transcriber.py
git commit -m "feat: transcriber module with faster-whisper and markdown output"
```

---

## Task 6: Summarizer Module

**Files:**
- Create: `meetingscribe/summarizer.py`
- Create: `tests/test_summarizer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_summarizer.py`:

```python
from unittest.mock import patch, MagicMock
from pathlib import Path
from meetingscribe.summarizer import summarize, build_prompt, PROMPTS


def test_all_meeting_types_have_prompts():
    assert "work" in PROMPTS
    assert "english" in PROMPTS
    assert "therapy" in PROMPTS


def test_build_prompt_work():
    prompt = build_prompt("Hello world transcript", "work")
    assert "Hello world transcript" in prompt
    assert "решения" in prompt.lower() or "action" in prompt.lower()


def test_build_prompt_english():
    prompt = build_prompt("Lesson transcript", "english")
    assert "Lesson transcript" in prompt
    assert "vocabulary" in prompt.lower() or "лексик" in prompt.lower()


def test_build_prompt_therapy():
    prompt = build_prompt("Session transcript", "therapy")
    assert "Session transcript" in prompt
    assert "инсайт" in prompt.lower() or "insight" in prompt.lower()


@patch("meetingscribe.summarizer.anthropic")
def test_summarize_calls_api_and_writes_file(mock_anthropic, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Summary\n\nTest summary content")]
    mock_client.messages.create.return_value = mock_response

    output_path = tmp_path / "summary.md"
    result = summarize(
        transcript="Test transcript text",
        output_path=output_path,
        meeting_type="work",
        language="ru",
        duration_seconds=300,
        api_key="sk-test",
        model="claude-sonnet-4-6",
    )

    assert output_path.exists()
    assert "Summary" in output_path.read_text(encoding="utf-8")
    mock_client.messages.create.assert_called_once()

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert len(call_kwargs["messages"]) == 1


@patch("meetingscribe.summarizer.anthropic")
def test_summarize_returns_none_on_empty_key(mock_anthropic, tmp_path):
    output_path = tmp_path / "summary.md"
    result = summarize(
        transcript="Test",
        output_path=output_path,
        meeting_type="work",
        language="ru",
        duration_seconds=60,
        api_key="",
        model="claude-sonnet-4-6",
    )
    assert result is None
    assert not output_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_summarizer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement summarizer with all 3 prompt templates**

Create `meetingscribe/summarizer.py`:

```python
import anthropic
from datetime import datetime
from pathlib import Path

PROMPTS = {
    "work": """Ты — профессиональный ассистент для ведения протоколов рабочих встреч. Проанализируй транскрипцию встречи и создай структурированное саммари на русском языке.

Сфокусируйся на:
- Принятых решениях
- Задачах (action items) с ответственными и дедлайнами
- Ключевых обсуждаемых вопросах
- Блокерах и рисках

Формат ответа:

# Встреча: [определи тему встречи]
**Дата:** {date}
**Длительность:** {duration}
**Язык:** {language}
**Тип:** Рабочая встреча

## Краткое содержание
2-3 предложения о сути встречи.

## Ключевые инсайты
- Инсайт 1
- Инсайт 2

## Решения и договорённости
- Что решили, кто отвечает

## Задачи (Action Items)
- [ ] Задача — ответственный — дедлайн

## Важные цитаты
> Дословные цитаты, которые важно запомнить

Транскрипция:

{transcript}""",

    "english": """Ты — профессиональный ассистент для анализа уроков английского языка. Проанализируй транскрипцию урока и создай структурированное саммари на русском языке.

Сфокусируйся на:
- Новой лексике и фразах
- Грамматических темах
- Ошибках ученика и исправлениях
- Рекомендациях преподавателя
- Домашнем задании
- Наблюдениях о прогрессе

Формат ответа:

# Урок английского: [определи тему урока]
**Дата:** {date}
**Длительность:** {duration}
**Язык:** {language}
**Тип:** Урок английского

## Краткое содержание
2-3 предложения о сути урока.

## Новая лексика и фразы
| Слово/фраза | Перевод | Пример использования |
|-------------|---------|---------------------|
| word | перевод | пример |

## Грамматика
- Тема 1: объяснение
- Тема 2: объяснение

## Ошибки и исправления
- Ошибка → Правильный вариант

## Рекомендации преподавателя
- Рекомендация 1

## Домашнее задание
- [ ] Задание 1

## Прогресс
Наблюдения о прогрессе ученика.

Транскрипция:

{transcript}""",

    "therapy": """Ты — профессиональный ассистент для конспектирования терапевтических сессий. Проанализируй транскрипцию сессии и создай структурированное саммари на русском языке. Будь уважителен и профессионален.

Сфокусируйся на:
- Ключевых личных инсайтах
- Рекомендациях и техниках психолога
- Обсуждаемых темах и эмоциональных паттернах
- Направлениях для дальнейшей проработки

Формат ответа:

# Сессия с психологом: [определи основную тему]
**Дата:** {date}
**Длительность:** {duration}
**Язык:** {language}
**Тип:** Сессия с психологом

## Краткое содержание
2-3 предложения о сути сессии.

## Ключевые инсайты
- Инсайт 1
- Инсайт 2

## Рекомендации и техники
- Рекомендация/техника 1
- Рекомендация/техника 2

## Обсуждаемые темы
- Тема 1: краткое описание
- Тема 2: краткое описание

## Направления для проработки
- Направление 1
- Направление 2

## Важные цитаты
> Дословные цитаты, которые важно запомнить

## Домашнее задание / упражнения
- [ ] Задание 1

Транскрипция:

{transcript}""",
}

LANGUAGE_NAMES = {
    "ru": "Русский",
    "en": "English",
    "auto": "Авто",
}


def _format_duration(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h} ч {m} мин"
    return f"{m} мин"


def build_prompt(transcript: str, meeting_type: str, **kwargs) -> str:
    template = PROMPTS.get(meeting_type, PROMPTS["work"])
    return template.format(
        transcript=transcript,
        date=kwargs.get("date", datetime.now().strftime("%Y-%m-%d %H:%M")),
        duration=kwargs.get("duration", "N/A"),
        language=kwargs.get("language", "Русский"),
    )


def summarize(
    transcript: str,
    output_path: Path,
    meeting_type: str,
    language: str,
    duration_seconds: int,
    api_key: str,
    model: str = "claude-sonnet-4-6",
) -> str | None:
    if not api_key:
        return None

    prompt = build_prompt(
        transcript,
        meeting_type,
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        duration=_format_duration(duration_seconds),
        language=LANGUAGE_NAMES.get(language, language),
    )

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    summary_text = response.content[0].text
    output_path.write_text(summary_text, encoding="utf-8")

    return summary_text
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_summarizer.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add meetingscribe/summarizer.py tests/test_summarizer.py
git commit -m "feat: summarizer with Claude API and 3 meeting type prompts"
```

---

## Task 7: Processing Pipeline

**Files:**
- Create: `meetingscribe/pipeline.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pipeline.py`:

```python
import json
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime
from meetingscribe.pipeline import Pipeline, PipelineStatus
from meetingscribe.config import Config


def _make_config(tmp_path, **overrides):
    defaults = {
        "recordings_dir": str(tmp_path / "recordings"),
        "anthropic_api_key": "sk-test",
        "keep_wav": False,
    }
    defaults.update(overrides)
    return Config(**defaults)


@patch("meetingscribe.pipeline.convert_to_ogg")
@patch("meetingscribe.pipeline.summarize")
@patch("meetingscribe.pipeline.transcribe")
def test_pipeline_runs_all_steps(mock_transcribe, mock_summarize, mock_convert, tmp_path):
    config = _make_config(tmp_path)
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"fake wav")

    mock_transcribe.return_value = "transcribed text"
    mock_summarize.return_value = "summary text"

    pipeline = Pipeline(config)
    status_log = []
    pipeline.run(
        wav_path=wav_path,
        meeting_type="work",
        language="ru",
        duration_seconds=120,
        start_time=datetime(2026, 4, 22, 14, 30),
        on_status=lambda s: status_log.append(s),
    )

    mock_transcribe.assert_called_once()
    mock_summarize.assert_called_once()
    mock_convert.assert_called_once()

    assert PipelineStatus.TRANSCRIBING in status_log
    assert PipelineStatus.SUMMARIZING in status_log
    assert PipelineStatus.CONVERTING in status_log
    assert PipelineStatus.DONE in status_log


@patch("meetingscribe.pipeline.convert_to_ogg")
@patch("meetingscribe.pipeline.summarize")
@patch("meetingscribe.pipeline.transcribe")
def test_pipeline_writes_meta_json(mock_transcribe, mock_summarize, mock_convert, tmp_path):
    config = _make_config(tmp_path)
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"fake wav")

    mock_transcribe.return_value = "text"
    mock_summarize.return_value = "summary"

    pipeline = Pipeline(config)
    pipeline.run(
        wav_path=wav_path,
        meeting_type="english",
        language="en",
        duration_seconds=3600,
        start_time=datetime(2026, 4, 22, 14, 30),
        on_status=lambda s: None,
    )

    recordings_dir = Path(config.recordings_dir)
    meta_files = list(recordings_dir.rglob("meta.json"))
    assert len(meta_files) == 1

    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert meta["language"] == "en"
    assert meta["meeting_type"] == "english"
    assert meta["duration_seconds"] == 3600


@patch("meetingscribe.pipeline.convert_to_ogg")
@patch("meetingscribe.pipeline.summarize")
@patch("meetingscribe.pipeline.transcribe")
def test_pipeline_skips_summary_without_api_key(mock_transcribe, mock_summarize, mock_convert, tmp_path):
    config = _make_config(tmp_path, anthropic_api_key="")
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"fake wav")

    mock_transcribe.return_value = "text"
    mock_summarize.return_value = None

    pipeline = Pipeline(config)
    pipeline.run(
        wav_path=wav_path,
        meeting_type="work",
        language="ru",
        duration_seconds=60,
        start_time=datetime(2026, 4, 22, 14, 30),
        on_status=lambda s: None,
    )

    mock_summarize.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_pipeline.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement pipeline**

Create `meetingscribe/pipeline.py`:

```python
import json
import subprocess
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

from meetingscribe.config import Config
from meetingscribe.storage import create_recording_paths
from meetingscribe.transcriber import transcribe
from meetingscribe.summarizer import summarize


class PipelineStatus(Enum):
    TRANSCRIBING = "Транскрибирую..."
    SUMMARIZING = "Генерирую саммари..."
    CONVERTING = "Конвертирую аудио..."
    DONE = "Готово"
    ERROR = "Ошибка"


def convert_to_ogg(wav_path: Path, ogg_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return False

    try:
        subprocess.run(
            [ffmpeg, "-i", str(wav_path), "-c:a", "libopus", "-b:a", "64k", "-y", str(ogg_path)],
            check=True,
            capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


class Pipeline:
    def __init__(self, config: Config):
        self.config = config

    def run(
        self,
        wav_path: Path,
        meeting_type: str,
        language: str,
        duration_seconds: int,
        start_time: datetime,
        on_status: Callable[[PipelineStatus], None],
    ):
        paths = create_recording_paths(
            self.config.recordings_dir, meeting_type, start_time
        )

        target_wav = paths.wav
        if wav_path != target_wav:
            shutil.move(str(wav_path), str(target_wav))

        on_status(PipelineStatus.TRANSCRIBING)
        transcript_text = transcribe(
            audio_path=target_wav,
            output_path=paths.transcript,
            language=language,
            model_size=self.config.whisper_model,
            device=self.config.whisper_device,
        )

        on_status(PipelineStatus.SUMMARIZING)
        summarize(
            transcript=transcript_text,
            output_path=paths.summary,
            meeting_type=meeting_type,
            language=language,
            duration_seconds=duration_seconds,
            api_key=self.config.anthropic_api_key,
            model=self.config.anthropic_model,
        )

        on_status(PipelineStatus.CONVERTING)
        converted = convert_to_ogg(target_wav, paths.ogg)
        if converted and not self.config.keep_wav:
            target_wav.unlink(missing_ok=True)

        meta = {
            "date": start_time.isoformat(),
            "duration_seconds": duration_seconds,
            "language": language,
            "meeting_type": meeting_type,
            "has_summary": paths.summary.exists(),
            "has_ogg": paths.ogg.exists(),
        }
        paths.meta.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        on_status(PipelineStatus.DONE)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_pipeline.py -v
```

Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add meetingscribe/pipeline.py tests/test_pipeline.py
git commit -m "feat: processing pipeline with transcribe, summarize, convert steps"
```

---

## Task 8: UI — Popup Window

**Files:**
- Create: `meetingscribe/ui/popup.py`

- [ ] **Step 1: Implement popup window**

Create `meetingscribe/ui/popup.py`:

```python
import tkinter as tk
from tkinter import ttk
from typing import Callable


LANGUAGES = [
    ("Русский", "ru"),
    ("English", "en"),
    ("Авто", "auto"),
]

MEETING_TYPES = [
    ("Рабочая встреча", "work"),
    ("Урок английского", "english"),
    ("Сессия с психологом", "therapy"),
]


class PopupWindow:
    def __init__(
        self,
        on_start: Callable[[str, str], None],
        on_stop: Callable[[], None],
    ):
        self._on_start = on_start
        self._on_stop = on_stop
        self._root: tk.Tk | None = None
        self._recording = False
        self._elapsed = 0
        self._timer_id = None
        self._level_value = 0.0

    def show(self):
        if self._root is not None:
            self._root.deiconify()
            self._root.lift()
            return

        self._root = tk.Tk()
        self._root.title("MeetingScribe")
        self._root.geometry("320x280")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        frame = ttk.Frame(self._root, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # Language
        ttk.Label(frame, text="Язык:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self._lang_var = tk.StringVar(value=LANGUAGES[0][0])
        self._lang_combo = ttk.Combobox(
            frame,
            textvariable=self._lang_var,
            values=[l[0] for l in LANGUAGES],
            state="readonly",
            width=22,
        )
        self._lang_combo.grid(row=0, column=1, pady=3)

        # Meeting type
        ttk.Label(frame, text="Тип:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self._type_var = tk.StringVar(value=MEETING_TYPES[0][0])
        self._type_combo = ttk.Combobox(
            frame,
            textvariable=self._type_var,
            values=[t[0] for t in MEETING_TYPES],
            state="readonly",
            width=22,
        )
        self._type_combo.grid(row=1, column=1, pady=3)

        # Audio level
        ttk.Label(frame, text="Уровень:").grid(row=2, column=0, sticky=tk.W, pady=8)
        self._level_bar = ttk.Progressbar(
            frame, orient=tk.HORIZONTAL, length=180, mode="determinate", maximum=100
        )
        self._level_bar.grid(row=2, column=1, pady=8)

        # Start/Stop button
        self._btn_var = tk.StringVar(value="● Начать запись")
        self._btn = ttk.Button(
            frame, textvariable=self._btn_var, command=self._toggle_recording
        )
        self._btn.grid(row=3, column=0, columnspan=2, pady=10, ipadx=20, ipady=5)

        # Status
        self._status_var = tk.StringVar(value="Готов к записи")
        self._status_label = ttk.Label(
            frame, textvariable=self._status_var, foreground="gray"
        )
        self._status_label.grid(row=4, column=0, columnspan=2, pady=5)

    def _on_close(self):
        if self._root:
            self._root.withdraw()

    def _toggle_recording(self):
        if not self._recording:
            lang_name = self._lang_var.get()
            lang_code = next(code for name, code in LANGUAGES if name == lang_name)
            type_name = self._type_var.get()
            type_code = next(code for name, code in MEETING_TYPES if name == type_name)

            self._on_start(lang_code, type_code)

            self._recording = True
            self._elapsed = 0
            self._btn_var.set("■ Остановить")
            self._lang_combo.config(state="disabled")
            self._type_combo.config(state="disabled")
            self._update_timer()
        else:
            self._recording = False
            if self._timer_id:
                self._root.after_cancel(self._timer_id)
                self._timer_id = None
            self._btn.config(state="disabled")
            self._on_stop()

    def _update_timer(self):
        if not self._recording:
            return
        h = self._elapsed // 3600
        m = (self._elapsed % 3600) // 60
        s = self._elapsed % 60
        self._status_var.set(f"Записываю... {h:02d}:{m:02d}:{s:02d}")
        self._elapsed += 1
        self._timer_id = self._root.after(1000, self._update_timer)

    def update_level(self, level: float):
        self._level_value = level
        if self._root and self._level_bar:
            self._level_bar["value"] = int(level * 100)

    def set_status(self, text: str):
        if self._root:
            self._status_var.set(text)

    def reset_after_processing(self):
        if self._root:
            self._recording = False
            self._btn_var.set("● Начать запись")
            self._btn.config(state="normal")
            self._lang_combo.config(state="readonly")
            self._type_combo.config(state="readonly")
            self._level_bar["value"] = 0

    def run_mainloop(self):
        if self._root:
            self._root.mainloop()

    def destroy(self):
        if self._root:
            self._root.destroy()
            self._root = None
```

- [ ] **Step 2: Quick manual test**

```bash
python -c "
from meetingscribe.ui.popup import PopupWindow

def on_start(lang, mtype):
    print(f'Start: lang={lang}, type={mtype}')

def on_stop():
    print('Stop')

popup = PopupWindow(on_start, on_stop)
popup.show()
popup.run_mainloop()
"
```

Expected: window appears with dropdowns, button, and level bar. Clicking Start/Stop prints to console.

- [ ] **Step 3: Commit**

```bash
git add meetingscribe/ui/popup.py
git commit -m "feat: tkinter popup window with recording controls"
```

---

## Task 9: System Tray + App Wiring

**Files:**
- Create: `meetingscribe/ui/tray.py`
- Create: `meetingscribe/ui/app.py`

- [ ] **Step 1: Implement tray icon**

Create `meetingscribe/ui/tray.py`:

```python
import threading
from PIL import Image, ImageDraw
import pystray


def _create_icon_image(color: str = "green") -> Image.Image:
    img = Image.new("RGB", 64, 64)
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill=color)
    return img


def create_tray(on_open: callable, on_quit: callable) -> pystray.Icon:
    icon = pystray.Icon(
        "MeetingScribe",
        _create_icon_image("green"),
        "MeetingScribe",
        menu=pystray.Menu(
            pystray.MenuItem("Открыть", on_open, default=True),
            pystray.MenuItem("Выход", on_quit),
        ),
    )
    return icon


def set_tray_recording(icon: pystray.Icon, is_recording: bool):
    color = "red" if is_recording else "green"
    icon.icon = _create_icon_image(color)
```

- [ ] **Step 2: Implement main app class**

Create `meetingscribe/ui/app.py`:

```python
import threading
import time
from datetime import datetime
from pathlib import Path

from meetingscribe.config import Config
from meetingscribe.audio_capture import AudioCapture
from meetingscribe.pipeline import Pipeline, PipelineStatus
from meetingscribe.ui.tray import create_tray, set_tray_recording
from meetingscribe.ui.popup import PopupWindow


class App:
    def __init__(self, config: Config):
        self.config = config
        self.capture = AudioCapture(config.audio_sample_rate)
        self.pipeline = Pipeline(config)

        self._recording_language = "ru"
        self._recording_type = "work"
        self._start_time: datetime | None = None
        self._level_thread: threading.Thread | None = None
        self._tray = None

        self.popup = PopupWindow(
            on_start=self._handle_start,
            on_stop=self._handle_stop,
        )

    def run(self):
        self._tray = create_tray(
            on_open=lambda icon, item: self._open_popup(),
            on_quit=lambda icon, item: self._quit(),
        )

        popup_thread = threading.Thread(target=self._run_popup, daemon=True)
        popup_thread.start()

        self._tray.run()

    def _run_popup(self):
        self.popup.show()
        self.popup.run_mainloop()

    def _open_popup(self):
        self.popup.show()

    def _handle_start(self, language: str, meeting_type: str):
        self._recording_language = language
        self._recording_type = meeting_type
        self._start_time = datetime.now()

        try:
            self.capture.start()
        except RuntimeError as e:
            self.popup.set_status(f"Ошибка: {e}")
            self.popup.reset_after_processing()
            return

        if self._tray:
            set_tray_recording(self._tray, True)

        self._level_thread = threading.Thread(target=self._update_levels, daemon=True)
        self._level_thread.start()

    def _handle_stop(self):
        if self._tray:
            set_tray_recording(self._tray, False)

        tmp_wav = Path(self.config.recordings_dir) / "_temp_recording.wav"
        tmp_wav.parent.mkdir(parents=True, exist_ok=True)
        duration = self.capture.stop(tmp_wav)

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(tmp_wav, duration),
            daemon=True,
        )
        thread.start()

    def _run_pipeline(self, wav_path: Path, duration: int):
        def on_status(status: PipelineStatus):
            self.popup.set_status(status.value)

        try:
            self.pipeline.run(
                wav_path=wav_path,
                meeting_type=self._recording_type,
                language=self._recording_language,
                duration_seconds=duration,
                start_time=self._start_time or datetime.now(),
                on_status=on_status,
            )
        except Exception as e:
            self.popup.set_status(f"Ошибка: {e}")

        self.popup.reset_after_processing()

    def _update_levels(self):
        while self.capture.is_recording:
            self.popup.update_level(self.capture.audio_level)
            time.sleep(0.05)
        self.popup.update_level(0.0)

    def _quit(self):
        if self.capture.is_recording:
            tmp = Path(self.config.recordings_dir) / "_abort.wav"
            self.capture.stop(tmp)
            tmp.unlink(missing_ok=True)

        self.popup.destroy()
        if self._tray:
            self._tray.stop()
```

- [ ] **Step 3: Commit**

```bash
git add meetingscribe/ui/tray.py meetingscribe/ui/app.py
git commit -m "feat: system tray icon and main app wiring"
```

---

## Task 10: Entry Point & Integration

**Files:**
- Create: `meetingscribe/__main__.py`
- Create: `run.pyw`

- [ ] **Step 1: Create entry point**

Create `meetingscribe/__main__.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from meetingscribe.config import Config
from meetingscribe.ui.app import App


def main():
    config = Config.load()

    if not config.anthropic_api_key:
        print(
            "WARNING: Anthropic API key not set in config.json. "
            "Summaries will be skipped."
        )

    app = App(config)
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create double-click launcher**

Create `run.pyw` (`.pyw` runs without console window on Windows):

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from meetingscribe.config import Config
from meetingscribe.ui.app import App

config = Config.load()
app = App(config)
app.run()
```

- [ ] **Step 3: Run all tests**

```bash
cd /c/AI/MeetingScribe
source venv/Scripts/activate
python -m pytest tests/ -v
```

Expected: all tests PASS (test_config: 5, test_storage: 6, test_summarizer: 6, test_pipeline: 3 = 20 tests)

- [ ] **Step 4: End-to-end manual test**

```bash
python -m meetingscribe
```

Test sequence:
1. Tray icon appears (green circle)
2. Click tray icon → popup opens
3. Select language: Русский, type: Рабочая встреча
4. Click "Начать запись" — play some audio, speak into mic
5. Level bar should show activity, timer counts up
6. Tray icon turns red
7. Click "Остановить"
8. Status shows: "Транскрибирую..." → "Генерирую саммари..." → "Конвертирую аудио..." → "Готово"
9. Check `recordings/2026/04/` — folder created with transcript.md, summary.md, audio.ogg, meta.json
10. Right-click tray → "Выход"

- [ ] **Step 5: Commit**

```bash
git add meetingscribe/__main__.py run.pyw
git commit -m "feat: entry point and launcher for MeetingScribe"
```

- [ ] **Step 6: Final commit — add .gitignore**

Create `.gitignore`:

```
venv/
__pycache__/
*.pyc
recordings/
_temp_recording.wav
.pytest_cache/
```

```bash
git add .gitignore
git commit -m "chore: add .gitignore"
```
