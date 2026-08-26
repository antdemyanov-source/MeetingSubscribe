import ctypes
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

import re
from pathlib import Path

from meetingscribe.session import RecordingSession, SessionStatus
from meetingscribe import db

logger = logging.getLogger(__name__)
from meetingscribe.ui.markdown_viewer import MarkdownViewer

# ── Neutral dark palette (Obsidian / VS Code style) ──────────────────────

BG = "#1e1e1e"
BG_RAISED = "#252526"
SURFACE = "#2d2d2d"
SURFACE_LIGHT = "#383838"
BORDER = "#3e3e42"
TEXT = "#cccccc"
TEXT_SEC = "#858585"
TEXT_DIS = "#5a5a5e"
ACCENT = "#7c6bc4"
ACCENT_HI = "#8b7bd4"
ACCENT_LO = "#6a5aaf"
SELECT = "#37373d"
GREEN = "#73c991"
RED = "#d4564e"
YELLOW = "#cca700"
BLUE = "#5c9fd6"

# ── Icons (Segoe MDL2 Assets — Windows 10 system icon font) ─────────────

_ICON_FONT = "Segoe MDL2 Assets"
_ICON_SZ = 11

ICO_REFRESH  = ""
ICO_FOLDER   = ""
ICO_DELETE   = ""
ICO_EDIT     = ""
ICO_PLAY     = ""
ICO_BACK     = ""
ICO_ADD      = ""
ICO_CHEVDOWN = ""
ICO_LINK     = ""
ICO_PAGE     = ""
ICO_MIC      = ""
ICO_RECORD   = ""
ICO_STOP     = ""
ICO_SETTINGS = ""
ICO_SHARE    = ""
ICO_SPLITVIEW = ""
ICO_CAPTION  = ""
ICO_SUMMARY  = ""
ICO_SEARCH   = ""

# ── Constants ────────────────────────────────────────────────────────────

LANGUAGES = [
    ("Русский", "ru"),
    ("English", "en"),
    ("Авто", "auto"),
]

MEETING_TYPES = [
    ("Рабочая встреча", "work"),
    ("Урок английского", "english"),
    ("Личная встреча", "personal"),
    ("Внешний источник", "external"),
]

WHISPER_MODELS = ["turbo", "large-v3", "medium", "small", "base", "tiny"]

STATUS_ICON = {
    SessionStatus.DONE.value: "✓",
    SessionStatus.RECORDING.value: "●",
    SessionStatus.TRANSCRIBING.value: "…",
    SessionStatus.IMPORTING.value: "↓",
    SessionStatus.ERROR.value: "✗",
    SessionStatus.IMPORTED.value: "◆",
}

STATUS_TAG = {
    SessionStatus.DONE.value: "done",
    SessionStatus.RECORDING.value: "recording",
    SessionStatus.TRANSCRIBING.value: "processing",
    SessionStatus.IMPORTING.value: "processing",
    SessionStatus.ERROR.value: "error",
    SessionStatus.IMPORTED.value: "imported",
}

TYPE_SHORT = {
    "work": "Раб",
    "english": "EN",
    "personal": "Лич",
    "external": "Вн",
}


# ── Dark titlebar (Windows 10 build 19041+) ──────────────────────────────

def _dark_titlebar(window):
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20,
            ctypes.byref(ctypes.c_int(1)),
            ctypes.sizeof(ctypes.c_int),
        )
    except Exception:
        pass


