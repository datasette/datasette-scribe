import base64
import json
from typing import Annotated

from datasette import Response
from datasette_plugin_router import Body

from ..page_data import (
    EditEntryRequest,
    EditResponse,
    NewTranscriptionRequest,
    NewTranscriptionResponse,
)
from ..router import router, check_permission, ensure_schema
from ..voxtral_api import transcribe


@router.POST("/-/api/scribe/new$", output=NewTranscriptionResponse)
@check_permission()
async def api_new_transcription(
    datasette, request, body: Annotated[NewTranscriptionRequest, Body()]
):
    if not body.url and not body.file_data:
        return Response.json(
            NewTranscriptionResponse(
                ok=False, error="Either url or file_data is required"
            ).model_dump(),
            status=400,
        )
    if body.url and body.file_data:
        return Response.json(
            NewTranscriptionResponse(
                ok=False, error="Provide either url or file_data, not both"
            ).model_dump(),
            status=400,
        )

    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)

    model = "voxtral-mini-2602"
    granularity = "segment"

    if body.file_data:
        input_type = "file"
        file_bytes = base64.b64decode(body.file_data)
        filename = body.filename or "audio.mp3"
        content_type = body.content_type or "audio/mpeg"
    else:
        input_type = "url"
        file_bytes = None
        filename = None
        content_type = None

    result = await db.execute_write(
        """
        insert into datasette_scribe_transcriptions (url, input_type, filename, model, granularity, submitted_at)
        values (?, ?, ?, ?, ?, datetime('now', 'subsec'))
        """,
        [body.url, input_type, filename, model, granularity],
    )
    transcription_id = result.lastrowid

    if file_bytes is not None:
        await db.execute_write(
            "insert into datasette_scribe_audio_blobs (transcription_id, data, content_type) values (?, ?, ?)",
            [transcription_id, file_bytes, content_type],
        )

    try:
        if file_bytes is not None:
            response = await transcribe(file_data=file_bytes, filename=filename)
        else:
            response = await transcribe(body.url)
    except Exception as e:
        error_msg = str(e)
        await db.execute_write(
            "update datasette_scribe_transcriptions set error = ? where id = ?",
            [error_msg, transcription_id],
        )
        return Response.json(
            NewTranscriptionResponse(
                ok=False, id=transcription_id, error=error_msg
            ).model_dump(),
            status=502,
        )

    usage_json = response.usage.model_dump_json() if response.usage else None

    await db.execute_write(
        """
        update datasette_scribe_transcriptions set completed_at = datetime('now', 'subsec'), usage = ?
        where id = ?
        """,
        [usage_json, transcription_id],
    )

    seen_speakers: set[str] = set()
    for segment in response.segments:
        # Prefix speaker IDs to keep them unique per transcription — the model
        # reuses generic names like "Speaker 1" across different audio files.
        # original_speaker_id preserves the raw value from the model.
        scoped_speaker = (
            f"t{transcription_id}_{segment.speaker_id}"
            if segment.speaker_id
            else None
        )
        await db.execute_write(
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
            await db.execute_write(
                "insert or ignore into datasette_scribe_speakers (name, is_original) values (?, 1)",
                [scoped_speaker],
            )

    if body.collection_id is not None:
        await db.execute_write(
            "insert into datasette_scribe_collection_transcriptions (collection_id, transcription_id) values (?, ?)",
            [body.collection_id, transcription_id],
        )

    return Response.json(
        NewTranscriptionResponse(
            ok=True, id=transcription_id, entries_count=len(response.segments)
        ).model_dump()
    )


@router.GET("/(?P<database>[^/]+)/-/api/scribe/transcription/(?P<transcription_id>\\d+)/audio$")
@check_permission()
async def api_transcription_audio(datasette, request, database: str, transcription_id: str):
    db = datasette.get_database(database)
    tid = int(transcription_id)
    row = (
        await db.execute(
            "select ab.data, ab.content_type from datasette_scribe_audio_blobs ab where ab.transcription_id = ?",
            [tid],
        )
    ).first()
    if row is not None:
        return Response(
            body=row["data"],
            content_type=row["content_type"],
            headers={"Cache-Control": "max-age=3600"},
        )
    return Response.text("Audio not found", status=404)


@router.POST("/-/api/scribe/entry/(?P<entry_id>\\d+)/edit$", output=EditResponse)
@check_permission()
async def api_edit_entry(
    datasette, request, entry_id: str, body: Annotated[EditEntryRequest, Body()]
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    eid = int(entry_id)

    row = (
        await db.execute(
            "select id, transcription_id, text, speaker_id from datasette_scribe_transcription_entries where id = ?",
            [eid],
        )
    ).first()
    if row is None:
        return Response.json(
            EditResponse(ok=False, error="Entry not found").model_dump(), status=404
        )

    tid = row["transcription_id"]

    if body.text is not None and body.text != row["text"]:
        await db.execute_write(
            "update datasette_scribe_transcription_entries set text = ? where id = ?",
            [body.text, eid],
        )
        await db.execute_write(
            "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
            " values (?, ?, ?, ?, datetime('now', 'subsec'))",
            [
                tid,
                eid,
                "edit_text",
                json.dumps({"old": row["text"], "new": body.text}),
            ],
        )

    if body.speaker_id is not None and body.speaker_id != row["speaker_id"]:
        await db.execute_write(
            "update datasette_scribe_transcription_entries set speaker_id = ? where id = ?",
            [body.speaker_id, eid],
        )
        await db.execute_write(
            "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
            " values (?, ?, ?, ?, datetime('now', 'subsec'))",
            [
                tid,
                eid,
                "reassign_speaker",
                json.dumps({"old": row["speaker_id"], "new": body.speaker_id}),
            ],
        )

    return Response.json(EditResponse(ok=True).model_dump())
