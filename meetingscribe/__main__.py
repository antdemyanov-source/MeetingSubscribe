import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from meetingscribe.config import Config
from meetingscribe.ui.app import App


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config = Config.load()
    app = App(config)
    app.run()


if __name__ == "__main__":
    main()
