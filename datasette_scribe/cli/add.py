import asyncio
import mimetypes
import os
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
        "allow_remote_components": ["ejs:github"],
    }

    click.echo("Downloading audio...")
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

    click.echo(f"Converting to mp3: {output_path}")
    return output_path, title


@click.command(name="add")
@click.argument("source")
@click.option(
    "-d",
    "--database",
    "db_path_str",
    type=click.Path(),
    default=None,
    help="Database path (default: derived from source)",
)
def scribe_add(source, db_path_str):
    "Transcribe an audio file or URL and add it to a database"

    if not os.environ.get("MISTRAL_API_KEY"):
        raise click.ClickException(
            "MISTRAL_API_KEY environment variable is required. "
            "Get one at https://console.mistral.ai/"
        )

    if _is_url(source):
        try:
            audio_path, title = _download_audio_from_url(source)
        except Exception as e:
            raise click.ClickException(f"Download failed: {e}")
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
        url = source if _is_url(source) else None
        default_db_name = audio_path.name

    if db_path_str is None:
        db_path = Path(f"{default_db_name}.db")
    else:
        db_path = Path(db_path_str)

    content_type, _ = mimetypes.guess_type(str(audio_path))
    if content_type is None:
        content_type = "audio/mpeg"

    click.echo(f"Uploading {filename} to Mistral for transcription...")

    file_bytes = audio_path.read_bytes()

    apply_schema(db_path)

    try:
        response = asyncio.run(transcribe(file_data=file_bytes, filename=filename))
    except Exception as e:
        # Build resume command using the local file
        resume_parts = ["datasette-scribe", "add", str(audio_path)]
        if db_path_str:
            resume_parts.extend(["-d", db_path_str])
        resume_cmd = " ".join(resume_parts)
        raise click.ClickException(
            f"Transcription failed: {e}\n\n"
            f"To retry without re-downloading:\n  {resume_cmd}"
        )

    transcription_id, entries_count = store_transcription(
        db_path, filename, file_bytes, content_type, response, url=url
    )

    click.echo(f"Saved transcription ({entries_count} segments) to {db_path}")
