import threading
from pathlib import Path
from PIL import Image, ImageDraw
import pystray

_ICON_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"


def _create_icon_image(color: str = "green") -> Image.Image:
    img = Image.new("RGB", (64, 64))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill=color)
    return img


def _load_tray_icon() -> Image.Image:
    if _ICON_PATH.exists():
        return Image.open(_ICON_PATH)
    return _create_icon_image("green")


def _recording_icon() -> Image.Image:
    """Tray icon with red recording dot overlay."""
    base = _load_tray_icon().convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.ellipse([42, 42, 62, 62], fill=(220, 50, 50, 255))
    return Image.alpha_composite(base, overlay)


def create_tray(on_open: callable, on_quit: callable) -> pystray.Icon:
    icon = pystray.Icon(
        "MeetingScribe",
        _load_tray_icon(),
        "MeetingScribe",
        menu=pystray.Menu(
            pystray.MenuItem("Открыть", on_open, default=True),
            pystray.MenuItem("Выход", on_quit),
        ),
    )
    return icon


def set_tray_recording(icon: pystray.Icon, is_recording: bool):
    if is_recording:
        icon.icon = _recording_icon()
    else:
        icon.icon = _load_tray_icon()
