from unittest.mock import patch, MagicMock
from pathlib import Path
from meetingscribe.summarizer import summarize, build_prompt, PROMPTS


def test_all_meeting_types_have_prompts():
    assert "work" in PROMPTS
    assert "english" in PROMPTS
    assert "personal" in PROMPTS


def test_build_prompt_work():
    prompt = build_prompt("Hello world transcript", "work")
    assert "Hello world transcript" in prompt
    assert "решения" in prompt.lower() or "action" in prompt.lower()


def test_build_prompt_english():
    prompt = build_prompt("Lesson transcript", "english")
    assert "Lesson transcript" in prompt
    assert "vocabulary" in prompt.lower() or "лексик" in prompt.lower()


def test_build_prompt_personal():
    prompt = build_prompt("Session transcript", "personal")
    assert "Session transcript" in prompt
    assert "инсайт" in prompt.lower() or "insight" in prompt.lower()


@patch("meetingscribe.summarizer.anthropic")
def test_summarize_calls_claude_api(mock_anthropic, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Summary\n\nTest summary content")]
    mock_client.messages.create.return_value = mock_response

    output_path = tmp_path / "summary.md"
    result = summarize(
        transcript="Test transcript text",
        output_path=output_path,
        meeting_type="work",
        language="ru",
        duration_seconds=300,
        api_key="sk-test",
        model="claude-sonnet-4-6",
    )

    assert output_path.exists()
    assert "Summary" in output_path.read_text(encoding="utf-8")
    mock_client.messages.create.assert_called_once()

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert len(call_kwargs["messages"]) == 1


@patch("meetingscribe.summarizer._summarize_gemini")
def test_summarize_uses_gemini_when_no_claude_key(mock_gemini, tmp_path):
    mock_gemini.return_value = "# Gemini Summary"

    output_path = tmp_path / "summary.md"
    result = summarize(
        transcript="Test transcript",
        output_path=output_path,
        meeting_type="work",
        language="ru",
        duration_seconds=60,
        api_key="",
        gemini_api_key="test-gemini-key",
    )

    assert result is not None
    assert output_path.exists()
    assert "Gemini Summary" in output_path.read_text(encoding="utf-8")
    mock_gemini.assert_called_once()


def test_summarize_returns_none_when_no_keys(tmp_path):
    output_path = tmp_path / "summary.md"
    result = summarize(
        transcript="Test",
        output_path=output_path,
        meeting_type="work",
        language="ru",
        duration_seconds=60,
        api_key="",
        gemini_api_key="",
    )
    assert result is None
    assert not output_path.exists()


@patch("meetingscribe.summarizer.anthropic")
def test_claude_preferred_over_gemini(mock_anthropic, tmp_path):
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="# Claude Summary")]
    mock_client.messages.create.return_value = mock_response

    output_path = tmp_path / "summary.md"
    result = summarize(
        transcript="Test",
        output_path=output_path,
        meeting_type="work",
        language="ru",
        duration_seconds=60,
        api_key="sk-test",
        gemini_api_key="gemini-key-also-set",
    )

    assert "Claude Summary" in output_path.read_text(encoding="utf-8")
    mock_client.messages.create.assert_called_once()
