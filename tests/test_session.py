import json
from datetime import datetime
from pathlib import Path
from meetingscribe.session import (
    SessionManager, SessionStatus, RecordingSession, MEETING_TYPE_DISPLAY,
)


def test_recording_session_display_date():
    session = RecordingSession(
        folder=Path("/tmp/test"),
        start_time=datetime(2026, 4, 22, 14, 30),
        duration=0,
        meeting_type="work",
        language="ru",
        status=SessionStatus.RECORDING,
    )
    assert session.display_date == "22.04.2026 14:30"


def test_recording_session_display_duration_minutes():
    session = RecordingSession(
        folder=Path("/tmp/test"),
        start_time=datetime(2026, 1, 1),
        duration=125,
        meeting_type="work",
        language="ru",
        status=SessionStatus.DONE,
    )
    assert session.display_duration == "2:05"


def test_recording_session_display_duration_hours():
    session = RecordingSession(
        folder=Path("/tmp/test"),
        start_time=datetime(2026, 1, 1),
        duration=3661,
        meeting_type="work",
        language="ru",
        status=SessionStatus.DONE,
    )
    assert session.display_duration == "1:01:01"


def test_recording_session_display_type():
    for code, display in MEETING_TYPE_DISPLAY.items():
        session = RecordingSession(
            folder=Path("/tmp"),
            start_time=datetime(2026, 1, 1),
            duration=0,
            meeting_type=code,
            language="ru",
            status=SessionStatus.DONE,
        )
        assert session.display_type == display


def test_session_manager_loads_existing(tmp_path):
    folder = tmp_path / "recordings" / "2026" / "04" / "2026-04-22_14-30_work_meeting"
    folder.mkdir(parents=True)

    (folder / "transcript.md").write_text("hello", encoding="utf-8")
    meta = {
        "date": "2026-04-22T14:30:00",
        "duration_seconds": 300,
        "meeting_type": "work",
        "language": "ru",
    }
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    mgr = SessionManager(str(tmp_path / "recordings"))
    sessions = mgr.get_sorted_sessions()
    assert len(sessions) == 1
    assert sessions[0].status == SessionStatus.READY
    assert sessions[0].duration == 300


def test_session_manager_done_with_summary(tmp_path):
    folder = tmp_path / "recordings" / "2026" / "04" / "2026-04-22_14-30_work_meeting"
    folder.mkdir(parents=True)

    (folder / "transcript.md").write_text("hello", encoding="utf-8")
    (folder / "summary.md").write_text("summary", encoding="utf-8")
    meta = {
        "date": "2026-04-22T14:30:00",
        "duration_seconds": 60,
        "meeting_type": "work",
        "language": "ru",
    }
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    mgr = SessionManager(str(tmp_path / "recordings"))
    sessions = mgr.get_sorted_sessions()
    assert sessions[0].status == SessionStatus.DONE


def test_session_manager_create_session(tmp_path):
    mgr = SessionManager(str(tmp_path / "recordings"))
    folder = tmp_path / "recordings" / "test_folder"
    session = mgr.create_session(
        folder, datetime(2026, 4, 22, 15, 0), "english", "en", "mic"
    )
    assert session.status == SessionStatus.RECORDING
    assert session.audio_mode == "mic"
    assert len(mgr.get_sorted_sessions()) == 1


def test_session_manager_update_status(tmp_path):
    mgr = SessionManager(str(tmp_path / "recordings"))
    folder = tmp_path / "recordings" / "test_folder"
    mgr.create_session(folder, datetime(2026, 4, 22, 15, 0), "work", "ru")

    mgr.update_status(folder, SessionStatus.TRANSCRIBING)
    assert mgr.get_session(folder).status == SessionStatus.TRANSCRIBING

    mgr.update_status(folder, SessionStatus.READY)
    assert mgr.get_session(folder).status == SessionStatus.READY


def test_session_manager_update_duration(tmp_path):
    mgr = SessionManager(str(tmp_path / "recordings"))
    folder = tmp_path / "recordings" / "test_folder"
    mgr.create_session(folder, datetime(2026, 4, 22, 15, 0), "work", "ru")
    mgr.update_duration(folder, 180)
    assert mgr.get_session(folder).duration == 180


def test_sessions_sorted_newest_first(tmp_path):
    mgr = SessionManager(str(tmp_path / "recordings"))
    f1 = tmp_path / "recordings" / "f1"
    f2 = tmp_path / "recordings" / "f2"
    mgr.create_session(f1, datetime(2026, 4, 20), "work", "ru")
    mgr.create_session(f2, datetime(2026, 4, 22), "work", "ru")

    sessions = mgr.get_sorted_sessions()
    assert sessions[0].start_time == datetime(2026, 4, 22)
    assert sessions[1].start_time == datetime(2026, 4, 20)


def test_imported_status_exists():
    assert SessionStatus.IMPORTED.value == "Загружено"


def test_session_manager_loads_imported(tmp_path):
    folder = tmp_path / "recordings" / "2026" / "04" / "2026-04-28_10-00_work_meeting"
    folder.mkdir(parents=True)

    (folder / "audio.mp3").write_bytes(b"fake audio")
    meta = {
        "date": "2026-04-28T10:00:00",
        "duration_seconds": 0,
        "meeting_type": "work",
        "language": "ru",
        "source": "import",
    }
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    mgr = SessionManager(str(tmp_path / "recordings"))
    sessions = mgr.get_sorted_sessions()
    assert len(sessions) == 1
    assert sessions[0].status == SessionStatus.IMPORTED
