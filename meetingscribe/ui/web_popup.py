"""Web-версия окна MeetingScribe на pywebview.

Реализует тот же интерфейс, что PopupWindow (Tkinter): App работает с обоими
окнами одинаково. Выбор бэкенда — config.json, поле "ui_backend": "web" | "tk".

Этап 1: список записей, транскрибация с прогрессом, удаление, открытие файлов.
Этап 2: запись с индикатором уровня и автостопом, импорт файла и по ссылке.
Настройки, микрофон, вкладки «Активности»/«Задачи» — пока в классическом UI.
"""
import json
import logging
import os
import threading
import time
from pathlib import Path

import webview

from meetingscribe import db
from meetingscribe.session import RecordingSession

logger = logging.getLogger(__name__)

WHISPER_MODELS = ["turbo", "large-v3", "medium", "small", "base", "tiny"]

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _make_activity_id(name: str) -> str:
    out = []
    for ch in name.lower():
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        else:
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:50] or "activity"

WEB_DIR = Path(__file__).parent / "web"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ICON_PATH = PROJECT_ROOT / "assets" / "icon.ico"
SUMMARY_PROMPT_PATH = PROJECT_ROOT / ".claude" / "commands" / "summary.md"

_STATUS_KIND = {
    "Готово": "done",
    "Загружено": "imported",
    "Ошибка": "error",
    "Записываю...": "recording",
    "Транскрибирую...": "working",
    "Импорт аудио...": "working",
}

_IMPORT_FILE_TYPES = (
    "Аудиофайлы (*.wav;*.ogg;*.opus;*.mp3;*.m4a;*.aac;*.flac;*.webm)",
    "Все файлы (*.*)",
)

_TRANSCRIPT_FILE_TYPES = (
    "Текстовые файлы (*.txt;*.md)",
    "Все файлы (*.*)",
)


def _run_safe(fn, *args):
    """Фоновый вызов колбэка с логированием ошибок (stderr у pythonw теряется)."""
    def run():
        try:
            fn(*args)
        except Exception:
            logger.exception("Ошибка обработчика %s", getattr(fn, "__name__", fn))
    threading.Thread(target=run, daemon=True).start()


