import pytest
from unittest.mock import patch, MagicMock
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


def test_summarize_raises_without_api_key(tmp_path):
    output_path = tmp_path / "summary.md"
    with pytest.raises(RuntimeError):
        summarize(
            transcript="Test",
            output_path=output_path,
            meeting_type="work",
            language="ru",
            duration_seconds=60,
            api_key="",
        )
    assert not output_path.exists()


@patch("meetingscribe.summarizer._summarize_claude")
def test_summarize_returns_none_on_api_error(mock_claude, tmp_path):
    mock_claude.side_effect = Exception("API error")

    output_path = tmp_path / "summary.md"
    result = summarize(
        transcript="Test",
        output_path=output_path,
        meeting_type="work",
        language="ru",
        duration_seconds=60,
        api_key="sk-test",
    )

    assert result is None
    assert not output_path.exists()
