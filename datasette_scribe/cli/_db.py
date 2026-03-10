import sqlite3
from pathlib import Path

from ..router import SCHEMA_SQL


def apply_schema(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.close()


def store_transcription(db_path: Path, filename: str, file_bytes: bytes, content_type: str, response, *, url=None):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    input_type = "url" if url else "file"
    cursor.execute(
        """
        insert into datasette_scribe_transcriptions (url, input_type, filename, model, granularity, submitted_at, completed_at, usage)
        values (?, ?, ?, ?, 'segment', datetime('now', 'subsec'), datetime('now', 'subsec'), ?)
        """,
        [
            url,
            input_type,
            filename,
            response.model,
            response.usage.model_dump_json() if response.usage else None,
        ],
    )
    transcription_id = cursor.lastrowid

    cursor.execute(
        "insert into datasette_scribe_audio_blobs (transcription_id, data, content_type) values (?, ?, ?)",
        [transcription_id, file_bytes, content_type],
    )

    seen_speakers = set()
    for segment in response.segments:
        scoped_speaker = (
            f"t{transcription_id}_{segment.speaker_id}"
            if segment.speaker_id
            else None
        )
        cursor.execute(
            """
            insert into datasette_scribe_transcription_entries
                (transcription_id, start, end, speaker_id, text, original_text, original_speaker_id)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                transcription_id,
                segment.start,
                segment.end,
                scoped_speaker,
                segment.text,
                segment.text,
                segment.speaker_id,
            ],
        )
        if scoped_speaker and scoped_speaker not in seen_speakers:
            seen_speakers.add(scoped_speaker)
            cursor.execute(
                "insert or ignore into datasette_scribe_speakers (name, is_original) values (?, 1)",
                [scoped_speaker],
            )

    conn.commit()
    conn.close()
    return transcription_id, len(response.segments)
