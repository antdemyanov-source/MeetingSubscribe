import re
import tkinter as tk
from tkinter import ttk

BG = "#1e1e1e"
TEXT = "#cccccc"
TEXT_DIM = "#858585"
TEXT_FAINT = "#5a5a5e"
SURFACE = "#252526"
SURFACE2 = "#2d2d2d"
ACCENT = "#b4a0dc"
BLUE = "#5c9fd6"
TEAL = "#4ec9b0"
GREEN = "#73c991"
RED = "#d4564e"
BORDER = "#3e3e42"
SEARCH_HL = "#614d29"
SEARCH_CURRENT = "#9e7c30"

ICO_SEARCH = "\U0001f50d"
ICO_CLOSE = "✕"
ICO_UP = "▲"
ICO_DOWN = "▼"


class MarkdownViewer(ttk.Frame):

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self._search_frame = tk.Frame(self, bg=SURFACE2, height=0)
        self._search_visible = False
        self._search_matches: list[str] = []
        self._search_current_idx = -1

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search_changed())

        self._search_entry = tk.Entry(
            self._search_frame, textvariable=self._search_var,
            bg=SURFACE, fg=TEXT, insertbackground=TEXT,
            borderwidth=1, relief="solid", highlightthickness=0,
            font=("Segoe UI", 10), width=30,
        )

        self._search_count_label = tk.Label(
            self._search_frame, text="", bg=SURFACE2, fg=TEXT_DIM,
            font=("Segoe UI", 9))

        btn_style = dict(bg=SURFACE2, fg=TEXT, font=("Segoe UI", 10),
                         borderwidth=0, cursor="hand2", padx=4, pady=1)

        self._search_up_btn = tk.Label(self._search_frame, text=ICO_UP, **btn_style)
        self._search_down_btn = tk.Label(self._search_frame, text=ICO_DOWN, **btn_style)
        self._search_close_btn = tk.Label(self._search_frame, text=ICO_CLOSE, **btn_style)

        self._search_up_btn.bind("<Button-1>", lambda e: self._search_prev())
        self._search_down_btn.bind("<Button-1>", lambda e: self._search_next())
        self._search_close_btn.bind("<Button-1>", lambda e: self.hide_search())
        self._search_entry.bind("<Return>", lambda e: self._search_next())
        self._search_entry.bind("<Shift-Return>", lambda e: self._search_prev())
        self._search_entry.bind("<Escape>", lambda e: self.hide_search())

        for w in (self._search_up_btn, self._search_down_btn):
            w.bind("<Enter>", lambda e, b=w: b.configure(bg=BORDER))
            w.bind("<Leave>", lambda e, b=w: b.configure(bg=SURFACE2))

        self._search_close_btn.bind("<Enter>",
                                     lambda e: self._search_close_btn.configure(bg=BORDER))
        self._search_close_btn.bind("<Leave>",
                                     lambda e: self._search_close_btn.configure(bg=SURFACE2))

        self._search_entry.pack(side=tk.LEFT, padx=(8, 4), pady=4)
        self._search_count_label.pack(side=tk.LEFT, padx=(0, 4))
        self._search_up_btn.pack(side=tk.LEFT, padx=1)
        self._search_down_btn.pack(side=tk.LEFT, padx=1)
        self._search_close_btn.pack(side=tk.RIGHT, padx=(4, 8))

        self._text = tk.Text(
            self, wrap=tk.WORD, state="disabled",
            padx=16, pady=12, borderwidth=0, highlightthickness=0,
            background=BG, foreground=TEXT,
            cursor="arrow", selectbackground="#37373d", selectforeground=TEXT,
            spacing1=1, spacing3=1, insertbackground=TEXT,
        )

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._text.yview)
        self._text.configure(yscrollcommand=scrollbar.set)

        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._text.bind("<Control-c>", self._copy)
        self._text.bind("<Control-a>", self._select_all)
        self._text.bind("<Control-f>", lambda e: self.show_search())

        self._setup_tags()

    def _setup_tags(self):
        ui = "Segoe UI"
        mono = "Consolas"

        self._text.tag_configure("h1", font=(ui, 15, "bold"),
                                 spacing1=4, spacing3=6, foreground=ACCENT)
        self._text.tag_configure("h2", font=(ui, 13, "bold"),
                                 spacing1=10, spacing3=4, foreground=BLUE)
        self._text.tag_configure("h3", font=(ui, 11, "bold"),
                                 spacing1=8, spacing3=3, foreground=TEAL)
        self._text.tag_configure("body", font=(ui, 10), foreground=TEXT)
        self._text.tag_configure("bold", font=(ui, 10, "bold"), foreground=TEXT)
        self._text.tag_configure("italic", font=(ui, 10, "italic"), foreground=TEXT)
        self._text.tag_configure("bold_italic", font=(ui, 10, "bold italic"), foreground=TEXT)
        self._text.tag_configure("code", font=(mono, 9),
                                 background=SURFACE2, foreground=GREEN)
        self._text.tag_configure("code_block", font=(mono, 9),
                                 background=SURFACE, lmargin1=12, lmargin2=12,
                                 spacing1=2, spacing3=2, foreground=TEXT)
        self._text.tag_configure("hr", foreground=BORDER, font=(mono, 6),
                                 spacing1=6, spacing3=6, justify="center")
        self._text.tag_configure("blockquote", font=(ui, 10, "italic"),
                                 foreground=TEXT_DIM, lmargin1=20, lmargin2=20)
        self._text.tag_configure("bullet", font=(ui, 10),
                                 lmargin1=16, lmargin2=32, foreground=TEXT)
        self._text.tag_configure("bullet2", font=(ui, 10),
                                 lmargin1=32, lmargin2=48, foreground=TEXT)
        self._text.tag_configure("numbered", font=(ui, 10),
                                 lmargin1=16, lmargin2=32, foreground=TEXT)
        self._text.tag_configure("timestamp", font=(mono, 9, "bold"),
                                 foreground=ACCENT)
        self._text.tag_configure("table_header", font=(ui, 10, "bold"),
                                 background=SURFACE2, spacing1=2, spacing3=2,
                                 lmargin1=8, lmargin2=8, foreground=TEXT)
        self._text.tag_configure("table_row", font=(ui, 10),
                                 spacing1=1, spacing3=1,
                                 lmargin1=8, lmargin2=8, foreground=TEXT)
        self._text.tag_configure("table_border", foreground=BORDER,
                                 font=(mono, 9), lmargin1=8)
        self._text.tag_configure("empty", font=(ui, 4))
        self._text.tag_configure("placeholder", foreground=TEXT_FAINT,
                                 justify="center", font=(ui, 11))

        self._text.tag_configure("search_hl", background=SEARCH_HL)
        self._text.tag_configure("search_current", background=SEARCH_CURRENT)
        self._text.tag_raise("search_hl")
        self._text.tag_raise("search_current")

        self._text.configure(font=(ui, 10))

    # ── Search ────────────────────────────────────────────────────────────

    def show_search(self):
        if not self._search_visible:
            self._search_frame.pack(before=self._text, fill=tk.X, side=tk.TOP)
            self._search_visible = True
        self._search_entry.focus_set()
        self._search_entry.select_range(0, tk.END)
        return "break"

    def hide_search(self):
        if self._search_visible:
            self._search_frame.pack_forget()
            self._search_visible = False
        self._clear_search_highlights()
        self._search_count_label.config(text="")
        self._text.focus_set()

    def _clear_search_highlights(self):
        self._text.tag_remove("search_hl", "1.0", tk.END)
        self._text.tag_remove("search_current", "1.0", tk.END)
        self._search_matches.clear()
        self._search_current_idx = -1

    def _on_search_changed(self):
        self._clear_search_highlights()
        query = self._search_var.get()
        if not query:
            self._search_count_label.config(text="")
            return
        self._do_search(query)

    def _do_search(self, query: str):
        start = "1.0"
        query_lower = query.lower()
        while True:
            pos = self._text.search(query_lower, start, stopindex=tk.END, nocase=True)
            if not pos:
                break
            end = f"{pos}+{len(query)}c"
            self._text.tag_add("search_hl", pos, end)
            self._search_matches.append(pos)
            start = end

        count = len(self._search_matches)
        if count == 0:
            self._search_count_label.config(text="нет совпадений")
        else:
            self._search_current_idx = 0
            self._highlight_current()

    def _highlight_current(self):
        self._text.tag_remove("search_current", "1.0", tk.END)
        if not self._search_matches:
            return
        idx = self._search_current_idx
        pos = self._search_matches[idx]
        query_len = len(self._search_var.get())
        end = f"{pos}+{query_len}c"
        self._text.tag_add("search_current", pos, end)
        self._text.see(pos)
        total = len(self._search_matches)
        self._search_count_label.config(text=f"{idx + 1} из {total}")

    def _search_next(self):
        if not self._search_matches:
            return
        self._search_current_idx = (self._search_current_idx + 1) % len(self._search_matches)
        self._highlight_current()

    def _search_prev(self):
        if not self._search_matches:
            return
        self._search_current_idx = (self._search_current_idx - 1) % len(self._search_matches)
        self._highlight_current()

    # ── Content ───────────────────────────────────────────────────────────

    def set_content(self, text: str):
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        if text:
            self._render(text)
        self._text.configure(state="disabled")
        self._text.yview_moveto(0)
        if self._search_visible and self._search_var.get():
            self._on_search_changed()

    def show_placeholder(self, message: str):
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.insert("1.0", "\n\n\n" + message, "placeholder")
        self._text.configure(state="disabled")

    def clear(self):
        self._text.configure(state="normal")
        self._text.delete("1.0", tk.END)
        self._text.configure(state="disabled")

    def _render(self, text: str):
        lines = text.split("\n")
        i = 0
        table_buf = []

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("<!--"):
                while i < len(lines) and "-->" not in lines[i]:
                    i += 1
                i += 1
                continue

            if table_buf and not (stripped.startswith("|") and stripped.endswith("|")):
                self._flush_table(table_buf)
                table_buf.clear()

            if stripped.startswith("|") and stripped.endswith("|"):
                if re.match(r'^\|[\s\-:]+(\|[\s\-:]+)+\|$', stripped):
                    table_buf.append(None)
                else:
                    cells = [c.strip() for c in stripped.split("|")[1:-1]]
                    table_buf.append(cells)
                i += 1
                continue

            if re.match(r'^-{3,}$', stripped) or re.match(r'^\*{3,}$', stripped):
                self._text.insert(tk.END, "─" * 50 + "\n", "hr")
                i += 1
                continue

            if stripped.startswith("```"):
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("```"):
                    code_lines.append(lines[i])
                    i += 1
                if i < len(lines):
                    i += 1
                self._text.insert(tk.END, "\n".join(code_lines) + "\n", "code_block")
                continue

            m = re.match(r'^(#{1,3})\s+(.+)', stripped)
            if m:
                level = len(m.group(1))
                self._insert_inline(m.group(2), f"h{level}")
                self._text.insert(tk.END, "\n")
                i += 1
                continue

            if stripped.startswith("> "):
                self._insert_inline(stripped[2:], "blockquote")
                self._text.insert(tk.END, "\n")
                i += 1
                continue

            bm = re.match(r'^(\s*)[-*]\s+(.+)', line)
            if bm:
                indent = len(bm.group(1))
                tag = "bullet2" if indent >= 2 else "bullet"
                self._text.insert(tk.END, "•  ", tag)
                self._insert_inline(bm.group(2), tag)
                self._text.insert(tk.END, "\n")
                i += 1
                continue

            nm = re.match(r'^(\s*)(\d+)\.\s+(.+)', line)
            if nm:
                num = nm.group(2)
                self._text.insert(tk.END, f"{num}.  ", "numbered")
                self._insert_inline(nm.group(3), "numbered")
                self._text.insert(tk.END, "\n")
                i += 1
                continue

            if not stripped:
                self._text.insert(tk.END, "\n", "empty")
                i += 1
                continue

            full_line = stripped.rstrip("\\").rstrip()
            while stripped.endswith("\\") and i + 1 < len(lines):
                i += 1
                stripped = lines[i].strip()
                full_line += "\n" + stripped.rstrip("\\").rstrip()

            ts = re.match(r'^(\[[\d:]+\])\s*(.*)', full_line)
            if ts:
                self._text.insert(tk.END, ts.group(1) + "  ", "timestamp")
                self._insert_inline(ts.group(2), "body")
                self._text.insert(tk.END, "\n\n", "body")
                i += 1
                continue

            self._insert_inline(full_line, "body")
            self._text.insert(tk.END, "\n")
            i += 1

        if table_buf:
            self._flush_table(table_buf)

    def _flush_table(self, buffer: list):
        rows = [r for r in buffer if r is not None]
        if not rows:
            return

        has_header = None in buffer
        if has_header:
            split = buffer.index(None)
            header_rows = [r for r in buffer[:split] if r is not None]
            body_rows = [r for r in buffer[split + 1:] if r is not None]
        else:
            header_rows = []
            body_rows = rows

        sep = "  │  "

        for row in header_rows:
            self._insert_inline(sep.join(row), "table_header")
            self._text.insert(tk.END, "\n")

        if header_rows:
            self._text.insert(tk.END, "─" * 45 + "\n", "table_border")

        for row in body_rows:
            self._insert_inline(sep.join(row), "table_row")
            self._text.insert(tk.END, "\n")

        self._text.insert(tk.END, "\n", "empty")

    _INLINE_RE = re.compile(
        r'\*\*\*(.+?)\*\*\*'
        r'|\*\*(.+?)\*\*'
        r'|\*(.+?)\*'
        r'|`([^`]+)`'
    )

    def _insert_inline(self, text: str, base_tag: str):
        pos = 0
        for m in self._INLINE_RE.finditer(text):
            if m.start() > pos:
                self._text.insert(tk.END, text[pos:m.start()], base_tag)

            if m.group(1):
                self._text.insert(tk.END, m.group(1), (base_tag, "bold_italic"))
            elif m.group(2):
                self._text.insert(tk.END, m.group(2), (base_tag, "bold"))
            elif m.group(3):
                self._text.insert(tk.END, m.group(3), (base_tag, "italic"))
            elif m.group(4):
                self._text.insert(tk.END, m.group(4), (base_tag, "code"))

            pos = m.end()

        if pos < len(text):
            self._text.insert(tk.END, text[pos:], base_tag)

    def _copy(self, _event=None):
        try:
            sel = self._text.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return "break"
        self._text.clipboard_clear()
        self._text.clipboard_append(sel)
        return "break"

    def _select_all(self, _event=None):
        self._text.tag_add(tk.SEL, "1.0", tk.END)
        return "break"
