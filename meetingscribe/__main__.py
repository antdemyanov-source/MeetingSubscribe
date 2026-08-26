import logging
import logging.handlers
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from meetingscribe.config import Config
from meetingscribe.ui.app import App

LOG_DIR = Path(__file__).parent.parent / "logs"


def main():
    # pythonw не имеет консоли — без файлового лога ошибки теряются
    LOG_DIR.mkdir(exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "meetingscribe.log", maxBytes=2_000_000, backupCount=3,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[file_handler, logging.StreamHandler()],
    )

    def _thread_excepthook(args):
        logging.getLogger("thread").error(
            "Необработанная ошибка в потоке %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
    threading.excepthook = _thread_excepthook
    config = Config.load()
    app = App(config)
    app.run()


if __name__ == "__main__":
    main()
