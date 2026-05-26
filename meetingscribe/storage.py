from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MEETING_TYPE_FOLDER = {
    "work": "work_meeting",
    "english": "english_lesson",
    "personal": "personal_meeting",
    "external": "external_source",
}

FOLDER_MEETING_TYPE = {v: k for k, v in MEETING_TYPE_FOLDER.items()}


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
