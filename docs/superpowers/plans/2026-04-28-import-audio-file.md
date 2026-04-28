# Import External Audio File — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to import an external audio file for transcription via a file dialog and metadata dialog.

**Architecture:** Add an "Добавить запись" button to the recordings list header. Clicking it opens a file picker, then a small dialog for language/type selection. The file is copied into the standard recording folder structure with a meta.json, and appears in the session list with IMPORTED status. The existing transcribe flow handles the rest.

**Tech Stack:** Python, tkinter (filedialog, Toplevel), shutil (file copy), existing session/storage/pipeline modules.

---

### File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `meetingscribe/session.py` | Modify | Add `IMPORTED` status to `SessionStatus` enum; update `_load_existing` to detect imported files; add `IMPORTED` to status resolution |
| `meetingscribe/ui/popup.py` | Modify | Add "Добавить запись" button; add import dialog (`Toplevel`); add `on_import` callback; enable "Транскрибировать" for `IMPORTED` status |
| `meetingscribe/ui/app.py` | Modify | Add `_handle_import` method; wire `on_import` callback to `PopupWindow` |
| `tests/test_session.py` | Modify | Add tests for `IMPORTED` status |

---

### Task 1: Add IMPORTED status to SessionStatus

**Files:**
- Modify: `meetingscribe/session.py:10-16`
- Modify: `meetingscribe/session.py:80-87` (`_load_existing` status resolution)
- Test: `tests/test_session.py`

- [ ] **Step 1: Write test for IMPORTED status existence**

Add to `tests/test_session.py`:

```python
def test_imported_status_exists():
    assert SessionStatus.IMPORTED.value == "Загружено"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /c/AI/MeetingScribe && python -m pytest tests/test_session.py::test_imported_status_exists -v`
Expected: FAIL — `AttributeError: 'IMPORTED' is not a member of 'SessionStatus'`

- [ ] **Step 3: Add IMPORTED to SessionStatus enum**

In `meetingscribe/session.py`, add after `ERROR = "Ошибка"` (line 16):

```python
class SessionStatus(Enum):
    RECORDING = "Записываю..."
    TRANSCRIBING = "Транскрибирую..."
    READY = "Готово к саммари"
    SUMMARIZING = "Генерирую саммари..."
    DONE = "Готово"
    ERROR = "Ошибка"
    IMPORTED = "Загружено"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /c/AI/MeetingScribe && python -m pytest tests/test_session.py::test_imported_status_exists -v`
Expected: PASS

- [ ] **Step 5: Write test for _load_existing with imported file (has meta.json, has audio, no transcript)**

Add to `tests/test_session.py`:

```python
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
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /c/AI/MeetingScribe && python -m pytest tests/test_session.py::test_session_manager_loads_imported -v`
Expected: FAIL — status is `ERROR` instead of `IMPORTED`

- [ ] **Step 7: Update _load_existing to resolve IMPORTED status**

In `meetingscribe/session.py`, in `_load_existing` method, replace the status resolution block (lines 80-87):

```python
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
```

Also update the orphan audio scan (lines 104-106) to accept more extensions:

```python
        for audio_file in self.recordings_dir.rglob("audio.*"):
            if audio_file.suffix not in (".wav", ".ogg", ".mp3", ".m4a", ".flac"):
                continue
```

- [ ] **Step 8: Run tests to verify all pass**

Run: `cd /c/AI/MeetingScribe && python -m pytest tests/test_session.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add meetingscribe/session.py tests/test_session.py
git commit -m "feat: add IMPORTED status for externally loaded audio files"
```

---

### Task 2: Add import dialog and button to PopupWindow

**Files:**
- Modify: `meetingscribe/ui/popup.py:1-2` (add filedialog import)
- Modify: `meetingscribe/ui/popup.py:21-66` (add on_import callback to __init__)
- Modify: `meetingscribe/ui/popup.py:174-178` (add button to list header)
- Modify: `meetingscribe/ui/popup.py:400-414` (enable transcribe for IMPORTED)
- Add new methods: `_import_recording`, `_show_import_dialog`

