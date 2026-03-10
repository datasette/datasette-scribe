import asyncio
import mimetypes
import re
import tempfile
from pathlib import Path

import click

from ..voxtral_api import transcribe
from ._db import apply_schema, store_transcription

_URL_RE = re.compile(r"https?://")


def _is_url(s: str) -> bool:
    return bool(_URL_RE.match(s))


def _download_audio_from_url(url: str) -> tuple[Path, str]:
    """Download audio from a URL using yt-dlp. Returns (temp_path, title)."""
    try:
        import yt_dlp
    except ImportError:
        raise click.ClickException(
            "yt-dlp is required for URL support. Install it with: "
            "uv pip install 'datasette-scribe[yt]'"
        )

    tmp_dir = tempfile.mkdtemp()
    output_path = Path(tmp_dir) / "audio.mp3"

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_path.with_suffix("")),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "audio")

    # yt-dlp may add the extension itself
    if not output_path.exists():
        files = list(Path(tmp_dir).glob("audio.*"))
        if files:
            output_path = files[0]
        else:
            raise click.ClickException("yt-dlp download failed: no output file found")

    return output_path, title


@click.command(name="add")
@click.argument("source")
@click.option("-d", "--database", "db_path_str", type=click.Path(), default=None, help="Database path (default: derived from source)")
def scribe_add(source, db_path_str):
    "Transcribe an audio file or URL and add it to a database"

    if _is_url(source):
        click.echo(f"Downloading audio from {source}...")
        audio_path, title = _download_audio_from_url(source)
        filename = f"{title}.mp3"
        url = source
        default_db_name = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "-")
        if not default_db_name:
            default_db_name = "scribe"
    else:
        audio_path = Path(source)
        if not audio_path.exists():
            raise click.ClickException(f"File not found: {source}")
        filename = audio_path.name
        url = None
        default_db_name = audio_path.name

    if db_path_str is None:
        db_path = Path(f"{default_db_name}.db")
    else:
        db_path = Path(db_path_str)

    content_type, _ = mimetypes.guess_type(str(audio_path))
    if content_type is None:
        content_type = "audio/mpeg"

    click.echo(f"Transcribing {filename}...")

    file_bytes = audio_path.read_bytes()

    apply_schema(db_path)

    try:
        response = asyncio.run(transcribe(file_data=file_bytes, filename=filename))
    except Exception as e:
        raise click.ClickException(f"Transcription failed: {e}")

    transcription_id, entries_count = store_transcription(
        db_path, filename, file_bytes, content_type, response, url=url
    )

    click.echo(f"Saved transcription ({entries_count} segments) to {db_path}")
