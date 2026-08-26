import json
import logging
import os
import shutil
import threading
import time

logger = logging.getLogger(__name__)
from datetime import datetime
from pathlib import Path

from meetingscribe.config import Config
from meetingscribe.audio_capture import AudioCapture, list_microphones
from meetingscribe.pipeline import Pipeline
from meetingscribe.session import (
    AUDIO_EXTENSIONS, RecordingSession, SessionManager, SessionStatus,
)
from meetingscribe.storage import create_recording_paths
from meetingscribe.ui.tray import create_tray, set_tray_recording
from meetingscribe.ui.popup import PopupWindow


def _short_path(path: Path) -> str:
    """Короткое имя Windows (8.3) для путей с пробелами — безопасно для CLI."""
    s = str(path)
    if " " not in s:
        return s
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetShortPathNameW(s, buf, 260):
            return buf.value
    except Exception:
        pass
    return s


TEXT_TRANSCRIPT_EXTENSIONS = (".txt", ".md")


def _read_text_file(path: Path) -> str:
    """Читает текстовый файл транскрипта, перебирая типичные для Windows кодировки."""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", data, 0, 1, "не удалось определить кодировку")


class App:
    def __init__(self, config: Config):
        self.config = config
        self.capture = AudioCapture(config.audio_sample_rate, config.mic_volume,
                                    config.silence_threshold,
                                    mic_device_name=config.mic_device_name)
        self.pipeline = Pipeline(config)
        self.session_mgr = SessionManager(config.recordings_dir)

        mic_devices = list_microphones()
        self._mic_devices = mic_devices
        mic_idx = None
        if config.mic_device_name:
            for d in mic_devices:
                if d["name"] == config.mic_device_name:
                    mic_idx = d["index"]
                    break
        if mic_idx is None and mic_devices:
            mic_idx = mic_devices[0]["index"]
        if mic_idx is not None:
            self.capture.set_mic_device(mic_idx)

        self._recording_language = "ru"
        self._recording_type = "work"
        self._recording_mic_only = False
        self._start_time: datetime | None = None
        self._current_session_folder: Path | None = None
        self._level_thread: threading.Thread | None = None
        self._tray = None

        self._popup_kwargs = dict(
            on_start=self._handle_start,
            on_stop=self._handle_stop,
            on_transcribe=self._handle_transcribe,
            on_delete=self._handle_delete,
            on_quit=self._quit,
            on_open_folder=self._handle_open_folder,
            on_reload=self._handle_reload,
            on_import=self._handle_import,
            on_import_transcript=self._handle_import_transcript,
            on_url_import=self._handle_url_import,
            on_title_changed=self._handle_title_changed,
            on_whisper_model_changed=self._handle_whisper_model_changed,
            on_mic_changed=self._handle_mic_changed,
            on_mic_test_start=self._handle_mic_test_start,
            on_mic_test_stop=self._handle_mic_test_stop,
            on_settings=self._get_settings,
            on_settings_changed=self._handle_settings_changed,
            on_obsidian=self._handle_obsidian,
            on_summarize=self._handle_summarize,
            mic_devices=mic_devices,
            initial_mic_name=config.mic_device_name,
            initial_whisper_model=config.whisper_model,
        )
        self.popup = self._create_popup()

    def _create_popup(self):
        if self.config.ui_backend == "web":
            try:
                from meetingscribe.ui.web_popup import WebPopupWindow
                return WebPopupWindow(**self._popup_kwargs)
            except Exception:
                logger.exception(
                    "Не удалось создать web-UI, откат на классический Tkinter"
                )
        return PopupWindow(**self._popup_kwargs)

    def run(self):
        self._tray = create_tray(
            on_open=lambda icon, item: self._open_popup(),
            on_quit=lambda icon, item: self._quit(),
        )

        if getattr(self.popup, "is_web", False):
            # pywebview обязан работать в главном потоке — трей уходит в фоновый
            self._tray.run_detached()
            self._run_popup()
        else:
            popup_thread = threading.Thread(target=self._run_popup, daemon=True)
            popup_thread.start()
            self._tray.run()

    def _run_popup(self):
        try:
            self.popup.show()
            self._refresh_list()
            self.popup.run_mainloop()
        except Exception:
            if not getattr(self.popup, "is_web", False):
                raise
            logger.exception("Web-UI упал, перезапуск на классическом Tkinter")
            self.popup = PopupWindow(**self._popup_kwargs)
            self.popup.show()
            self._refresh_list()
            self.popup.run_mainloop()

    def _open_popup(self):
        self.popup.show()

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

    # --- Whisper model ---

    def _handle_whisper_model_changed(self, model: str):
        self.config.whisper_model = model
        self.config.save()

    # --- Microphone ---

    def _handle_mic_changed(self, device_index: int):
        self.capture.set_mic_device(device_index)
        for d in self._mic_devices:
            if d["index"] == device_index:
                self.config.mic_device_name = d["name"]
                break
        self.config.save()

    def _handle_mic_test_start(self, device_index: int):
        try:
            self.capture.start_mic_test(device_index)
        except RuntimeError as e:
            self.popup.set_status(f"Ошибка: {e}")
            return

        self._level_thread = threading.Thread(target=self._update_test_levels, daemon=True)
        self._level_thread.start()

    def _handle_mic_test_stop(self):
        self.capture.stop_mic_test()

    # --- Settings ---

    def _get_settings(self) -> dict:
        return {
            "silence_threshold": self.config.silence_threshold,
            "silence_auto_stop_minutes": self.config.silence_auto_stop_minutes,
            "max_recording_minutes": self.config.max_recording_minutes,
            "obsidian_vault_path": self.config.obsidian_vault_path,
            "anthropic_api_key": self.config.anthropic_api_key,
            "hide_personal": self.config.hide_personal,
            "summary_cli": self.config.summary_cli,
            "recordings_dir": self.config.recordings_dir,
            "auto_transcribe": self.config.auto_transcribe,
            "summary_activities": self.config.summary_activities,
            "summary_tasks": self.config.summary_tasks,
        }

    def _handle_settings_changed(self, settings: dict):
        self.config.silence_threshold = settings["silence_threshold"]
        self.config.silence_auto_stop_minutes = settings["silence_auto_stop_minutes"]
        self.config.max_recording_minutes = settings["max_recording_minutes"]
        self.config.obsidian_vault_path = settings["obsidian_vault_path"]
        self.config.anthropic_api_key = settings.get(
            "anthropic_api_key", self.config.anthropic_api_key)
        self.config.hide_personal = bool(settings.get(
            "hide_personal", self.config.hide_personal))
        self.config.summary_cli = settings.get(
            "summary_cli", self.config.summary_cli).strip() or self.config.summary_cli
        self.config.auto_transcribe = bool(settings.get(
            "auto_transcribe", self.config.auto_transcribe))
        self.config.summary_activities = bool(settings.get(
            "summary_activities", self.config.summary_activities))
        self.config.summary_tasks = bool(settings.get(
            "summary_tasks", self.config.summary_tasks))

        new_dir = settings.get("recordings_dir", "").strip()
        if new_dir and new_dir != self.config.recordings_dir:
            try:
                Path(new_dir).mkdir(parents=True, exist_ok=True)
                self.config.recordings_dir = new_dir
                self.session_mgr = SessionManager(new_dir)
            except Exception:
                logger.exception("Не удалось сменить папку записей на %s", new_dir)
                self.popup.set_status("Не удалось сменить папку записей")

        self.capture.silence_threshold = settings["silence_threshold"]
        self.config.save()
        self._refresh_list()

    # --- Summary (через Claude Code CLI и скилл /summary) ---

    def _write_summary_extra(self) -> Path | None:
        """Собрать файл системных инструкций саммари по галкам настроек.

        Пользовательский промпт (summary.md) отвечает только за текст саммари;
        привязка активностей и создание задач управляются приложением.
        """
        prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
        parts = ["# Системные инструкции MeetingScribe (сгенерировано приложением)\n"]

        if self.config.summary_activities:
            try:
                parts.append((prompts_dir / "summary_activities.md")
                             .read_text(encoding="utf-8"))
            except Exception:
                logger.exception("Не удалось прочитать summary_activities.md")
        else:
            parts.append(
                "## Активности: ОТКЛЮЧЕНО\n\n"
                "НЕ привязывай встречу к активностям и НЕ создавай активности, "
                "даже если основные правила саммари это предписывают. "
                "Пропусти соответствующие шаги.")

        if self.config.summary_tasks:
            try:
                parts.append((prompts_dir / "summary_tasks.md")
                             .read_text(encoding="utf-8"))
            except Exception:
                logger.exception("Не удалось прочитать summary_tasks.md")
        else:
            parts.append(
                "## Задачи: ОТКЛЮЧЕНО\n\n"
                "НЕ создавай задачи в базе данных, даже если основные правила "
                "саммари это предписывают. Пропусти соответствующие шаги.")

        try:
            extra_path = Path(__file__).resolve().parents[2] / "data" / "summary_extra.md"
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_text("\n\n".join(parts), encoding="utf-8")
            return extra_path
        except Exception:
            logger.exception("Не удалось записать summary_extra.md")
            return None

    def _handle_summarize(self, folder_key: str):
        import subprocess

        folder = Path(folder_key)
        transcript_path = folder / "transcript.md"
        if not transcript_path.exists():
            self.popup.set_status("Транскрипция не найдена")
            return

        template = self.config.summary_cli or ""
        if "{transcript}" not in template:
            self.popup.set_status(
                "В команде саммари нет {transcript} — проверьте настройки")
            return
        cli_name = template.strip().split()[0]
        if not shutil.which(cli_name):
            self.popup.set_status(
                f"Команда «{cli_name}» не найдена — проверьте настройки саммари")
            return

        extra_path = self._write_summary_extra()
        args = _short_path(transcript_path)
        if extra_path:
            args += (". Обязательно прочитай и выполни также системные "
                     f"инструкции из файла {_short_path(extra_path)}")
        command = template.replace("{transcript}", args)

        project_root = Path(__file__).resolve().parents[2]
        self.popup.set_status("Формирую саммари (несколько минут)...")
        logger.info("Запуск саммари: %s", command)

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=1800,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            logger.info("Claude CLI завершился (код %d). Ответ: %s",
                        result.returncode, (result.stdout or "")[-2000:])
            if result.returncode != 0:
                logger.error("Claude CLI stderr: %s", (result.stderr or "")[-2000:])
        except subprocess.TimeoutExpired:
            logger.error("Claude CLI: таймаут формирования саммари")
            self.popup.set_status("Саммари: превышено время ожидания Claude CLI")
            return
        except Exception:
            logger.exception("Не удалось запустить Claude CLI")
            self.popup.set_status("Ошибка запуска Claude CLI (см. лог)")
            return

        if (folder / "summary.md").exists():
            self.popup.set_status("Саммари готово")
        else:
            self.popup.set_status("Саммари не создано — подробности в логе")
        self.session_mgr.reload()
        self._refresh_list()

    # --- Obsidian ---

    def _handle_obsidian(self, folder_key: str):
        vault_path = self.config.obsidian_vault_path
        if not vault_path:
            self.popup.set_status("Укажите путь к Obsidian vault в настройках")
            return

        folder = Path(folder_key)
        summary_path = folder / "summary.md"
        if not summary_path.exists():
            self.popup.set_status("Summary не найден")
            return

        session = self.session_mgr.get_session(folder)
        date_str = session.start_time.strftime("%Y-%m-%d") if session else "unknown"
        title = session.title if session and session.title else session.display_type if session else "Meeting"
        safe_title = "".join(c if c not in '<>:"/\\|?*' else "_" for c in title)
        filename = f"{date_str} {safe_title}.md"

        vault = Path(vault_path)
        target_dir = vault / "MeetingScribe"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / filename

        content = summary_path.read_text(encoding="utf-8")
        target_file.write_text(content, encoding="utf-8")

        vault_name = vault.name
        relative = f"MeetingScribe/{filename}"
        import urllib.parse
        uri = f"obsidian://open?vault={urllib.parse.quote(vault_name)}&file={urllib.parse.quote(relative)}"
        os.startfile(uri)

        self.popup.set_status(f"Скопировано в Obsidian: {filename}")

    def _update_test_levels(self):
        while self.capture._testing_mic:
            self.popup.update_level(self.capture.audio_level)
            time.sleep(0.05)
        self.popup.update_level(0.0)

    # --- Recording ---

    def _handle_start(self, language: str, meeting_type: str, mic_only: bool):
        self._recording_language = language
        self._recording_type = meeting_type
        self._recording_mic_only = mic_only
        self._start_time = datetime.now()

        try:
            self.capture.start(mic_only=mic_only)
        except Exception as e:
            logger.exception("Не удалось начать запись")
            self.popup.set_status(f"Ошибка: {e}")
            self.popup.reset_after_processing()
            return

        if self._tray:
            set_tray_recording(self._tray, True)

        paths = create_recording_paths(
            self.config.recordings_dir, meeting_type, self._start_time
        )
        self._current_session_folder = paths.folder
        audio_mode = "mic" if mic_only else "loopback"
        self.session_mgr.create_session(
            paths.folder, self._start_time, meeting_type, language, audio_mode
        )
        self._refresh_list()

        self._level_thread = threading.Thread(target=self._update_levels, daemon=True)
        self._level_thread.start()

    def _handle_stop(self):
        if self._tray:
            set_tray_recording(self._tray, False)

        recording_type = self._recording_type
        recording_language = self._recording_language
        recording_mic_only = self._recording_mic_only
        start_time = self._start_time or datetime.now()
        folder = self._current_session_folder

        ts = start_time.strftime("%H%M%S")
        tmp_wav = Path(self.config.recordings_dir) / f"_temp_{ts}.wav"
        tmp_wav.parent.mkdir(parents=True, exist_ok=True)
        try:
            duration = self.capture.stop(tmp_wav)
        except Exception:
            logger.exception("Не удалось сохранить запись")
            if folder:
                self.session_mgr.update_status(folder, SessionStatus.ERROR)
                self._refresh_list()
            self.popup.set_status("Ошибка: не удалось сохранить запись")
            self.popup.reset_after_processing()
            return

        if folder:
            self.session_mgr.update_duration(folder, duration)
            self.session_mgr.update_status(
                folder,
                SessionStatus.TRANSCRIBING if self.config.auto_transcribe
                else SessionStatus.IMPORTED,
            )
            self._refresh_list()

        if self.config.auto_transcribe:
            thread = threading.Thread(
                target=self._run_transcription,
                args=(tmp_wav, duration, folder, recording_type,
                      recording_language, start_time, recording_mic_only),
                daemon=True,
            )
        else:
            thread = threading.Thread(
                target=self._save_without_transcription,
                args=(tmp_wav, duration, folder, recording_type,
                      recording_language, start_time, recording_mic_only),
                daemon=True,
            )
        thread.start()

    def _save_without_transcription(
        self, wav_path: Path, duration: int, folder: Path | None,
        meeting_type: str, language: str, start_time: datetime, mic_only: bool,
    ):
        """Автотранскрибация выключена: сохранить аудио и метаданные, не распознавая."""
        import json as _json
        try:
            from meetingscribe.pipeline import convert_to_ogg
            paths = create_recording_paths(
                self.config.recordings_dir, meeting_type, start_time)
            target_wav = paths.wav
            if wav_path != target_wav:
                shutil.move(str(wav_path), str(target_wav))
            converted = convert_to_ogg(target_wav, paths.ogg)
            if converted and not self.config.keep_wav:
                target_wav.unlink(missing_ok=True)
            meta = {
                "date": start_time.isoformat(),
                "duration_seconds": duration,
                "language": language,
                "meeting_type": meeting_type,
                "audio_mode": "mic" if mic_only else "loopback",
                "has_ogg": paths.ogg.exists(),
            }
            paths.meta.write_text(
                _json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            self.popup.set_status("Запись сохранена — транскрибация по кнопке ▶")
        except Exception:
            logger.exception("Не удалось сохранить запись без транскрибации")
            if folder:
                self.session_mgr.update_status(folder, SessionStatus.ERROR)
            self.popup.set_status("Ошибка сохранения записи")

        self.session_mgr.reload()
        self._refresh_list()

    def _run_transcription(
        self, wav_path: Path, duration: int, folder: Path | None,
        meeting_type: str, language: str, start_time: datetime, mic_only: bool,
    ):
        try:
            audio_mode = "mic" if mic_only else "loopback"

            def _on_progress(p):
                if folder:
                    self.popup.update_transcription_progress(str(folder), p)

            self.pipeline.run_transcription(
                wav_path=wav_path,
                meeting_type=meeting_type,
                language=language,
                duration_seconds=duration,
                start_time=start_time,
                audio_mode=audio_mode,
                on_progress=_on_progress,
            )
            if folder:
                self.session_mgr.update_status(folder, SessionStatus.DONE)
        except Exception:
            logger.exception("Ошибка транскрибации")
            if folder:
                self.session_mgr.update_status(folder, SessionStatus.ERROR)

        # перечитать диск: у сессии должен появиться has_transcript
        self.session_mgr.reload()
        self._refresh_list()

    # --- Import ---

    def _handle_import(self, file_path: str, meeting_type: str, language: str):
        src = Path(file_path)
        if src.suffix.lower() in TEXT_TRANSCRIPT_EXTENSIONS:
            # текстовый файл выбран через диалог импорта аудио ("Все файлы") —
            # это готовый транскрипт, а не аудио
            self._handle_import_transcript(file_path, meeting_type)
            return

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

    # --- Transcript Import ---

    def _handle_import_transcript(self, file_path: str, meeting_type: str):
        src = Path(file_path)
        try:
            text = _read_text_file(src)
        except (OSError, UnicodeDecodeError):
            logger.exception("Не удалось прочитать файл транскрипта")
            self.popup.set_status(f"Не удалось прочитать файл: {src.name}")
            return
        if not text.strip():
            self.popup.set_status(f"Файл пуст: {src.name}")
            return

        now = datetime.now()
        paths = create_recording_paths(
            self.config.recordings_dir, meeting_type, now
        )
        paths.transcript.write_text(text, encoding="utf-8")

        meta = {
            "date": now.isoformat(),
            "duration_seconds": 0,
            "language": "ru",
            "meeting_type": meeting_type,
            "audio_mode": "text_import",
            "source": "text_import",
            "original_filename": src.name,
            "has_summary": False,
            "has_ogg": False,
        }
        paths.meta.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        self.session_mgr.create_session(
            paths.folder, now, meeting_type, "ru", audio_mode="text_import"
        )
        self.session_mgr.update_status(paths.folder, SessionStatus.DONE)
        self.session_mgr.reload()
        self._refresh_list()

    # --- URL Import ---

    def _handle_url_import(self, url: str):
        now = datetime.now()
        paths = create_recording_paths(
            self.config.recordings_dir, "external", now
        )

        self.session_mgr.create_session(
            paths.folder, now, "external", "ru", audio_mode="url_import"
        )
        self.session_mgr.update_status(paths.folder, SessionStatus.IMPORTING)
        self._refresh_list()

        thread = threading.Thread(
            target=self._run_url_import,
            args=(url, paths.folder, now),
            daemon=True,
        )
        thread.start()

    def _run_url_import(self, url: str, folder: Path, start_time: datetime):
        try:
            from meetingscribe.downloader import download_audio

            audio_path, video_meta = download_audio(url, folder)

            duration = int(video_meta.get("duration") or 0)
            self.session_mgr.update_duration(folder, duration)
            self.session_mgr.update_status(folder, SessionStatus.TRANSCRIBING)
            self._refresh_list()

            from meetingscribe.transcriber import transcribe
            transcribe(
                audio_path=audio_path,
                output_path=folder / "transcript.md",
                language="ru",
                model_size=self.config.whisper_model,
                device=self.config.whisper_device,
            )

            meta = {
                "date": start_time.isoformat(),
                "duration_seconds": duration,
                "language": "ru",
                "meeting_type": "external",
                "audio_mode": "url_import",
                "source": "url",
                "source_url": video_meta.get("url", url),
                "source_title": video_meta.get("title", ""),
                "source_platform": video_meta.get("platform", ""),
                "has_ogg": audio_path.suffix in (".opus", ".ogg"),
            }
            (folder / "meta.json").write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            self.session_mgr.update_status(folder, SessionStatus.DONE)
        except Exception as e:
            logger.exception("Ошибка импорта по ссылке")
            self.session_mgr.update_status(folder, SessionStatus.ERROR)
            short = str(e).split("\n")[0][:120]
            self.popup.set_status(f"Ошибка: {short}")

        self.session_mgr.reload()
        self._refresh_list()

    # --- Manual transcription ---

    def _handle_transcribe(self, folder_key: str):
        folder = Path(folder_key)
        session = self.session_mgr.get_session(folder)
        if not session:
            return

        audio_path = None
        for ext in AUDIO_EXTENSIONS:
            candidate = folder / f"audio{ext}"
            if candidate.exists():
                audio_path = candidate
                break
        if audio_path is None:
            self.popup.set_status("Ошибка: аудиофайл не найден")
            return

        self.session_mgr.update_status(folder, SessionStatus.TRANSCRIBING)
        self._refresh_list()

        thread = threading.Thread(
            target=self._run_manual_transcription,
            args=(audio_path, folder, session),
            daemon=True,
        )
        thread.start()

    def _run_manual_transcription(
        self, audio_path: Path, folder: Path, session: RecordingSession,
    ):
        try:
            def _on_progress(p):
                self.popup.update_transcription_progress(str(folder), p)

            self.pipeline.run_transcription(
                wav_path=audio_path,
                meeting_type=session.meeting_type,
                language=session.language,
                duration_seconds=session.duration,
                start_time=session.start_time,
                audio_mode=session.audio_mode,
                on_progress=_on_progress,
            )
            self.session_mgr.update_status(folder, SessionStatus.DONE)
        except Exception:
            logger.exception("Ошибка транскрибации (ручная)")
            self.session_mgr.update_status(folder, SessionStatus.ERROR)

        self.session_mgr.reload()
        self._refresh_list()

    # --- Delete ---

    def _handle_delete(self, folder_key: str):
        folder = Path(folder_key)
        if folder.exists():
            try:
                from send2trash import send2trash
                send2trash(str(folder))
            except Exception as e:
                self.popup.set_status(f"Ошибка удаления: {e}")
                return

        self.session_mgr.remove_session(folder)
        try:
            from meetingscribe import db
            conn = db.get_connection()
            db.delete_meeting_by_folder(conn, folder_key)
            conn.close()
        except Exception:
            logger.exception("Не удалось удалить встречу из БД")
        self._refresh_list()

    # --- Misc ---

    def _handle_reload(self):
        self.session_mgr.reload()
        self._refresh_list()

    def _handle_open_folder(self, folder_key: str):
        os.startfile(folder_key)

    def _refresh_list(self):
        sessions = self.session_mgr.get_sorted_sessions()
        if self.config.hide_personal:
            sessions = [s for s in sessions if s.meeting_type != "personal"]
        self.popup.set_sessions(sessions)

    def _streams_alive(self) -> bool:
        for stream in (self.capture._loopback_stream, self.capture._mic_stream):
            if stream is not None:
                try:
                    if stream.is_active():
                        return True
                except Exception:
                    pass
        return False

    def _update_levels(self):
        silence_limit = self.config.silence_auto_stop_minutes * 60
        max_limit = self.config.max_recording_minutes * 60
        start = time.monotonic()
        dead_since = None
        while self.capture.is_recording:
            self.popup.update_level(self.capture.audio_level)
            # вотчдог: если все аудиопотоки умерли (смена устройства и т.п.) —
            # аварийно останавливаем запись, сохраняя то, что успело записаться
            if not self._streams_alive():
                if dead_since is None:
                    dead_since = time.monotonic()
                elif time.monotonic() - dead_since >= 5:
                    logger.error(
                        "Аудиопотоки неактивны более 5 с — аварийная остановка записи"
                    )
                    self.popup.trigger_auto_stop(
                        "Ошибка аудиопотока — запись остановлена и сохранена"
                    )
                    break
            else:
                dead_since = None
            if silence_limit > 0 and self.capture.silence_duration >= silence_limit:
                minutes = self.config.silence_auto_stop_minutes
                self.popup.trigger_auto_stop(
                    f"Автостоп: тишина более {minutes} мин."
                )
                break
            if max_limit > 0 and (time.monotonic() - start) >= max_limit:
                self.popup.trigger_auto_stop(
                    f"Автостоп: достигнут лимит {self.config.max_recording_minutes} мин."
                )
                break
            time.sleep(0.05)
        self.popup.update_level(0.0)

    def _quit(self):
        if self.capture._testing_mic:
            self.capture.stop_mic_test()

        if self.capture.is_recording:
            tmp = Path(self.config.recordings_dir) / "_abort.wav"
            self.capture.stop(tmp)
            tmp.unlink(missing_ok=True)

        self.popup.destroy()
        if self._tray:
            self._tray.stop()
