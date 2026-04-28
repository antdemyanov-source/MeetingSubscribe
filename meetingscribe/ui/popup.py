import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from meetingscribe.session import RecordingSession, SessionStatus


LANGUAGES = [
    ("Русский", "ru"),
    ("English", "en"),
    ("Авто", "auto"),
]

MEETING_TYPES = [
    ("Рабочая встреча", "work"),
    ("Урок английского", "english"),
    ("Личная", "therapy"),
]


class PopupWindow:
    def __init__(
        self,
        on_start: Callable[[str, str, bool], None],
        on_stop: Callable[[], None],
        on_summarize: Callable[[str], None],
        on_open_folder: Callable[[str], None],
        on_transcribe: Callable[[str], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        on_reload: Callable[[], None] | None = None,
        on_import: Callable[[str, str, str], None] | None = None,
        on_mic_changed: Callable[[int], None] | None = None,
        on_mic_test_start: Callable[[int], None] | None = None,
        on_mic_test_stop: Callable[[], None] | None = None,
        on_gemini_key_changed: Callable[[str], None] | None = None,
        on_claude_key_changed: Callable[[str], None] | None = None,
        initial_gemini_key: str = "",
        initial_claude_key: str = "",
        mic_devices: list[dict] | None = None,
        initial_mic_index: int = -1,
    ):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_summarize = on_summarize
        self._on_transcribe = on_transcribe
        self._on_delete = on_delete
        self._on_quit = on_quit
        self._on_open_folder = on_open_folder
        self._on_reload = on_reload
        self._on_import = on_import
        self._on_mic_changed = on_mic_changed
        self._on_mic_test_start = on_mic_test_start
        self._on_mic_test_stop = on_mic_test_stop
        self._on_gemini_key_changed = on_gemini_key_changed
        self._on_claude_key_changed = on_claude_key_changed
        self._initial_gemini_key = initial_gemini_key
        self._initial_claude_key = initial_claude_key
        self._mic_devices = mic_devices or []
        self._initial_mic_index = initial_mic_index
        self._root: tk.Tk | None = None
        self._recording = False
        self._testing_mic = False
        self._elapsed = 0
        self._timer_id = None
        self._level_value = 0.0
        self._tree: ttk.Treeview | None = None
        self._folder_keys: dict[str, str] = {}

    def show(self):
        if self._root is not None:
            self._root.deiconify()
            self._root.lift()
            return

        self._root = tk.Tk()
        self._root.title("MeetingScribe")
        self._root.geometry("520x640")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        frame = ttk.Frame(self._root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Language + Type row
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(controls, text="Язык:").pack(side=tk.LEFT, padx=(0, 5))
        self._lang_var = tk.StringVar(value=LANGUAGES[0][0])
        self._lang_combo = ttk.Combobox(
            controls,
            textvariable=self._lang_var,
            values=[l[0] for l in LANGUAGES],
            state="readonly",
            width=12,
        )
        self._lang_combo.pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(controls, text="Тип:").pack(side=tk.LEFT, padx=(0, 5))
        self._type_var = tk.StringVar(value=MEETING_TYPES[0][0])
        self._type_combo = ttk.Combobox(
            controls,
            textvariable=self._type_var,
            values=[t[0] for t in MEETING_TYPES],
            state="readonly",
            width=18,
        )
        self._type_combo.pack(side=tk.LEFT)

        # Microphone selection row
        mic_row = ttk.Frame(frame)
        mic_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(mic_row, text="Микрофон:").pack(side=tk.LEFT, padx=(0, 5))

        mic_names = [d["name"] for d in self._mic_devices]
        preselect = ""
        if mic_names:
            preselect = mic_names[0]
            for d in self._mic_devices:
                if d["index"] == self._initial_mic_index:
                    preselect = d["name"]
                    break

        self._mic_var = tk.StringVar(value=preselect)
        self._mic_combo = ttk.Combobox(
            mic_row,
            textvariable=self._mic_var,
            values=mic_names,
            state="readonly",
            width=38,
        )
        self._mic_combo.pack(side=tk.LEFT, padx=(0, 5))
        self._mic_combo.bind("<<ComboboxSelected>>", self._on_mic_selected)

        self._test_btn_var = tk.StringVar(value="Проверить")
        self._test_btn = ttk.Button(
            mic_row, textvariable=self._test_btn_var, command=self._toggle_mic_test, width=10
        )
        self._test_btn.pack(side=tk.LEFT)

        # Recording buttons row
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=5)

        self._btn_var = tk.StringVar(value="Начать запись")
        self._btn = ttk.Button(
            btn_frame, textvariable=self._btn_var, command=self._toggle_recording
        )
        self._btn.pack(side=tk.LEFT, padx=(0, 10), ipadx=10, ipady=3)

        self._mic_btn = ttk.Button(
            btn_frame, text="Включить микрофон", command=self._start_mic_only
        )
        self._mic_btn.pack(side=tk.LEFT, ipadx=10, ipady=3)

        # Level bar
        level_frame = ttk.Frame(frame)
        level_frame.pack(fill=tk.X, pady=3)
        ttk.Label(level_frame, text="Уровень:").pack(side=tk.LEFT, padx=(0, 5))
        self._level_bar = ttk.Progressbar(
            level_frame, orient=tk.HORIZONTAL, length=200, mode="determinate", maximum=100
        )
        self._level_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Status
        self._status_var = tk.StringVar(value="Готов к записи")
        self._status_label = ttk.Label(
            frame, textvariable=self._status_var, foreground="gray"
        )
        self._status_label.pack(fill=tk.X, pady=3)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # Recordings list header
        list_header = ttk.Frame(frame)
        list_header.pack(fill=tk.X)
        ttk.Label(list_header, text="Записи:", font=("", 9, "bold")).pack(side=tk.LEFT)
        ttk.Button(list_header, text="Обновить", command=self._reload_list, width=10).pack(side=tk.RIGHT)
        ttk.Button(list_header, text="Добавить запись", command=self._import_recording, width=16).pack(side=tk.RIGHT, padx=(0, 5))

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(3, 5))

        columns = ("date", "duration", "type", "status")
        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=8, selectmode="browse"
        )
        self._tree.heading("date", text="Дата")
        self._tree.heading("duration", text="Длительность")
        self._tree.heading("type", text="Тип")
        self._tree.heading("status", text="Статус")

        self._tree.column("date", width=130, minwidth=100)
        self._tree.column("duration", width=90, minwidth=70)
        self._tree.column("type", width=100, minwidth=80)
        self._tree.column("status", width=150, minwidth=100)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<<TreeviewSelect>>", self._on_selection_changed)

        # Action buttons
        action_frame = ttk.Frame(frame)
        action_frame.pack(fill=tk.X, pady=3)

        self._transcribe_btn = ttk.Button(
            action_frame, text="Транскрибировать", command=self._transcribe_selected, state="disabled"
        )
        self._transcribe_btn.pack(side=tk.LEFT, padx=(0, 10), ipadx=5)

        self._summary_btn = ttk.Button(
            action_frame, text="Создать саммари", command=self._summarize_selected, state="disabled"
        )
        self._summary_btn.pack(side=tk.LEFT, padx=(0, 10), ipadx=5)

        self._folder_btn = ttk.Button(
            action_frame, text="Открыть папку", command=self._open_selected_folder, state="disabled"
        )
        self._folder_btn.pack(side=tk.LEFT, padx=(0, 10), ipadx=5)

        self._delete_btn = ttk.Button(
            action_frame, text="Удалить", command=self._delete_selected, state="disabled"
        )
        self._delete_btn.pack(side=tk.LEFT, ipadx=5)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # LLM indicator
        self._llm_var = tk.StringVar()
        self._llm_label = ttk.Label(frame, textvariable=self._llm_var, foreground="blue")
        self._llm_label.pack(fill=tk.X, pady=2)
        self._update_llm_indicator()

        # Gemini Key row
        gemini_frame = ttk.Frame(frame)
        gemini_frame.pack(fill=tk.X, pady=2)
        ttk.Label(gemini_frame, text="Gemini Key:").pack(side=tk.LEFT, padx=(0, 5))
        self._gemini_key_var = tk.StringVar(value=self._initial_gemini_key)
        ttk.Entry(gemini_frame, textvariable=self._gemini_key_var, width=22, show="*").pack(side=tk.LEFT)
        ttk.Button(gemini_frame, text="Сохранить", command=self._save_gemini_key, width=10).pack(side=tk.LEFT, padx=(5, 0))

        # Claude Key row
        claude_frame = ttk.Frame(frame)
        claude_frame.pack(fill=tk.X, pady=2)
        ttk.Label(claude_frame, text="Claude Key:").pack(side=tk.LEFT, padx=(0, 5))
        self._claude_key_var = tk.StringVar(value=self._initial_claude_key)
        ttk.Entry(claude_frame, textvariable=self._claude_key_var, width=22, show="*").pack(side=tk.LEFT)
        ttk.Button(claude_frame, text="Сохранить", command=self._save_claude_key, width=10).pack(side=tk.LEFT, padx=(5, 0))

    # --- Reload ---

    def _reload_list(self):
        if self._on_reload:
            self._on_reload()

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

    # --- Microphone selection & test ---

    def _get_selected_mic_index(self) -> int | None:
        name = self._mic_var.get()
        for d in self._mic_devices:
            if d["name"] == name:
                return d["index"]
        return None

    def _on_mic_selected(self, event):
        idx = self._get_selected_mic_index()
        if idx is not None and self._on_mic_changed:
            self._on_mic_changed(idx)

    def _toggle_mic_test(self):
        if not self._testing_mic:
            idx = self._get_selected_mic_index()
            if idx is None:
                return
            if self._on_mic_test_start:
                self._on_mic_test_start(idx)
            self._testing_mic = True
            self._test_btn_var.set("Остановить")
            self._status_var.set("Проверка микрофона...")
        else:
            if self._on_mic_test_stop:
                self._on_mic_test_stop()
            self._testing_mic = False
            self._test_btn_var.set("Проверить")
            self._status_var.set("Готов к записи")
            self._level_bar["value"] = 0

    # --- API Keys ---

    def _update_llm_indicator(self):
        if self._initial_claude_key:
            self._llm_var.set("LLM: Claude API")
        elif self._initial_gemini_key:
            self._llm_var.set("LLM: Gemini Flash (бесплатно)")
        else:
            self._llm_var.set("LLM: не настроен")

    def _save_gemini_key(self):
        key = self._gemini_key_var.get().strip()
        self._initial_gemini_key = key
        self._update_llm_indicator()
        if self._on_gemini_key_changed:
            self._on_gemini_key_changed(key)

    def _save_claude_key(self):
        key = self._claude_key_var.get().strip()
        self._initial_claude_key = key
        self._update_llm_indicator()
        if self._on_claude_key_changed:
            self._on_claude_key_changed(key)

    # --- Window ---

    def _on_close(self):
        if self._on_quit:
            self._on_quit()
        elif self._root:
            self._root.withdraw()

    # --- Recording ---

    def _toggle_recording(self):
        if not self._recording:
            self._start_recording(mic_only=False)
        else:
            self._stop_recording()

    def _start_mic_only(self):
        if not self._recording:
            self._start_recording(mic_only=True)

    def _start_recording(self, mic_only: bool):
        if self._testing_mic:
            self._toggle_mic_test()

        lang_name = self._lang_var.get()
        lang_code = next(code for name, code in LANGUAGES if name == lang_name)
        type_name = self._type_var.get()
        type_code = next(code for name, code in MEETING_TYPES if name == type_name)

        self._recording = True
        self._elapsed = 0
        self._btn_var.set("Остановить")
        self._mic_btn.config(state="disabled")
        self._test_btn.config(state="disabled")
        self._mic_combo.config(state="disabled")
        self._lang_combo.config(state="disabled")
        self._type_combo.config(state="disabled")

        self._on_start(lang_code, type_code, mic_only)

        if self._recording:
            self._update_timer()

    def _stop_recording(self):
        self._recording = False
        if self._timer_id:
            self._root.after_cancel(self._timer_id)
            self._timer_id = None
        self._on_stop()
        self._reset_controls()

    def _reset_controls(self):
        self._btn_var.set("Начать запись")
        self._btn.config(state="normal")
        self._mic_btn.config(state="normal")
        self._test_btn.config(state="normal")
        self._mic_combo.config(state="readonly")
        self._lang_combo.config(state="readonly")
        self._type_combo.config(state="readonly")
        self._level_bar["value"] = 0
        self._status_var.set("Готов к записи")

    def _update_timer(self):
        if not self._recording:
            return
        h = self._elapsed // 3600
        m = (self._elapsed % 3600) // 60
        s = self._elapsed % 60
        self._status_var.set(f"Записываю... {h:02d}:{m:02d}:{s:02d}")
        self._elapsed += 1
        self._timer_id = self._root.after(1000, self._update_timer)

    # --- Recordings list ---

    def _on_selection_changed(self, event):
        selected = self._tree.selection()
        if not selected:
            self._transcribe_btn.config(state="disabled")
            self._summary_btn.config(state="disabled")
            self._folder_btn.config(state="disabled")
            self._delete_btn.config(state="disabled")
            return

        iid = selected[0]
        self._folder_btn.config(state="normal")

        values = self._tree.item(iid, "values")
        status_text = values[3] if len(values) > 3 else ""
        is_active = status_text in (
            SessionStatus.RECORDING.value,
            SessionStatus.TRANSCRIBING.value,
            SessionStatus.SUMMARIZING.value,
        )
        can_transcribe = status_text in (
            SessionStatus.ERROR.value,
            SessionStatus.IMPORTED.value,
        )
        can_summarize = status_text in (
            SessionStatus.READY.value,
            SessionStatus.DONE.value,
        )
        self._transcribe_btn.config(state="normal" if can_transcribe else "disabled")
        self._summary_btn.config(state="normal" if can_summarize else "disabled")
        self._delete_btn.config(state="normal" if not is_active else "disabled")

    def _transcribe_selected(self):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if folder_key and self._on_transcribe:
            self._on_transcribe(folder_key)

    def _summarize_selected(self):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if folder_key:
            self._on_summarize(folder_key)

    def _delete_selected(self):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if not folder_key:
            return
        confirmed = messagebox.askyesno(
            "Удаление записи",
            "Вы уверены, что хотите удалить эту запись?\n"
            "Папка со всеми файлами будет перемещена в корзину.",
            parent=self._root,
        )
        if confirmed and self._on_delete:
            self._on_delete(folder_key)

    def _open_selected_folder(self):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if folder_key:
            self._on_open_folder(folder_key)

    def set_sessions(self, sessions: list[RecordingSession]):
        if self._root:
            self._root.after(0, lambda s=sessions: self._do_set_sessions(s))

    def _do_set_sessions(self, sessions: list[RecordingSession]):
        if not self._tree:
            return

        selected = self._tree.selection()
        selected_key = self._folder_keys.get(selected[0]) if selected else None

        self._tree.delete(*self._tree.get_children())
        self._folder_keys.clear()

        reselect_iid = None
        for i, session in enumerate(sessions):
            iid = str(i)
            self._tree.insert("", tk.END, iid=iid, values=(
                session.display_date,
                session.display_duration,
                session.display_type,
                session.status.value,
            ))
            self._folder_keys[iid] = session.folder_key
            if session.folder_key == selected_key:
                reselect_iid = iid

        if reselect_iid:
            self._tree.selection_set(reselect_iid)
            self._on_selection_changed(None)

    # --- Shared UI updates ---

    def update_level(self, level: float):
        if self._root:
            self._root.after(0, lambda v=level: self._do_update_level(v))

    def _do_update_level(self, level: float):
        if self._level_bar:
            self._level_bar["value"] = int(level * 100)

    def set_status(self, text: str):
        if self._root:
            self._root.after(0, lambda t=text: self._status_var.set(t))

    def reset_after_processing(self):
        if self._root:
            self._recording = False
            if self._timer_id:
                self._root.after_cancel(self._timer_id)
                self._timer_id = None
            self._reset_controls()

    def run_mainloop(self):
        if self._root:
            self._root.mainloop()

    def destroy(self):
        if self._root:
            self._root.destroy()
            self._root = None
