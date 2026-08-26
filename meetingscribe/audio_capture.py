import logging
import threading
import time
import numpy as np
import pyaudiowpatch as pyaudio
import soundfile as sf
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SILENCE_THRESHOLD = 0.03


def _is_virtual_input(name: str) -> bool:
    low = name.lower()
    return "stereo mix" in low or "what u hear" in low or "wave out" in low


def list_microphones() -> list[dict]:
    pa = pyaudio.PyAudio()
    try:
        wasapi_index = pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        mics = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if (
                int(info.get("hostApi", -1)) == wasapi_index
                and int(info.get("maxInputChannels", 0)) > 0
                and not info.get("isLoopbackDevice", False)
                and not _is_virtual_input(info.get("name", ""))
            ):
                mics.append({
                    "index": int(info["index"]),
                    "name": info["name"],
                    "channels": int(info["maxInputChannels"]),
                    "sample_rate": int(info["defaultSampleRate"]),
                })
        logger.info("Найдено %d микрофонов: %s", len(mics),
                     ", ".join(f"[{m['index']}] {m['name']} ({m['sample_rate']}Hz)"
                               for m in mics))
        return mics
    finally:
        pa.terminate()


def _resample(data: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    if orig_rate == target_rate or len(data) == 0:
        return data
    ratio = target_rate / orig_rate
    new_len = int(len(data) * ratio)
    x_old = np.linspace(0, 1, len(data), endpoint=False)
    x_new = np.linspace(0, 1, new_len, endpoint=False)
    resampled = np.interp(x_new, x_old, data.astype(np.float32))
    logger.debug("Ресемплинг микрофона: %d Hz → %d Hz (%d → %d сэмплов)",
                 orig_rate, target_rate, len(data), new_len)
    return resampled.astype(np.int16)


class AudioCapture:
    def __init__(self, sample_rate: int = 44100, mic_volume: float = 0.5,
                 silence_threshold: float = DEFAULT_SILENCE_THRESHOLD,
                 mic_device_name: str = ""):
        self.target_sample_rate = sample_rate
        self.mic_volume = max(0.0, min(1.0, mic_volume))
        self.silence_threshold = silence_threshold
        self.is_recording = False
        self.audio_level = 0.0
        self._pa: pyaudio.PyAudio | None = None
        self._loopback_stream = None
        self._mic_stream = None
        self._loopback_frames: list[np.ndarray] = []
        self._mic_frames: list[np.ndarray] = []
        self._loopback_channels = 2
        self._actual_rate = sample_rate
        self._mic_rate: int | None = None
        self._mic_only = False
        self._mic_device_index: int | None = None
        self._mic_device_name: str = mic_device_name
        self._testing_mic = False
        self._test_stream = None
        self._lock = threading.Lock()
        self._last_sound_time: float = 0.0
        self._loopback_level: float = 0.0
        self._mic_level: float = 0.0

    def _loopback_callback(self, in_data, frame_count, time_info, status):
        if status:
            logger.warning("Loopback stream status: %s", status)
        data = np.frombuffer(in_data, dtype=np.int16)
        with self._lock:
            self._loopback_frames.append(data.copy())
        rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))
        level = min(1.0, rms / 3276.8)
        self._loopback_level = level
        self.audio_level = max(self._loopback_level, self._mic_level)
        if self.audio_level >= self.silence_threshold:
            self._last_sound_time = time.monotonic()
        return (in_data, pyaudio.paContinue)

    def _mic_callback(self, in_data, frame_count, time_info, status):
        if status:
            logger.warning("Mic stream status: %s", status)
        data = np.frombuffer(in_data, dtype=np.int16)
        with self._lock:
            self._mic_frames.append(data.copy())
        rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))
        level = min(1.0, rms / 3276.8)
        self._mic_level = level
        self.audio_level = max(self._loopback_level, self._mic_level)
        if self.audio_level >= self.silence_threshold:
            self._last_sound_time = time.monotonic()
        return (in_data, pyaudio.paContinue)

    def _find_loopback_device(self):
        wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_speakers = self._pa.get_device_info_by_index(
            wasapi_info["defaultOutputDevice"]
        )
        for loopback in self._pa.get_loopback_device_info_generator():
            if default_speakers["name"] in loopback["name"]:
                return loopback
        return None

    def set_mic_device(self, device_index: int | None):
        self._mic_device_index = device_index

    def start_mic_test(self, device_index: int | None = None):
        idx = device_index if device_index is not None else self._mic_device_index
        self._pa = pyaudio.PyAudio()
        self.audio_level = 0.0
        self._testing_mic = True

        try:
            if idx is not None:
                mic_info = self._pa.get_device_info_by_index(idx)
            else:
                mic_info = self._pa.get_default_input_device_info()
            rate = int(mic_info["defaultSampleRate"])
            self._test_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=rate,
                frames_per_buffer=1024,
                input=True,
                input_device_index=int(mic_info["index"]),
                stream_callback=self._test_callback,
            )
        except Exception as e:
            self._testing_mic = False
            if self._pa:
                self._pa.terminate()
                self._pa = None
            raise RuntimeError(f"Не удалось открыть микрофон: {e}")

    def _test_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16)
        rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))
        self.audio_level = min(1.0, rms / 3276.8)
        return (in_data, pyaudio.paContinue)

    def stop_mic_test(self):
        self._testing_mic = False
        if self._test_stream:
            self._test_stream.stop_stream()
            self._test_stream.close()
            self._test_stream = None
        if self._pa and not self.is_recording:
            self._pa.terminate()
            self._pa = None
        self.audio_level = 0.0

    def _is_real_microphone(self, info: dict) -> bool:
        if info.get("isLoopbackDevice", False):
            return False
        if _is_virtual_input(info.get("name", "")):
            return False
        return int(info.get("maxInputChannels", 0)) > 0

    def _find_mic_by_name(self, name: str) -> dict | None:
        wasapi_index = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if (
                int(info.get("hostApi", -1)) == wasapi_index
                and info.get("name") == name
                and self._is_real_microphone(info)
            ):
                return info
        return None

    def _find_any_real_mic(self) -> dict | None:
        wasapi_index = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if (
                int(info.get("hostApi", -1)) == wasapi_index
                and self._is_real_microphone(info)
            ):
                return info
        return None

    def _open_mic_stream(self):
        idx = self._mic_device_index
        mic_info = None
        if idx is not None:
            try:
                info = self._pa.get_device_info_by_index(idx)
                if self._is_real_microphone(info):
                    mic_info = info
                    logger.info("Микрофон по индексу %d: %s", idx, mic_info["name"])
                else:
                    logger.warning("Устройство %d (%s) — не микрофон, пропускаю",
                                   idx, info.get("name", "?"))
            except OSError:
                logger.warning("Микрофон с индексом %d не найден", idx)
        if mic_info is None and self._mic_device_name:
            mic_info = self._find_mic_by_name(self._mic_device_name)
            if mic_info:
                logger.info("Микрофон найден по имени '%s': [%d]",
                            self._mic_device_name, int(mic_info["index"]))
        if mic_info is None:
            mic_info = self._find_any_real_mic()
            if mic_info:
                logger.info("Fallback микрофон: [%d] %s",
                            int(mic_info["index"]), mic_info["name"])
        if mic_info is None:
            if self._mic_only:
                if self._pa:
                    self._pa.terminate()
                    self._pa = None
                raise RuntimeError("Не найден ни один микрофон.")
            logger.warning("Микрофон не найден, запись только через loopback")
            self._mic_stream = None
            return

        mic_native_rate = int(mic_info["defaultSampleRate"])
        if self._mic_only:
            self._actual_rate = mic_native_rate
            self._mic_rate = mic_native_rate
        else:
            self._mic_rate = mic_native_rate

        stream_rate = mic_native_rate if not self._mic_only else self._actual_rate
        logger.info("Открываю микрофон: rate=%d Hz (native=%d Hz, loopback=%d Hz)",
                     stream_rate, mic_native_rate, self._actual_rate)

        try:
            self._mic_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=stream_rate,
                frames_per_buffer=1024,
                input=True,
                input_device_index=int(mic_info["index"]),
                stream_callback=self._mic_callback,
            )
        except OSError as e:
            if self._mic_only:
                if self._pa:
                    self._pa.terminate()
                    self._pa = None
                raise RuntimeError(f"Не удалось открыть микрофон: {e}")
            logger.error("Не удалось открыть микрофон: %s", e)
            self._mic_stream = None

    @property
    def silence_duration(self) -> float:
        if not self.is_recording or self._last_sound_time == 0.0:
            return 0.0
        return time.monotonic() - self._last_sound_time

    def start(self, mic_only: bool = False):
        self._mic_only = mic_only
        self._pa = pyaudio.PyAudio()
        self._loopback_frames = []
        self._mic_frames = []
        self._mic_rate = None
        self.audio_level = 0.0
        self._loopback_level = 0.0
        self._mic_level = 0.0
        self._last_sound_time = time.monotonic()

        logger.info("Начало записи: режим=%s", "mic_only" if mic_only else "loopback+mic")

        if not mic_only:
            loopback_device = self._find_loopback_device()
            if loopback_device is None:
                self._pa.terminate()
                raise RuntimeError(
                    "Не найдено устройство loopback. Проверьте аудиовыход."
                )

            self._loopback_channels = int(loopback_device["maxInputChannels"])
            self._actual_rate = int(loopback_device["defaultSampleRate"])
            logger.info("Loopback: %s, channels=%d, rate=%d Hz",
                        loopback_device["name"], self._loopback_channels,
                        self._actual_rate)

            self._loopback_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=self._loopback_channels,
                rate=self._actual_rate,
                frames_per_buffer=1024,
                input=True,
                input_device_index=loopback_device["index"],
                stream_callback=self._loopback_callback,
            )

        self._open_mic_stream()

        self.is_recording = True
        logger.info("Запись запущена: loopback=%s, mic=%s",
                     self._loopback_stream is not None,
                     self._mic_stream is not None)

    def stop(self, output_path: Path) -> int:
        self.is_recording = False

        if self._loopback_stream:
            self._loopback_stream.stop_stream()
            self._loopback_stream.close()
            self._loopback_stream = None
        if self._mic_stream:
            self._mic_stream.stop_stream()
            self._mic_stream.close()
            self._mic_stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None

        with self._lock:
            mic_data = (
                np.concatenate(self._mic_frames)
                if self._mic_frames
                else np.array([], dtype=np.int16)
            )
            loopback_data = (
                np.concatenate(self._loopback_frames)
                if self._loopback_frames
                else np.array([], dtype=np.int16)
            )

        logger.info("Остановка записи: loopback=%d сэмплов, mic=%d сэмплов",
                     len(loopback_data), len(mic_data))

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self._mic_only:
            if len(mic_data) == 0:
                logger.warning("Mic-only: нет данных с микрофона")
                sf.write(str(output_path), np.zeros((1, 1), dtype=np.int16), self._actual_rate)
                return 0
            sf.write(str(output_path), mic_data, self._actual_rate)
            return int(len(mic_data) / self._actual_rate)

        channels = self._loopback_channels

        if len(loopback_data) > 0:
            loopback_data = loopback_data.reshape(-1, channels).astype(np.float32)
        else:
            loopback_data = np.zeros((0, channels), dtype=np.float32)

        if len(mic_data) > 0:
            if self._mic_rate and self._mic_rate != self._actual_rate:
                mic_data = _resample(mic_data, self._mic_rate, self._actual_rate)
            mic_rms = np.sqrt(np.mean(mic_data.astype(np.float32) ** 2))
            logger.info("Микрофон: %d сэмплов, RMS=%.1f", len(mic_data), mic_rms)
            mic_mono = mic_data.reshape(-1, 1).astype(np.float32)
            mic_data = np.repeat(mic_mono, channels, axis=1)
        else:
            logger.warning("Микрофон: 0 сэмплов — данные не поступали")
            mic_data = np.zeros((0, channels), dtype=np.float32)

        max_len = max(len(loopback_data), len(mic_data))
        if max_len == 0:
            logger.warning("Нет аудиоданных ни из loopback, ни из микрофона")
            sf.write(str(output_path), np.zeros((1, channels), dtype=np.int16), self._actual_rate)
            return 0

        if len(loopback_data) < max_len:
            pad = np.zeros((max_len - len(loopback_data), channels), dtype=np.float32)
            loopback_data = np.concatenate([loopback_data, pad])
        if len(mic_data) < max_len:
            pad = np.zeros((max_len - len(mic_data), channels), dtype=np.float32)
            mic_data = np.concatenate([mic_data, pad])

        mixed = loopback_data + mic_data * self.mic_volume
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)

        logger.info("Микширование: loopback×1.0 + mic×%.2f, итого %d фреймов, rate=%d Hz",
                     self.mic_volume, len(mixed), self._actual_rate)

        sf.write(str(output_path), mixed, self._actual_rate)

        return int(len(mixed) / self._actual_rate)
