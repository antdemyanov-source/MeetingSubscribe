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
