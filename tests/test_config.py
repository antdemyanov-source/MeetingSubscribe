import json
from pathlib import Path
from meetingscribe.config import Config


def test_default_config_values():
    config = Config()
    assert config.default_language == "ru"
    assert config.default_meeting_type == "work"
    assert config.whisper_model == "turbo"
    assert config.whisper_device == "cpu"
    assert config.anthropic_api_key == ""
    assert config.anthropic_model == "claude-sonnet-4-6"
    assert config.audio_sample_rate == 44100
    assert config.keep_wav is False


def test_load_from_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "default_language": "en",
        "anthropic_api_key": "sk-test-123",
    }), encoding="utf-8")

    config = Config.load(config_path)
    assert config.default_language == "en"
    assert config.anthropic_api_key == "sk-test-123"
    assert config.whisper_model == "turbo"


def test_load_missing_file_returns_defaults(tmp_path):
    config = Config.load(tmp_path / "nonexistent.json")
    assert config.default_language == "ru"


def test_save_and_reload(tmp_path):
    config_path = tmp_path / "config.json"
    config = Config(anthropic_api_key="sk-saved")
    config.save(config_path)

    loaded = Config.load(config_path)
    assert loaded.anthropic_api_key == "sk-saved"


def test_load_ignores_unknown_keys(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "unknown_field": "value",
        "default_language": "en",
    }), encoding="utf-8")

    config = Config.load(config_path)
    assert config.default_language == "en"
