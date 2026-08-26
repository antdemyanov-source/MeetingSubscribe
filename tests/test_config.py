import json
from pathlib import Path
from meetingscribe.config import Config


def test_default_config_values():
    config = Config()
    assert config.default_language == "ru"
    assert config.default_meeting_type == "work"
    assert config.whisper_model == "turbo"
    assert config.whisper_device == "cpu"
    assert config.audio_sample_rate == 44100
    assert config.keep_wav is False
    assert config.silence_threshold == 0.03
    assert config.obsidian_vault_path == ""
    assert config.ui_backend == "tk"
    assert config.anthropic_api_key == ""
    assert config.auto_transcribe is True
    assert "{transcript}" in config.summary_cli
    assert config.summary_activities is True
    assert config.summary_tasks is True


def test_load_ui_backend(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"ui_backend": "web"}), encoding="utf-8")
    assert Config.load(config_path).ui_backend == "web"


def test_load_from_file(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "default_language": "en",
        "obsidian_vault_path": "C:/vault",
    }), encoding="utf-8")

    config = Config.load(config_path)
    assert config.default_language == "en"
    assert config.obsidian_vault_path == "C:/vault"
    assert config.whisper_model == "turbo"


def test_load_missing_file_returns_defaults(tmp_path):
    config = Config.load(tmp_path / "nonexistent.json")
    assert config.default_language == "ru"


def test_save_and_reload(tmp_path):
    config_path = tmp_path / "config.json"
    config = Config(obsidian_vault_path="C:/vault")
    config.save(config_path)

    loaded = Config.load(config_path)
    assert loaded.obsidian_vault_path == "C:/vault"


def test_load_ignores_unknown_keys(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "unknown_field": "value",
        "default_language": "en",
    }), encoding="utf-8")

    config = Config.load(config_path)
    assert config.default_language == "en"
