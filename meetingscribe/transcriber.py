import ctypes
import os
import sys
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


def _set_low_priority():
    if sys.platform == "win32":
        BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(),
            BELOW_NORMAL_PRIORITY_CLASS,
        )


def _restore_priority():
    if sys.platform == "win32":
        NORMAL_PRIORITY_CLASS = 0x00000020
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(),
            NORMAL_PRIORITY_CLASS,
        )


def transcribe(
    audio_path: Path,
    output_path: Path,
    language: str = "ru",
    model_size: str = "turbo",
    device: str = "cpu",
    on_progress=None,
) -> str:
    _set_low_priority()
    try:
        return _do_transcribe(
            audio_path, output_path, language, model_size, device,
            on_progress=on_progress,
        )
    finally:
        _restore_priority()


def _do_transcribe(
    audio_path: Path,
    output_path: Path,
    language: str,
    model_size: str,
    device: str,
    on_progress=None,
) -> str:
    from faster_whisper import WhisperModel, BatchedInferencePipeline

    if on_progress:
        on_progress(0.05)

    cpu_threads = max(1, (os.cpu_count() or 4) // 2)
    model = WhisperModel(
        model_size,
        device=device,
        compute_type="int8",
        cpu_threads=cpu_threads,
    )
    batched = BatchedInferencePipeline(model=model)

    if on_progress:
        on_progress(0.15)

    lang_param = None if language == "auto" else language
    segments, info = batched.transcribe(
        str(audio_path),
        language=lang_param,
        beam_size=5,
        word_timestamps=True,
        batch_size=8,
        hallucination_silence_threshold=2,
        condition_on_previous_text=False,
        vad_filter=True,
        vad_parameters=dict(
            threshold=0.3,
            min_speech_duration_ms=100,
            min_silence_duration_ms=1000,
            speech_pad_ms=400,
        ),
    )

    detected_lang = info.language
    duration = info.duration

    if on_progress:
        on_progress(0.25)

    lines = []
    lines.append("# Транскрипция\n")
    lines.append(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Длительность:** {_format_timestamp(duration)}")
    lines.append(f"**Язык:** {LANGUAGE_NAMES.get(detected_lang, detected_lang)}\n")
    lines.append("---\n")

    full_text_parts = []
    prev_text = None
    repeat_count = 0
    last_progress_pct = -1
    for segment in segments:
        text = segment.text.strip()
        if text == prev_text:
            repeat_count += 1
            if repeat_count >= 3:
                continue
        else:
            prev_text = text
            repeat_count = 0
        timestamp = _format_timestamp(segment.start)
        lines.append(f"[{timestamp}] {text}\n")
        full_text_parts.append(text)

        if on_progress and duration > 0:
            raw = min(1.0, segment.end / duration)
            pct = int(raw * 100)
            if pct > last_progress_pct:
                last_progress_pct = pct
                on_progress(0.25 + raw * 0.75)

    transcript_md = "\n".join(lines)
    output_path.write_text(transcript_md, encoding="utf-8")

    return "\n".join(full_text_parts)
