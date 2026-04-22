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
