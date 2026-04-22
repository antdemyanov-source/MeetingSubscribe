import threading
import numpy as np
import pyaudiowpatch as pyaudio
import soundfile as sf
from pathlib import Path


class AudioCapture:
    def __init__(self, sample_rate: int = 44100):
        self.target_sample_rate = sample_rate
        self.is_recording = False
        self.audio_level = 0.0
        self._pa: pyaudio.PyAudio | None = None
        self._loopback_stream = None
        self._mic_stream = None
        self._loopback_frames: list[np.ndarray] = []
        self._mic_frames: list[np.ndarray] = []
        self._loopback_channels = 2
        self._actual_rate = sample_rate
        self._lock = threading.Lock()

    def _loopback_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16)
        with self._lock:
            self._loopback_frames.append(data.copy())
        rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))
        self.audio_level = min(1.0, rms / 3276.8)
        return (in_data, pyaudio.paContinue)

    def _mic_callback(self, in_data, frame_count, time_info, status):
        data = np.frombuffer(in_data, dtype=np.int16)
        with self._lock:
            self._mic_frames.append(data.copy())
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

    def start(self):
        self._pa = pyaudio.PyAudio()
        self._loopback_frames = []
        self._mic_frames = []
        self.audio_level = 0.0

        loopback_device = self._find_loopback_device()
        if loopback_device is None:
            self._pa.terminate()
            raise RuntimeError(
                "Не найдено устройство loopback. Проверьте аудиовыход."
            )

        self._loopback_channels = int(loopback_device["maxInputChannels"])
        self._actual_rate = int(loopback_device["defaultSampleRate"])

        self._loopback_stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=self._loopback_channels,
            rate=self._actual_rate,
            frames_per_buffer=1024,
            input=True,
            input_device_index=loopback_device["index"],
            stream_callback=self._loopback_callback,
        )

        try:
            mic_info = self._pa.get_default_input_device_info()
            self._mic_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self._actual_rate,
                frames_per_buffer=1024,
                input=True,
                input_device_index=mic_info["index"],
                stream_callback=self._mic_callback,
            )
        except (OSError, pyaudio.PyAudioError):
            self._mic_stream = None

        self.is_recording = True

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
            loopback_data = (
                np.concatenate(self._loopback_frames)
                if self._loopback_frames
                else np.array([], dtype=np.int16)
            )
            mic_data = (
                np.concatenate(self._mic_frames)
                if self._mic_frames
                else np.array([], dtype=np.int16)
            )

        channels = self._loopback_channels

        if len(loopback_data) > 0:
            loopback_data = loopback_data.reshape(-1, channels).astype(np.float32)
        else:
            loopback_data = np.zeros((0, channels), dtype=np.float32)

        if len(mic_data) > 0:
            mic_mono = mic_data.reshape(-1, 1).astype(np.float32)
            mic_data = np.repeat(mic_mono, channels, axis=1)
        else:
            mic_data = np.zeros((0, channels), dtype=np.float32)

        max_len = max(len(loopback_data), len(mic_data))
        if max_len == 0:
            sf.write(str(output_path), np.zeros((1, channels), dtype=np.int16), self._actual_rate)
            return 0

        if len(loopback_data) < max_len:
            pad = np.zeros((max_len - len(loopback_data), channels), dtype=np.float32)
            loopback_data = np.concatenate([loopback_data, pad])
        if len(mic_data) < max_len:
            pad = np.zeros((max_len - len(mic_data), channels), dtype=np.float32)
            mic_data = np.concatenate([mic_data, pad])

        mixed = (loopback_data + mic_data) / 2.0
        mixed = np.clip(mixed, -32768, 32767).astype(np.int16)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), mixed, self._actual_rate)

        return int(len(mixed) / self._actual_rate)