def _get_monitor_workarea(x: int, y: int) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) work area of the monitor containing (x, y)."""
    try:
        import ctypes.wintypes
        MONITOR_DEFAULTTONEAREST = 2

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.DWORD),
                ("rcMonitor", ctypes.wintypes.RECT),
                ("rcWork", ctypes.wintypes.RECT),
                ("dwFlags", ctypes.wintypes.DWORD),
            ]

        _MonitorFromPoint = ctypes.windll.user32.MonitorFromPoint
        _MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, ctypes.wintypes.DWORD]
        _MonitorFromPoint.restype = ctypes.wintypes.HANDLE

        pt = ctypes.wintypes.POINT(x, y)
        hmon = _MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        rc = info.rcWork
        return (rc.left, rc.top, rc.right, rc.bottom)
    except Exception:
        return (0, 0, 1920, 1080)


# ── Calendar popup ──────────────────────────────────────────────────────

def _show_calendar_popup(parent: tk.Toplevel, target_entry: ttk.Entry):
    """Show a dropdown calendar below *target_entry* and write the picked date."""
    import calendar as _cal
    from datetime import date as _date, timedelta as _td

    popup = tk.Toplevel(parent)
    popup.overrideredirect(True)
    popup.configure(bg=BORDER)
    _dark_titlebar(popup)

    parent.update_idletasks()
    ex = target_entry.winfo_rootx()
    ey = target_entry.winfo_rooty() + target_entry.winfo_height() + 2
    popup.geometry(f"+{ex}+{ey}")

    cur = target_entry.get().strip()
    try:
        parts = cur.split("-")
        year, month = int(parts[0]), int(parts[1])
    except Exception:
        today = _date.today()
        year, month = today.year, today.month

    state = {"year": year, "month": month}

    frame = tk.Frame(popup, bg=BG, padx=4, pady=4)
    frame.pack()

    MONTH_NAMES_RU = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
    ]
    DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

    header = tk.Frame(frame, bg=BG)
    header.pack(fill=tk.X)
    btn_kw = dict(fg=TEXT, bg=BG, activebackground=SURFACE2, activeforeground=TEXT,
                  bd=0, font=("Segoe MDL2 Assets", 10), cursor="hand2", padx=4)
    prev_btn = tk.Label(header, text="", **{k: v for k, v in btn_kw.items() if k != "activebackground" and k != "activeforeground"})
    prev_btn.configure(cursor="hand2")
    next_btn = tk.Label(header, text="", fg=TEXT, bg=BG,
                        font=("Segoe MDL2 Assets", 10), cursor="hand2", padx=4)
    month_label = tk.Label(header, text="", fg=TEXT, bg=BG,
                           font=("Segoe UI", 10, "bold"))
    prev_btn.pack(side=tk.LEFT)
    month_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
    next_btn.pack(side=tk.RIGHT)

    days_frame = tk.Frame(frame, bg=BG)
    days_frame.pack()

    for col, dn in enumerate(DAY_NAMES):
        tk.Label(days_frame, text=dn, fg=TEXT_SEC, bg=BG,
                 font=("Segoe UI", 8), width=4).grid(row=0, column=col)

    day_labels: list[tk.Label] = []

    def _render():
        for lb in day_labels:
            lb.destroy()
        day_labels.clear()

        y, m = state["year"], state["month"]
        month_label.configure(text=f"{MONTH_NAMES_RU[m]} {y}")
        matrix = _cal.monthcalendar(y, m)
        today = _date.today()

        for r, week in enumerate(matrix):
            for c, day in enumerate(week):
                if day == 0:
                    lb = tk.Label(days_frame, text="", bg=BG, width=4)
                else:
                    is_today = (y == today.year and m == today.month
                                and day == today.day)
                    fg = BLUE if is_today else TEXT
                    lb = tk.Label(days_frame, text=str(day), fg=fg, bg=BG,
                                  font=("Segoe UI", 9, "bold" if is_today else ""),
                                  width=4, cursor="hand2")
                    lb.bind("<Button-1>",
                            lambda e, d=day: _pick(d))
                    lb.bind("<Enter>",
                            lambda e, w=lb: w.configure(bg=SURFACE2))
                    lb.bind("<Leave>",
                            lambda e, w=lb: w.configure(bg=BG))
                lb.grid(row=r + 1, column=c)
                day_labels.append(lb)

    def _pick(day: int):
        val = f"{state['year']}-{state['month']:02d}-{day:02d}"
        target_entry.delete(0, tk.END)
        target_entry.insert(0, val)
        popup.destroy()

    def _prev(_e=None):
        if state["month"] == 1:
            state["month"] = 12
            state["year"] -= 1
        else:
            state["month"] -= 1
        _render()

    def _next(_e=None):
        if state["month"] == 12:
            state["month"] = 1
            state["year"] += 1
        else:
            state["month"] += 1
        _render()

    prev_btn.bind("<Button-1>", _prev)
    next_btn.bind("<Button-1>", _next)

    _render()
    popup.focus_set()
    popup.bind("<Escape>", lambda e: popup.destroy())

    def _on_deactivate(e):
        popup.after(50, lambda: _try_dismiss())

    def _try_dismiss():
        try:
            fw = popup.focus_get()
            if fw is None:
                popup.destroy()
                return
            fw_path = str(fw)
            popup_path = str(popup)
            if not fw_path.startswith(popup_path):
                popup.destroy()
        except Exception:
            try:
                popup.destroy()
            except Exception:
                pass

    popup.bind("<FocusOut>", _on_deactivate)


# ── Theme ────────────────────────────────────────────────────────────────

def _apply_dark_theme(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")

    f = ("Segoe UI", 10)
    fs = ("Segoe UI", 9)
    fb = ("Segoe UI", 10, "bold")

    # Combobox dropdown
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", SELECT)
    root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
    root.option_add("*TCombobox*Listbox.font", f)

    # ── Root (cascades to all) ──
    style.configure(".",
        background=BG, foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=BG, darkcolor=BG,
        focuscolor=BG,
        troughcolor=SURFACE, fieldbackground=SURFACE,
        selectbackground=SELECT, selectforeground=TEXT,
        font=f, insertcolor=TEXT, insertwidth=2)
    style.map(".",
        foreground=[("disabled", TEXT_DIS)],
        lightcolor=[("focus", BG)],
        darkcolor=[("focus", BG)])

    # ── Frame ──
    style.configure("TFrame", background=BG)

    # ── Label ──
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Dim.TLabel", foreground=TEXT_SEC)
    style.configure("Status.TLabel", foreground=TEXT_SEC, font=fs)
    style.configure("RecStatus.TLabel", foreground=RED, font=(fs[0], fs[1], "bold"))
    style.configure("SummaryStatus.TLabel", foreground=GREEN, font=(fs[0], fs[1], "bold"))
    style.configure("Section.TLabel", foreground=TEXT_SEC, font=fb)

    # ── Button ──
    _btn = dict(background=SURFACE_LIGHT, foreground=TEXT,
                bordercolor=BORDER, lightcolor=SURFACE_LIGHT,
                darkcolor=SURFACE_LIGHT, padding=(10, 5), font=f)
    style.configure("TButton", **_btn)
    style.map("TButton",
        background=[("active", BORDER), ("pressed", ACCENT_LO)],
        lightcolor=[("active", BORDER), ("pressed", ACCENT_LO)],
        darkcolor=[("active", BORDER), ("pressed", ACCENT_LO)],
        foreground=[("disabled", TEXT_DIS)])

    style.configure("Accent.TButton",
        background=ACCENT_LO, foreground="#e8e0ff",
        bordercolor=ACCENT_LO, lightcolor=ACCENT_LO,
        darkcolor=ACCENT_LO, padding=(14, 6), font=fb)
    style.map("Accent.TButton",
        background=[("active", ACCENT_HI), ("pressed", ACCENT)],
        lightcolor=[("active", ACCENT_HI), ("pressed", ACCENT)],
        darkcolor=[("active", ACCENT_HI), ("pressed", ACCENT)],
        bordercolor=[("active", ACCENT_HI)])

    style.configure("Stop.TButton",
        background="#8b2020", foreground="#fecaca",
        bordercolor="#8b2020", lightcolor="#8b2020",
        darkcolor="#8b2020", padding=(14, 6), font=fb)
    style.map("Stop.TButton",
        background=[("active", "#a52828")],
        lightcolor=[("active", "#a52828")],
        darkcolor=[("active", "#a52828")],
        bordercolor=[("active", "#a52828")])

    style.configure("Sm.TButton", padding=(6, 3), font=fs)

    # ── Combobox ──
    style.configure("TCombobox",
        fieldbackground=SURFACE, foreground=TEXT,
        background=SURFACE,
        selectbackground=SELECT, selectforeground=TEXT,
        arrowcolor=TEXT_SEC,
        bordercolor=BORDER,
        lightcolor=SURFACE, darkcolor=SURFACE,
        padding=(4, 3))
    style.map("TCombobox",
        fieldbackground=[("readonly", SURFACE), ("readonly focus", SURFACE)],
        background=[("readonly", SURFACE), ("readonly focus", SURFACE)],
        foreground=[("readonly", TEXT)],
        bordercolor=[("focus", ACCENT_LO), ("readonly focus", ACCENT_LO)],
        lightcolor=[("focus", SURFACE), ("readonly", SURFACE), ("readonly focus", SURFACE)],
        darkcolor=[("focus", SURFACE), ("readonly", SURFACE), ("readonly focus", SURFACE)],
        arrowcolor=[("disabled", TEXT_DIS)])

    # ── Treeview ──
    style.configure("Treeview",
        background=SURFACE, foreground=TEXT,
        fieldbackground=SURFACE,
        borderwidth=0, relief="flat",
        lightcolor=SURFACE, darkcolor=SURFACE,
        rowheight=28, font=f)
    style.configure("Treeview.Heading",
        background=BG_RAISED, foreground=TEXT_SEC,
        bordercolor=BORDER, borderwidth=1,
        lightcolor=BG_RAISED, darkcolor=BG_RAISED,
        font=fs, padding=(4, 3))
    style.map("Treeview",
        background=[("selected", SELECT)],
        foreground=[("selected", TEXT)])
    style.map("Treeview.Heading",
        background=[("active", SURFACE_LIGHT)],
        lightcolor=[("active", SURFACE_LIGHT)],
        darkcolor=[("active", SURFACE_LIGHT)])

    # ── Sidebar tree (Obsidian-like) ──
    style.configure("Sidebar.Treeview",
        background=BG, foreground=TEXT,
        fieldbackground=BG,
        borderwidth=0, relief="flat",
        lightcolor=BG, darkcolor=BG,
        rowheight=30, font=f)
    style.configure("Sidebar.Treeview.Heading",
        background=BG, foreground=TEXT_SEC,
        bordercolor=BORDER, borderwidth=0,
        lightcolor=BG, darkcolor=BG,
        font=fs, padding=(4, 4))
    style.map("Sidebar.Treeview",
        background=[("selected", SELECT)],
        foreground=[("selected", TEXT)])
    style.map("Sidebar.Treeview.Heading",
        background=[("active", BG_RAISED)],
        lightcolor=[("active", BG_RAISED)],
        darkcolor=[("active", BG_RAISED)])

    try:
        from PIL import Image as _Img, ImageDraw as _Drw, ImageTk as _ImgTk
        _sz, _ss = 14, 4
        _big = _sz * _ss
        _clr = (133, 133, 133, 255)
        _w = _ss + 1

        _closed = _Img.new("RGBA", (_big, _big), (0, 0, 0, 0))
        _d = _Drw.Draw(_closed)
        _m = 4 * _ss
        _d.line([(_m, 2 * _ss), (_big - _m, _big // 2), (_m, _big - 2 * _ss)],
                fill=_clr, width=_w)
        _closed = _closed.resize((_sz, _sz), _Img.LANCZOS)

        _opened = _Img.new("RGBA", (_big, _big), (0, 0, 0, 0))
        _d = _Drw.Draw(_opened)
        _d.line([(2 * _ss, _m), (_big // 2, _big - _m), (_big - 2 * _ss, _m)],
                fill=_clr, width=_w)
        _opened = _opened.resize((_sz, _sz), _Img.LANCZOS)

        _empty = _Img.new("RGBA", (_sz, _sz), (0, 0, 0, 0))

        _closed_tk = _ImgTk.PhotoImage(_closed)
        _opened_tk = _ImgTk.PhotoImage(_opened)
        _empty_tk = _ImgTk.PhotoImage(_empty)
        root._tree_chevrons = (_closed_tk, _opened_tk, _empty_tk)

        style.element_create("Sidebar.indicator", "image",
                             _closed_tk,
                             ("user1", "!user2", _opened_tk),
                             ("user2", _empty_tk),
                             sticky="", width=_sz, height=_sz)
        style.layout("Sidebar.Treeview.Item", [
            ("Treeitem.padding", {"sticky": "nswe", "children": [
                ("Sidebar.indicator", {"side": "left", "sticky": ""}),
                ("Treeitem.image", {"side": "left", "sticky": ""}),
                ("Treeitem.text", {"sticky": "nswe"}),
            ]}),
        ])
    except Exception:
        pass

    # ── Progressbar ──
    style.configure("TProgressbar",
        background=ACCENT, troughcolor=SURFACE,
        bordercolor=SURFACE, lightcolor=ACCENT, darkcolor=ACCENT,
        thickness=5)
    style.configure("Rec.TProgressbar",
        background=RED, troughcolor=SURFACE,
        bordercolor=SURFACE, lightcolor=RED, darkcolor=RED,
        thickness=5)
    style.layout("Horizontal.Rec.TProgressbar",
        style.layout("Horizontal.TProgressbar"))

    # ── Separator ──
    style.configure("TSeparator", background=BORDER)

    # ── Scrollbar ──
    style.configure("Vertical.TScrollbar",
        background=BG_RAISED, troughcolor=BG,
        bordercolor=BG, lightcolor=BG, darkcolor=BG,
        arrowcolor=TEXT_SEC, gripcount=0)
    style.map("Vertical.TScrollbar",
        background=[("active", SURFACE_LIGHT), ("pressed", BORDER)],
        lightcolor=[("active", BG), ("pressed", BG)],
        darkcolor=[("active", BG), ("pressed", BG)])

    # ── Toolbutton (filter tabs) ──
    style.configure("Toolbutton",
        background=BG, foreground=TEXT_SEC,
        bordercolor=BG, lightcolor=BG, darkcolor=BG,
        padding=(8, 4), font=fs)
    style.map("Toolbutton",
        background=[("selected", SURFACE), ("active", BG_RAISED)],
        foreground=[("selected", ACCENT_HI), ("active", TEXT)],
        lightcolor=[("selected", SURFACE), ("active", BG_RAISED)],
        darkcolor=[("selected", SURFACE), ("active", BG_RAISED)],
        bordercolor=[("selected", BORDER), ("!selected", BG)],
        relief=[("selected", "flat"), ("!selected", "flat")])

    # ── Spinbox ──
    style.configure("TSpinbox",
        fieldbackground=SURFACE, foreground=TEXT,
        background=SURFACE, arrowcolor=TEXT_SEC,
        bordercolor=BORDER,
        lightcolor=SURFACE, darkcolor=SURFACE)
    style.map("TSpinbox",
        lightcolor=[("focus", SURFACE)],
        darkcolor=[("focus", SURFACE)],
        bordercolor=[("focus", ACCENT_LO)])

    # ── Scale ──
    style.configure("Horizontal.TScale",
        background=BG, troughcolor=SURFACE,
        lightcolor=BG, darkcolor=BG, sliderrelief="flat")

    # ── PanedWindow ──
    style.configure("TPanedwindow", background=BORDER)
    style.configure("Sash", sashthickness=3, gripcount=0)
    root.option_add("*Panedwindow.sashWidth", 3)
    root.option_add("*Panedwindow.sashRelief", "flat")

    # ── Entry ──
    style.configure("TEntry",
        fieldbackground=SURFACE, foreground=TEXT,
        bordercolor=BORDER,
        lightcolor=SURFACE, darkcolor=SURFACE,
        insertcolor=TEXT, padding=(4, 3))
    style.map("TEntry",
        bordercolor=[("focus", ACCENT_LO)],
        lightcolor=[("focus", SURFACE)],
        darkcolor=[("focus", SURFACE)])

    return style


# ── Minimal widgets (VS Code / Obsidian style) ───────────────────────────

class _Tooltip:
    """VS Code-style tooltip — appears ABOVE the widget, centered."""
    def __init__(self, widget, text, delay=400):
        self._widget = widget
        self._text = text
        self._delay = delay
        self._tip = None
        self._timer = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")

    def _schedule(self, event=None):
        self._cancel()
        self._timer = self._widget.after(self._delay, self._show)

    def _cancel(self, event=None):
        if self._timer:
            self._widget.after_cancel(self._timer)
            self._timer = None
        self._hide()

    def _show(self):
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)
        self._tip.configure(bg=BORDER)
        inner = tk.Frame(self._tip, bg=SURFACE)
        inner.pack(padx=1, pady=1)
        tk.Label(inner, text=self._text, bg=SURFACE, fg=TEXT,
                 font=("Segoe UI", 9), padx=6, pady=2).pack()
        self._tip.update_idletasks()
        tw = self._tip.winfo_reqwidth()
        th = self._tip.winfo_reqheight()
        wx = self._widget.winfo_rootx()
        wy = self._widget.winfo_rooty()
        ww = self._widget.winfo_width()
        x = wx + ww // 2 - tw // 2
        y = wy - th - 4
        ml, mt, mr, mb = _get_monitor_workarea(wx + ww // 2, wy)
        if y < mt:
            y = wy + self._widget.winfo_height() + 4
        if x < ml:
            x = ml
        if x + tw > mr:
            x = mr - tw
        self._tip.wm_geometry(f"+{x}+{y}")

    def _hide(self):
        if self._tip:
            self._tip.destroy()
            self._tip = None

    def update_text(self, text):
        self._text = text


class _IconBtn(tk.Label):
    """Flat borderless icon button — VS Code style.

    Uses Segoe MDL2 Assets by default for crisp vector icons.
    Hover shows subtle bg highlight + brighter fg.
    Supports .config(state=...) and .config(style=...) for compat.
    """
    def __init__(self, parent, icon, tooltip, command=None,
                 fg=TEXT_SEC, fg_hover=TEXT,
                 font_name=_ICON_FONT, font_size=_ICON_SZ, **kw):
        bg = kw.pop("bg", BG)
        super().__init__(parent, text=icon,
                         font=(font_name, font_size),
                         fg=fg, bg=bg, cursor="hand2",
                         padx=4, pady=2, **kw)
        self._command = command
        self._enabled = True
        self._fg = fg
        self._fg_hover = fg_hover
        self._bg = bg
        self._tt = _Tooltip(self, tooltip)
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<Button-1>", self._on_click)

    def _on_enter(self, event):
        if self._enabled:
            super().configure(fg=self._fg_hover, bg=SURFACE_LIGHT)

    def _on_leave(self, event):
        super().configure(
            fg=self._fg if self._enabled else TEXT_DIS,
            bg=self._bg)

    def _on_click(self, event):
        if self._enabled and self._command:
            self._command()

    def set_enabled(self, enabled):
        self._enabled = enabled
        super().configure(
            fg=self._fg if enabled else TEXT_DIS,
            cursor="hand2" if enabled else "arrow")

    def set_colors(self, fg, fg_hover=None):
        self._fg = fg
        self._fg_hover = fg_hover or fg
        if self._enabled:
            super().configure(fg=fg)

    def configure(self, **kw):
        state = kw.pop("state", None)
        style = kw.pop("style", None)
        if state is not None:
            self.set_enabled(state in ("normal", "!disabled"))
        if style == "Stop.TButton":
            self.set_colors(RED, "#ff6666")
            super().configure(text=ICO_STOP)
            self._tt.update_text("Остановить запись")
        elif style == "Accent.TButton":
            self.set_colors(ACCENT, ACCENT_HI)
            super().configure(text=ICO_RECORD)
            self._tt.update_text("Начать запись")
        remaining = {k: v for k, v in kw.items()
                     if k not in ("state", "style")}
        if remaining:
            super().configure(**remaining)

    config = configure


# ── Autocomplete popup (focus-safe dropdown) ────────────────────────────

class _AutocompletePopup:
    """Custom dropdown list that never steals keyboard focus from the entry."""

    def __init__(self, entry: ttk.Combobox | ttk.Entry):
        self._entry = entry
        self._win: tk.Toplevel | None = None
        self._lb: tk.Listbox | None = None
        self._items: list[str] = []
        entry.bind("<Destroy>", lambda e: self.destroy(), add="+")

    def show(self, items: list[str]):
        if not items:
            self.hide()
            return
        self._items = items
        if self._win is None:
            self._create()
        self._lb.delete(0, tk.END)
        for item in items:
            self._lb.insert(tk.END, item)
        self._position()
        self._win.deiconify()
        self._win.lift()

    def hide(self):
        if self._win and self._win.winfo_exists():
            self._win.withdraw()

    def destroy(self):
        if self._win:
            try:
                self._win.destroy()
            except tk.TclError:
                pass
            self._win = None

    def _create(self):
        self._win = tk.Toplevel(self._entry)
        self._win.withdraw()
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._lb = tk.Listbox(
            self._win, bg=SURFACE, fg=TEXT,
            selectbackground="#37373d", selectforeground=TEXT,
            borderwidth=1, relief="solid", highlightthickness=0,
            font=("Segoe UI", 10), activestyle="none", cursor="hand2",
        )
        self._lb.pack(fill=tk.BOTH, expand=True)
        self._lb.bind("<Button-1>", self._on_click)

    def _position(self):
        self._entry.update_idletasks()
        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height()
        w = max(self._entry.winfo_width(), 200)
        h = min(len(self._items), 8) * 22 + 4
        self._win.geometry(f"{w}x{h}+{x}+{y}")

    def _on_click(self, event):
        idx = self._lb.nearest(event.y)
        if idx < 0:
            return
        value = self._lb.get(idx)
        if isinstance(self._entry, ttk.Combobox):
            self._entry.set(value)
            self._entry.icursor(tk.END)
            self._entry.event_generate("<<ComboboxSelected>>")
        else:
            self._entry.delete(0, tk.END)
            self._entry.insert(0, value)
        self.hide()
        self._entry.focus_set()
        return "break"


# ── Activity picker widget (searchable combobox) ────────────────────────

class _ActivityPickerWidget:
    """Inline searchable activity selector with optional '+ Новая тема' button."""

    def __init__(self, parent, activities: list[dict], db_conn, popup_win,
                 *, allow_none: bool = False, selected_name: str = ""):
        self.frame = ttk.Frame(parent)
        self._activities = list(activities)
        self._db_conn = db_conn
        self._popup_win = popup_win
        self._allow_none = allow_none

        self._all_names = (["(нет)"] if allow_none else []) + [a["name"] for a in activities]
        self._all_ids = ([""] if allow_none else []) + [a["id"] for a in activities]

        self._var = tk.StringVar(value=selected_name or ("(нет)" if allow_none else ""))
        self._combo = ttk.Combobox(self.frame, textvariable=self._var,
                                   values=self._all_names)
        self._combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._combo.bind("<KeyRelease>", self._on_key)
        self._combo.bind("<FocusOut>", lambda e: self._combo.after(150, self._ac.hide))
        self._ac = _AutocompletePopup(self._combo)

        add_btn = tk.Label(
            self.frame, text="+", fg=TEXT, bg=BG,
            font=("Segoe UI", 12, "bold"), cursor="hand2", padx=6)
        add_btn.pack(side=tk.LEFT)
        add_btn.bind("<Button-1>", lambda e: self._create_new())

    def _on_key(self, event):
        if event.keysym in ("Return", "Escape", "Tab", "Up", "Down"):
            if event.keysym in ("Escape", "Return", "Tab"):
                self._ac.hide()
            return
        query = self._var.get().strip().lower()
        if not query:
            self._combo["values"] = self._all_names
            self._ac.hide()
        else:
            filtered = [n for n in self._all_names
                        if n == "(нет)" or query in n.lower()]
            self._combo["values"] = filtered
            self._ac.show(filtered)

    def _create_new(self):
        self._popup_win._show_new_activity_dialog(callback=self._on_created)

    def _on_created(self, new_id: str):
        row = self._db_conn.execute(
            "SELECT id, name FROM activities WHERE id = ?", (new_id,)
        ).fetchone()
        if row:
            self._all_names.append(row["name"])
            self._all_ids.append(row["id"])
            self._combo["values"] = self._all_names
            self._var.set(row["name"])

    def get_selected_id(self) -> str:
        name = self._var.get().strip()
        if name in self._all_names:
            return self._all_ids[self._all_names.index(name)]
        return ""


# ── PopupWindow ──────────────────────────────────────────────────────────

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
        on_import_transcript: Callable[[str, str], None] | None = None,  # используется в web-UI
        on_url_import: Callable[[str], None] | None = None,
        on_title_changed: Callable[[str, str], None] | None = None,
        on_whisper_model_changed: Callable[[str], None] | None = None,
        on_mic_changed: Callable[[int], None] | None = None,
        on_mic_test_start: Callable[[int], None] | None = None,
        on_mic_test_stop: Callable[[], None] | None = None,
        on_settings: Callable[[], dict] | None = None,
        on_settings_changed: Callable[[dict], None] | None = None,
        on_obsidian: Callable[[str], None] | None = None,
        on_summarize: Callable[[str], None] | None = None,  # используется в web-UI
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
        self._on_import_transcript = on_import_transcript
        self._on_url_import = on_url_import
        self._on_title_changed = on_title_changed
        self._on_whisper_model_changed = on_whisper_model_changed
        self._on_mic_changed = on_mic_changed
        self._on_mic_test_start = on_mic_test_start
        self._on_mic_test_stop = on_mic_test_stop
        self._on_settings = on_settings
        self._on_settings_changed = on_settings_changed
        self._on_obsidian = on_obsidian
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
        self._item_status: dict[str, str] = {}
        self._all_sessions: list[RecordingSession] = []
        self._preview_visible = False
        self._md_viewer: MarkdownViewer | None = None
        self._preview_mode_var: tk.StringVar | None = None
        self._preview_title_var: tk.StringVar | None = None
        self._paned: ttk.PanedWindow | None = None
        self._preview_outer: ttk.Frame | None = None
        self._pulse_timer_id = None
        self._pulse_on = False
        self._iid_by_folder: dict[str, str] = {}
        self._transcription_progress: dict[str, float] = {}
        self._summary_running = False
        self._summary_iid: str | None = None
        self._summary_anim_pos = 0
        self._view_var: tk.StringVar | None = None
        self._recordings_frame: ttk.Frame | None = None
        self._activities_frame: ttk.Frame | None = None
        self._activities_tree: ttk.Treeview | None = None
        self._activities_folder_keys: dict[str, str] = {}
        self._activities_task_ids: dict[str, int] = {}
        self._act_sub_view: tk.StringVar | None = None
        self._activities_data: list[dict] = []
        self._folder_to_activity: dict[str, str] = {}
        self._db_conn = db.get_connection()
        db.init_db(self._db_conn)
        db.migrate_from_json(self._db_conn)
        self._tasks_tree: ttk.Treeview | None = None
        self._tasks_frame: ttk.Frame | None = None
        self._task_filter_var: tk.StringVar | None = None
        self._task_responsible_var: tk.StringVar | None = None
        self._task_responsible_combo: ttk.Combobox | None = None
        self._tasks_iid_to_id: dict[str, int] = {}

    # ── Window ───────────────────────────────────────────────────────────

    def show(self):
        if self._root is not None:
            self._root.deiconify()
            self._root.lift()
            return

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "meetingscribe.app")
        except Exception:
            pass

        self._root = tk.Tk()
        self._root.title("MeetingScribe")
        self._root.geometry("720x680")
        self._root.resizable(True, True)
        self._root.minsize(580, 520)
        self._root.configure(bg=BG)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.bind("<Control-f>", lambda e: self._toggle_preview_search())

        assets = Path(__file__).resolve().parent.parent.parent / "assets"
        icon_path = assets / "icon.ico"
        if icon_path.exists():
            self._root.iconbitmap(str(icon_path))
        try:
            from PIL import Image, ImageTk
            icons = []
            for sz in (256, 48, 32, 16):
                img_path = assets / f"icon_{sz}.png"
                if img_path.exists():
                    icons.append(ImageTk.PhotoImage(Image.open(img_path)))
            if icons:
                self._root.iconphoto(True, *icons)
                self._app_icons = icons
        except Exception:
            pass

        _apply_dark_theme(self._root)
        _dark_titlebar(self._root)

        self._paned = ttk.PanedWindow(self._root, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True)

        main = ttk.Frame(self._paned, padding=12)
        self._paned.add(main, weight=0)

        self._build_recording_section(main)
        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        self._build_list_section(main)

        self._preview_outer = self._build_preview_panel(self._paned)

    def _on_close(self):
        if self._on_quit:
            self._on_quit()
        elif self._root:
            self._root.withdraw()

    # ── Recording section ────────────────────────────────────────────────

    def _build_recording_section(self, parent):
        row1 = ttk.Frame(parent)
        row1.pack(fill=tk.X, pady=(0, 6))

        _IconBtn(row1, ICO_SETTINGS, "Настройки",
                 command=self._open_settings).pack(side=tk.RIGHT)
        _IconBtn(row1, ICO_SPLITVIEW, "Панель просмотра",
                 command=self._toggle_preview).pack(side=tk.RIGHT)

        ttk.Label(row1, text="Язык:", style="Dim.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self._lang_var = tk.StringVar(value=LANGUAGES[0][0])
        self._lang_combo = ttk.Combobox(
            row1, textvariable=self._lang_var,
            values=[l[0] for l in LANGUAGES], state="readonly", width=10)
        self._lang_combo.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(row1, text="Тип:", style="Dim.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self._type_var = tk.StringVar(value=MEETING_TYPES[0][0])
        self._type_combo = ttk.Combobox(
            row1, textvariable=self._type_var,
            values=[t[0] for t in MEETING_TYPES], state="readonly", width=18)
        self._type_combo.pack(side=tk.LEFT, padx=(0, 12))
        self._type_combo.bind("<<ComboboxSelected>>", self._on_type_selected)

        ttk.Label(row1, text="Модель:", style="Dim.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self._whisper_model_var = tk.StringVar(value=self._initial_whisper_model)
        self._whisper_model_combo = ttk.Combobox(
            row1, textvariable=self._whisper_model_var,
            values=WHISPER_MODELS, state="readonly", width=9)
        self._whisper_model_combo.pack(side=tk.LEFT)
        self._whisper_model_combo.bind("<<ComboboxSelected>>", self._on_whisper_model_selected)

        row2 = ttk.Frame(parent)
        row2.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(row2, text="Микрофон:", style="Dim.TLabel").pack(side=tk.LEFT, padx=(0, 4))

        mic_names = [d["name"] for d in self._mic_devices]
        preselect = ""
        if mic_names:
            preselect = mic_names[0]
            if self._initial_mic_name in mic_names:
                preselect = self._initial_mic_name

        self._mic_var = tk.StringVar(value=preselect)
        self._mic_combo = ttk.Combobox(
            row2, textvariable=self._mic_var,
            values=mic_names, state="readonly", width=36)
        self._mic_combo.pack(side=tk.LEFT, padx=(0, 6))
        self._mic_combo.bind("<<ComboboxSelected>>", self._on_mic_selected)

        self._test_btn_var = tk.StringVar(value="Тест")
        self._test_btn = ttk.Button(
            row2, textvariable=self._test_btn_var,
            command=self._toggle_mic_test, style="Sm.TButton", width=7)
        self._test_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._level_bar = ttk.Progressbar(
            row2, orient=tk.HORIZONTAL, length=120,
            mode="determinate", maximum=100)
        self._level_bar.pack(side=tk.LEFT)

        row3 = ttk.Frame(parent)
        row3.pack(fill=tk.X)

        self._btn_var = tk.StringVar(value="Начать запись")
        self._btn = _IconBtn(
            row3, ICO_RECORD, "Начать запись",
            command=self._toggle_recording,
            fg=ACCENT, fg_hover=ACCENT_HI, font_size=14)
        self._btn.pack(side=tk.LEFT, padx=(0, 4))

        self._mic_btn = _IconBtn(
            row3, ICO_MIC, "Запись с микрофона",
            command=self._start_mic_only, font_size=14)
        self._mic_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._transcribe_btn = _IconBtn(
            row3, ICO_CAPTION, "Транскрибировать",
            command=self._transcribe_selected, fg=GREEN, fg_hover="#a3e9b1")
        self._transcribe_btn.set_enabled(False)
        self._transcribe_btn.pack(side=tk.LEFT, padx=(30, 1))

        self._summary_btn = _IconBtn(
            row3, ICO_SUMMARY, "Саммари (Claude)",
            command=self._run_summary, fg=GREEN, fg_hover="#a3e9b1")
        self._summary_btn.set_enabled(False)
        self._summary_btn.pack(side=tk.LEFT, padx=(0, 10))

        self._status_var = tk.StringVar(value="")
        self._status_label = ttk.Label(
            row3, textvariable=self._status_var, style="Status.TLabel")
        self._status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ── List section ─────────────────────────────────────────────────────

    def _build_list_section(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill=tk.X, pady=(0, 4))

        self._view_var = tk.StringVar(value="recordings")
        for label, value in [("Записи", "recordings"),
                             ("Активности", "activities"),
                             ("Задачи", "tasks")]:
            ttk.Radiobutton(
                header, text=label, variable=self._view_var,
                value=value, style="Toolbutton",
                command=self._switch_view,
            ).pack(side=tk.LEFT, padx=(0, 2))

        self._import_frame = ttk.Frame(header)
        self._import_frame.pack(side=tk.RIGHT)
        _IconBtn(self._import_frame, ICO_LINK, "Импорт по ссылке",
                 command=self._import_from_url).pack(side=tk.RIGHT, padx=(2, 0))
        _IconBtn(self._import_frame, ICO_PAGE, "Импорт из файла",
                 command=self._import_recording).pack(side=tk.RIGHT, padx=(2, 0))
        ttk.Label(self._import_frame, text="Импорт", style="Dim.TLabel").pack(
            side=tk.RIGHT, padx=(8, 2))

        # ── Recordings view ──
        self._recordings_frame = ttk.Frame(parent)
        self._recordings_frame.pack(fill=tk.BOTH, expand=True)
        self._build_recordings_view(self._recordings_frame)

        # ── Activities view (hidden initially) ──
        self._activities_frame = ttk.Frame(parent)
        self._build_activities_view(self._activities_frame)

        # ── Tasks view (hidden initially) ──
        self._tasks_frame = ttk.Frame(parent)
        self._build_tasks_view(self._tasks_frame)

    def _build_recordings_view(self, parent):
        tabs = ttk.Frame(parent)
        tabs.pack(fill=tk.X, pady=(0, 4))

        self._tab_var = tk.StringVar(value="all")
        for label, value in [("Все", "all"), ("Работа", "work"),
                             ("English", "english"), ("Личное", "personal"),
                             ("Внешние", "external")]:
            ttk.Radiobutton(
                tabs, text=label, variable=self._tab_var, value=value,
                style="Toolbutton", command=self._apply_filter,
            ).pack(side=tk.LEFT, padx=(0, 2))

        _IconBtn(tabs, ICO_REFRESH, "Обновить список",
                 command=self._reload_list).pack(side=tk.RIGHT)

        actions = ttk.Frame(parent)
        actions.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))

        self._folder_btn = _IconBtn(
            actions, ICO_FOLDER, "Открыть папку",
            command=self._open_selected_folder)
        self._folder_btn.set_enabled(False)
        self._folder_btn.pack(side=tk.LEFT, padx=(0, 1))

        self._obsidian_btn = _IconBtn(
            actions, ICO_SHARE, "Отправить в Obsidian",
            command=self._send_to_obsidian)
        self._obsidian_btn.set_enabled(False)
        self._obsidian_btn.pack(side=tk.LEFT, padx=(0, 1))

        self._delete_btn = _IconBtn(
            actions, ICO_DELETE, "Удалить",
            command=self._delete_selected)
        self._delete_btn.set_enabled(False)
        self._delete_btn.pack(side=tk.LEFT)

        self._preview_btn_var = tk.StringVar(value=ICO_PLAY)
        self._preview_btn = _IconBtn(
            actions, ICO_PLAY, "Просмотр",
            command=self._toggle_preview)
        self._preview_btn.pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("status", "date", "title", "activity", "duration", "type")
        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            height=10, selectmode="browse")

        self._tree.heading("status", text="")
        self._tree.heading("date", text="Дата")
        self._tree.heading("title", text="Название")
        self._tree.heading("activity", text="Активность")
        self._tree.heading("duration", text="⏱")
        self._tree.heading("type", text="Тип")

        self._tree.column("status", width=28, minwidth=28, stretch=False, anchor="center")
        self._tree.column("date", width=80, minwidth=68, stretch=False)
        self._tree.column("title", width=200, minwidth=100)
        self._tree.column("activity", width=120, minwidth=60)
        self._tree.column("duration", width=68, minwidth=52, stretch=False, anchor="e")
        self._tree.column("type", width=38, minwidth=32, stretch=False, anchor="center")

        self._tree.tag_configure("done", foreground=TEXT)
        self._tree.tag_configure("recording", foreground=RED)
        self._tree.tag_configure("processing", foreground=TEXT_SEC)
        self._tree.tag_configure("pulse_on", foreground=GREEN)
        self._tree.tag_configure("error", foreground=RED)
        self._tree.tag_configure("imported", foreground=BLUE)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<<TreeviewSelect>>", self._on_selection_changed)
        self._tree.bind("<Double-1>", self._on_tree_double_click)
        self._tree.bind("<Button-3>", self._on_recording_right_click)
        self._title_editor: tk.Entry | None = None

    def _build_activities_view(self, parent):
        sub_tabs = ttk.Frame(parent)
        sub_tabs.pack(fill=tk.X, pady=(0, 4))

        self._act_sub_view = tk.StringVar(value="meetings")
        for label, value in [("Встречи", "meetings"), ("Задачи", "tasks")]:
            ttk.Radiobutton(
                sub_tabs, text=label, variable=self._act_sub_view,
                value=value, style="Toolbutton",
                command=self._load_activities,
            ).pack(side=tk.LEFT, padx=(0, 2))

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("count", "last_date")
        self._activities_tree = ttk.Treeview(
            tree_frame, columns=columns, show="tree headings",
            height=10, selectmode="browse", style="Sidebar.Treeview")

        self._activities_tree.heading("#0", text="Активность / Встреча", anchor="w")
        self._activities_tree.heading("count", text="Встреч")
        self._activities_tree.heading("last_date", text="Последняя")

        self._activities_tree.column("#0", width=340, minwidth=180)
        self._activities_tree.column("count", width=60, minwidth=50, stretch=False, anchor="center")
        self._activities_tree.column("last_date", width=85, minwidth=70, stretch=False)

        self._activities_tree.tag_configure("activity", foreground=TEXT)
        self._activities_tree.tag_configure("activity_closed", foreground=TEXT_DIS)
        self._activities_tree.tag_configure("meeting", foreground=TEXT)
        self._activities_tree.tag_configure("new", foreground=TEXT)
        self._activities_tree.tag_configure("in_progress", foreground=BLUE)
        self._activities_tree.tag_configure("hold", foreground=YELLOW)
        self._activities_tree.tag_configure("done", foreground=GREEN)
        self._activities_tree.tag_configure("cancelled", foreground=TEXT_SEC)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                  command=self._activities_tree.yview)
        self._activities_tree.configure(yscrollcommand=scrollbar.set)
        self._activities_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._activities_tree.bind("<<TreeviewSelect>>", self._on_activity_selection)
        self._activities_tree.bind("<Button-3>", self._on_activity_right_click)

        self._drag_source_iid: str | None = None
        self._activities_tree.bind("<ButtonPress-1>", self._on_act_drag_start)
        self._activities_tree.bind("<B1-Motion>", self._on_act_drag_motion)
        self._activities_tree.bind("<ButtonRelease-1>", self._on_act_drag_drop)

        actions = ttk.Frame(parent)
        actions.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))

        self._act_folder_btn = _IconBtn(
            actions, ICO_FOLDER, "Открыть папку",
            command=self._open_activity_folder)
        self._act_folder_btn.set_enabled(False)
        self._act_folder_btn.pack(side=tk.LEFT, padx=(0, 1))

        _IconBtn(
            actions, ICO_ADD, "Новая тема",
            command=self._create_new_activity,
        ).pack(side=tk.LEFT, padx=(0, 1))

        self._act_preview_btn = _IconBtn(
            actions, ICO_PLAY, "Просмотр",
            command=self._toggle_preview)
        self._act_preview_btn.pack(side=tk.RIGHT)

    def _switch_view(self):
        view = self._view_var.get()
        for frame in (self._recordings_frame, self._activities_frame, self._tasks_frame):
            if frame:
                frame.pack_forget()
        self._import_frame.pack_forget()

        if view == "recordings":
            self._recordings_frame.pack(fill=tk.BOTH, expand=True)
            self._import_frame.pack(side=tk.RIGHT)
        elif view == "activities":
            self._activities_frame.pack(fill=tk.BOTH, expand=True)
            self._load_activities()
        elif view == "tasks":
            self._tasks_frame.pack(fill=tk.BOTH, expand=True)
            self._load_tasks()
        self._load_preview_content()

    def _load_activities_data(self):
        self._activities_data = db.get_activities(self._db_conn)
        self._folder_to_activity = db.get_folder_activity_map(self._db_conn)

    def _load_activities(self):
        if not self._activities_tree:
            return

        open_nodes = {iid for iid in self._activities_tree.get_children()
                      if self._activities_tree.item(iid, "open")}
        selected = self._activities_tree.selection()
        selected_iid = selected[0] if selected else None

        self._activities_tree.delete(*self._activities_tree.get_children())
        self._activities_folder_keys.clear()
        self._activities_task_ids.clear()

        self._load_activities_data()
        sub = self._act_sub_view.get() if self._act_sub_view else "meetings"

        if sub == "tasks":
            self._load_activities_tasks_sub()
        else:
            self._load_activities_meetings_sub()

        for iid in open_nodes:
            if self._activities_tree.exists(iid):
                self._activities_tree.item(iid, open=True)
        if selected_iid and self._activities_tree.exists(selected_iid):
            self._activities_tree.selection_set(selected_iid)
            self._activities_tree.see(selected_iid)

    def _load_activities_meetings_sub(self):
        self._activities_tree.heading("count", text="Встреч")
        self._activities_tree.heading("last_date", text="Последняя")
        task_counts = db.get_task_counts_by_activity(self._db_conn)

        for activity in self._activities_data:
            act_id = activity["id"]
            act_iid = f"act_{act_id}"
            is_closed = activity.get("status") == "closed"
            tc = task_counts.get(act_id, {})
            active_tasks = tc.get("active", 0)
            count_text = str(activity["meeting_count"])
            if active_tasks:
                count_text += f" / {active_tasks}✓"
            name = activity["name"]
            if is_closed:
                name = f"✓  {name}"
            tag = "activity_closed" if is_closed else "activity"
            self._activities_tree.insert(
                "", tk.END, iid=act_iid,
                text=name,
                values=(count_text, activity.get("last_meeting") or ""),
                open=False, tags=(tag,))

            meetings = db.get_activity_meetings(self._db_conn, act_id)
            for meeting in meetings:
                m_iid = f"m_{act_id}_{meeting['id']}"
                self._activities_tree.insert(
                    act_iid, tk.END, iid=m_iid,
                    text=f"{meeting['date']}  {meeting.get('topic', '')}",
                    values=("", meeting.get("time", "")),
                    tags=("meeting",))
                self._activities_folder_keys[m_iid] = meeting.get("folder", "")

    def _load_activities_tasks_sub(self):
        self._activities_tree.heading("count", text="Задач")
        self._activities_tree.heading("last_date", text="Активных")
        task_counts = db.get_task_counts_by_activity(self._db_conn)

        for activity in self._activities_data:
            act_id = activity["id"]
            act_iid = f"act_{act_id}"
            is_closed = activity.get("status") == "closed"
            tc = task_counts.get(act_id, {})
            total = tc.get("total", 0)
            active = tc.get("active", 0)
            if total == 0:
                continue
            name = activity["name"]
            if is_closed:
                name = f"✓  {name}"
            tag = "activity_closed" if is_closed else "activity"
            self._activities_tree.insert(
                "", tk.END, iid=act_iid,
                text=name,
                values=(str(total), str(active)),
                open=False, tags=(tag,))

            tasks = db.get_tasks(self._db_conn, activity_id=act_id)
            for task in tasks:
                t_iid = f"t_{act_id}_{task['id']}"
                status_display = db.TASK_STATUS_DISPLAY.get(task["status"], task["status"])
                responsible = task.get("responsible", "")
                label = task["title"]
                if responsible:
                    label = f"[{responsible}] {label}"
                self._activities_tree.insert(
                    act_iid, tk.END, iid=t_iid,
                    text=f"{status_display}  {label}",
                    values=("", task.get("created_at", "")),
                    tags=(task["status"],))
                self._activities_task_ids[t_iid] = task["id"]

    def _on_activity_selection(self, event):
        selected = self._activities_tree.selection()
        if not selected:
            self._act_folder_btn.config(state="disabled")
            self._load_preview_content()
            return

        iid = selected[0]
        has_folder = iid in self._activities_folder_keys
        self._act_folder_btn.config(state="normal" if has_folder else "disabled")
        self._load_preview_content()

    def _open_activity_folder(self):
        selected = self._activities_tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._activities_folder_keys.get(iid)
        if folder_key:
            self._on_open_folder(folder_key)

    # ── Tasks view ────────────────────────────────────────────────────────

    def _build_tasks_view(self, parent):
        filter_frame = ttk.Frame(parent)
        filter_frame.pack(fill=tk.X, pady=(0, 4))

        self._task_filter_var = tk.StringVar(value="active")
        for label, value in [("Активные", "active"), ("Все", "all"),
                             ("Завершённые", "done")]:
            ttk.Radiobutton(
                filter_frame, text=label, variable=self._task_filter_var,
                value=value, style="Toolbutton",
                command=self._load_tasks,
            ).pack(side=tk.LEFT, padx=(0, 2))

        ttk.Label(filter_frame, text="  Кто:").pack(side=tk.LEFT, padx=(8, 2))
        self._task_responsible_var = tk.StringVar(value="Все")
        self._task_responsible_combo = ttk.Combobox(
            filter_frame, textvariable=self._task_responsible_var,
            width=28)
        self._task_responsible_combo["values"] = ["Все"]
        self._task_responsible_combo.pack(side=tk.LEFT, padx=(0, 2))
        self._task_responsible_combo.bind("<<ComboboxSelected>>", lambda e: self._apply_responsible_filter())
        self._task_responsible_combo.bind("<KeyRelease>", self._on_responsible_filter_key)
        self._task_responsible_combo.bind("<FocusOut>",
            lambda e: self._task_responsible_combo.after(150, self._resp_ac.hide))
        self._task_all_responsible_values: list[str] = ["Все"]
        self._resp_ac = _AutocompletePopup(self._task_responsible_combo)

        actions = ttk.Frame(parent)
        actions.pack(side=tk.BOTTOM, fill=tk.X, pady=(4, 0))

        _IconBtn(
            actions, ICO_ADD, "Новая задача",
            command=self._create_task_dialog,
        ).pack(side=tk.LEFT, padx=(0, 1))

        self._task_status_btn = _IconBtn(
            actions, ICO_CHEVDOWN, "Изменить статус",
            command=self._change_task_status)
        self._task_status_btn.set_enabled(False)
        self._task_status_btn.pack(side=tk.LEFT, padx=(0, 1))

        self._task_edit_btn = _IconBtn(
            actions, ICO_EDIT, "Изменить задачу",
            command=self._edit_task_dialog)
        self._task_edit_btn.set_enabled(False)
        self._task_edit_btn.pack(side=tk.LEFT, padx=(0, 1))

        self._task_del_btn = _IconBtn(
            actions, ICO_DELETE, "Удалить",
            command=self._delete_task)
        self._task_del_btn.set_enabled(False)
        self._task_del_btn.pack(side=tk.LEFT)

        self._tasks_preview_btn = _IconBtn(
            actions, ICO_PLAY, "Просмотр",
            command=self._toggle_preview)
        self._tasks_preview_btn.pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("status", "title", "responsible", "deadline", "created", "activity")
        self._tasks_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            height=10, selectmode="browse")

        self._tasks_tree.heading("status", text="Статус")
        self._tasks_tree.heading("title", text="Задача")
        self._tasks_tree.heading("responsible", text="Кто")
        self._tasks_tree.heading("deadline", text="Срок")
        self._tasks_tree.heading("created", text="Создана")
        self._tasks_tree.heading("activity", text="Тема")

        self._tasks_tree.column("status", width=85, minwidth=70, stretch=False)
        self._tasks_tree.column("title", width=220, minwidth=120)
        self._tasks_tree.column("responsible", width=140, minwidth=80, stretch=False)
        self._tasks_tree.column("deadline", width=80, minwidth=60, stretch=False)
        self._tasks_tree.column("created", width=80, minwidth=60, stretch=False)
        self._tasks_tree.column("activity", width=120, minwidth=60)

        self._tasks_tree.tag_configure("new", foreground=TEXT)
        self._tasks_tree.tag_configure("in_progress", foreground=BLUE)
        self._tasks_tree.tag_configure("hold", foreground=YELLOW)
        self._tasks_tree.tag_configure("done", foreground=GREEN)
        self._tasks_tree.tag_configure("cancelled", foreground=TEXT_SEC)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                  command=self._tasks_tree.yview)
        self._tasks_tree.configure(yscrollcommand=scrollbar.set)
        self._tasks_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tasks_tree.bind("<<TreeviewSelect>>", self._on_task_selection)
        self._tasks_tree.bind("<Button-3>", self._on_task_right_click)

    def _on_responsible_filter_key(self, event):
        if event.keysym in ("Return", "Escape", "Tab", "Up", "Down"):
            self._resp_ac.hide()
            if event.keysym == "Return":
                self._apply_responsible_filter()
            return
        query = self._task_responsible_var.get().strip().lower()
        if not query:
            self._task_responsible_combo["values"] = self._task_all_responsible_values
            self._resp_ac.hide()
        else:
            filtered = [v for v in self._task_all_responsible_values
                        if v == "Все" or query in v.lower()]
            self._task_responsible_combo["values"] = filtered
            self._resp_ac.show(filtered)

    def _apply_responsible_filter(self):
        self._task_responsible_combo.selection_clear()
        self._load_tasks()

    def _load_tasks(self):
        if not self._tasks_tree:
            return
        self._tasks_tree.delete(*self._tasks_tree.get_children())
        self._tasks_iid_to_id.clear()

        filt = self._task_filter_var.get() if self._task_filter_var else "active"
        if filt == "active":
            tasks = db.get_tasks(self._db_conn, exclude_done=True)
        elif filt == "done":
            tasks = [t for t in db.get_tasks(self._db_conn)
                     if t["status"] in ("done", "cancelled")]
        else:
            tasks = db.get_tasks(self._db_conn)

        all_responsible = sorted({t.get("responsible", "") for t in tasks} - {""})
        self._task_all_responsible_values = ["Все"] + all_responsible
        self._task_responsible_combo["values"] = self._task_all_responsible_values

        resp_filter = self._task_responsible_var.get() if self._task_responsible_var else "Все"
        if resp_filter != "Все":
            tasks = [t for t in tasks if t.get("responsible", "") == resp_filter]

        resp_comments = {r["name"]: r["comment"]
                         for r in db.get_all_responsibles(self._db_conn) if r["comment"]}

        for i, task in enumerate(tasks):
            iid = str(i)
            status_display = db.TASK_STATUS_DISPLAY.get(task["status"], task["status"])
            created = task.get("created_at", "")
            if created and len(created) > 10:
                created = created[:10]
            resp = task.get("responsible", "")
            resp_display = resp
            comment = resp_comments.get(resp, "")
            if comment:
                resp_display = f"{resp} ({comment})"
            self._tasks_tree.insert("", tk.END, iid=iid, values=(
                status_display,
                task["title"],
                resp_display,
                task.get("deadline", ""),
                created,
                task.get("activity_name", ""),
            ), tags=(task["status"],))
            self._tasks_iid_to_id[iid] = task["id"]

    def _on_task_selection(self, event):
        selected = self._tasks_tree.selection()
        state = "normal" if selected else "disabled"
        self._task_status_btn.config(state=state)
        self._task_edit_btn.config(state=state)
        self._task_del_btn.config(state=state)

    def _on_task_right_click(self, event):
        iid = self._tasks_tree.identify_row(event.y)
        if not iid:
            return
        self._tasks_tree.selection_set(iid)
        task_id = self._tasks_iid_to_id.get(iid)
        if not task_id:
            return

        items = []
        for status_key, status_label in db.TASK_STATUS_DISPLAY.items():
            items.append((f"→ {status_label}",
                          lambda s=status_key, tid=task_id: self._set_task_status(tid, s)))
        items.append(("Изменить ответственного…",
                      lambda: self._change_responsible_dialog(task_id)))
        items.append(("Переназначить тему…",
                      lambda: self._reassign_task_activity(task_id)))
        items.append(("Изменить…", lambda: self._edit_task_dialog()))
        items.append(("Удалить", lambda: self._delete_task()))
        self._show_context_menu(event.x_root, event.y_root, items)

    def _set_task_status(self, task_id: int, status: str):
        db.update_task(self._db_conn, task_id, status=status)
        self._load_tasks()

    def _change_responsible_dialog(self, task_id: int):
        task_row = self._db_conn.execute(
            "SELECT responsible FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        current_resp = task_row["responsible"] if task_row else ""

        all_resp = db.get_all_responsibles(self._db_conn)
        all_names = [r["name"] for r in all_resp]
        comments_map = {r["name"]: r["comment"] for r in all_resp}

        dialog = tk.Toplevel(self._root)
        dialog.title("Изменить ответственного")
        self._position_dialog(dialog, 460, 300)
        dialog.configure(bg=BG)
        dialog.transient(self._root)
        dialog.grab_set()
        _dark_titlebar(dialog)
        self._set_dialog_icon(dialog)

        ttk.Label(dialog, text=f"Текущий: {current_resp or '(не указан)'}",
                  style="Dim.TLabel").pack(anchor="w", padx=12, pady=(10, 4))

        apply_all_var = tk.BooleanVar(value=True)

        ttk.Label(dialog, text="Введите имя или выберите из списка:",
                  style="Dim.TLabel").pack(anchor="w", padx=12, pady=(4, 0))

        picker_frame = ttk.Frame(dialog)
        picker_frame.pack(fill=tk.X, padx=12, pady=(2, 4))

        resp_var = tk.StringVar(value=current_resp)
        resp_combo = ttk.Combobox(picker_frame, textvariable=resp_var,
                                  values=all_names, width=36)
        resp_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        resp_ac = _AutocompletePopup(resp_combo)

        def _on_resp_key(event):
            if event.keysym in ("Return", "Escape", "Tab", "Up", "Down"):
                resp_ac.hide()
                return
            q = resp_var.get().strip().lower()
            if not q:
                resp_combo["values"] = all_names
                resp_ac.hide()
            else:
                filtered = [n for n in all_names if q in n.lower()]
                resp_combo["values"] = filtered
                resp_ac.show(filtered)

        resp_combo.bind("<KeyRelease>", _on_resp_key)
        resp_combo.bind("<FocusOut>",
                        lambda e: resp_combo.after(150, resp_ac.hide))

        def _on_resp_selected(event):
            selected = resp_var.get()
            comment_var.set(comments_map.get(selected, ""))

        resp_combo.bind("<<ComboboxSelected>>", _on_resp_selected)

        if current_resp:
            ttk.Checkbutton(
                dialog, text="Применить ко всем задачам с таким ответственным",
                variable=apply_all_var,
            ).pack(anchor="w", padx=12, pady=(2, 4))

        ttk.Label(dialog, text="Комментарий (роль, описание):",
                  style="Dim.TLabel").pack(anchor="w", padx=12, pady=(4, 0))
        comment_var = tk.StringVar(value=comments_map.get(current_resp, ""))
        comment_entry = ttk.Entry(dialog, textvariable=comment_var, width=40)
        comment_entry.pack(fill=tk.X, padx=12, pady=(2, 8))

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        def do_save(event=None):
            new_name = resp_var.get().strip()
            if not new_name:
                return
            comment = comment_var.get().strip()
            if apply_all_var.get() and current_resp and new_name != current_resp:
                db.rename_responsible(self._db_conn, current_resp, new_name)
            elif new_name != current_resp:
                db.update_task(self._db_conn, task_id, responsible=new_name)
            old_comment = comments_map.get(new_name, comments_map.get(current_resp, ""))
            if comment != old_comment:
                db.set_responsible_comment(self._db_conn, new_name, comment)
            dialog.destroy()
            self._load_tasks()

        dialog.bind("<Control-Return>", do_save)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        ttk.Button(btn_frame, text="Сохранить", command=do_save,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                   style="Sm.TButton").pack(side=tk.LEFT)

        resp_combo.focus_set()

    def _change_task_status(self):
        selected = self._tasks_tree.selection()
        if not selected:
            return
        iid = selected[0]
        task_id = self._tasks_iid_to_id.get(iid)
        if not task_id:
            return

        bbox = self._tasks_tree.bbox(iid, column="status")
        if not bbox:
            return
        x = self._tasks_tree.winfo_rootx() + bbox[0]
        y = self._tasks_tree.winfo_rooty() + bbox[1] + bbox[3]

        items = [(label, lambda s=key, tid=task_id: self._set_task_status(tid, s))
                 for key, label in db.TASK_STATUS_DISPLAY.items()]
        self._show_context_menu(x, y, items)

    def _create_task_dialog(self):
        self._show_task_editor()

    def _edit_task_dialog(self):
        selected = self._tasks_tree.selection()
        if not selected:
            return
        task_id = self._tasks_iid_to_id.get(selected[0])
        if not task_id:
            return
        tasks = db.get_tasks(self._db_conn)
        task = None
        for t in tasks:
            if t["id"] == task_id:
                task = t
                break
        if task:
            self._show_task_editor(task)

    def _position_dialog(self, dialog: tk.Toplevel, width: int, height: int):
        """Center dialog on the parent window, clamped to monitor work area."""
        self._root.update_idletasks()
        rx = self._root.winfo_x()
        ry = self._root.winfo_y()
        rw = self._root.winfo_width()
        rh = self._root.winfo_height()
        cx = rx + rw // 2
        cy = ry + rh // 2
        x = cx - width // 2
        y = cy - height // 2
        ml, mt, mr, mb = _get_monitor_workarea(cx, cy)
        if x < ml:
            x = ml
        if x + width > mr:
            x = mr - width
        if y < mt:
            y = mt
        if y + height > mb:
            y = mb - height
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def _show_task_editor(self, task: dict | None = None):
        is_edit = task is not None
        dialog = tk.Toplevel(self._root)
        dialog.title("Изменить задачу" if is_edit else "Новая задача")
        self._position_dialog(dialog, 480, 460 if is_edit else 380)
        dialog.resizable(True, True)
        dialog.configure(bg=BG)
        dialog.transient(self._root)
        dialog.grab_set()
        _dark_titlebar(dialog)
        self._set_dialog_icon(dialog)

        fields = {}

        ttk.Label(dialog, text="Задача:", style="Dim.TLabel").pack(
            anchor="w", padx=12, pady=(8, 0))
        title_entry = ttk.Entry(dialog, width=55)
        title_entry.pack(fill=tk.X, padx=12, pady=(0, 2))
        if is_edit:
            title_entry.insert(0, task.get("title", ""))
        fields["title"] = title_entry

        ttk.Label(dialog, text="Описание:", style="Dim.TLabel").pack(
            anchor="w", padx=12, pady=(4, 0))
        desc_entry = ttk.Entry(dialog, width=55)
        desc_entry.pack(fill=tk.X, padx=12, pady=(0, 2))
        if is_edit:
            desc_entry.insert(0, task.get("description", ""))
        fields["description"] = desc_entry

        row_frame = ttk.Frame(dialog)
        row_frame.pack(fill=tk.X, padx=12, pady=(4, 2))

        left = ttk.Frame(row_frame)
        left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Label(left, text="Ответственный:", style="Dim.TLabel").pack(anchor="w")
        resp_entry = ttk.Entry(left)
        resp_entry.pack(fill=tk.X)
        if is_edit:
            resp_entry.insert(0, task.get("responsible", ""))
        fields["responsible"] = resp_entry

        right = ttk.Frame(row_frame)
        right.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(right, text="Срок:", style="Dim.TLabel").pack(anchor="w")
        deadline_frame = ttk.Frame(right)
        deadline_frame.pack(fill=tk.X)
        deadline_entry = ttk.Entry(deadline_frame)
        deadline_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if is_edit:
            deadline_entry.insert(0, task.get("deadline", ""))
        fields["deadline"] = deadline_entry
        cal_btn = tk.Label(
            deadline_frame, text="", font=("Segoe MDL2 Assets", 11),
            fg=TEXT, bg=BG, cursor="hand2", padx=4)
        cal_btn.pack(side=tk.LEFT)
        cal_btn.bind("<Button-1>", lambda e: _show_calendar_popup(dialog, deadline_entry))

        ttk.Label(dialog, text="Тема:", style="Dim.TLabel").pack(
            anchor="w", padx=12, pady=(6, 0))
        activities = db.get_activities(self._db_conn)
        act_picker = _ActivityPickerWidget(
            dialog, activities, self._db_conn, self,
            allow_none=True,
            selected_name=task.get("activity_name", "") if is_edit else "")
        act_picker.frame.pack(fill=tk.X, padx=12, pady=(0, 2))

        if is_edit:
            status_frame = ttk.Frame(dialog)
            status_frame.pack(fill=tk.X, padx=12, pady=(4, 2))
            ttk.Label(status_frame, text="Статус:", style="Dim.TLabel").pack(
                side=tk.LEFT, padx=(0, 8))
            status_labels = list(db.TASK_STATUS_DISPLAY.values())
            status_var = tk.StringVar(
                value=db.TASK_STATUS_DISPLAY.get(task["status"], "Не начата"))
            ttk.Combobox(status_frame, textvariable=status_var,
                         values=status_labels,
                         state="readonly", width=20).pack(side=tk.LEFT)

        title_entry.focus_set()
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=12, pady=(10, 10))

        def do_save(event=None):
            title = fields["title"].get().strip()
            if not title:
                return
            activity_id = act_picker.get_selected_id()

            if is_edit:
                updates = {
                    "title": title,
                    "description": fields["description"].get().strip(),
                    "responsible": fields["responsible"].get().strip(),
                    "deadline": fields["deadline"].get().strip(),
                    "activity_id": activity_id or None,
                    "status": db.TASK_STATUS_FROM_DISPLAY.get(
                        status_var.get(), task["status"]),
                }
                db.update_task(self._db_conn, task["id"], **updates)
            else:
                from datetime import date
                db.create_task(
                    self._db_conn,
                    title=title,
                    description=fields["description"].get().strip(),
                    responsible=fields["responsible"].get().strip(),
                    deadline=fields["deadline"].get().strip(),
                    activity_id=activity_id,
                    created_at=date.today().isoformat(),
                )
            dialog.destroy()
            self._load_tasks()
            if self._view_var and self._view_var.get() == "activities":
                self._load_activities()

        dialog.bind("<Control-Return>", do_save)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        ttk.Button(btn_frame, text="Сохранить", command=do_save,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                   style="Sm.TButton").pack(side=tk.LEFT)
    def _delete_task(self):
        selected = self._tasks_tree.selection()
        if not selected:
            return
        task_id = self._tasks_iid_to_id.get(selected[0])
        if not task_id:
            return
        confirmed = messagebox.askyesno(
            "Удаление задачи", "Удалить эту задачу?", parent=self._root)
        if confirmed:
            db.delete_task(self._db_conn, task_id)
            self._load_tasks()

    def _reassign_task_activity(self, task_id: int):
        activities = db.get_activities(self._db_conn)
        if not activities:
            return

        current_name = ""
        task_row = self._db_conn.execute(
            "SELECT a.name FROM tasks t LEFT JOIN activities a ON t.activity_id = a.id WHERE t.id = ?",
            (task_id,),
        ).fetchone()
        if task_row and task_row[0]:
            current_name = task_row[0]

        dialog = tk.Toplevel(self._root)
        dialog.title("Переназначить тему")
        self._position_dialog(dialog, 420, 200)
        dialog.configure(bg=BG)
        dialog.transient(self._root)
        dialog.grab_set()
        _dark_titlebar(dialog)
        self._set_dialog_icon(dialog)

        ttk.Label(dialog, text="Начните вводить название темы:", style="Dim.TLabel").pack(
            anchor="w", padx=12, pady=(10, 0))
        act_picker = _ActivityPickerWidget(
            dialog, activities, self._db_conn, self,
            allow_none=False, selected_name=current_name)
        act_picker.frame.pack(fill=tk.X, padx=12, pady=(2, 8))

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        def do_save(event=None):
            act_id = act_picker.get_selected_id()
            if not act_id:
                return
            db.update_task(self._db_conn, task_id, activity_id=act_id)
            dialog.destroy()
            self._load_tasks()

        dialog.bind("<Control-Return>", do_save)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        ttk.Button(btn_frame, text="Сохранить", command=do_save,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                   style="Sm.TButton").pack(side=tk.LEFT)
    # ── Drag and drop in activities tree ────────────────────────────────

    def _on_act_drag_start(self, event):
        iid = self._activities_tree.identify_row(event.y)
        if iid and iid in self._activities_folder_keys:
            self._drag_source_iid = iid
        else:
            self._drag_source_iid = None

    def _on_act_drag_motion(self, event):
        if not self._drag_source_iid:
            return
        target = self._activities_tree.identify_row(event.y)
        if not target:
            self._activities_tree.configure(cursor="no")
            return
        if target.startswith("act_"):
            self._activities_tree.configure(cursor="plus")
        elif target in self._activities_folder_keys:
            parent = self._activities_tree.parent(target)
            if parent and parent.startswith("act_"):
                self._activities_tree.configure(cursor="plus")
            else:
                self._activities_tree.configure(cursor="no")
        else:
            self._activities_tree.configure(cursor="no")

    def _on_act_drag_drop(self, event):
        self._activities_tree.configure(cursor="")
        source = self._drag_source_iid
        self._drag_source_iid = None
        if not source:
            return

        target = self._activities_tree.identify_row(event.y)
        if not target:
            return

        if target.startswith("act_"):
            target_act_id = target[4:]
        elif target in self._activities_folder_keys:
            parent = self._activities_tree.parent(target)
            if parent and parent.startswith("act_"):
                target_act_id = parent[4:]
            else:
                return
        else:
            return

        folder_key = self._activities_folder_keys.get(source, "")
        if not folder_key:
            return
        source_act_id = self._folder_to_activity.get(folder_key, "")
        if source_act_id == target_act_id:
            return

        self._reassign_meeting(folder_key, source_act_id, target_act_id)

    # ── Create new activity ──────────────────────────────────────────────

    def _create_new_activity(self):
        self._show_new_activity_dialog()

    def _show_new_activity_dialog(self, callback=None):
        dialog = tk.Toplevel(self._root)
        dialog.title("Новая тема")
        self._position_dialog(dialog, 400, 180)
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.transient(self._root)
        dialog.grab_set()
        _dark_titlebar(dialog)

        self._set_dialog_icon(dialog)

        ttk.Label(dialog, text="Название темы:", style="Section.TLabel").pack(
            anchor="w", padx=12, pady=(12, 4))
        name_entry = ttk.Entry(dialog, width=50)
        name_entry.pack(fill=tk.X, padx=12, pady=(0, 8))
        name_entry.focus_set()

        ttk.Label(dialog, text="Описание (необязательно):", style="Dim.TLabel").pack(
            anchor="w", padx=12, pady=(0, 4))
        desc_entry = ttk.Entry(dialog, width=50)
        desc_entry.pack(fill=tk.X, padx=12, pady=(0, 12))

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        def do_create(event=None):
            name = name_entry.get().strip()
            if not name:
                return
            new_id = self._make_activity_id(name)
            db.create_activity(self._db_conn, new_id, name,
                               desc_entry.get().strip())
            dialog.destroy()
            if callback:
                callback(new_id)
            elif self._activities_tree:
                self._load_activities()

        name_entry.bind("<Return>", lambda e: desc_entry.focus_set())
        desc_entry.bind("<Return>", do_create)
        dialog.bind("<Control-Return>", do_create)
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        ttk.Button(btn_frame, text="Создать", command=do_create,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                   style="Sm.TButton").pack(side=tk.LEFT)

    @staticmethod
    def _make_activity_id(name: str) -> str:
        tr = {
            'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh',
            'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
            'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts',
            'ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
        }
        result = []
        for ch in name.lower():
            if ch in tr:
                result.append(tr[ch])
            elif ch.isascii() and (ch.isalnum() or ch in '-_'):
                result.append(ch)
            elif ch in ' /—–':
                result.append('-')
        return re.sub(r'-+', '-', ''.join(result)).strip('-')[:50]

    # ── Context menus ────────────────────────────────────────────────────

    _context_menu: tk.Toplevel | None = None

    def _show_context_menu(self, x: int, y: int, items: list[tuple[str, callable]]):
        if self._context_menu:
            self._context_menu.destroy()

        popup = tk.Toplevel(self._root)
        popup.overrideredirect(True)
        popup.configure(bg=BORDER)
        popup.attributes("-topmost", True)
        self._context_menu = popup

        inner = tk.Frame(popup, bg=SURFACE, padx=1, pady=1)
        inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)

        for label, command in items:
            btn = tk.Label(
                inner, text=label, bg=SURFACE, fg=TEXT,
                font=("Segoe UI", 9), anchor="w",
                padx=12, pady=5, cursor="hand2")
            btn.pack(fill=tk.X)
            btn.bind("<Enter>", lambda e, b=btn: b.configure(bg=SELECT))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(bg=SURFACE))
            btn.bind("<Button-1>", lambda e, cmd=command: (popup.destroy(), cmd()))

        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        ml, mt, mr, mb = _get_monitor_workarea(x, y)
        if x + pw > mr:
            x = mr - pw
        if x < ml:
            x = ml
        if y + ph > mb:
            y = mb - ph
        if y < mt:
            y = mt
        popup.geometry(f"+{x}+{y}")

        def close_menu(event=None):
            if self._context_menu:
                self._context_menu.destroy()
                self._context_menu = None

        popup.bind("<FocusOut>", close_menu)
        popup.bind("<Escape>", close_menu)
        self._root.bind("<Button-1>", lambda e: close_menu(), add="+")
        popup.focus_set()

    def _on_activity_right_click(self, event):
        iid = self._activities_tree.identify_row(event.y)
        if not iid:
            return
        self._activities_tree.selection_set(iid)

        items = []

        task_id = self._activities_task_ids.get(iid)
        if task_id:
            for status_key, status_label in db.TASK_STATUS_DISPLAY.items():
                items.append((f"→ {status_label}",
                              lambda s=status_key, tid=task_id: self._set_act_task_status(tid, s)))
            items.append(("Изменить…",
                          lambda tid=task_id: self._edit_act_task(tid)))
            items.append(("Удалить",
                          lambda tid=task_id: self._delete_act_task(tid)))
            self._show_context_menu(event.x_root, event.y_root, items)
            return

        folder_key = self._activities_folder_keys.get(iid)
        if folder_key:
            items.append(("Привязать к другой активности…",
                          lambda: self._show_reassign_dialog(iid)))
            items.append(("Открыть папку",
                          lambda fk=folder_key: self._on_open_folder(fk)))
        else:
            act_id = iid[4:] if iid.startswith("act_") else ""
            if act_id:
                activity = next((a for a in self._activities_data
                                 if a["id"] == act_id), None)
                if activity:
                    if activity.get("status") == "closed":
                        items.append(("→ Открыть тему",
                                      lambda aid=act_id: self._reopen_activity(aid)))
                    else:
                        items.append(("→ Закрыть тему",
                                      lambda aid=act_id: self._close_activity(aid)))
                items.append(("Переименовать тему…",
                              lambda aid=act_id: self._rename_activity(aid)))
                items.append(("Удалить тему…",
                              lambda aid=act_id: self._delete_activity(aid)))

        if items:
            self._show_context_menu(event.x_root, event.y_root, items)

    def _rename_activity(self, activity_id: str):
        current_name = ""
        for a in self._activities_data:
            if a["id"] == activity_id:
                current_name = a["name"]
                break

        dialog = tk.Toplevel(self._root)
        dialog.title("Переименовать тему")
        self._position_dialog(dialog, 400, 120)
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.transient(self._root)
        dialog.grab_set()
        _dark_titlebar(dialog)
        self._set_dialog_icon(dialog)

        ttk.Label(dialog, text="Название темы:", style="Section.TLabel").pack(
            anchor="w", padx=12, pady=(12, 4))
        name_entry = ttk.Entry(dialog, width=50)
        name_entry.pack(fill=tk.X, padx=12, pady=(0, 12))
        name_entry.insert(0, current_name)
        name_entry.select_range(0, tk.END)
        name_entry.focus_set()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        def do_rename(event=None):
            new_name = name_entry.get().strip()
            if not new_name or new_name == current_name:
                dialog.destroy()
                return
            db.rename_activity(self._db_conn, activity_id, new_name)
            self._load_activities()
            dialog.destroy()

        name_entry.bind("<Return>", do_rename)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        ttk.Button(btn_frame, text="Сохранить", command=do_rename,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                   style="Sm.TButton").pack(side=tk.LEFT)

    def _delete_activity(self, activity_id: str):
        activity = None
        for a in self._activities_data:
            if a["id"] == activity_id:
                activity = a
                break
        if not activity:
            return

        meeting_count = activity.get("meeting_count", 0)
        msg = f"Удалить тему «{activity['name']}»?"
        if meeting_count:
            msg += f"\n\n{meeting_count} встреч будут откреплены от этой темы."

        confirmed = messagebox.askyesno(
            "Удаление темы", msg, parent=self._root)
        if not confirmed:
            return

        db.delete_activity(self._db_conn, activity_id)
        self._load_activities()

    def _close_activity(self, activity_id: str):
        can_close, reason = db.can_close_activity(self._db_conn, activity_id)
        if not can_close:
            messagebox.showwarning("Нельзя закрыть", reason, parent=self._root)
            return
        db.update_activity_status(self._db_conn, activity_id, "closed")
        self._load_activities()

    def _reopen_activity(self, activity_id: str):
        db.update_activity_status(self._db_conn, activity_id, "active")
        self._load_activities()

    def _set_act_task_status(self, task_id: int, status: str):
        db.update_task(self._db_conn, task_id, status=status)
        self._load_activities()

    def _edit_act_task(self, task_id: int):
        tasks = db.get_tasks(self._db_conn)
        task = next((t for t in tasks if t["id"] == task_id), None)
        if task:
            self._show_task_editor(task)

    def _delete_act_task(self, task_id: int):
        confirmed = messagebox.askyesno(
            "Удаление задачи", "Удалить задачу?", parent=self._root)
        if confirmed:
            db.delete_task(self._db_conn, task_id)
            self._load_activities()

    def _set_dialog_icon(self, dialog):
        if hasattr(self, "_app_icons") and self._app_icons:
            try:
                dialog.iconphoto(False, *self._app_icons)
                return
            except Exception:
                pass
        icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            dialog.iconbitmap(str(icon_path))

    def _on_recording_right_click(self, event):
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._tree.selection_set(iid)

        folder_key = self._folder_keys.get(iid)
        if not folder_key:
            return

        if not self._folder_to_activity:
            self._load_activities_data()

        items = []
        act_id = self._folder_to_activity.get(folder_key)
        if act_id:
            act_name = ""
            for a in self._activities_data:
                if a["id"] == act_id:
                    act_name = a["name"]
                    break
            items.append((f"Перейти к активности: {act_name}",
                          lambda aid=act_id: self._jump_to_activity(aid)))
        else:
            items.append(("Привязать к активности…",
                          lambda fk=folder_key: self._show_assign_dialog(fk)))

        items.append(("Открыть папку",
                      lambda fk=folder_key: self._on_open_folder(fk)))

        self._show_context_menu(event.x_root, event.y_root, items)

    def _jump_to_activity(self, activity_id: str):
        self._view_var.set("activities")
        self._switch_view()
        act_iid = f"act_{activity_id}"
        if self._activities_tree.exists(act_iid):
            self._activities_tree.item(act_iid, open=True)
            self._activities_tree.selection_set(act_iid)
            self._activities_tree.see(act_iid)

    def _show_reassign_dialog(self, meeting_iid: str):
        folder_key = self._activities_folder_keys.get(meeting_iid)
        if not folder_key:
            return

        current_act_id = self._folder_to_activity.get(folder_key, "")
        meeting_text = self._activities_tree.item(meeting_iid, "text")
        self._open_activity_picker(folder_key, meeting_text, current_act_id)

    def _show_assign_dialog(self, folder_key: str):
        if not self._folder_to_activity:
            self._load_activities_data()

        title = Path(folder_key).name
        current_act_id = self._folder_to_activity.get(folder_key, "")
        self._open_activity_picker(folder_key, title, current_act_id)

    def _open_activity_picker(self, folder_key: str, meeting_label: str,
                              current_act_id: str):
        dialog = tk.Toplevel(self._root)
        dialog.title("Привязка к активности")
        self._position_dialog(dialog, 440, 360)
        dialog.resizable(True, True)
        dialog.configure(bg=BG)
        dialog.transient(self._root)
        dialog.grab_set()
        _dark_titlebar(dialog)
        self._set_dialog_icon(dialog)

        ttk.Label(dialog, text="Встреча:", style="Dim.TLabel").pack(
            anchor="w", padx=12, pady=(10, 0))
        ttk.Label(dialog, text=meeting_label, wraplength=400).pack(
            anchor="w", padx=12, pady=(0, 6))

        ttk.Separator(dialog, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=8)

        ttk.Label(dialog, text="Поиск темы:", style="Section.TLabel").pack(
            anchor="w", padx=12, pady=(8, 0))

        activities = db.get_activities(self._db_conn)
        current_name = ""
        for a in activities:
            if a["id"] == current_act_id:
                current_name = a["name"]
                break

        search_var = tk.StringVar()
        search_entry = ttk.Entry(dialog, textvariable=search_var)
        search_entry.pack(fill=tk.X, padx=12, pady=(2, 4))
        search_entry.focus_set()

        list_frame = ttk.Frame(dialog)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 4))

        listbox = tk.Listbox(
            list_frame, bg=SURFACE, fg=TEXT,
            selectbackground=SELECT, selectforeground=TEXT,
            font=("Segoe UI", 10), borderwidth=0, highlightthickness=0,
            activestyle="none")
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                  command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        filtered_ids = []

        def _filter(*_args):
            nonlocal filtered_ids
            query = search_var.get().strip().lower()
            listbox.delete(0, tk.END)
            filtered_ids.clear()
            select_idx = None
            for a in activities:
                if query and query not in a["name"].lower():
                    continue
                prefix = "● " if a["id"] == current_act_id else "  "
                listbox.insert(tk.END,
                               f"{prefix}{a['name']}  ({a['meeting_count']})")
                filtered_ids.append(a["id"])
                if a["id"] == current_act_id:
                    select_idx = len(filtered_ids) - 1
            if select_idx is not None:
                listbox.selection_set(select_idx)
                listbox.see(select_idx)
            elif filtered_ids:
                listbox.selection_set(0)

        search_var.trace_add("write", _filter)
        _filter()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=12, pady=(0, 10))

        def do_assign(event=None):
            sel = listbox.curselection()
            if not sel:
                return
            target_id = filtered_ids[sel[0]]
            if target_id != current_act_id:
                self._reassign_meeting(folder_key, target_id)
            dialog.destroy()

        def do_create_and_assign():
            dialog.grab_release()

            def on_created(new_id):
                self._reassign_meeting(folder_key, new_id)
                dialog.destroy()

            self._show_new_activity_dialog(callback=on_created)

        listbox.bind("<Double-Button-1>", do_assign)
        dialog.bind("<Control-Return>", do_assign)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        ttk.Button(btn_frame, text="Привязать", command=do_assign,
                   style="Accent.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="+ Новая тема", command=do_create_and_assign,
                   style="Sm.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy,
                   style="Sm.TButton").pack(side=tk.LEFT)
    def _reassign_meeting(self, folder_key: str, to_act_id: str):
        existing = db.get_meeting_by_folder(self._db_conn, folder_key)
        if not existing:
            folder = Path(folder_key)
            m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})_(.+)", folder.name)
            if m:
                topic = ""
                for s in self._all_sessions:
                    if s.folder_key == folder_key:
                        topic = s.title
                        break
                self._db_conn.execute(
                    "INSERT INTO meetings (activity_id, date, time, topic, folder) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (to_act_id, m.group(1), f"{m.group(2)}:{m.group(3)}",
                     topic, folder_key))
                self._db_conn.commit()
            else:
                return
        else:
            db.reassign_meeting(self._db_conn, folder_key, to_act_id)

        self._load_activities_data()
        if self._activities_tree and self._view_var and self._view_var.get() == "activities":
            self._load_activities()
        if self._tree and self._view_var and self._view_var.get() == "recordings":
            self._apply_filter()

    # ── Reload / Import ──────────────────────────────────────────────────

    def _reload_list(self):
        if self._on_reload:
            self._on_reload()

    def _import_recording(self):
        file_path = filedialog.askopenfilename(
            parent=self._root,
            title="Выберите аудиофайл",
            filetypes=[
                ("Аудиофайлы", "*.wav *.ogg *.opus *.mp3 *.m4a *.aac *.flac *.webm"),
                ("Все файлы", "*.*"),
            ],
        )
        if not file_path:
            return
        self._show_import_dialog(file_path)

    def _show_import_dialog(self, file_path: str):
        dialog = tk.Toplevel(self._root)
        dialog.title("Параметры записи")
        self._position_dialog(dialog, 340, 200)
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.grab_set()
        dialog.transient(self._root)
        _dark_titlebar(dialog)

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Тип записи:").pack(anchor=tk.W, pady=(0, 3))
        type_var = tk.StringVar(value=MEETING_TYPES[0][0])
        ttk.Combobox(
            frame, textvariable=type_var,
            values=[t[0] for t in MEETING_TYPES],
            state="readonly", width=28,
        ).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(frame, text="Язык записи:").pack(anchor=tk.W, pady=(0, 3))
        lang_var = tk.StringVar(value=LANGUAGES[0][0])
        ttk.Combobox(
            frame, textvariable=lang_var,
            values=[l[0] for l in LANGUAGES],
            state="readonly", width=28,
        ).pack(fill=tk.X, pady=(0, 15))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        def on_ok():
            type_code = next(code for name, code in MEETING_TYPES if name == type_var.get())
            lang_code = next(code for name, code in LANGUAGES if name == lang_var.get())
            dialog.destroy()
            if self._on_import:
                self._on_import(file_path, type_code, lang_code)

        dialog.bind("<Escape>", lambda e: dialog.destroy())
        ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy, width=10).pack(side=tk.RIGHT)

    def _import_from_url(self):
        dialog = tk.Toplevel(self._root)
        dialog.title("Импорт по ссылке")
        self._position_dialog(dialog, 460, 140)
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.transient(self._root)
        _dark_titlebar(dialog)

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Вставьте ссылку на видео:").pack(anchor=tk.W, pady=(0, 3))
        url_var = tk.StringVar()

        entry_row = ttk.Frame(frame)
        entry_row.pack(fill=tk.X, pady=(0, 15))

        ttk.Entry(entry_row, textvariable=url_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

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

        ttk.Button(entry_row, text="Вставить", command=_do_paste,
                   style="Sm.TButton", width=10).pack(side=tk.LEFT)

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

    # ── Microphone ───────────────────────────────────────────────────────

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
            self._test_btn_var.set("Стоп")
            self._status_var.set("Проверка микрофона…")
            self._status_label.configure(style="Status.TLabel")
        else:
            if self._on_mic_test_stop:
                self._on_mic_test_stop()
            self._testing_mic = False
            self._test_btn_var.set("Тест")
            self._status_var.set("")
            self._level_bar["value"] = 0

    # ── Settings ─────────────────────────────────────────────────────────

    def _open_settings(self):
        if not self._on_settings:
            return
        current = self._on_settings()

        dialog = tk.Toplevel(self._root)
        dialog.title("Настройки")
        self._position_dialog(dialog, 420, 370)
        dialog.resizable(False, False)
        dialog.configure(bg=BG)
        dialog.grab_set()
        dialog.transient(self._root)
        _dark_titlebar(dialog)

        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Порог тишины (чувствительность):").grid(
            row=0, column=0, sticky=tk.W, pady=(0, 3))
        threshold_var = tk.DoubleVar(value=current["silence_threshold"])
        threshold_label = ttk.Label(frame, text=f"{current['silence_threshold']:.2f}",
                                     style="Dim.TLabel")
        threshold_label.grid(row=0, column=1, sticky=tk.E, pady=(0, 3))

        def _on_threshold_change(val):
            v = round(float(val), 2)
            threshold_var.set(v)
            threshold_label.config(text=f"{v:.2f}")

        ttk.Scale(frame, from_=0.01, to=0.15, variable=threshold_var,
                  orient=tk.HORIZONTAL, command=_on_threshold_change,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 5))
        ttk.Label(frame, text="← чувствительнее    грубее →",
                  style="Dim.TLabel").grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(frame, text="Автостоп при тишине (минуты):").grid(
            row=3, column=0, sticky=tk.W, pady=(0, 3))
        silence_min_var = tk.IntVar(value=current["silence_auto_stop_minutes"])
        ttk.Spinbox(frame, from_=1, to=30, textvariable=silence_min_var, width=5
        ).grid(row=3, column=1, sticky=tk.E, pady=(0, 3))
        ttk.Label(frame,
                  text="Запись остановится, если уровень звука ниже порога в течение этого времени",
                  style="Dim.TLabel", wraplength=370
        ).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(frame, text="Макс. длительность записи (минуты):").grid(
            row=5, column=0, sticky=tk.W, pady=(0, 3))
        max_min_var = tk.IntVar(value=current["max_recording_minutes"])
        ttk.Spinbox(frame, from_=10, to=180, increment=10, textvariable=max_min_var, width=5
        ).grid(row=5, column=1, sticky=tk.E, pady=(0, 3))
        ttk.Label(frame, text="Запись автоматически остановится по достижении лимита",
                  style="Dim.TLabel").grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        ttk.Label(frame, text="Путь к Obsidian vault:").grid(
            row=7, column=0, sticky=tk.W, pady=(0, 3))
        vault_var = tk.StringVar(value=current.get("obsidian_vault_path", ""))
        vault_row = ttk.Frame(frame)
        vault_row.grid(row=8, column=0, columnspan=2, sticky=tk.EW, pady=(0, 15))
        ttk.Entry(vault_row, textvariable=vault_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def _browse_vault():
            path = filedialog.askdirectory(parent=dialog, title="Выберите папку Obsidian vault")
            if path:
                vault_var.set(path)

        ttk.Button(vault_row, text="Обзор", command=_browse_vault,
                   style="Sm.TButton", width=8).pack(side=tk.LEFT)

        frame.columnconfigure(0, weight=1)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=9, column=0, columnspan=2, sticky=tk.EW)

        def on_save():
            settings = {
                "silence_threshold": round(threshold_var.get(), 2),
                "silence_auto_stop_minutes": silence_min_var.get(),
                "max_recording_minutes": max_min_var.get(),
                "obsidian_vault_path": vault_var.get().strip(),
            }
            dialog.destroy()
            if self._on_settings_changed:
                self._on_settings_changed(settings)

        ttk.Button(btn_frame, text="Сохранить", command=on_save, width=12).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy, width=12).pack(side=tk.RIGHT)

    # ── Obsidian ─────────────────────────────────────────────────────────

    def _send_to_obsidian(self):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if folder_key and self._on_obsidian:
            self._on_obsidian(folder_key)

    # ── Preview panel ────────────────────────────────────────────────────

    def _toggle_preview(self):
        self._cancel_title_edit()
        if self._preview_visible:
            self._paned.forget(self._preview_outer)
            self._preview_visible = False
            self._preview_btn_var.set(ICO_PLAY)
            self._set_preview_icons(ICO_PLAY, "Просмотр")
            self._root.geometry("720x680")
            self._root.minsize(580, 520)
        else:
            self._paned.add(self._preview_outer, weight=1)
            self._preview_visible = True
            self._preview_btn_var.set(ICO_BACK)
            self._set_preview_icons(ICO_BACK, "Скрыть просмотр")
            w = self._root.winfo_width()
            if w < 1000:
                self._root.geometry("1240x720")
            self._root.minsize(900, 520)
            self._root.update_idletasks()
            half = self._root.winfo_width() // 2
            try:
                self._paned.sashpos(0, half)
            except Exception:
                pass
            self._load_preview_content()

    def _set_preview_icons(self, icon, tooltip):
        for btn in (getattr(self, '_preview_btn', None),
                    getattr(self, '_act_preview_btn', None),
                    getattr(self, '_tasks_preview_btn', None)):
            if btn and isinstance(btn, _IconBtn):
                btn.configure(text=icon)
                btn._tt.update_text(tooltip)

    def _build_preview_panel(self, parent) -> ttk.Frame:
        outer = ttk.Frame(parent)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, padx=10, pady=(8, 4))

        self._preview_mode_var = tk.StringVar(value="summary")

        ttk.Radiobutton(
            header, text="Саммари", variable=self._preview_mode_var,
            value="summary", command=self._load_preview_content,
            style="Toolbutton",
        ).pack(side=tk.LEFT, padx=(0, 2))

        ttk.Radiobutton(
            header, text="Транскрипция", variable=self._preview_mode_var,
            value="transcript", command=self._load_preview_content,
            style="Toolbutton",
        ).pack(side=tk.LEFT, padx=(0, 10))

        self._preview_title_var = tk.StringVar(value="")
        ttk.Label(
            header, textvariable=self._preview_title_var,
            style="Dim.TLabel",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        _IconBtn(
            header, ICO_SEARCH, "Поиск (Ctrl+F)",
            command=self._toggle_preview_search,
        ).pack(side=tk.RIGHT, padx=(4, 0))

        ttk.Separator(outer, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=5)

        self._md_viewer = MarkdownViewer(outer)
        self._md_viewer.pack(fill=tk.BOTH, expand=True, padx=(2, 5), pady=(0, 5))

        return outer

    def _toggle_preview_search(self):
        if self._md_viewer:
            if self._md_viewer._search_visible:
                self._md_viewer.hide_search()
            else:
                self._md_viewer.show_search()

    def _load_preview_content(self):
        if not self._preview_visible or not self._md_viewer:
            return

        view = self._view_var.get() if self._view_var else "recordings"

        if view == "activities":
            self._load_activity_preview()
            return

        selected = self._tree.selection() if self._tree else ()
        if not selected:
            self._md_viewer.show_placeholder("Выберите запись для просмотра")
            self._preview_title_var.set("")
            return

        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if not folder_key:
            self._md_viewer.show_placeholder("Выберите запись для просмотра")
            return

        folder = Path(folder_key)
        mode = self._preview_mode_var.get()

        if mode == "summary":
            file_path = folder / "summary.md"
            placeholder = "Саммари не найден"
        else:
            file_path = folder / "transcript.md"
            placeholder = "Транскрипция не найдена"

        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                self._md_viewer.set_content(content)
            except Exception:
                self._md_viewer.show_placeholder("Ошибка чтения файла")
        else:
            self._md_viewer.show_placeholder(placeholder)

        values = self._tree.item(iid, "values")
        title = values[2] if len(values) > 2 else ""
        date = values[1] if len(values) > 1 else ""
        self._preview_title_var.set(f"{title} — {date}" if title else date)

    def _load_activity_preview(self):
        selected = self._activities_tree.selection() if self._activities_tree else ()
        if not selected:
            self._md_viewer.show_placeholder("Выберите элемент для просмотра")
            self._preview_title_var.set("")
            return

        iid = selected[0]

        task_id = self._activities_task_ids.get(iid)
        if task_id:
            tasks = db.get_tasks(self._db_conn)
            task = next((t for t in tasks if t["id"] == task_id), None)
            if task:
                status_display = db.TASK_STATUS_DISPLAY.get(task["status"], task["status"])
                lines = [f"# {task['title']}", ""]
                lines.append(f"**Статус:** {status_display}")
                if task.get("responsible"):
                    lines.append(f"**Ответственный:** {task['responsible']}")
                if task.get("deadline"):
                    lines.append(f"**Срок:** {task['deadline']}")
                if task.get("activity_name"):
                    lines.append(f"**Тема:** {task['activity_name']}")
                if task.get("created_at"):
                    lines.append(f"**Дата создания:** {task['created_at']}")
                if task.get("meeting_date"):
                    lines.append(f"**Встреча:** {task['meeting_date']} {task.get('meeting_topic', '')}")
                if task.get("description"):
                    lines += ["", "---", "", task["description"]]
                self._md_viewer.set_content("\n".join(lines))
                self._preview_title_var.set(task["title"][:60])
            return

        folder_key = self._activities_folder_keys.get(iid)

        if not folder_key:
            act_text = self._activities_tree.item(iid, "text")
            values = self._activities_tree.item(iid, "values")
            count = values[0] if values else ""
            last = values[1] if len(values) > 1 else ""
            desc = ""
            for a in self._activities_data:
                if f"act_{a['id']}" == iid:
                    desc = a.get("description", "")
                    break
            lines = [f"# {act_text}", ""]
            if desc:
                lines += [desc, ""]
            sub = self._act_sub_view.get() if self._act_sub_view else "meetings"
            if sub == "tasks":
                lines += [f"**Задач:** {count}", f"**Активных:** {last}", ""]
                children = self._activities_tree.get_children(iid)
                if children:
                    lines.append("## Задачи")
                    for child in children:
                        t_text = self._activities_tree.item(child, "text")
                        lines.append(f"- {t_text}")
            else:
                lines += [f"**Встреч:** {count}", f"**Последняя:** {last}", ""]
                children = self._activities_tree.get_children(iid)
                if children:
                    lines.append("## Встречи")
                    for child in children:
                        m_text = self._activities_tree.item(child, "text")
                        lines.append(f"- {m_text}")
            self._md_viewer.set_content("\n".join(lines))
            self._preview_title_var.set(act_text)
            return

        folder = Path(folder_key)
        mode = self._preview_mode_var.get()

        if mode == "summary":
            file_path = folder / "summary.md"
            placeholder = "Саммари не найден"
        else:
            file_path = folder / "transcript.md"
            placeholder = "Транскрипция не найдена"

        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                self._md_viewer.set_content(content)
            except Exception:
                self._md_viewer.show_placeholder("Ошибка чтения файла")
        else:
            self._md_viewer.show_placeholder(placeholder)

        m_text = self._activities_tree.item(iid, "text")
        self._preview_title_var.set(m_text)

    # ── Inline title editing ─────────────────────────────────────────────

    def _on_tree_double_click(self, event):
        region = self._tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self._tree.identify_column(event.x)
        if col != "#3":
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

        entry = tk.Entry(self._tree, font=("Segoe UI", 10),
                         bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                         selectbackground=SELECT, selectforeground=TEXT,
                         highlightbackground=ACCENT_LO, highlightthickness=1,
                         relief="flat")
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

    # ── Recording state ──────────────────────────────────────────────────

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
        self._btn.configure(style="Stop.TButton")
        self._level_bar.configure(style="Rec.TProgressbar")
        self._status_label.configure(style="RecStatus.TLabel")
        self._mic_btn.config(state="disabled")
        self._test_btn.config(state="disabled")
        self._mic_combo.config(state="disabled")
        self._lang_combo.config(state="disabled")
        self._type_combo.config(state="disabled")
        self._whisper_model_combo.config(state="disabled")

        try:
            self._on_start(lang_code, type_code, mic_only)
        except Exception:
            logger.exception("Ошибка при запуске записи")
            self._recording = False
            self._reset_controls()
            return

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
        self._btn.configure(style="Accent.TButton")
        self._btn.config(state="normal")
        self._level_bar.configure(style="TProgressbar")
        self._status_label.configure(style="Status.TLabel")
        self._mic_btn.config(state="normal")
        self._test_btn.config(state="normal")
        self._mic_combo.config(state="readonly")
        self._lang_combo.config(state="readonly")
        self._type_combo.config(state="readonly")
        self._whisper_model_combo.config(state="readonly")
        self._level_bar["value"] = 0
        self._status_var.set("")

    def _update_timer(self):
        if not self._recording:
            return
        h = self._elapsed // 3600
        m = (self._elapsed % 3600) // 60
        s = self._elapsed % 60
        self._status_var.set(f"●  {h:02d}:{m:02d}:{s:02d}")
        self._elapsed += 1
        self._timer_id = self._root.after(1000, self._update_timer)

    # ── Recordings list logic ────────────────────────────────────────────

    def _on_selection_changed(self, event):
        selected = self._tree.selection()
        if not selected:
            self._transcribe_btn.config(state="disabled")
            self._folder_btn.config(state="disabled")
            self._summary_btn.config(state="disabled")
            self._obsidian_btn.config(state="disabled")
            self._delete_btn.config(state="disabled")
            self._load_preview_content()
            return

        iid = selected[0]
        self._folder_btn.config(state="normal")

        status_text = self._item_status.get(iid, "")
        is_done = status_text == SessionStatus.DONE.value
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
        folder_key = self._folder_keys.get(iid, "")
        can_summary = is_done and folder_key and not (Path(folder_key) / "summary.md").exists()
        self._summary_btn.config(state="normal" if can_summary else "disabled")
        self._obsidian_btn.config(state="normal" if is_done else "disabled")
        self._delete_btn.config(state="normal" if not is_active else "disabled")
        self._load_preview_content()

    def _transcribe_selected(self):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if folder_key and self._on_transcribe:
            self._on_transcribe(folder_key)

    def _run_summary(self):
        selected = self._tree.selection()
        if not selected:
            return
        iid = selected[0]
        folder_key = self._folder_keys.get(iid)
        if not folder_key:
            return
        folder = Path(folder_key)
        if not (folder / "transcript.md").exists():
            self.set_status("Нет транскрипции для создания саммари")
            return
        self._summary_btn.config(state="disabled")
        self._summary_iid = iid
        self._summary_running = True
        self._summary_anim_pos = 0
        self._status_var.set("● Создание саммари (Claude)...")
        self._status_label.configure(style="SummaryStatus.TLabel")
        try:
            self._tree.item(iid, tags=("pulse_on",))
        except Exception:
            pass
        self._summary_animate()

        import subprocess, threading

        def _finish_ok():
            self._summary_btn.config(state="normal")
            self._status_var.set("Саммари создано ✓")
            self._status_label.configure(style="SummaryStatus.TLabel")
            self._root.after(3000, lambda: self._status_label.configure(style="Status.TLabel"))
            if self._on_reload:
                self._on_reload()

        def _finish_err(msg):
            self._summary_btn.config(state="normal")
            self._status_var.set(msg)
            self._status_label.configure(style="RecStatus.TLabel")

        def _run():
            try:
                project_root = str(Path(__file__).resolve().parent.parent.parent)
                cmd = f'claude -p "/summary {folder_key}" --allowedTools "Read,Write,Edit,Bash,Glob,Grep"'
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=600,
                    cwd=project_root, shell=True,
                )
                self._summary_running = False
                if result.returncode == 0 and (folder / "summary.md").exists():
                    self._post_process_summary(folder_key)
                    self._root.after(0, _finish_ok)
                else:
                    err = (result.stderr or result.stdout or "")[:200]
                    self._root.after(0, lambda: _finish_err(f"Ошибка саммари: {err}"))
            except subprocess.TimeoutExpired:
                self._summary_running = False
                self._root.after(0, lambda: _finish_err("Таймаут создания саммари (10 мин)"))
            except Exception as e:
                self._summary_running = False
                self._root.after(0, lambda: _finish_err(f"Ошибка: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def _post_process_summary(self, folder_key: str):
        """Parse summary.md and ensure activity binding + task creation in DB."""
        import re as _re
        from datetime import datetime as _dt

        folder = Path(folder_key)
        summary_path = folder / "summary.md"
        if not summary_path.exists():
            return

        text = summary_path.read_text(encoding="utf-8")
        conn = self._db_conn

        # --- Extract activity name from summary ---
        act_match = _re.search(r"\*\*Активность:\*\*\s*(.+)", text)
        activity_name = act_match.group(1).strip() if act_match else ""

        # --- Extract title from first heading ---
        title_match = _re.search(r"^#\s+(?:Саммари\s*[—–-]\s*)?(.+)", text, _re.MULTILINE)
        title = title_match.group(1).strip()[:100] if title_match else ""

        # --- Update meta.json title ---
        meta_path = folder / "meta.json"
        if meta_path.exists() and title:
            import json
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["title"] = title
            meta["has_summary"] = True
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        # --- Bind to activity ---
        act_id = None
        if activity_name:
            row = conn.execute(
                "SELECT id FROM activities WHERE name = ?", (activity_name,)
            ).fetchone()
            if row:
                act_id = row["id"]
            else:
                act_id = _re.sub(r"[^a-z0-9]+", "-", activity_name.lower()).strip("-")[:50]
                try:
                    from transliterate import translit
                    act_id = translit(act_id, "ru", reversed=True)
                except Exception:
                    pass
                act_id = _re.sub(r"[^a-z0-9-]", "", act_id).strip("-")[:50]
                if act_id:
                    try:
                        conn.execute(
                            "INSERT INTO activities (id, name, description) VALUES (?, ?, ?)",
                            (act_id, activity_name, ""),
                        )
                        conn.commit()
                    except Exception:
                        pass

        # Ensure meeting record exists and is bound
        if act_id:
            existing = conn.execute(
                "SELECT id FROM meetings WHERE folder = ?", (folder_key,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE meetings SET activity_id = ? WHERE folder = ?",
                    (act_id, folder_key),
                )
            else:
                m = _re.match(r"(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})_(.+)", Path(folder_key).name)
                date_val = m.group(1) if m else ""
                time_val = f"{m.group(2)}:{m.group(3)}" if m else ""
                conn.execute(
                    "INSERT INTO meetings (activity_id, date, time, topic, folder) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (act_id, date_val, time_val, title, folder_key),
                )
            conn.commit()

        # --- Get meeting_id ---
        meeting_row = conn.execute(
            "SELECT id FROM meetings WHERE folder = ?", (folder_key,)
        ).fetchone()
        meeting_id = meeting_row["id"] if meeting_row else None

        # --- Extract and create tasks from action table ---
        table_match = _re.search(
            r"##\s*Действия\s*\n\n\|.+\|\s*\n\|[-| ]+\|\s*\n((?:\|.+\|\s*\n?)+)",
            text,
        )
        if table_match and meeting_id:
            existing_tasks = conn.execute(
                "SELECT COUNT(*) AS cnt FROM tasks WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()
            if existing_tasks["cnt"] == 0:
                now = _dt.now().strftime("%Y-%m-%d %H:%M")
                for row_match in _re.finditer(r"\|\s*(.+?)\s*\|\s*(.+?)\s*\|", table_match.group(1)):
                    who = row_match.group(1).strip()
                    what = row_match.group(2).strip()
                    if who.startswith("-") or not what:
                        continue
                    conn.execute(
                        "INSERT INTO tasks (title, description, responsible, deadline, "
                        "status, priority, source, created_at, meeting_id, activity_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (what, "", who, "", "pending", "medium", "meeting",
                         now, meeting_id, act_id or ""),
                    )
                conn.commit()

    def _summary_animate(self):
        if not self._summary_running:
            iid = getattr(self, "_summary_iid", None)
            if iid:
                try:
                    self._tree.item(iid, tags=())
                except Exception:
                    pass
            return
        iid = getattr(self, "_summary_iid", None)
        if not iid or not self._tree:
            return
        width = 20
        pos = self._summary_anim_pos % (width + 3)
        bar = list("░" * width)
        for i in range(3):
            idx = pos - i
            if 0 <= idx < width:
                bar[idx] = "█"
        text = f"{''.join(bar)} Саммари..."
        try:
            self._tree.set(iid, "title", text)
        except Exception:
            pass
        self._summary_anim_pos += 1
        self._root.after(200, self._summary_animate)

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
            self._cascade_delete_from_db(folder_key)
            self._on_delete(folder_key)

    def _cascade_delete_from_db(self, folder_key: str):
        """Remove meeting, tasks, and orphaned activity from DB."""
        conn = self._db_conn
        meeting = conn.execute(
            "SELECT id, activity_id FROM meetings WHERE folder = ?", (folder_key,)
        ).fetchone()
        if not meeting:
            return
        meeting_id = meeting["id"]
        activity_id = meeting["activity_id"]

        conn.execute("DELETE FROM tasks WHERE meeting_id = ?", (meeting_id,))
        conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))

        if activity_id:
            other = conn.execute(
                "SELECT COUNT(*) AS cnt FROM meetings WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()
            if other["cnt"] == 0:
                conn.execute("DELETE FROM tasks WHERE activity_id = ?", (activity_id,))
                conn.execute("DELETE FROM activities WHERE id = ?", (activity_id,))

        conn.commit()

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
        self._item_status.clear()
        self._iid_by_folder.clear()

        if not self._folder_to_activity:
            self._load_activities_data()

        act_name_by_id = db.get_activity_name_map(self._db_conn)

        type_filter = self._tab_var.get() if hasattr(self, "_tab_var") else "all"
        sessions = self._all_sessions
        if type_filter != "all":
            sessions = [s for s in sessions if s.meeting_type == type_filter]

        has_processing = False
        reselect_iid = None
        for i, session in enumerate(sessions):
            iid = str(i)
            status_icon = STATUS_ICON.get(session.status.value, "?")
            date_compact = session.start_time.strftime("%d.%m.%y")
            type_short = TYPE_SHORT.get(session.meeting_type, "")
            tag = STATUS_TAG.get(session.status.value, "done")

            title = session.title
            is_processing = session.status.value in (
                SessionStatus.TRANSCRIBING.value,
                SessionStatus.IMPORTING.value,
            )
            if is_processing:
                has_processing = True
                progress = self._transcription_progress.get(session.folder_key, 0.0)
                title = self._progress_bar_text(progress)

            act_id = self._folder_to_activity.get(session.folder_key, "")
            act_name = act_name_by_id.get(act_id, "")

            self._tree.insert("", tk.END, iid=iid, values=(
                status_icon,
                date_compact,
                title,
                act_name,
                session.display_duration,
                type_short,
            ), tags=(tag,))
            self._folder_keys[iid] = session.folder_key
            self._iid_by_folder[session.folder_key] = iid
            self._item_status[iid] = session.status.value
            if session.folder_key == selected_key:
                reselect_iid = iid

        if has_processing:
            self._start_pulse_animation()
        else:
            self._stop_pulse_animation()

        if reselect_iid:
            self._tree.selection_set(reselect_iid)
        self._on_selection_changed(None)

    @staticmethod
    def _progress_bar_text(progress: float) -> str:
        width = 20
        filled = int(progress * width)
        empty = width - filled
        pct = int(progress * 100)
        return f"{'█' * filled}{'░' * empty} {pct}%"

    # ── Pulse animation for transcribing rows ─────────────────────────────

    def _start_pulse_animation(self):
        if self._pulse_timer_id is not None:
            return
        self._pulse_on = False
        self._pulse_tick()

    def _stop_pulse_animation(self):
        if self._pulse_timer_id is not None:
            self._root.after_cancel(self._pulse_timer_id)
            self._pulse_timer_id = None

    def _pulse_tick(self):
        if not self._tree or not self._root:
            self._pulse_timer_id = None
            return

        self._pulse_on = not self._pulse_on
        tag_to_set = "pulse_on" if self._pulse_on else "processing"
        tag_to_clear = "processing" if self._pulse_on else "pulse_on"

        for iid, status in self._item_status.items():
            if status in (SessionStatus.TRANSCRIBING.value, SessionStatus.IMPORTING.value):
                tags = list(self._tree.item(iid, "tags"))
                if tag_to_clear in tags:
                    tags.remove(tag_to_clear)
                if tag_to_set not in tags:
                    tags.append(tag_to_set)
                self._tree.item(iid, tags=tags)

        self._pulse_timer_id = self._root.after(600, self._pulse_tick)

    # ── Public API ───────────────────────────────────────────────────────

    def update_level(self, level: float):
        if self._root:
            self._root.after(0, lambda v=level: self._do_update_level(v))

    def _do_update_level(self, level: float):
        if self._level_bar:
            self._level_bar["value"] = int(level * 100)

    def set_status(self, text: str):
        if self._root:
            self._root.after(0, lambda t=text: self._do_set_status(t))

    def _do_set_status(self, text: str):
        self._status_var.set(text)
        if self._recording:
            return
        lower = text.lower()
        is_err = any(w in lower for w in ("ошибка", "не найден", "укажите"))
        self._status_label.configure(
            style="RecStatus.TLabel" if is_err else "Status.TLabel")

    def update_transcription_progress(self, folder_key: str, progress: float):
        self._transcription_progress[folder_key] = progress
        if self._root:
            self._root.after(0, lambda fk=folder_key, p=progress:
                             self._do_update_progress(fk, p))

    def _do_update_progress(self, folder_key: str, progress: float):
        iid = self._iid_by_folder.get(folder_key)
        if iid and self._tree:
            self._tree.set(iid, "title", self._progress_bar_text(progress))

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
            self._stop_pulse_animation()
            self._root.destroy()
            self._root = None
