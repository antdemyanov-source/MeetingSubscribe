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
from meetingscribe.session import RecordingSession, SessionManager, SessionStatus
from meetingscribe.storage import create_recording_paths
from meetingscribe.ui.tray import create_tray, set_tray_recording
from meetingscribe.ui.popup import PopupWindow


class App:
    def __init__(self, config: Config):
        self.config = config
        self.capture = AudioCapture(config.audio_sample_rate, config.mic_volume,
                                    config.silence_threshold)
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

        self.popup = PopupWindow(
            on_start=self._handle_start,
            on_stop=self._handle_stop,
            on_transcribe=self._handle_transcribe,
            on_delete=self._handle_delete,
            on_quit=self._quit,
            on_open_folder=self._handle_open_folder,
            on_reload=self._handle_reload,
            on_import=self._handle_import,
            on_url_import=self._handle_url_import,
            on_title_changed=self._handle_title_changed,
            on_whisper_model_changed=self._handle_whisper_model_changed,
            on_mic_changed=self._handle_mic_changed,
            on_mic_test_start=self._handle_mic_test_start,
            on_mic_test_stop=self._handle_mic_test_stop,
            on_settings=self._get_settings,
            on_settings_changed=self._handle_settings_changed,
            on_obsidian=self._handle_obsidian,
            mic_devices=mic_devices,
            initial_mic_name=config.mic_device_name,
            initial_whisper_model=config.whisper_model,
        )

    def run(self):
        self._tray = create_tray(
            on_open=lambda icon, item: self._open_popup(),
            on_quit=lambda icon, item: self._quit(),
        )

        popup_thread = threading.Thread(target=self._run_popup, daemon=True)
        popup_thread.start()

        self._tray.run()

    def _run_popup(self):
        self.popup.show()
        self._refresh_list()
        self.popup.run_mainloop()

    def _open_popup(self):
        self.popup.show()

    # --- Title ---

    def _handle_title_changed(self, folder_key: str, title: str):
        folder = Path(folder_key)
        self.session_mgr.update_title(folder, title)

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
        }

    def _handle_settings_changed(self, settings: dict):
        self.config.silence_threshold = settings["silence_threshold"]
        self.config.silence_auto_stop_minutes = settings["silence_auto_stop_minutes"]
        self.config.max_recording_minutes = settings["max_recording_minutes"]
        self.config.obsidian_vault_path = settings["obsidian_vault_path"]
        self.capture.silence_threshold = settings["silence_threshold"]
        self.config.save()

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
        except RuntimeError as e:
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
        duration = self.capture.stop(tmp_wav)

        if folder:
            self.session_mgr.update_duration(folder, duration)
            self.session_mgr.update_status(folder, SessionStatus.TRANSCRIBING)
            self._refresh_list()

        thread = threading.Thread(
            target=self._run_transcription,
            args=(tmp_wav, duration, folder, recording_type,
                  recording_language, start_time, recording_mic_only),
            daemon=True,
        )
        thread.start()

    def _run_transcription(
        self, wav_path: Path, duration: int, folder: Path | None,
        meeting_type: str, language: str, start_time: datetime, mic_only: bool,
    ):
        try:
            audio_mode = "mic" if mic_only else "loopback"
            self.pipeline.run_transcription(
                wav_path=wav_path,
                meeting_type=meeting_type,
                language=language,
                duration_seconds=duration,
                start_time=start_time,
                audio_mode=audio_mode,
            )
            if folder:
                self.session_mgr.update_status(folder, SessionStatus.DONE)
        except Exception:
            logger.exception("Ошибка транскрибации")
            if folder:
                self.session_mgr.update_status(folder, SessionStatus.ERROR)

        self._refresh_list()

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

        self._refresh_list()

    # --- Manual transcription ---

    def _handle_transcribe(self, folder_key: str):
        folder = Path(folder_key)
        session = self.session_mgr.get_session(folder)
        if not session:
            return

        audio_path = None
        for ext in (".wav", ".ogg", ".mp3", ".m4a", ".flac"):
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
            self.pipeline.run_transcription(
                wav_path=audio_path,
                meeting_type=session.meeting_type,
                language=session.language,
                duration_seconds=session.duration,
                start_time=session.start_time,
                audio_mode=session.audio_mode,
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
        if not folder.exists():
            self.session_mgr.remove_session(folder)
            self._refresh_list()
            return

        try:
            from send2trash import send2trash
            send2trash(str(folder))
        except Exception as e:
            self.popup.set_status(f"Ошибка удаления: {e}")
            return

        self.session_mgr.remove_session(folder)
        self._refresh_list()

    # --- Misc ---

    def _handle_reload(self):
        self.session_mgr.reload()
        self._refresh_list()

    def _handle_open_folder(self, folder_key: str):
        os.startfile(folder_key)

    def _refresh_list(self):
        sessions = self.session_mgr.get_sorted_sessions()
        self.popup.set_sessions(sessions)

    def _update_levels(self):
        silence_limit = self.config.silence_auto_stop_minutes * 60
        max_limit = self.config.max_recording_minutes * 60
        start = time.monotonic()
        while self.capture.is_recording:
            self.popup.update_level(self.capture.audio_level)
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
