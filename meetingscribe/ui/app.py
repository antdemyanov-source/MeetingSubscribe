import threading
import time
from datetime import datetime
from pathlib import Path

from meetingscribe.config import Config
from meetingscribe.audio_capture import AudioCapture
from meetingscribe.pipeline import Pipeline, PipelineStatus
from meetingscribe.ui.tray import create_tray, set_tray_recording
from meetingscribe.ui.popup import PopupWindow


class App:
    def __init__(self, config: Config):
        self.config = config
        self.capture = AudioCapture(config.audio_sample_rate)
        self.pipeline = Pipeline(config)

        self._recording_language = "ru"
        self._recording_type = "work"
        self._start_time: datetime | None = None
        self._level_thread: threading.Thread | None = None
        self._tray = None

        self.popup = PopupWindow(
            on_start=self._handle_start,
            on_stop=self._handle_stop,
            on_api_key_changed=self._handle_api_key_changed,
            initial_api_key=config.anthropic_api_key,
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
        self.popup.run_mainloop()

    def _open_popup(self):
        self.popup.show()

    def _handle_start(self, language: str, meeting_type: str):
        self._recording_language = language
        self._recording_type = meeting_type
        self._start_time = datetime.now()

        try:
            self.capture.start()
        except RuntimeError as e:
            self.popup.set_status(f"Ошибка: {e}")
            self.popup.reset_after_processing()
            return

        if self._tray:
            set_tray_recording(self._tray, True)

        self._level_thread = threading.Thread(target=self._update_levels, daemon=True)
        self._level_thread.start()

    def _handle_stop(self):
        if self._tray:
            set_tray_recording(self._tray, False)

        tmp_wav = Path(self.config.recordings_dir) / "_temp_recording.wav"
        tmp_wav.parent.mkdir(parents=True, exist_ok=True)
        duration = self.capture.stop(tmp_wav)

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(tmp_wav, duration),
            daemon=True,
        )
        thread.start()

    def _run_pipeline(self, wav_path: Path, duration: int):
        def on_status(status: PipelineStatus):
            self.popup.set_status(status.value)

        try:
            self.pipeline.run(
                wav_path=wav_path,
                meeting_type=self._recording_type,
                language=self._recording_language,
                duration_seconds=duration,
                start_time=self._start_time or datetime.now(),
                on_status=on_status,
            )
        except Exception as e:
            self.popup.set_status(f"Ошибка: {e}")

        self.popup.reset_after_processing()

    def _update_levels(self):
        while self.capture.is_recording:
            self.popup.update_level(self.capture.audio_level)
            time.sleep(0.05)
        self.popup.update_level(0.0)

    def _handle_api_key_changed(self, api_key: str):
        self.config.anthropic_api_key = api_key
        self.config.save()
        self.pipeline = Pipeline(self.config)

    def _quit(self):
        if self.capture.is_recording:
            tmp = Path(self.config.recordings_dir) / "_abort.wav"
            self.capture.stop(tmp)
            tmp.unlink(missing_ok=True)

        self.popup.destroy()
        if self._tray:
            self._tray.stop()
