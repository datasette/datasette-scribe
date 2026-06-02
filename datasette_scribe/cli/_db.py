import sqlite3
from pathlib import Path

from ..router import SCHEMA_SQL


def apply_schema(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.close()


def store_transcription(
    db_path: Path,
    filename: str | None,
    file_bytes: bytes | None,
    content_type: str | None,
    response,
    *,
    url=None,
) -> tuple[int, int]:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    if url:
        input_type = "url"
    elif file_bytes is not None:
        input_type = "file"
    else:
        input_type = "import"
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
    assert transcription_id is not None

    if file_bytes is not None:
        cursor.execute(
            "insert into datasette_scribe_audio_blobs (transcription_id, data, content_type) values (?, ?, ?)",
            [transcription_id, file_bytes, content_type],
        )

    # Mirror of datasette_scribe.routes._scope.store_segments (sync sqlite3
    # variant). Speakers are scoped to the freshly created standalone transcript;
    # raw labels are unique per-transcript so no prefix is needed, and entries
    # link to speakers by integer id. Keep the two in sync.
    speaker_id_for: dict[str, int] = {}
    for segment in response.segments:
        raw = segment.speaker_id
        sid = None
        if raw:
            if raw not in speaker_id_for:
                cursor.execute(
                    "insert into datasette_scribe_speakers"
                    " (transcription_id, name, is_configured) values (?, ?, 0)",
                    [transcription_id, raw],
                )
                speaker_id = cursor.lastrowid
                assert speaker_id is not None
                speaker_id_for[raw] = speaker_id
            sid = speaker_id_for[raw]
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
                sid,
                segment.text,
                segment.text,
                raw,
            ],
        )

    conn.commit()
    conn.close()
    return transcription_id, len(response.segments)
