import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from meetingscribe.config import Config
from meetingscribe.ui.app import App

config = Config.load()
app = App(config)
app.run()
