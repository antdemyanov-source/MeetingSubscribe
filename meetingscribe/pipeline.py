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
            ollama_url=self.config.ollama_url,
            ollama_model=self.config.ollama_model,
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
