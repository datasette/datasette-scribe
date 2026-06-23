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
from ..permissions import ensure_edit, ensure_view, seed_owner_grant
from ..router import router, check_permission, ensure_schema
from ..voxtral_api import transcribe
from ._scope import (
    scope_columns,
    scope_of_transcript,
    store_segments,
    copy_and_rescope,
)


def _actor_id(request):
    return request.actor.get("id") if request.actor else None


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

    created_by = _actor_id(request)
    result = await db.execute_write(
        """
        insert into datasette_scribe_transcriptions (url, input_type, filename, model, granularity, submitted_at, created_by)
        values (?, ?, ?, ?, ?, datetime('now', 'subsec'), ?)
        """,
        [body.url, input_type, filename, model, granularity, created_by],
    )
    transcription_id = result.lastrowid

    # Private by default: seed the creator as Manager (owner) of this
    # transcription. No-op for anonymous creates / when acl is absent. Done
    # before transcription runs so ownership holds even if transcription errors.
    await seed_owner_grant(datasette, body.database, transcription_id, created_by)

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

    await store_segments(db, transcription_id, response.segments)

    if body.collection_id is not None:
        # Assigning a fresh transcript to a collection is a move: its just-
        # extracted transcript-scoped speakers are copied into the collection
        # scope (name-suffixed on clash) and the entries keep their assignments.
        await copy_and_rescope(
            datasette,
            body.database,
            transcription_id,
            new_collection_id=body.collection_id,
        )

    return Response.json(
        NewTranscriptionResponse(
            ok=True, id=transcription_id, entries_count=len(response.segments)
        ).model_dump()
    )


@router.GET(
    "/(?P<database>[^/]+)/-/api/scribe/transcription/(?P<transcription_id>\\d+)/audio$"
)
@check_permission()
async def api_transcription_audio(
    datasette, request, database: str, transcription_id: str
):
    await ensure_schema(datasette, database)
    db = datasette.get_database(database)
    tid = int(transcription_id)

    owner_row = (
        await db.execute(
            "select created_by from datasette_scribe_transcriptions where id = ?",
            [tid],
        )
    ).first()
    if owner_row is None:
        return Response.text("Transcription not found", status=404)
    await ensure_view(datasette, request.actor, database, tid, owner_row["created_by"])

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

    owner_row = (
        await db.execute(
            "select created_by from datasette_scribe_transcriptions where id = ?",
            [tid],
        )
    ).first()
    await ensure_edit(
        datasette,
        request.actor,
        body.database,
        tid,
        owner_row["created_by"] if owner_row else None,
    )

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
        # The target speaker must belong to this entry's transcript scope.
        scope = await scope_of_transcript(db, tid)
        col, ref = scope_columns(scope)
        ok = (
            await db.execute(
                f"select 1 from datasette_scribe_speakers where id = ? and {col} = ?",
                [body.speaker_id, ref],
            )
        ).first()
        if not ok:
            return Response.json(
                EditResponse(
                    ok=False, error="Speaker not in this transcript's scope"
                ).model_dump(),
                status=400,
            )
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
