import json
import mimetypes
from pathlib import Path

import click

from ..voxtral_api import TranscriptionResponse
from ._db import apply_schema, store_transcription


@click.command(name="import-json")
@click.argument("json_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "-a",
    "--audio",
    "audio_path_str",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Optional audio file to store alongside the transcript",
)
@click.option(
    "-d",
    "--database",
    "db_path_str",
    type=click.Path(),
    default=None,
    help="Database path (default: derived from JSON filename)",
)
@click.option(
    "--url",
    "source_url",
    default=None,
    help="Optional source URL to record on the transcription row",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host used to print the serve URL (default: 127.0.0.1)",
)
@click.option(
    "-p",
    "--port",
    type=int,
    default=8001,
    help="Port used to print the serve URL (default: 8001)",
)
def scribe_import_json(json_path, audio_path_str, db_path_str, source_url, host, port):
    "Import a Voxtral-format transcript JSON into a database"

    json_path = Path(json_path)
    try:
        raw = json.loads(json_path.read_text())
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON: {e}")

    try:
        response = TranscriptionResponse.model_validate(raw)
    except Exception as e:
        raise click.ClickException(f"JSON does not match transcription format: {e}")

    if db_path_str is None:
        db_path = Path(f"{json_path.name}.db")
    else:
        db_path = Path(db_path_str)

    if audio_path_str:
        audio_path = Path(audio_path_str)
        file_bytes = audio_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(audio_path))
        if content_type is None:
            content_type = "audio/mpeg"
        filename = audio_path.name
    else:
        file_bytes = None
        content_type = None
        filename = json_path.name

    apply_schema(db_path)

    transcription_id, entries_count = store_transcription(
        db_path, filename, file_bytes, content_type, response, url=source_url
    )

    click.echo(f"Saved transcription ({entries_count} segments) to {db_path}")

    db_name = db_path.stem
    transcript_url = (
        f"http://{host}:{port}/{db_name}/-/scribe/transcription/{transcription_id}"
    )
    click.echo(transcript_url)
