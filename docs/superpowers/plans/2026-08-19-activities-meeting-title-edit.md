# Editable Meeting Title in Activities Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user edit a meeting's title inline from the Activities tab, and fix the existing gap where `meetings.topic` (db) goes stale relative to `RecordingSession.title` (meta.json).

**Architecture:** Add a pure `db.update_meeting_topic()` function (TDD'd against an in-memory sqlite connection), wire it into the existing `set_title` bridge call path in `app.py` so both title stores update together, then add a pencil-button + inline `<input>` editor to `.meet-row` in the Activities tab that reuses the existing `set_title` JS API call.

**Tech Stack:** Python (sqlite3, pywebview bridge), vanilla JS/HTML/CSS (single-file `index.html`), pytest.

---

### Task 1: Add `db.update_meeting_topic` with tests

**Files:**
- Create: `tests/test_db.py`
- Modify: `meetingscribe/db.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_db.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — `AttributeError: module 'meetingscribe.db' has no attribute 'update_meeting_topic'`

- [ ] **Step 3: Implement `update_meeting_topic`**

In `meetingscribe/db.py`, add this function directly after `delete_meeting_by_folder` (currently at line 209-211):

```python
def update_meeting_topic(conn: sqlite3.Connection, folder: str, topic: str):
    conn.execute("UPDATE meetings SET topic = ? WHERE folder = ?", (topic, folder))
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/test_db.py meetingscribe/db.py
git commit -m "feat: add db.update_meeting_topic for syncing meeting titles"
```

---

### Task 2: Sync `meetings.topic` when a title is renamed

**Files:**
- Modify: `meetingscribe/ui/app.py:153-155`

- [ ] **Step 1: Update `_handle_title_changed`**

Current code (`meetingscribe/ui/app.py:151-155`):

```python
    # --- Title ---

    def _handle_title_changed(self, folder_key: str, title: str):
        folder = Path(folder_key)
        self.session_mgr.update_title(folder, title)
```

Replace with:

```python
    # --- Title ---

    def _handle_title_changed(self, folder_key: str, title: str):
        folder = Path(folder_key)
        self.session_mgr.update_title(folder, title)
        try:
            from meetingscribe import db
            conn = db.get_connection()
            db.update_meeting_topic(conn, folder_key, title)
            conn.close()
        except Exception:
            logger.exception("Не удалось синхронизировать название встречи в БД")
```

This follows the exact same open-connection/use/close/log-on-error pattern already
used in `_handle_delete` (`meetingscribe/ui/app.py:747-753`).

- [ ] **Step 2: Manually verify**

This handler has no existing unit-test scaffold (App requires audio/tray/pipeline
dependencies not mocked anywhere in this repo — consistent with there being no
`test_app.py`). Verify manually instead:

Run: `python -m py_compile meetingscribe/ui/app.py`
Expected: no output (syntax OK)

Full end-to-end verification happens in Task 4 (manual browser test) after the
frontend piece is wired up.

- [ ] **Step 3: Commit**

```bash
git add meetingscribe/ui/app.py
git commit -m "feat: sync meetings.topic in db whenever a meeting title changes"
```

---

### Task 3: Add inline title editing to the Activities tab

**Files:**
- Modify: `meetingscribe/ui/web/index.html`

- [ ] **Step 1: Add CSS for the meeting-row action button and topic input**

In `meetingscribe/ui/web/index.html`, find this existing rule (around line 177):

```css
  .row-title input {
    width: 100%;
    background: #3c3c3c;
    border: 1px solid var(--accent);
    border-radius: 2px;
    color: var(--text-bright);
    font: inherit;
    padding: 1px 5px;
```

Read a few more lines to get the full rule block (it continues to a closing `}`),
then change its selector line from:

```css
  .row-title input {
```

to:

```css
  .row-title input, .meet-topic input {
```

Next, find the `.meet-row` block (around line 257-267):

```css
  .meet-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 16px 5px 42px;
    cursor: pointer;
    font-size: 12.5px;
  }
  .meet-row:hover { background: var(--bg-hover); }
  .meet-topic { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meet-date { color: var(--text-dim); font-size: 12px; flex-shrink: 0; }
```

Add a hover rule for the actions div right after the existing `.meet-row:hover` rule:

```css
  .meet-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 16px 5px 42px;
    cursor: pointer;
    font-size: 12.5px;
  }
  .meet-row:hover { background: var(--bg-hover); }
  .meet-row:hover .actions { visibility: visible; }
  .meet-topic { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .meet-date { color: var(--text-dim); font-size: 12px; flex-shrink: 0; }
```

- [ ] **Step 2: Add the pencil button to each meeting row**

Find the meeting-row rendering code inside `renderActivities()` (around line 1328-1334):

```js
        html += a.meetings.map(m => {
          const f = esc(m.folder || "").replace(/\\/g, "\\\\");
          return `<div class="meet-row" onclick="meetClick('${f}')">
            <span class="meet-topic">${esc(m.topic || "(без темы)")}</span>
            <span class="meet-date">${esc(m.date)}${m.time ? " " + esc(m.time) : ""}</span>
          </div>`;
        }).join("");
```

Replace with:

```js
        html += a.meetings.map(m => {
          const f = esc(m.folder || "").replace(/\\/g, "\\\\");
          return `<div class="meet-row" onclick="meetClick('${f}')">
            <span class="meet-topic">${esc(m.topic || "(без темы)")}</span>
            <div class="actions">
              <button class="act" title="Переименовать" onclick="editMeetingTopic(event,'${f}')">${ico("i-pencil", 14)}</button>
            </div>
            <span class="meet-date">${esc(m.date)}${m.time ? " " + esc(m.time) : ""}</span>
          </div>`;
        }).join("");
```

- [ ] **Step 3: Add the `editMeetingTopic` function**

Find the `editTitle` function (around line 1087-1112):

```js
/* ── Переименование ── */
function editTitle(ev, folder) {
  ev.stopPropagation();
  const span = document.querySelector(`.row-title[data-tfolder="${CSS.escape(folder)}"]`);
  if (!span) return;
  const s = sessions.find(x => x.folder === folder);
  editingFolder = folder;
  span.innerHTML = `<input type="text" value="${esc(s.title)}" onclick="event.stopPropagation()">`;
  const input = span.querySelector("input");
  input.focus();
  input.select();
  const done = save => {
    editingFolder = null;
    if (save) {
      const title = input.value.trim();
      api("set_title", folder, title);
      if (s) s.title = title || "Без названия";
    }
    render();
  };
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") done(true);
    if (e.key === "Escape") done(false);
  });
  input.addEventListener("blur", () => done(true));
}
```

Add a new function immediately after it (still inside the same `/* ── Переименование ── */` section):

```js
function editMeetingTopic(ev, folder) {
  ev.stopPropagation();
  const row = ev.currentTarget.closest(".meet-row");
  const span = row ? row.querySelector(".meet-topic") : null;
  if (!span) return;
  const current = span.textContent === "(без темы)" ? "" : span.textContent;
  span.innerHTML = `<input type="text" value="${esc(current)}" onclick="event.stopPropagation()">`;
  const input = span.querySelector("input");
  input.focus();
  input.select();
  const done = save => {
    if (save) {
      const topic = input.value.trim();
      api("set_title", folder, topic);
    }
    renderActivities();
  };
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") done(true);
    if (e.key === "Escape") done(false);
  });
  input.addEventListener("blur", () => done(true));
}
```

- [ ] **Step 4: Commit**

```bash
git add meetingscribe/ui/web/index.html
git commit -m "feat: allow editing meeting title inline from the Activities tab"
```

---

### Task 4: Manual end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Launch the app**

Run the app per its normal launch path (e.g. `python -m meetingscribe` or
`MeetingScribe.bat`, whichever the project normally uses) so the web UI opens.

- [ ] **Step 2: Verify editing from the Activities tab**

1. Open the Activities tab, expand an activity that has at least one meeting.
2. Hover a meeting row — confirm a pencil icon appears.
3. Click the pencil icon — confirm the topic text turns into an editable input
   pre-filled with the current title.
4. Type a new title and press Enter — confirm the row re-renders showing the new
   title (not the old one), and no console error appears.

- [ ] **Step 3: Verify cross-tab sync**

1. Switch to the Recordings tab, find the same meeting (matching folder/date),
   confirm its title also shows the new value.
2. In the Recordings tab, rename the same meeting again via its existing pencil
   button.
3. Switch back to the Activities tab and re-expand the activity — confirm the
   title shown there now matches the Recordings-tab rename (this is the
   previously-broken sync path).

- [ ] **Step 4: Verify empty-title fallback**

1. Edit a meeting title in the Activities tab, clear the input completely, press
   Enter.
2. Confirm the row displays "(без темы)" after re-render, consistent with the
   existing empty-topic display convention.

- [ ] **Step 5: Verify Escape cancels**

1. Click the pencil icon on a meeting row, type something, press Escape.
2. Confirm the row reverts to showing the original (unedited) title and no API
   call was made (no change persisted — re-check after switching tabs and back).

No commit for this task — it's verification of Tasks 1-3, which are already
committed.
