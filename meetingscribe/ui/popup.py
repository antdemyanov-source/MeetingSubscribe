import tkinter as tk
from tkinter import ttk
from typing import Callable


LANGUAGES = [
    ("Русский", "ru"),
    ("English", "en"),
    ("Авто", "auto"),
]

MEETING_TYPES = [
    ("Рабочая встреча", "work"),
    ("Урок английского", "english"),
    ("Сессия с психологом", "therapy"),
]


class PopupWindow:
    def __init__(
        self,
        on_start: Callable[[str, str], None],
        on_stop: Callable[[], None],
        on_api_key_changed: Callable[[str], None] | None = None,
        initial_api_key: str = "",
    ):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_api_key_changed = on_api_key_changed
        self._initial_api_key = initial_api_key
        self._root: tk.Tk | None = None
        self._recording = False
        self._elapsed = 0
        self._timer_id = None
        self._level_value = 0.0

    def show(self):
        if self._root is not None:
            self._root.deiconify()
            self._root.lift()
            return

        self._root = tk.Tk()
        self._root.title("MeetingScribe")
        self._root.geometry("320x350")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        frame = ttk.Frame(self._root, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # Language
        ttk.Label(frame, text="Язык:").grid(row=0, column=0, sticky=tk.W, pady=3)
        self._lang_var = tk.StringVar(value=LANGUAGES[0][0])
        self._lang_combo = ttk.Combobox(
            frame,
            textvariable=self._lang_var,
            values=[l[0] for l in LANGUAGES],
            state="readonly",
            width=22,
        )
        self._lang_combo.grid(row=0, column=1, pady=3)

        # Meeting type
        ttk.Label(frame, text="Тип:").grid(row=1, column=0, sticky=tk.W, pady=3)
        self._type_var = tk.StringVar(value=MEETING_TYPES[0][0])
        self._type_combo = ttk.Combobox(
            frame,
            textvariable=self._type_var,
            values=[t[0] for t in MEETING_TYPES],
            state="readonly",
            width=22,
        )
        self._type_combo.grid(row=1, column=1, pady=3)

        # Audio level
        ttk.Label(frame, text="Уровень:").grid(row=2, column=0, sticky=tk.W, pady=8)
        self._level_bar = ttk.Progressbar(
            frame, orient=tk.HORIZONTAL, length=180, mode="determinate", maximum=100
        )
        self._level_bar.grid(row=2, column=1, pady=8)

        # Start/Stop button
        self._btn_var = tk.StringVar(value="● Начать запись")
        self._btn = ttk.Button(
            frame, textvariable=self._btn_var, command=self._toggle_recording
        )
        self._btn.grid(row=3, column=0, columnspan=2, pady=10, ipadx=20, ipady=5)

        # Status
        self._status_var = tk.StringVar(value="Готов к записи")
        self._status_label = ttk.Label(
            frame, textvariable=self._status_var, foreground="gray"
        )
        self._status_label.grid(row=4, column=0, columnspan=2, pady=5)

        # Separator
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(
            row=5, column=0, columnspan=2, sticky=tk.EW, pady=5
        )

        # LLM indicator
        has_key = bool(self._initial_api_key)
        llm_text = "LLM: Claude API" if has_key else "LLM: Ollama (локальная)"
        self._llm_var = tk.StringVar(value=llm_text)
        self._llm_label = ttk.Label(frame, textvariable=self._llm_var, foreground="blue")
        self._llm_label.grid(row=6, column=0, columnspan=2, pady=2)

        # API Key
        key_frame = ttk.Frame(frame)
        key_frame.grid(row=7, column=0, columnspan=2, pady=3)
        ttk.Label(key_frame, text="API Key:").pack(side=tk.LEFT, padx=(0, 5))
        self._api_key_var = tk.StringVar(value=self._initial_api_key)
        self._api_key_entry = ttk.Entry(key_frame, textvariable=self._api_key_var, width=18, show="*")
        self._api_key_entry.pack(side=tk.LEFT)
        self._api_key_btn = ttk.Button(key_frame, text="Сохранить", command=self._save_api_key, width=9)
        self._api_key_btn.pack(side=tk.LEFT, padx=(5, 0))

    def _save_api_key(self):
        key = self._api_key_var.get().strip()
        if key:
            self._llm_var.set("LLM: Claude API")
        else:
            self._llm_var.set("LLM: Ollama (локальная)")
        if self._on_api_key_changed:
            self._on_api_key_changed(key)

    def _on_close(self):
        if self._root:
            self._root.withdraw()

    def _toggle_recording(self):
        if not self._recording:
            lang_name = self._lang_var.get()
            lang_code = next(code for name, code in LANGUAGES if name == lang_name)
            type_name = self._type_var.get()
            type_code = next(code for name, code in MEETING_TYPES if name == type_name)

            self._on_start(lang_code, type_code)

            self._recording = True
            self._elapsed = 0
            self._btn_var.set("■ Остановить")
            self._lang_combo.config(state="disabled")
            self._type_combo.config(state="disabled")
            self._update_timer()
        else:
            self._recording = False
            if self._timer_id:
                self._root.after_cancel(self._timer_id)
                self._timer_id = None
            self._btn.config(state="disabled")
            self._on_stop()

    def _update_timer(self):
        if not self._recording:
            return
        h = self._elapsed // 3600
        m = (self._elapsed % 3600) // 60
        s = self._elapsed % 60
        self._status_var.set(f"Записываю... {h:02d}:{m:02d}:{s:02d}")
        self._elapsed += 1
        self._timer_id = self._root.after(1000, self._update_timer)

    def update_level(self, level: float):
        self._level_value = level
        if self._root and self._level_bar:
            self._level_bar["value"] = int(level * 100)

    def set_status(self, text: str):
        if self._root:
            self._status_var.set(text)

    def reset_after_processing(self):
        if self._root:
            self._recording = False
            self._btn_var.set("● Начать запись")
            self._btn.config(state="normal")
            self._lang_combo.config(state="readonly")
            self._type_combo.config(state="readonly")
            self._level_bar["value"] = 0

    def run_mainloop(self):
        if self._root:
            self._root.mainloop()

    def destroy(self):
        if self._root:
            self._root.destroy()
            self._root = None