class _JsApi:
    """Мост JS → Python. Методы вызываются из окна через window.pywebview.api."""

    def __init__(self, owner: "WebPopupWindow"):
        self._o = owner

    def get_sessions(self):
        return self._o.serialized_sessions()

    def transcribe(self, folder_key: str):
        if self._o.on_transcribe:
            _run_safe(self._o.on_transcribe, folder_key)

    def summarize(self, folder_key: str):
        if not self._o.on_summarize:
            return

        def run():
            self._o.mark_summarizing(folder_key, True)
            try:
                self._o.on_summarize(folder_key)
            except Exception:
                logger.exception("Ошибка формирования саммари")
            finally:
                self._o.mark_summarizing(folder_key, False)

        threading.Thread(target=run, daemon=True).start()

    def delete(self, folder_key: str):
        if self._o.on_delete:
            self._o.on_delete(folder_key)

    def reload(self):
        if self._o.on_reload:
            self._o.on_reload()

    def open_folder(self, folder_key: str):
        if self._o.on_open_folder:
            self._o.on_open_folder(folder_key)

    def open_file(self, folder_key: str, name: str) -> bool:
        if name not in ("transcript.md", "summary.md"):
            return False
        path = Path(folder_key) / name
        if path.exists():
            os.startfile(str(path))
            return True
        return False

    # ── Запись ──

    def start_recording(self, language: str, meeting_type: str, mic_only: bool):
        self._o.begin_recording(language, meeting_type, mic_only)

    def stop_recording(self):
        self._o.finish_recording()

    # ── Импорт ──

    def pick_import_file(self) -> str | None:
        return self._o.pick_import_file()

    def do_import(self, file_path: str, meeting_type: str, language: str):
        if self._o.on_import:
            _run_safe(self._o.on_import, file_path, meeting_type, language)

    def pick_transcript_file(self) -> str | None:
        return self._o.pick_transcript_file()

    def do_import_transcript(self, file_path: str, meeting_type: str):
        if self._o.on_import_transcript:
            _run_safe(self._o.on_import_transcript, file_path, meeting_type)

    def import_url(self, url: str):
        if self._o.on_url_import and url.strip():
            self._o.on_url_import(url.strip())

    # ── Настройки / микрофон ──

    # ── Состояние UI (ширина панели просмотра и т.п.) ──

    _UI_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "ui_state.json"

    def get_ui_state(self) -> dict:
        try:
            return json.loads(self._UI_STATE_PATH.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}

    def save_ui_state(self, state: dict):
        try:
            current = self.get_ui_state()
            current.update(state or {})
            self._UI_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._UI_STATE_PATH.write_text(
                json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.debug("Не удалось сохранить состояние UI", exc_info=True)

    def get_bootstrap(self) -> dict:
        return {
            "mic_devices": self._o.mic_devices,
            "mic_name": self._o.initial_mic_name,
            "whisper_model": self._o.initial_whisper_model,
            "whisper_models": WHISPER_MODELS,
        }

    def get_settings(self) -> dict:
        return self._o.on_settings() if self._o.on_settings else {}

    def save_settings(self, settings: dict):
        if self._o.on_settings_changed:
            self._o.on_settings_changed(settings)

    def set_whisper_model(self, model: str):
        if self._o.on_whisper_model_changed and model in WHISPER_MODELS:
            self._o.on_whisper_model_changed(model)

    # ── Модель Whisper: статус и загрузка ──

    @staticmethod
    def _model_cache_dir(model: str) -> "Path | None":
        try:
            from faster_whisper.utils import _MODELS
            from huggingface_hub.constants import HF_HUB_CACHE
            repo = _MODELS.get(model)
            if not repo:
                return None
            return Path(HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))
        except Exception:
            logger.debug("Не удалось определить кэш модели", exc_info=True)
            return None

    def whisper_model_status(self, model: str) -> dict:
        cache_dir = self._model_cache_dir(model)
        if cache_dir is None:
            return {"known": False}
        downloaded = cache_dir.exists() and any(cache_dir.rglob("model.bin"))
        size_mb = 0
        if downloaded:
            size_mb = round(sum(
                f.stat().st_size for f in cache_dir.rglob("*") if f.is_file()
            ) / 1_000_000)
        return {
            "known": True,
            "downloaded": downloaded,
            "size_mb": size_mb,
            "path": str(cache_dir),
        }

    def download_whisper_model(self, model: str):
        if model not in WHISPER_MODELS:
            return

        def run():
            self._o.set_status(f"Скачиваю модель {model} — может занять долго...")
            try:
                from faster_whisper import download_model
                download_model(model)
                self._o.set_status(f"Модель {model} скачана и актуальна")
            except Exception as e:
                logger.exception("Ошибка загрузки модели %s", model)
                self._o.set_status(f"Ошибка загрузки модели: {str(e)[:80]}")
            self._o._js("window.refreshModelStatus && window.refreshModelStatus()")

        threading.Thread(target=run, daemon=True).start()

    def set_mic(self, device_index: int):
        if self._o.on_mic_changed:
            self._o.on_mic_changed(int(device_index))

    def mic_test_start(self, device_index: int):
        if self._o.on_mic_test_start:
            _run_safe(self._o.on_mic_test_start, int(device_index))

    def mic_test_stop(self):
        if self._o.on_mic_test_stop:
            self._o.on_mic_test_stop()

    def pick_folder(self) -> str | None:
        if self._o._window is None:
            return None
        try:
            result = self._o._window.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:
            logger.exception("Диалог выбора папки не открылся")
            return None
        return str(result[0]) if result else None

    # ── Промпт саммари ──

    def summary_prompt_info(self) -> dict:
        return {
            "path": str(SUMMARY_PROMPT_PATH),
            "exists": SUMMARY_PROMPT_PATH.exists(),
        }

    def open_summary_prompt(self) -> bool:
        if SUMMARY_PROMPT_PATH.exists():
            os.startfile(str(SUMMARY_PROMPT_PATH))
            return True
        return False

    def load_summary_prompt(self) -> dict:
        """Заменить промпт саммари содержимым выбранного .md файла (с бэкапом)."""
        if self._o._window is None:
            return {"error": "Окно недоступно"}
        try:
            result = self._o._window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Markdown (*.md)", "Все файлы (*.*)"),
            )
        except Exception:
            logger.exception("Диалог выбора промпта не открылся")
            return {"error": "Не удалось открыть диалог"}
        if not result:
            return {}
        src = Path(result[0])
        try:
            text = src.read_text(encoding="utf-8-sig")
            SUMMARY_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
            if SUMMARY_PROMPT_PATH.exists():
                backup = SUMMARY_PROMPT_PATH.with_suffix(".md.bak")
                backup.write_text(
                    SUMMARY_PROMPT_PATH.read_text(encoding="utf-8-sig"),
                    encoding="utf-8")
            SUMMARY_PROMPT_PATH.write_text(text, encoding="utf-8")
            logger.info("Промпт саммари заменён файлом %s", src)
            return {"ok": True, "loaded_from": src.name}
        except Exception as e:
            logger.exception("Не удалось заменить промпт саммари")
            return {"error": str(e)[:120]}

    # ── Записи: название, Obsidian, markdown ──

    def set_title(self, folder_key: str, title: str):
        if self._o.on_title_changed:
            self._o.on_title_changed(folder_key, title.strip())

    def obsidian(self, folder_key: str):
        if self._o.on_obsidian:
            _run_safe(self._o.on_obsidian, folder_key)

    def search_content(self, query: str, scope: str) -> dict:
        """Поиск по содержимому всех саммари или транскрипций.

        Возвращает {folder_key: число совпадений} только для встреч с находками.
        """
        q = (query or "").strip().lower()
        if not q or scope not in ("summary", "transcript"):
            return {}
        name = "summary.md" if scope == "summary" else "transcript.md"
        result = {}
        for s in self._o._sessions:
            text = self._o.read_text_cached(s.folder / name)
            if text:
                count = text.lower().count(q)
                if count:
                    result[s.folder_key] = count
        return result

    def read_md(self, folder_key: str, name: str) -> str | None:
        if name not in ("transcript.md", "summary.md"):
            return None
        path = Path(folder_key) / name
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception:
                logger.exception("Не удалось прочитать %s", path)
        return None

    # ── Активности / задачи ──

    def get_activities(self, include_tasks: bool = False) -> list[dict]:
        conn = self._o.db_conn
        removed = db.cleanup_dead_meetings(conn)
        if removed:
            logger.info("Удалено встреч с несуществующими папками: %d", removed)
        activities = db.get_activities(conn)
        task_counts = db.get_task_counts_by_activity(conn)
        for a in activities:
            a["meetings"] = db.get_activity_meetings(conn, a["id"])
            a["tasks"] = task_counts.get(a["id"], {"total": 0, "active": 0})
            if include_tasks:
                tasks = db.get_tasks(conn, activity_id=a["id"])
                for t in tasks:
                    t["status_display"] = db.TASK_STATUS_DISPLAY.get(
                        t["status"], t["status"])
                a["tasks_list"] = tasks
        return activities

    def get_tasks(self, filt: str) -> list[dict]:
        conn = self._o.db_conn
        if filt == "all":
            tasks = db.get_tasks(conn)
        elif filt in db.TASK_STATUSES:
            tasks = db.get_tasks(conn, status_filter=filt)
        else:
            tasks = db.get_tasks(conn, exclude_done=True)
        for t in tasks:
            t["status_display"] = db.TASK_STATUS_DISPLAY.get(t["status"], t["status"])
        return tasks

    def set_task_status(self, task_id: int, status: str):
        if status in db.TASK_STATUSES:
            db.update_task(self._o.db_conn, int(task_id), status=status)

    def task_statuses(self) -> list[dict]:
        return [{"value": k, "label": v} for k, v in db.TASK_STATUS_DISPLAY.items()]

    _TASK_FIELDS = ("title", "description", "responsible", "deadline",
                    "status", "priority", "activity_id")

    def create_task(self, data: dict) -> int | None:
        title = (data.get("title") or "").strip()
        if not title:
            return None
        from datetime import datetime
        return db.create_task(
            self._o.db_conn,
            title=title,
            description=(data.get("description") or "").strip(),
            responsible=(data.get("responsible") or "").strip(),
            deadline=(data.get("deadline") or "").strip(),
            status=data.get("status") if data.get("status") in db.TASK_STATUSES else "new",
            priority=data.get("priority") or "medium",
            source="manual",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
            activity_id=data.get("activity_id") or "",
        )

    def update_task_fields(self, task_id: int, data: dict):
        fields = {}
        for k in self._TASK_FIELDS:
            if k in data:
                v = data[k]
                fields[k] = v.strip() if isinstance(v, str) else v
        if "status" in fields and fields["status"] not in db.TASK_STATUSES:
            fields.pop("status")
        if "activity_id" in fields and not fields["activity_id"]:
            fields["activity_id"] = None
        if fields:
            db.update_task(self._o.db_conn, int(task_id), **fields)

    def delete_task(self, task_id: int):
        db.delete_task(self._o.db_conn, int(task_id))

    def get_responsibles(self) -> list[str]:
        return [r["name"] for r in db.get_all_responsibles(self._o.db_conn)]

    # ── Активности: CRUD и привязка встреч ──

    def activities_brief(self) -> list[dict]:
        return [{"id": a["id"], "name": a["name"], "status": a["status"]}
                for a in db.get_activities(self._o.db_conn)]

    def create_activity(self, name: str, description: str = "") -> dict:
        name = (name or "").strip()
        if not name:
            return {"error": "Пустое название"}
        act_id = _make_activity_id(name)
        existing = {a["id"] for a in db.get_activities(self._o.db_conn)}
        base, n = act_id, 2
        while act_id in existing:
            act_id = f"{base}-{n}"
            n += 1
        db.create_activity(self._o.db_conn, act_id, name, (description or "").strip())
        return {"id": act_id}

    def rename_activity(self, act_id: str, new_name: str):
        new_name = (new_name or "").strip()
        if new_name:
            db.rename_activity(self._o.db_conn, act_id, new_name)

    def set_activity_status(self, act_id: str, status: str) -> dict:
        if status == "closed":
            ok, reason = db.can_close_activity(self._o.db_conn, act_id)
            if not ok:
                return {"error": reason}
        db.update_activity_status(self._o.db_conn, act_id, status)
        return {}

    def delete_activity(self, act_id: str):
        db.delete_activity(self._o.db_conn, act_id)

    def get_meeting_activity(self, folder_key: str) -> str:
        meeting = db.get_meeting_by_folder(self._o.db_conn, folder_key)
        return (meeting or {}).get("activity_id") or ""

    def assign_meeting(self, folder_key: str, activity_id: str):
        conn = self._o.db_conn
        meeting = db.get_meeting_by_folder(conn, folder_key)
        if meeting:
            db.reassign_meeting(conn, folder_key, activity_id or None)
            return
        # встречи ещё нет в БД — создаём с датой/темой из сессии
        session = next(
            (s for s in self._o._sessions if s.folder_key == folder_key), None)
        date_val = session.start_time.strftime("%Y-%m-%d") if session else ""
        time_val = session.start_time.strftime("%H:%M") if session else ""
        topic = (session.title if session else "") or ""
        conn.execute(
            "INSERT INTO meetings (activity_id, date, time, topic, folder) "
            "VALUES (?, ?, ?, ?, ?)",
            (activity_id or None, date_val, time_val, topic, folder_key),
        )
        conn.commit()


