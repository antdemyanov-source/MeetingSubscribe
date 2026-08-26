import json
from unittest.mock import patch, MagicMock
from pathlib import Path
from datetime import datetime
from meetingscribe.pipeline import Pipeline, PipelineStatus
from meetingscribe.config import Config


def _make_config(tmp_path, **overrides):
    defaults = {
        "recordings_dir": str(tmp_path / "recordings"),
        "keep_wav": False,
    }
    defaults.update(overrides)
    return Config(**defaults)


@patch("meetingscribe.pipeline.convert_to_ogg")
@patch("meetingscribe.transcriber.transcribe")
def test_pipeline_runs_all_steps(mock_transcribe, mock_convert, tmp_path):
    config = _make_config(tmp_path)
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"fake wav")

    mock_transcribe.return_value = "transcribed text"

    pipeline = Pipeline(config)
    status_log = []
    pipeline.run(
        wav_path=wav_path,
        meeting_type="work",
        language="ru",
        duration_seconds=120,
        start_time=datetime(2026, 4, 22, 14, 30),
        on_status=lambda s: status_log.append(s),
    )

    mock_transcribe.assert_called_once()
    mock_convert.assert_called_once()

    assert PipelineStatus.TRANSCRIBING in status_log
    assert PipelineStatus.CONVERTING in status_log
    assert PipelineStatus.DONE in status_log


@patch("meetingscribe.pipeline.convert_to_ogg")
@patch("meetingscribe.transcriber.transcribe")
def test_pipeline_writes_meta_json(mock_transcribe, mock_convert, tmp_path):
    config = _make_config(tmp_path)
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"fake wav")

    mock_transcribe.return_value = "text"

    pipeline = Pipeline(config)
    pipeline.run(
        wav_path=wav_path,
        meeting_type="english",
        language="en",
        duration_seconds=3600,
        start_time=datetime(2026, 4, 22, 14, 30),
        on_status=lambda s: None,
    )

    recordings_dir = Path(config.recordings_dir)
    meta_files = list(recordings_dir.rglob("meta.json"))
    assert len(meta_files) == 1

    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert meta["language"] == "en"
    assert meta["meeting_type"] == "english"
    assert meta["duration_seconds"] == 3600
