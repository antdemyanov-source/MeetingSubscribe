import logging
import sys
import os
import msvcrt
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    filename=str(Path(__file__).parent / "meetingscribe.log"),
    encoding="utf-8",
)

sys.path.insert(0, str(Path(__file__).parent))

LOCK_FILE = Path(__file__).parent / ".meetingscribe.lock"


def acquire_lock():
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return fd
    except (OSError, IOError):
        return None


lock_fd = acquire_lock()
if lock_fd is None:
    sys.exit(0)

from meetingscribe.config import Config
from meetingscribe.ui.app import App

config = Config.load()
app = App(config)
app.run()
