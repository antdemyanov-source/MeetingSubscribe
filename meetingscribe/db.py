"""SQLite database for activities, meetings, and tasks."""

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "meetingscribe.db"

TASK_STATUSES = ("pending", "new", "in_progress", "hold", "done", "cancelled")

TASK_STATUS_DISPLAY = {
    "pending": "Новая",
    "new": "Не начата",
    "in_progress": "В работе",
    "hold": "Hold",
    "done": "Готова",
    "cancelled": "Отменена",
}

TASK_STATUS_FROM_DISPLAY = {v: k for k, v in TASK_STATUS_DISPLAY.items()}

ACTIVITY_STATUS_DISPLAY = {
    "active": "Активна",
    "closed": "Закрыта",
}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id TEXT REFERENCES activities(id) ON DELETE SET NULL,
            date TEXT NOT NULL,
            time TEXT DEFAULT '',
            topic TEXT DEFAULT '',
            folder TEXT UNIQUE
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            responsible TEXT DEFAULT '',
            deadline TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new',
            priority TEXT NOT NULL DEFAULT 'medium',
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL,
            meeting_id INTEGER REFERENCES meetings(id) ON DELETE SET NULL,
            activity_id TEXT REFERENCES activities(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_meetings_activity ON meetings(activity_id);
        CREATE INDEX IF NOT EXISTS idx_meetings_folder ON meetings(folder);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_tasks_meeting ON tasks(meeting_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_activity ON tasks(activity_id);
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS responsibles (
            name TEXT PRIMARY KEY,
            comment TEXT DEFAULT ''
        )
    """)

    try:
        conn.execute(
            "ALTER TABLE activities ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    except sqlite3.OperationalError:
        pass

    conn.commit()

    age_pending_tasks(conn)


def migrate_from_json(conn: sqlite3.Connection):
    """Import activities.json into the database (one-time migration)."""
    json_path = DB_PATH.parent / "activities.json"
    if not json_path.exists():
        return

    existing = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    if existing > 0:
        return

    data = json.loads(json_path.read_text(encoding="utf-8"))
    activities = data.get("activities", [])

    for a in activities:
        conn.execute(
            "INSERT OR IGNORE INTO activities (id, name, description) VALUES (?, ?, ?)",
            (a["id"], a["name"], a.get("description", "")),
        )
        for m in a.get("meetings", []):
            conn.execute(
                "INSERT OR IGNORE INTO meetings (activity_id, date, time, topic, folder) "
                "VALUES (?, ?, ?, ?, ?)",
                (a["id"], m["date"], m.get("time", ""), m.get("topic", ""),
                 m.get("folder", "")),
            )
    conn.commit()


# ── Activity CRUD ────────────────────────────────────────────────────────

def get_activities(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT a.id, a.name, a.description, a.status,
               COUNT(m.id) AS meeting_count,
               MIN(m.date) AS first_meeting,
               MAX(m.date) AS last_meeting
        FROM activities a
        LEFT JOIN meetings m ON m.activity_id = a.id
        GROUP BY a.id
        ORDER BY a.status ASC, last_meeting DESC NULLS LAST
    """).fetchall()
    return [dict(r) for r in rows]


def get_activity_meetings(conn: sqlite3.Connection, activity_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM meetings WHERE activity_id = ? ORDER BY date DESC, time DESC",
        (activity_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_activity(conn: sqlite3.Connection, act_id: str, name: str,
                    description: str = "") -> str:
    conn.execute(
        "INSERT INTO activities (id, name, description) VALUES (?, ?, ?)",
        (act_id, name, description),
    )
    conn.commit()
    return act_id


def rename_activity(conn: sqlite3.Connection, act_id: str, new_name: str):
    conn.execute("UPDATE activities SET name = ? WHERE id = ?", (new_name, act_id))
    conn.commit()


def update_activity_status(conn: sqlite3.Connection, act_id: str, status: str):
    conn.execute("UPDATE activities SET status = ? WHERE id = ?", (status, act_id))
    conn.commit()


def can_close_activity(conn: sqlite3.Connection, act_id: str) -> tuple[bool, str]:
    row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM tasks "
        "WHERE activity_id = ? AND status IN ('pending', 'new', 'in_progress')",
        (act_id,),
    ).fetchone()
    if row[0] > 0:
        return False, f"Есть незавершённые задачи ({row[0]})"
    return True, ""


def delete_activity(conn: sqlite3.Connection, act_id: str):
    conn.execute("UPDATE meetings SET activity_id = NULL WHERE activity_id = ?",
                 (act_id,))
    conn.execute("UPDATE tasks SET activity_id = NULL WHERE activity_id = ?",
                 (act_id,))
    conn.execute("DELETE FROM activities WHERE id = ?", (act_id,))
    conn.commit()


# ── Meeting CRUD ─────────────────────────────────────────────────────────

def get_meeting_by_folder(conn: sqlite3.Connection, folder: str) -> dict | None:
    row = conn.execute("SELECT * FROM meetings WHERE folder = ?", (folder,)).fetchone()
    return dict(row) if row else None


def reassign_meeting(conn: sqlite3.Connection, folder: str,
                     new_activity_id: str):
    existing = get_meeting_by_folder(conn, folder)
    if existing:
        conn.execute("UPDATE meetings SET activity_id = ? WHERE folder = ?",
                     (new_activity_id, folder))
        conn.execute("UPDATE tasks SET activity_id = ? WHERE meeting_id = ?",
                     (new_activity_id, existing["id"]))
    else:
        conn.execute(
            "INSERT INTO meetings (activity_id, date, time, topic, folder) "
            "VALUES (?, '', '', '', ?)",
            (new_activity_id, folder),
        )
    conn.commit()


def delete_meeting_by_folder(conn: sqlite3.Connection, folder: str):
    conn.execute("DELETE FROM meetings WHERE folder = ?", (folder,))
    conn.commit()


def update_meeting_topic(conn: sqlite3.Connection, folder: str, topic: str):
    conn.execute("UPDATE meetings SET topic = ? WHERE folder = ?", (topic, folder))
    conn.commit()


def cleanup_dead_meetings(conn: sqlite3.Connection) -> int:
    """Удалить встречи, чьи папки больше не существуют на диске.

    Задачи таких встреч сохраняются (meeting_id обнуляется по FK).
    """
    import os
    rows = conn.execute(
        "SELECT id, folder FROM meetings WHERE folder IS NOT NULL AND folder != ''"
    ).fetchall()
    dead = [r["id"] for r in rows if not os.path.isdir(r["folder"])]
    for mid in dead:
        conn.execute("DELETE FROM meetings WHERE id = ?", (mid,))
    if dead:
        conn.commit()
    return len(dead)


def get_folder_activity_map(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute(
        "SELECT folder, activity_id FROM meetings WHERE activity_id IS NOT NULL"
    ).fetchall()
    return {r["folder"]: r["activity_id"] for r in rows}


def get_activity_name_map(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT id, name FROM activities").fetchall()
    return {r["id"]: r["name"] for r in rows}


# ── Task CRUD ────────────────────────────────────────────────────────────

def get_tasks(conn: sqlite3.Connection, status_filter: str | None = None,
              activity_id: str | None = None,
              meeting_id: int | None = None,
              exclude_done: bool = False) -> list[dict]:
    query = """
        SELECT t.*, m.folder AS meeting_folder, m.date AS meeting_date,
               m.topic AS meeting_topic, a.name AS activity_name
        FROM tasks t
        LEFT JOIN meetings m ON t.meeting_id = m.id
        LEFT JOIN activities a ON t.activity_id = a.id
        WHERE 1=1
    """
    params: list = []

    if status_filter:
        query += " AND t.status = ?"
        params.append(status_filter)
    if activity_id:
        query += " AND t.activity_id = ?"
        params.append(activity_id)
    if meeting_id is not None:
        query += " AND t.meeting_id = ?"
        params.append(meeting_id)
    if exclude_done:
        query += " AND t.status NOT IN ('done', 'cancelled')"

    query += " ORDER BY t.created_at DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_tasks_for_meeting_folder(conn: sqlite3.Connection, folder: str) -> list[dict]:
    meeting = get_meeting_by_folder(conn, folder)
    if not meeting:
        return []
    return get_tasks(conn, meeting_id=meeting["id"])


def create_task(conn: sqlite3.Connection, title: str, description: str = "",
                responsible: str = "", deadline: str = "",
                status: str = "new", priority: str = "medium",
                source: str = "manual", created_at: str = "",
                meeting_folder: str = "",
                activity_id: str = "") -> int:
    meeting_id = None
    if meeting_folder:
        meeting = get_meeting_by_folder(conn, meeting_folder)
        if meeting:
            meeting_id = meeting["id"]
            if not activity_id and meeting.get("activity_id"):
                activity_id = meeting["activity_id"]

    cursor = conn.execute(
        "INSERT INTO tasks (title, description, responsible, deadline, status, "
        "priority, source, created_at, meeting_id, activity_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, description, responsible, deadline, status, priority,
         source, created_at, meeting_id, activity_id or None),
    )
    conn.commit()
    return cursor.lastrowid


def update_task(conn: sqlite3.Connection, task_id: int, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [task_id]
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
    conn.commit()


def delete_task(conn: sqlite3.Connection, task_id: int):
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()


def age_pending_tasks(conn: sqlite3.Connection, days: int = 7) -> int:
    """Move tasks from 'pending' to 'new' if created_at is older than `days` days."""
    cursor = conn.execute(
        "UPDATE tasks SET status = 'new' "
        "WHERE status = 'pending' AND created_at <= datetime('now', ?)",
        (f"-{days} days",),
    )
    conn.commit()
    return cursor.rowcount


def get_task_counts_by_activity(conn: sqlite3.Connection) -> dict[str, dict]:
    rows = conn.execute("""
        SELECT activity_id,
               COUNT(*) AS total,
               SUM(CASE WHEN status NOT IN ('done', 'cancelled') THEN 1 ELSE 0 END) AS active
        FROM tasks
        WHERE activity_id IS NOT NULL
        GROUP BY activity_id
    """).fetchall()
    return {r["activity_id"]: {"total": r["total"], "active": r["active"]}
            for r in rows}


def get_task_counts_by_meeting(conn: sqlite3.Connection) -> dict[int, dict]:
    rows = conn.execute("""
        SELECT meeting_id,
               COUNT(*) AS total,
               SUM(CASE WHEN status NOT IN ('done', 'cancelled') THEN 1 ELSE 0 END) AS active
        FROM tasks
        WHERE meeting_id IS NOT NULL
        GROUP BY meeting_id
    """).fetchall()
    return {r["meeting_id"]: {"total": r["total"], "active": r["active"]}
            for r in rows}


# ── Responsibles ────────────────────────────────────────────────────────

def get_all_responsibles(conn: sqlite3.Connection) -> list[dict]:
    """Return all unique responsibles: from the responsibles table + any in tasks."""
    known = {r["name"]: r["comment"]
             for r in conn.execute("SELECT name, comment FROM responsibles").fetchall()}
    in_tasks = conn.execute(
        "SELECT DISTINCT responsible FROM tasks WHERE responsible != ''"
    ).fetchall()
    for r in in_tasks:
        if r["responsible"] not in known:
            known[r["responsible"]] = ""
    return [{"name": n, "comment": c} for n, c in sorted(known.items())]


def rename_responsible(conn: sqlite3.Connection, old_name: str, new_name: str):
    conn.execute("UPDATE tasks SET responsible = ? WHERE responsible = ?",
                 (new_name, old_name))
    conn.execute("DELETE FROM responsibles WHERE name = ?", (old_name,))
    conn.execute("INSERT OR IGNORE INTO responsibles (name) VALUES (?)", (new_name,))
    conn.commit()


def set_responsible_comment(conn: sqlite3.Connection, name: str, comment: str):
    conn.execute(
        "INSERT INTO responsibles (name, comment) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET comment = excluded.comment",
        (name, comment))
    conn.commit()
