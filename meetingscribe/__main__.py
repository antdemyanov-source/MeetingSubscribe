import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from meetingscribe.config import Config
from meetingscribe.ui.app import App


def main():
    config = Config.load()

    if not config.anthropic_api_key:
        print(
            "WARNING: Anthropic API key not set in config.json. "
            "Summaries will be skipped."
        )

    app = App(config)
    app.run()


if __name__ == "__main__":
    main()
