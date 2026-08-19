# Editable meeting title in the Activities tab

## Problem

The Activities tab lists meetings under each activity (`.meet-row`), showing each
meeting's `topic`. This value comes from the `meetings.topic` column in the SQLite
database, which is written once when a meeting row is first created and never
updated afterward. The Recordings tab already supports renaming a meeting (via
`RecordingSession.title` in `meta.json`, edited through `set_title`), but that
rename does not propagate to `meetings.topic`, so the Activities tab can show a
stale title. There is also no way to edit a meeting's title from the Activities
tab at all.

## Goals

- Let the user edit a meeting's title inline from the Activities tab.
- Fix the sync gap so `meetings.topic` and `RecordingSession.title` never diverge,
  regardless of which tab the edit originates from.

## Non-goals

- Editing meeting topic from the classic Tkinter UI (`popup.py`) — stays read-only there.
- Auto-generating titles for untitled meetings.

## Design

### Frontend — `meetingscribe/ui/web/index.html`

- Add a hover-revealed `.actions` div with a pencil button to each `.meet-row`,
  placed between `.meet-topic` and `.meet-date`, mirroring the existing pattern
  used by `.act-row` and `.row`.
- Add `editMeetingTopic(ev, folder)`:
  - `ev.stopPropagation()` so the click doesn't also trigger `meetClick` (which
    opens the meeting).
  - Locate the sibling `.meet-topic` span via `ev.currentTarget.closest('.meet-row')`.
  - Replace its contents with a text `<input>` pre-filled with the current topic
    text, focused and selected.
  - On Enter or blur: read the trimmed value, call `api("set_title", folder, title)`
    (existing endpoint — no new backend API), then call `renderActivities()` to
    refresh the list from fresh server data.
  - On Escape: cancel without saving, re-render.
- CSS: add `.meet-row:hover .actions { visibility: visible; }`, and extend the
  existing `.row-title input` rule to also cover `.meet-topic input` (same visual
  treatment).

### Backend sync fix — `meetingscribe/db.py` + `meetingscribe/ui/app.py`

- Add `db.update_meeting_topic(conn, folder, topic)`:
  `UPDATE meetings SET topic = ? WHERE folder = ?` — no-op if no matching row.
- In `app.py`'s `_handle_title_changed` (already wired to the `set_title` bridge
  call), after `self.session_mgr.update_title(folder, title)`, also open a db
  connection and call `db.update_meeting_topic(conn, folder_key, title)`, wrapped
  in try/except with logging and connection close — following the same pattern
  already used in `_handle_delete` (app.py:747-753).
- Net effect: the single `set_title` code path now keeps `meta.json`'s
  `RecordingSession.title` and the db's `meetings.topic` in sync no matter which
  tab (Recordings or Activities) triggered the rename.

## Data flow

1. User clicks the pencil icon on a `.meet-row` in the Activities tab.
2. `editMeetingTopic` swaps the topic span for an input.
3. On save, JS calls `api("set_title", folder, title)` →
   `_JsApi.set_title` (web_popup.py) → `on_title_changed` callback →
   `App._handle_title_changed` (app.py) → updates `meta.json` via
   `session_mgr.update_title` AND updates `meetings.topic` via
   `db.update_meeting_topic`.
4. JS calls `renderActivities()`, which re-fetches `get_activities` from the
   backend and re-renders with the updated topic.

## Testing

Manual only (no automated UI tests in this project):
- Rename a meeting from the Activities tab; confirm the new title shows there
  and also appears updated in the Recordings tab.
- Rename a meeting from the Recordings tab; confirm the Activities tab now shows
  the updated title too (previously it would not).
- Rename to an empty string; confirm it falls back to displaying
  "(без темы)" in the Activities tab, consistent with existing empty-topic display.
