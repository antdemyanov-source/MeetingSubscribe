import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from meetingscribe.storage import FOLDER_MEETING_TYPE


class SessionStatus(Enum):
    RECORDING = "Записываю..."
    TRANSCRIBING = "Транскрибирую..."
    READY = "Готово к саммари"
    SUMMARIZING = "Генерирую саммари..."
    DONE = "Готово"
    ERROR = "Ошибка"
    IMPORTED = "Загружено"


MEETING_TYPE_DISPLAY = {
    "work": "Рабочая",
    "english": "Английский",
    "therapy": "Личная",
}


@dataclass
class RecordingSession:
    folder: Path
    start_time: datetime
    duration: int
    meeting_type: str
    language: str
    status: SessionStatus
    audio_mode: str = "loopback"
    has_audio: bool = False
    has_transcript: bool = False

    @property
    def display_date(self) -> str:
        return self.start_time.strftime("%d.%m.%Y %H:%M")

    @property
    def display_duration(self) -> str:
        h = self.duration // 3600
        m = (self.duration % 3600) // 60
        s = self.duration % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    @property
    def display_type(self) -> str:
        return MEETING_TYPE_DISPLAY.get(self.meeting_type, self.meeting_type)

    @property
    def folder_key(self) -> str:
        return str(self.folder)


class SessionManager:
    def __init__(self, recordings_dir: str):
        self.recordings_dir = Path(recordings_dir)
        self.sessions: dict[str, RecordingSession] = {}
        self._load_existing()

    def _load_existing(self):
        if not self.recordings_dir.exists():
            return

        known_folders: set[str] = set()

        for meta_file in self.recordings_dir.rglob("meta.json"):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                folder = meta_file.parent
                known_folders.add(str(folder))
                start_time = datetime.fromisoformat(meta["date"])
                has_summary = (folder / "summary.md").exists()
                has_transcript = (folder / "transcript.md").exists()
                has_audio = any(
                    (folder / f"audio{ext}").exists()
                    for ext in (".wav", ".ogg", ".mp3", ".m4a", ".flac")
                )

                if has_summary:
                    status = SessionStatus.DONE
                elif has_transcript:
                    status = SessionStatus.READY
                elif has_audio and meta.get("source") == "import":
                    status = SessionStatus.IMPORTED
                else:
                    status = SessionStatus.ERROR

                session = RecordingSession(
                    folder=folder,
                    start_time=start_time,
                    duration=meta.get("duration_seconds", 0),
                    meeting_type=meta.get("meeting_type", "work"),
                    language=meta.get("language", "ru"),
                    status=status,
                    audio_mode=meta.get("audio_mode", "loopback"),
                    has_audio=has_audio,
                    has_transcript=has_transcript,
                )
                self.sessions[session.folder_key] = session
            except (json.JSONDecodeError, KeyError, ValueError):
                pass

        for audio_file in self.recordings_dir.rglob("audio.*"):
            if audio_file.suffix not in (".wav", ".ogg", ".mp3", ".m4a", ".flac"):
                continue
            folder = audio_file.parent
            if str(folder) in known_folders or str(folder) in self.sessions:
                continue
            session = self._parse_orphan_folder(folder)
            if session:
                known_folders.add(str(folder))
                self.sessions[session.folder_key] = session

    def _parse_orphan_folder(self, folder: Path) -> RecordingSession | None:
        name = folder.name
        if len(name) < 18 or name[16] != "_":
            return None
        date_str = name[:16]
        type_folder = name[17:]
        try:
            start_time = datetime.strptime(date_str, "%Y-%m-%d_%H-%M")
        except ValueError:
            return None

        meeting_type = FOLDER_MEETING_TYPE.get(type_folder, "work")
        has_transcript = (folder / "transcript.md").exists()
        has_audio = (folder / "audio.wav").exists() or (folder / "audio.ogg").exists()

        if has_transcript:
            status = SessionStatus.READY
        else:
            status = SessionStatus.ERROR

        return RecordingSession(
            folder=folder,
            start_time=start_time,
            duration=0,
            meeting_type=meeting_type,
            language="ru",
            status=status,
            has_audio=has_audio,
            has_transcript=has_transcript,
        )

    def create_session(
        self,
        folder: Path,
        start_time: datetime,
        meeting_type: str,
        language: str,
        audio_mode: str = "loopback",
    ) -> RecordingSession:
        session = RecordingSession(
            folder=folder,
            start_time=start_time,
            duration=0,
            meeting_type=meeting_type,
            language=language,
            status=SessionStatus.RECORDING,
            audio_mode=audio_mode,
        )
        self.sessions[session.folder_key] = session
        return session

    def update_status(self, folder: Path, status: SessionStatus):
        key = str(folder)
        if key in self.sessions:
            self.sessions[key].status = status

    def update_duration(self, folder: Path, duration: int):
        key = str(folder)
        if key in self.sessions:
            self.sessions[key].duration = duration

    def get_session(self, folder: Path) -> RecordingSession | None:
        return self.sessions.get(str(folder))

    def reload(self):
        active = {k: v for k, v in self.sessions.items()
                  if v.status in (SessionStatus.RECORDING, SessionStatus.TRANSCRIBING, SessionStatus.SUMMARIZING)}
        self.sessions = active
        self._load_existing()

    def remove_session(self, folder: Path):
        self.sessions.pop(str(folder), None)

    def get_sorted_sessions(self) -> list[RecordingSession]:
        return sorted(
            self.sessions.values(), key=lambda s: s.start_time, reverse=True
        )