class WebPopupWindow:
    is_web = True

    def __init__(
        self,
        on_start=None,
        on_stop=None,
        on_transcribe=None,
        on_delete=None,
        on_quit=None,
        on_open_folder=None,
        on_reload=None,
        on_import=None,
        on_import_transcript=None,
        on_url_import=None,
        on_title_changed=None,
        on_whisper_model_changed=None,
        on_mic_changed=None,
        on_mic_test_start=None,
        on_mic_test_stop=None,
        on_settings=None,
        on_settings_changed=None,
        on_obsidian=None,
        on_summarize=None,
        mic_devices=None,
        initial_mic_name="",
        initial_whisper_model="",
    ):
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_transcribe = on_transcribe
        self.on_delete = on_delete
        self.on_quit = on_quit
        self.on_open_folder = on_open_folder
        self.on_reload = on_reload
        self.on_import = on_import
        self.on_import_transcript = on_import_transcript
        self.on_url_import = on_url_import
        self.on_title_changed = on_title_changed
        self.on_whisper_model_changed = on_whisper_model_changed
        self.on_mic_changed = on_mic_changed
        self.on_mic_test_start = on_mic_test_start
        self.on_mic_test_stop = on_mic_test_stop
        self.on_settings = on_settings
        self.on_settings_changed = on_settings_changed
        self.on_obsidian = on_obsidian
        self.on_summarize = on_summarize
        self.mic_devices = mic_devices or []
        self.initial_mic_name = initial_mic_name
        self.initial_whisper_model = initial_whisper_model

        self.db_conn = db.get_connection()
        db.init_db(self.db_conn)
        db.migrate_from_json(self.db_conn)

        self._window: webview.Window | None = None
        self._started = False
        self._quitting = False
        self._recording = False
        self._sessions: list[RecordingSession] = []
        self._progress: dict[str, float] = {}
        self._summarizing: set[str] = set()
        self._last_level_push = 0.0
        self._text_cache: dict[str, tuple[float, str]] = {}

    # ── Данные для JS ────────────────────────────────────────────────────

    def serialized_sessions(self) -> list[dict]:
        try:
            folder_map = db.get_folder_activity_map(self.db_conn)
            name_map = db.get_activity_name_map(self.db_conn)
        except Exception:
            folder_map, name_map = {}, {}
        result = []
        for s in self._sessions:
            folder_key = s.folder_key
            status = s.status.value
            kind = _STATUS_KIND.get(status, "working")
            progress = self._progress.get(folder_key)
            if folder_key in self._summarizing:
                status, kind, progress = "Формирую саммари...", "working", None
            result.append({
                "folder": folder_key,
                "date": s.display_date,
                "title": s.title or "Без названия",
                "type": s.display_type,
                "duration": s.display_duration if s.duration else "",
                "status": status,
                "kind": kind,
                # проверяем диск, а не кэш сессии: транскрипт мог появиться позже
                "has_transcript": s.has_transcript or (s.folder / "transcript.md").exists(),
                "has_summary": (s.folder / "summary.md").exists(),
                "progress": progress,
                "activity": name_map.get(folder_map.get(folder_key, ""), ""),
            })
        return result

    def read_text_cached(self, path: Path) -> str | None:
        """Чтение файла с кэшем по mtime — для быстрого полнотекстового поиска."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            self._text_cache.pop(str(path), None)
            return None
        key = str(path)
        cached = self._text_cache.get(key)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            logger.debug("Не удалось прочитать %s", path, exc_info=True)
            return None
        self._text_cache[key] = (mtime, text)
        return text

    def mark_summarizing(self, folder_key: str, active: bool):
        if active:
            self._summarizing.add(folder_key)
        else:
            self._summarizing.discard(folder_key)
        self._js(f"window.setSessions({json.dumps(self.serialized_sessions())})")

    def _js(self, code: str):
        if self._started and self._window is not None:
            try:
                self._window.evaluate_js(code)
            except Exception:
                logger.debug("evaluate_js не выполнен", exc_info=True)

    # ── Запись ───────────────────────────────────────────────────────────

    def begin_recording(self, language: str, meeting_type: str, mic_only: bool):
        if self._recording or not self.on_start:
            return
        self._recording = True
        _run_safe(self.on_start, language, meeting_type, mic_only)

    def finish_recording(self):
        if not self._recording or not self.on_stop:
            return
        self._recording = False
        _run_safe(self.on_stop)

    def trigger_auto_stop(self, reason: str):
        if not self._recording:
            return
        self._recording = False
        if self.on_stop:
            _run_safe(self.on_stop)
        self._js(f"window.stopRecordingUI({json.dumps(reason)})")

    def reset_after_processing(self):
        self._recording = False
        self._js("window.resetRecordingUI()")

    def update_level(self, level: float):
        # не чаще ~12 раз/сек, чтобы не заливать мост evaluate_js
        now = time.monotonic()
        if now - self._last_level_push < 0.08:
            return
        self._last_level_push = now
        self._js(f"window.setLevel({level:.3f})")

    # ── Импорт ───────────────────────────────────────────────────────────

    def pick_import_file(self) -> str | None:
        if self._window is None:
            return None
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG, file_types=_IMPORT_FILE_TYPES
            )
        except Exception:
            logger.exception("Диалог выбора файла не открылся")
            return None
        if result:
            return str(result[0])
        return None

    def pick_transcript_file(self) -> str | None:
        if self._window is None:
            return None
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG, file_types=_TRANSCRIPT_FILE_TYPES
            )
        except Exception:
            logger.exception("Диалог выбора файла транскрипта не открылся")
            return None
        if result:
            return str(result[0])
        return None

    # ── Интерфейс PopupWindow ────────────────────────────────────────────

    def _get_hwnd(self) -> int:
        import ctypes
        native = getattr(self._window, "native", None)
        if native is not None and hasattr(native, "Handle"):
            try:
                return int(native.Handle.ToInt64())
            except Exception:
                pass
        return ctypes.windll.user32.FindWindowW(None, "MeetingScribe")

    def _on_shown(self):
        """Штрихи Windows-окна: тёмный заголовок и иконка приложения."""
        import ctypes
        try:
            hwnd = self._get_hwnd()
            if not hwnd:
                return
            value = ctypes.c_int(1)
            # 20 — DWMWA_USE_IMMERSIVE_DARK_MODE, 19 — его номер в старых сборках
            for attr in (20, 19):
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
            self._apply_window_icon(hwnd)
            # перерисовать рамку сразу, не дожидаясь смены фокуса окна
            SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)
        except Exception:
            logger.debug("Не удалось оформить окно", exc_info=True)

    def _apply_window_icon(self, hwnd: int):
        """Иконка в заголовке окна и на панели задач вместо стандартной Python."""
        import ctypes
        from ctypes import wintypes
        if not ICON_PATH.exists():
            return
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = (
            wintypes.HINSTANCE, wintypes.LPCWSTR, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_uint,
        )
        user32.SendMessageW.argtypes = (
            wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM,
        )
        IMAGE_ICON, LR_LOADFROMFILE, WM_SETICON = 1, 0x10, 0x80
        big = user32.LoadImageW(None, str(ICON_PATH), IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        small = user32.LoadImageW(None, str(ICON_PATH), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if big:
            user32.SendMessageW(hwnd, WM_SETICON, 1, big)   # ICON_BIG — панель задач
        if small:
            user32.SendMessageW(hwnd, WM_SETICON, 0, small)  # ICON_SMALL — заголовок

    def show(self):
        if self._window is None:
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "meetingscribe.app")
            except Exception:
                pass
            self._window = webview.create_window(
                "MeetingScribe",
                str(WEB_DIR / "index.html"),
                js_api=_JsApi(self),
                width=980,
                height=720,
                min_size=(720, 480),
                background_color="#1e1e1e",
            )
            self._window.events.closed += self._on_closed
            self._window.events.shown += self._on_shown
        else:
            try:
                self._window.restore()
                self._window.show()
            except Exception:
                pass

    def run_mainloop(self):
        self._started = True
        webview.start()
        self._started = False

    def _on_closed(self):
        self._window = None
        if not self._quitting and self.on_quit:
            self.on_quit()

    def set_sessions(self, sessions: list[RecordingSession]):
        self._sessions = sessions
        # прогресс завершённых транскрибаций больше не нужен
        alive = {s.folder_key for s in sessions
                 if s.status.value == "Транскрибирую..."}
        self._progress = {k: v for k, v in self._progress.items() if k in alive}
        self._js(f"window.setSessions({json.dumps(self.serialized_sessions())})")

    def update_transcription_progress(self, folder_key: str, progress: float):
        self._progress[folder_key] = progress
        self._js(f"window.setProgress({json.dumps(folder_key)}, {progress:.3f})")

    def set_status(self, text: str):
        self._js(f"window.setStatus({json.dumps(text)})")

    def destroy(self):
        self._quitting = True
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