- [ ] **Step 1: Add filedialog import**

In `meetingscribe/ui/popup.py`, change line 1:

```python
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
```

- [ ] **Step 2: Add on_import callback to __init__**

In `PopupWindow.__init__`, add parameter after `on_reload`:

```python
        on_import: Callable[[str, str, str], None] | None = None,
```

And store it:

```python
        self._on_import = on_import
```

The callback signature: `on_import(file_path: str, meeting_type: str, language: str)`.

- [ ] **Step 3: Add "Добавить запись" button to list header**

In the `show()` method, after `ttk.Label(list_header, ...)` and before the "Обновить" button (around line 177-178), add:

```python
        ttk.Button(list_header, text="Добавить запись", command=self._import_recording, width=16).pack(side=tk.RIGHT, padx=(0, 5))
```

So the header becomes:
```python
        # Recordings list header
        list_header = ttk.Frame(frame)
        list_header.pack(fill=tk.X)
        ttk.Label(list_header, text="Записи:", font=("", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(list_header, text="Обновить", command=self._reload_list, width=10).pack(side=tk.RIGHT)
        ttk.Button(list_header, text="Добавить запись", command=self._import_recording, width=16).pack(side=tk.RIGHT, padx=(0, 5))
```

- [ ] **Step 4: Implement _import_recording method**

Add to `PopupWindow` class, in the "Reload" section area (after `_reload_list`):

```python
    # --- Import ---

    def _import_recording(self):
        file_path = filedialog.askopenfilename(
            parent=self._root,
            title="Выберите аудиофайл",
            filetypes=[
                ("Аудиофайлы", "*.wav *.ogg *.mp3 *.m4a *.flac"),
                ("Все файлы", "*.*"),
            ],
        )
        if not file_path:
            return
        self._show_import_dialog(file_path)
```

- [ ] **Step 5: Implement _show_import_dialog method**

Add right after `_import_recording`:

```python
    def _show_import_dialog(self, file_path: str):
        dialog = tk.Toplevel(self._root)
        dialog.title("Параметры записи")
        dialog.geometry("300x180")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.transient(self._root)

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Тип записи:").pack(anchor=tk.W, pady=(0, 3))
        type_var = tk.StringVar(value=MEETING_TYPES[0][0])
        ttk.Combobox(
            frame, textvariable=type_var,
            values=[t[0] for t in MEETING_TYPES],
            state="readonly", width=25,
        ).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(frame, text="Язык записи:").pack(anchor=tk.W, pady=(0, 3))
        lang_var = tk.StringVar(value=LANGUAGES[0][0])
        ttk.Combobox(
            frame, textvariable=lang_var,
            values=[l[0] for l in LANGUAGES],
            state="readonly", width=25,
        ).pack(fill=tk.X, pady=(0, 15))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        def on_ok():
            type_code = next(code for name, code in MEETING_TYPES if name == type_var.get())
            lang_code = next(code for name, code in LANGUAGES if name == lang_var.get())
            dialog.destroy()
            if self._on_import:
                self._on_import(file_path, type_code, lang_code)

        ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy, width=10).pack(side=tk.RIGHT)
```

- [ ] **Step 6: Enable transcribe button for IMPORTED status**

In `_on_selection_changed`, change the `can_transcribe` line (line 407):

```python
        can_transcribe = status_text in (
            SessionStatus.ERROR.value,
            SessionStatus.IMPORTED.value,
        )
```

- [ ] **Step 7: Run existing tests to verify nothing is broken**

Run: `cd /c/AI/MeetingScribe && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add meetingscribe/ui/popup.py
git commit -m "feat: add import recording button and dialog to popup UI"
```

---

### Task 3: Implement _handle_import in App

**Files:**
- Modify: `meetingscribe/ui/app.py:1-5` (add shutil import)
- Modify: `meetingscribe/ui/app.py:36-54` (wire on_import callback)
- Add method: `_handle_import`
- Modify: `meetingscribe/ui/app.py:184-195` (update _handle_transcribe to find any audio extension)

