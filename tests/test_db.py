import sqlite3

import pytest

from meetingscribe import db


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    db.init_db(c)
    return c


def test_update_meeting_topic_updates_existing_row(conn):
    conn.execute(
        "INSERT INTO meetings (date, time, topic, folder) VALUES (?, ?, ?, ?)",
        ("2026-08-19", "10:00", "old title", "/tmp/meeting-a"),
    )
    conn.commit()

    db.update_meeting_topic(conn, "/tmp/meeting-a", "new title")

    row = db.get_meeting_by_folder(conn, "/tmp/meeting-a")
    assert row["topic"] == "new title"


def test_update_meeting_topic_noop_when_folder_missing(conn):
    # Should not raise even if no meeting row exists for the folder yet.
    db.update_meeting_topic(conn, "/tmp/does-not-exist", "new title")

    assert db.get_meeting_by_folder(conn, "/tmp/does-not-exist") is None


def test_update_meeting_topic_only_touches_matching_folder(conn):
    conn.execute(
        "INSERT INTO meetings (date, time, topic, folder) VALUES (?, ?, ?, ?)",
        ("2026-08-19", "10:00", "keep me", "/tmp/meeting-b"),
    )
    conn.execute(
        "INSERT INTO meetings (date, time, topic, folder) VALUES (?, ?, ?, ?)",
        ("2026-08-19", "11:00", "old title", "/tmp/meeting-c"),
    )
    conn.commit()

    db.update_meeting_topic(conn, "/tmp/meeting-c", "new title")

    assert db.get_meeting_by_folder(conn, "/tmp/meeting-b")["topic"] == "keep me"
    assert db.get_meeting_by_folder(conn, "/tmp/meeting-c")["topic"] == "new title"
