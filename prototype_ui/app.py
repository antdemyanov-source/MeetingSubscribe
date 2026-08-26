"""Прототип UI MeetingScribe на pywebview.

Читает реальные записи через SessionManager (read-only).
Кнопки действий — заглушки, кроме открытия папки/файлов.

Запуск:  python prototype_ui/app.py
"""
import os
import sys
from pathlib import Path

import webview

sys.path.insert(0, str(Path(__file__).parent.parent))

from meetingscribe.config import Config
from meetingscribe.session import SessionManager


STATUS_KIND = {
    "Готово": "done",
    "Загружено": "imported",
    "Ошибка": "error",
    "Записываю...": "recording",
    "Транскрибирую...": "working",
    "Импорт аудио...": "working",
}


class Api:
    def __init__(self):
        config = Config.load()
        self._mgr = SessionManager(config.recordings_dir)

    def get_sessions(self):
        result = []
        for s in self._mgr.get_sorted_sessions():
            result.append({
                "folder": str(s.folder),
                "date": s.display_date,
                "title": s.title or "Без названия",
                "type": s.display_type,
                "duration": s.display_duration if s.duration else "",
                "status": s.status.value,
                "kind": STATUS_KIND.get(s.status.value, "working"),
                "has_transcript": s.has_transcript,
                "has_summary": (s.folder / "summary.md").exists(),
            })
        return result

    def open_folder(self, folder: str):
        os.startfile(folder)

    def open_file(self, folder: str, name: str):
        path = Path(folder) / name
        if path.exists():
            os.startfile(str(path))
            return True
        return False


if __name__ == "__main__":
    window = webview.create_window(
        "MeetingScribe — прототип",
        str(Path(__file__).parent / "index.html"),
        js_api=Api(),
        width=980,
        height=720,
        background_color="#1e1e1e",
    )
    webview.start()
