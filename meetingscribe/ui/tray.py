import threading
from PIL import Image, ImageDraw
import pystray


def _create_icon_image(color: str = "green") -> Image.Image:
    img = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill=color)
    return img


def create_tray(on_open: callable, on_quit: callable) -> pystray.Icon:
    icon = pystray.Icon(
        "MeetingScribe",
        _create_icon_image("green"),
        "MeetingScribe",
        menu=pystray.Menu(
            pystray.MenuItem("Открыть", on_open, default=True),
            pystray.MenuItem("Выход", on_quit),
        ),
    )
    return icon


def set_tray_recording(icon: pystray.Icon, is_recording: bool):
    color = "red" if is_recording else "green"
    icon.icon = _create_icon_image(color)
