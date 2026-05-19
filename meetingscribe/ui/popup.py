import ctypes
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
    ("Внешний источник", "external"),
]

WHISPER_MODELS = ["turbo", "large-v3", "medium", "small", "base", "tiny"]


class PopupWindow:
    def __init__(
        self,
        on_start: Callable[[str, str, bool], None],
        on_stop: Callable[[], None],
        on_open_folder: Callable[[str], None],
        on_transcribe: Callable[[str], None] | None = None,
        on_delete: Callable[[str], None] | None = None,
        on_quit: Callable[[], None] | None = None,
        on_reload: Callable[[], None] | None = None,
        on_import: Callable[[str, str, str], None] | None = None,
        on_url_import: Callable[[str], None] | None = None,
        on_title_changed: Callable[[str, str], None] | None = None,
        on_whisper_model_changed: Callable[[str], None] | None = None,
        on_mic_changed: Callable[[int], None] | None = None,
        on_mic_test_start: Callable[[int], None] | None = None,
        on_mic_test_stop: Callable[[], None] | None = None,
        on_settings: Callable[[], dict] | None = None,
        on_settings_changed: Callable[[dict], None] | None = None,
        mic_devices: list[dict] | None = None,
        initial_mic_name: str = "",
        initial_whisper_model: str = "turbo",
    ):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_transcribe = on_transcribe
        self._on_delete = on_delete
        self._on_quit = on_quit
        self._on_open_folder = on_open_folder
        self._on_reload = on_reload
        self._on_import = on_import
        self._on_url_import = on_url_import
        self._on_title_changed = on_title_changed
        self._on_whisper_model_changed = on_whisper_model_changed
        self._on_mic_changed = on_mic_changed
        self._on_mic_test_start = on_mic_test_start
        self._on_mic_test_stop = on_mic_test_stop
        self._on_settings = on_settings
        self._on_settings_changed = on_settings_changed
        self._mic_devices = mic_devices or []
        self._initial_mic_name = initial_mic_name
        self._initial_whisper_model = initial_whisper_model
        self._root: tk.Tk | None = None
        self._recording = False
        self._testing_mic = False
        self._elapsed = 0
        self._timer_id = None
        self._level_value = 0.0
        self._tree: ttk.Treeview | None = None
        self._folder_keys: dict[str, str] = {}
        self._all_sessions: list[RecordingSession] = []

    def show(self):
        if self._root is not None:
            self._root.deiconify()
            self._root.lift()
            return

        self._root = tk.Tk()
        self._root.title("MeetingScribe")
        self._root.geometry("680x640")
        self._root.resizable(True, True)
        self._root.minsize(580, 500)
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
        self._type_combo.bind("<<ComboboxSelected>>", self._on_type_selected)

        ttk.Label(controls, text="Модель:").pack(side=tk.LEFT, padx=(15, 5))
        self._whisper_model_var = tk.StringVar(value=self._initial_whisper_model)
        self._whisper_model_combo = ttk.Combobox(
            controls,
            textvariable=self._whisper_model_var,
            values=WHISPER_MODELS,
            state="readonly",
            width=10,
        )
        self._whisper_model_combo.pack(side=tk.LEFT)
        self._whisper_model_combo.bind("<<ComboboxSelected>>", self._on_whisper_model_selected)

        # Microphone selection row
        mic_row = ttk.Frame(frame)
        mic_row.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(mic_row, text="Микрофон:").pack(side=tk.LEFT, padx=(0, 5))

        mic_names = [d["name"] for d in self._mic_devices]
        preselect = ""
        if mic_names:
            preselect = mic_names[0]
            if self._initial_mic_name in mic_names:
                preselect = self._initial_mic_name

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

        ttk.Button(
            btn_frame, text="Настройки", command=self._open_settings
        ).pack(side=tk.RIGHT, ipadx=10, ipady=3)

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

        self._tab_var = tk.StringVar(value="all")
        tab_items = [
            ("Все", "all"), ("Работа", "work"), ("Английский", "english"),
            ("Личное", "therapy"), ("Внешние", "external"),
        ]
        for label, value in tab_items:
            ttk.Radiobutton(
                list_header, text=label, variable=self._tab_var, value=value,
                style="Toolbutton", command=self._apply_filter,
            ).pack(side=tk.LEFT, padx=(0, 2))

        ttk.Button(list_header, text="Обновить", command=self._reload_list, width=10).pack(side=tk.RIGHT)
        ttk.Button(list_header, text="Импорт по ссылке", command=self._import_from_url, width=16).pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(list_header, text="Добавить запись", command=self._import_recording, width=16).pack(side=tk.RIGHT, padx=(0, 5))

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=(3, 5))

        columns = ("date", "title", "duration", "type", "status")
        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", height=8, selectmode="browse"
        )
        self._tree.heading("date", text="Дата")
        self._tree.heading("title", text="Название")
        self._tree.heading("duration", text="Длительность")
        self._tree.heading("type", text="Тип")
        self._tree.heading("status", text="Статус")

        self._tree.column("date", width=120, minwidth=100, stretch=False)
        self._tree.column("title", width=200, minwidth=100)
        self._tree.column("duration", width=80, minwidth=60, stretch=False)
        self._tree.column("type", width=90, minwidth=70, stretch=False)
        self._tree.column("status", width=80, minwidth=60, stretch=False)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<<TreeviewSelect>>", self._on_selection_changed)
        self._tree.bind("<Double-1>", self._on_tree_double_click)
        self._title_editor: tk.Entry | None = None

        # Action buttons
        action_frame = ttk.Frame(frame)
        action_frame.pack(fill=tk.X, pady=3)

        self._transcribe_btn = ttk.Button(
            action_frame, text="Транскрибировать", command=self._transcribe_selected, state="disabled"
        )
        self._transcribe_btn.pack(side=tk.LEFT, padx=(0, 10), ipadx=5)

        self._folder_btn = ttk.Button(
            action_frame, text="Открыть папку", command=self._open_selected_folder, state="disabled"
        )
        self._folder_btn.pack(side=tk.LEFT, padx=(0, 10), ipadx=5)

        self._delete_btn = ttk.Button(
            action_frame, text="Удалить", command=self._delete_selected, state="disabled"
        )
        self._delete_btn.pack(side=tk.LEFT, ipadx=5)

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

    # --- URL Import ---

    def _import_from_url(self):
        dialog = tk.Toplevel(self._root)
        dialog.title("Импорт по ссылке")
        dialog.geometry("420x130")
        dialog.resizable(False, False)
        dialog.transient(self._root)

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Вставьте ссылку на видео:").pack(anchor=tk.W, pady=(0, 3))
        url_var = tk.StringVar()

        entry_row = ttk.Frame(frame)
        entry_row.pack(fill=tk.X, pady=(0, 15))

        url_entry = ttk.Entry(entry_row, textvariable=url_var)
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def _do_paste():
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
            kernel32.GlobalLock.restype = ctypes.c_void_p
            kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
            user32.GetClipboardData.restype = ctypes.c_void_p
            if not user32.OpenClipboard(0):
                return
            try:
                handle = user32.GetClipboardData(13)
                if not handle:
                    return
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return
                try:
                    text = ctypes.wstring_at(ptr)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
            if text:
                url_var.set(text.strip())

        ttk.Button(entry_row, text="Вставить", command=_do_paste, width=10).pack(side=tk.LEFT)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        def on_ok():
            url = url_var.get().strip()
            if not url:
                return
            dialog.destroy()
            if self._on_url_import:
                self._on_url_import(url)

        dialog.bind("<Return>", lambda e: on_ok())
        ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy, width=10).pack(side=tk.RIGHT)

        dialog.grab_set()

    # --- Microphone selection & test ---

    def _get_selected_mic_index(self) -> int | None:
        name = self._mic_var.get()
        for d in self._mic_devices:
            if d["name"] == name:
                return d["index"]
        return None

    def _on_type_selected(self, event):
        type_name = self._type_var.get()
        type_code = next((code for name, code in MEETING_TYPES if name == type_name), None)
        if type_code == "english":
            self._lang_var.set("English")

    def _on_whisper_model_selected(self, event):
        model = self._whisper_model_var.get()
        if self._on_whisper_model_changed:
            self._on_whisper_model_changed(model)

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

    # --- Settings dialog ---

    def _open_settings(self):
        if not self._on_settings:
            return
        current = self._on_settings()

        dialog = tk.Toplevel(self._root)
        dialog.title("Настройки записи")
        dialog.geometry("400x280")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.transient(self._root)

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # Silence threshold
        ttk.Label(frame, text="Порог тишины (чувствительность):").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 3))
        threshold_var = tk.DoubleVar(value=current["silence_threshold"])
        threshold_label = ttk.Label(frame, text=f"{current['silence_threshold']:.2f}")
        threshold_label.grid(row=0, column=1, sticky=tk.E, pady=(0, 3))

        def _on_threshold_change(val):
            v = round(float(val), 2)
            threshold_var.set(v)
            threshold_label.config(text=f"{v:.2f}")

        threshold_scale = ttk.Scale(
            frame, from_=0.01, to=0.15, variable=threshold_var,
            orient=tk.HORIZONTAL, command=_on_threshold_change,
        )
        threshold_scale.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 5))
        ttk.Label(frame, text="← чувствительнее    грубее →",
                  foreground="gray").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        # Silence auto-stop minutes
        ttk.Label(frame, text="Автостоп при тишине (минуты):").grid(
            row=3, column=0, sticky=tk.W, pady=(0, 3))
        silence_min_var = tk.IntVar(value=current["silence_auto_stop_minutes"])
        silence_spin = ttk.Spinbox(
            frame, from_=1, to=30, textvariable=silence_min_var, width=5)
        silence_spin.grid(row=3, column=1, sticky=tk.E, pady=(0, 3))
        ttk.Label(frame, text="Запись остановится, если уровень звука ниже порога в течение этого времени",
                  foreground="gray", wraplength=370).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        # Max recording minutes
        ttk.Label(frame, text="Максимальная длительность записи (минуты):").grid(
            row=5, column=0, sticky=tk.W, pady=(0, 3))
        max_min_var = tk.IntVar(value=current["max_recording_minutes"])
        max_spin = ttk.Spinbox(
            frame, from_=10, to=180, increment=10, textvariable=max_min_var, width=5)
        max_spin.grid(row=5, column=1, sticky=tk.E, pady=(0, 3))
        ttk.Label(frame, text="Запись автоматически остановится по достижении лимита",
                  foreground="gray").grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(0, 15))

        frame.columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=2, sticky=tk.EW)

        def on_save():
            settings = {
                "silence_threshold": round(threshold_var.get(), 2),
                "silence_auto_stop_minutes": silence_min_var.get(),
                "max_recording_minutes": max_min_var.get(),
            }
            dialog.destroy()
            if self._on_settings_changed:
                self._on_settings_changed(settings)

        ttk.Button(btn_frame, text="Сохранить", command=on_save, width=12).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy, width=12).pack(side=tk.RIGHT)

    # --- Inline title editing ---

    def _on_tree_double_click(self, event):
        region = self._tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self._tree.identify_column(event.x)
        if col != "#2":
            return
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._start_title_edit(iid)

    def _start_title_edit(self, iid: str):
        self._cancel_title_edit()

        bbox = self._tree.bbox(iid, column="title")
        if not bbox:
            return

        x, y, w, h = bbox
        current = self._tree.set(iid, "title")

        entry = tk.Entry(self._tree, font=("", 9))
        entry.insert(0, current)
        entry.select_range(0, tk.END)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus_set()

        def commit(event=None):
            new_title = entry.get().strip()
            entry.destroy()
            self._title_editor = None
            self._tree.set(iid, "title", new_title)
            folder_key = self._folder_keys.get(iid)
            if folder_key and self._on_title_changed:
                self._on_title_changed(folder_key, new_title)

        def cancel(event=None):
            entry.destroy()
            self._title_editor = None

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)
        self._title_editor = entry

    def _cancel_title_edit(self):
        if self._title_editor:
            self._title_editor.destroy()
            self._title_editor = None

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

        mic_idx = self._get_selected_mic_index()
        if mic_idx is not None and self._on_mic_changed:
            self._on_mic_changed(mic_idx)

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
        self._whisper_model_combo.config(state="disabled")

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

    def trigger_auto_stop(self, reason: str):
        if self._root and self._recording:
            self._root.after(0, lambda: self._do_auto_stop(reason))

    def _do_auto_stop(self, reason: str):
        if not self._recording:
            return
        self._stop_recording()
        self._status_var.set(reason)

    def _reset_controls(self):
        self._btn_var.set("Начать запись")
        self._btn.config(state="normal")
        self._mic_btn.config(state="normal")
        self._test_btn.config(state="normal")
        self._mic_combo.config(state="readonly")
        self._lang_combo.config(state="readonly")
        self._type_combo.config(state="readonly")
        self._whisper_model_combo.config(state="readonly")
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
            self._folder_btn.config(state="disabled")
            self._delete_btn.config(state="disabled")
            return

        iid = selected[0]
        self._folder_btn.config(state="normal")

        values = self._tree.item(iid, "values")
        status_text = values[4] if len(values) > 4 else ""
        is_active = status_text in (
            SessionStatus.RECORDING.value,
            SessionStatus.IMPORTING.value,
            SessionStatus.TRANSCRIBING.value,
        )
        can_transcribe = status_text in (
            SessionStatus.ERROR.value,
            SessionStatus.IMPORTED.value,
        )
        self._transcribe_btn.config(state="normal" if can_transcribe else "disabled")
        self._delete_btn.config(state="normal" if not is_active else "disabled")

    def _transcribe_selected(self):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if folder_key and self._on_transcribe:
            self._on_transcribe(folder_key)

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
        self._all_sessions = sessions
        self._apply_filter()

    def _apply_filter(self):
        if not self._tree:
            return

        selected = self._tree.selection()
        selected_key = self._folder_keys.get(selected[0]) if selected else None

        self._cancel_title_edit()
        self._tree.delete(*self._tree.get_children())
        self._folder_keys.clear()

        type_filter = self._tab_var.get() if hasattr(self, "_tab_var") else "all"
        sessions = self._all_sessions
        if type_filter != "all":
            sessions = [s for s in sessions if s.meeting_type == type_filter]

        reselect_iid = None
        for i, session in enumerate(sessions):
            iid = str(i)
            self._tree.insert("", tk.END, iid=iid, values=(
                session.display_date,
                session.title,
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
