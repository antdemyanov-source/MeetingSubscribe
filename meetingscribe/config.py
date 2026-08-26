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
    audio_sample_rate: int = 44100
    mic_device_name: str = ""
    mic_volume: float = 0.5
    keep_wav: bool = False
    silence_threshold: float = 0.03
    silence_auto_stop_minutes: int = 5
    max_recording_minutes: int = 70
    obsidian_vault_path: str = ""
    ui_backend: str = "tk"  # "tk" — классический UI, "web" — новый на pywebview
    hide_personal: bool = False  # скрывать личные встречи из списка и фильтров
    # команда формирования саммари; {transcript} заменяется на путь к transcript.md
    summary_cli: str = 'claude -p "/summary {transcript}" --dangerously-skip-permissions'
    auto_transcribe: bool = True  # транскрибировать автоматически после остановки записи
    summary_activities: bool = True  # определять активность встречи при саммари
    summary_tasks: bool = True       # создавать задачи из саммари
    anthropic_api_key: str = ""  # для формирования саммари из UI

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