- [ ] **Step 1: Add shutil import to app.py**

In `meetingscribe/ui/app.py`, add to imports:

```python
import shutil
```

- [ ] **Step 2: Wire on_import callback in PopupWindow construction**

In `App.__init__`, add `on_import=self._handle_import` to the PopupWindow constructor:

```python
        self.popup = PopupWindow(
            on_start=self._handle_start,
            on_stop=self._handle_stop,
            on_summarize=self._handle_summarize,
            on_transcribe=self._handle_transcribe,
            on_delete=self._handle_delete,
            on_quit=self._quit,
            on_open_folder=self._handle_open_folder,
            on_reload=self._handle_reload,
            on_import=self._handle_import,
            on_mic_changed=self._handle_mic_changed,
            on_mic_test_start=self._handle_mic_test_start,
            on_mic_test_stop=self._handle_mic_test_stop,
            on_gemini_key_changed=self._handle_gemini_key_changed,
            on_claude_key_changed=self._handle_claude_key_changed,
            initial_gemini_key=config.gemini_api_key,
            initial_claude_key=config.anthropic_api_key,
            mic_devices=mic_devices,
            initial_mic_index=config.mic_device_index,
        )
```

- [ ] **Step 3: Implement _handle_import method**

Add to `App` class, after the `_handle_stop` / recording section and before the manual transcription section:

```python
    # --- Import ---

    def _handle_import(self, file_path: str, meeting_type: str, language: str):
        src = Path(file_path)
        now = datetime.now()

        paths = create_recording_paths(
            self.config.recordings_dir, meeting_type, now
        )

        dest = paths.folder / f"audio{src.suffix}"
        shutil.copy2(file_path, dest)

        meta = {
            "date": now.isoformat(),
            "duration_seconds": 0,
            "language": language,
            "meeting_type": meeting_type,
            "audio_mode": "import",
            "source": "import",
            "original_filename": src.name,
            "has_summary": False,
            "has_ogg": False,
        }
        paths.meta.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        self.session_mgr.create_session(
            paths.folder, now, meeting_type, language, audio_mode="import"
        )
        self.session_mgr.update_status(paths.folder, SessionStatus.IMPORTED)
        self._refresh_list()
```

- [ ] **Step 4: Add json import to app.py**

In `meetingscribe/ui/app.py`, add to imports:

```python
import json
```

- [ ] **Step 5: Update _handle_transcribe to find imported audio files**

In `_handle_transcribe`, replace the audio file lookup (lines 190-194):

```python
        audio_path = None
        for ext in (".wav", ".ogg", ".mp3", ".m4a", ".flac"):
            candidate = folder / f"audio{ext}"
            if candidate.exists():
                audio_path = candidate
                break
        if audio_path is None:
            self.popup.set_status("Ошибка: аудиофайл не найден")
            return
```

- [ ] **Step 6: Run all tests**

Run: `cd /c/AI/MeetingScribe && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add meetingscribe/ui/app.py
git commit -m "feat: implement import handler — copy file, create session, find any audio format"
```

---

### Task 4: Manual smoke test

- [ ] **Step 1: Launch the app**

Run: `cd /c/AI/MeetingScribe && python -m meetingscribe`

- [ ] **Step 2: Test the import flow**

1. Click "Добавить запись" button in the recordings list header
2. Select any audio file (.wav, .ogg, .mp3, etc.) from file explorer
3. Verify the import dialog appears with type and language dropdowns
4. Select type and language, click OK
5. Verify new entry appears in the list with status "Загружено"
6. Verify the recording folder was created in `recordings/` with the audio file and meta.json
7. Select the imported entry and verify "Транскрибировать" button is enabled
8. Click "Транскрибировать" and verify transcription starts

- [ ] **Step 3: Test cancel flows**

1. Click "Добавить запись", then cancel the file picker — verify nothing happens
2. Click "Добавить запись", select a file, then click "Отмена" in the dialog — verify nothing happens

- [ ] **Step 4: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: address issues found during smoke test"
```
