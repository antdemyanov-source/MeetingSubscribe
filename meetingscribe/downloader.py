import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    parts = urlparse(url)
    query = parts.query
    if "?" in query:
        first, rest = query.split("?", 1)
        query = first + "&" + rest
    params = parse_qs(query)
    for key in ("utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "r"):
        params.pop(key, None)
    clean_query = urlencode(params, doseq=True)
    return urlunparse(parts._replace(query=clean_query))


def download_audio(url: str, output_dir: Path) -> tuple[Path, dict]:
    """Download audio from a URL using yt-dlp. Returns (audio_path, info_dict)."""
    import yt_dlp

    url = _normalize_url(url)

    ffmpeg = shutil.which("ffmpeg")

    output_template = str(output_dir / "audio.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "opus",
            "preferredquality": "64",
        }],
    }

    if ffmpeg:
        ydl_opts["ffmpeg_location"] = str(Path(ffmpeg).parent)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    audio_path = output_dir / "audio.opus"
    if not audio_path.exists():
        for f in output_dir.glob("audio.*"):
            if f.suffix in (".opus", ".ogg", ".m4a", ".mp3", ".wav", ".webm"):
                audio_path = f
                break

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found in {output_dir}")

    meta = {
        "title": info.get("title", ""),
        "url": info.get("webpage_url") or info.get("original_url") or url,
        "duration": info.get("duration") or 0,
        "uploader": info.get("uploader", ""),
        "platform": info.get("extractor_key", ""),
    }

    return audio_path, meta
