import json
from typing import Annotated

from datasette import Response
from datasette_plugin_router import Body

from ..page_data import (
    CombineSpeakersRequest,
    CreateSpeakerRequest,
    DeleteSpeakerRequest,
    EditResponse,
    RenameSpeakerRequest,
)
from ..permissions import ensure_edit
from ..router import router, check_permission, ensure_schema
from ._scope import scope_columns, scope_of_transcript


async def _ensure_transcription_edit(datasette, request, database, tid):
    """Require edit access on the transcription a speaker op targets."""
    db = datasette.get_database(database)
    owner_row = (
        await db.execute(
            "select created_by from datasette_scribe_transcriptions where id = ?",
            [tid],
        )
    ).first()
    await ensure_edit(
        datasette,
        request.actor,
        database,
        tid,
        owner_row["created_by"] if owner_row else None,
    )


@router.POST(
    "/-/api/scribe/transcription/(?P<transcription_id>\\d+)/speakers/create$",
    output=EditResponse,
)
@check_permission()
async def api_create_speaker(
    datasette,
    request,
    transcription_id: str,
    body: Annotated[CreateSpeakerRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    tid = int(transcription_id)
    await _ensure_transcription_edit(datasette, request, body.database, tid)

    # Speakers are scoped to the transcript's scope (its collection, or the
    # transcript itself when standalone). User-created speakers are configured.
    scope = await scope_of_transcript(db, tid)
    col, ref = scope_columns(scope)
    try:
        await db.execute_write(
            f"insert into datasette_scribe_speakers ({col}, name, is_configured, configured_at)"
            f" values (?, ?, 1, datetime('now', 'subsec'))",
            [ref, body.name],
        )
    except Exception:
        return Response.json(
            EditResponse(
                ok=False, error="A speaker with that name already exists in this scope"
            ).model_dump(),
            status=400,
        )

    await db.execute_write(
        "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
        " values (?, null, ?, ?, datetime('now', 'subsec'))",
        [tid, "create_speaker", json.dumps({"name": body.name})],
    )

    return Response.json(EditResponse(ok=True).model_dump())


@router.POST(
    "/-/api/scribe/transcription/(?P<transcription_id>\\d+)/speakers/combine$",
    output=EditResponse,
)
@check_permission()
async def api_combine_speakers(
    datasette,
    request,
    transcription_id: str,
    body: Annotated[CombineSpeakersRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    tid = int(transcription_id)
    await _ensure_transcription_edit(datasette, request, body.database, tid)

    # Both speakers must belong to the transcript's scope. Combine then spans
    # the whole scope (every transcript in the collection that uses from), which
    # is correct — it is one shared speaker.
    scope = await scope_of_transcript(db, tid)
    col, ref = scope_columns(scope)
    valid = (
        await db.execute(
            f"select count(*) c from datasette_scribe_speakers"
            f" where id in (?, ?) and {col} = ?",
            [body.from_speaker_id, body.to_speaker_id, ref],
        )
    ).first()
    if valid["c"] != 2:
        return Response.json(
            EditResponse(
                ok=False, error="Both speakers must belong to this scope"
            ).model_dump(),
            status=400,
        )

    affected = (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries"
            " where speaker_id = ?",
            [body.from_speaker_id],
        )
    ).first()["c"]
    await db.execute_write(
        "update datasette_scribe_transcription_entries set speaker_id = ?"
        " where speaker_id = ?",
        [body.to_speaker_id, body.from_speaker_id],
    )
    # Explicit photo cascade (FK enforcement is off on shared user databases).
    await db.execute_write(
        "delete from datasette_scribe_speaker_photos where speaker_id = ?",
        [body.from_speaker_id],
    )
    await db.execute_write(
        "delete from datasette_scribe_speakers where id = ?",
        [body.from_speaker_id],
    )

    await db.execute_write(
        "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
        " values (?, null, ?, ?, datetime('now', 'subsec'))",
        [
            tid,
            "combine_speakers",
            json.dumps(
                {
                    "from": body.from_speaker_id,
                    "to": body.to_speaker_id,
                    "affected_entries": affected,
                }
            ),
        ],
    )

    return Response.json(EditResponse(ok=True).model_dump())


@router.POST(
    "/-/api/scribe/transcription/(?P<transcription_id>\\d+)/speakers/delete$",
    output=EditResponse,
)
@check_permission()
async def api_delete_speaker(
    datasette,
    request,
    transcription_id: str,
    body: Annotated[DeleteSpeakerRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    tid = int(transcription_id)
    await _ensure_transcription_edit(datasette, request, body.database, tid)

    # Deletion is scope-level: null every entry in scope that points at this
    # speaker, then delete it (its photo cascades via the FK). No "used in other
    # transcriptions" guard — the speaker is shared across its whole scope.
    affected = (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries where speaker_id = ?",
            [body.speaker_id],
        )
    ).first()["c"]
    await db.execute_write(
        "update datasette_scribe_transcription_entries set speaker_id = null where speaker_id = ?",
        [body.speaker_id],
    )
    # FK enforcement is off on shared user databases, so the photo cascade is
    # done explicitly (the on-delete-cascade clause documents intent).
    await db.execute_write(
        "delete from datasette_scribe_speaker_photos where speaker_id = ?",
        [body.speaker_id],
    )
    await db.execute_write(
        "delete from datasette_scribe_speakers where id = ?",
        [body.speaker_id],
    )

    await db.execute_write(
        "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
        " values (?, null, ?, ?, datetime('now', 'subsec'))",
        [
            tid,
            "delete_speaker",
            json.dumps(
                {
                    "speaker_id": body.speaker_id,
                    "affected_entries": affected,
                }
            ),
        ],
    )

    return Response.json(EditResponse(ok=True).model_dump())


@router.POST(
    "/-/api/scribe/speakers/(?P<speaker_id>\\d+)/rename$",
    output=EditResponse,
)
@check_permission()
async def api_rename_speaker(
    datasette,
    request,
    speaker_id: str,
    body: Annotated[RenameSpeakerRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    sid = int(speaker_id)

    # Get current speaker name
    row = (
        await db.execute(
            "select name from datasette_scribe_speakers where id = ?", [sid]
        )
    ).first()
    if row is None:
        return Response.json(
            EditResponse(ok=False, error="Speaker not found").model_dump(), status=404
        )

    old_name = row["name"]
    new_name = body.new_name.strip()
    if not new_name:
        return Response.json(
            EditResponse(ok=False, error="Name cannot be empty").model_dump(),
            status=400,
        )

    if old_name == new_name:
        return Response.json(EditResponse(ok=True).model_dump())

    # Check if new name already exists
    existing = (
        await db.execute(
            "select id from datasette_scribe_speakers where name = ?", [new_name]
        )
    ).first()
    if existing:
        return Response.json(
            EditResponse(
                ok=False, error="A speaker with that name already exists"
            ).model_dump(),
            status=400,
        )

    # Update the speaker name
    await db.execute_write(
        "update datasette_scribe_speakers set name = ? where id = ?", [new_name, sid]
    )

    # Update all entries referencing old name (global, does NOT update original_speaker_id)
    await db.execute_write(
        "update datasette_scribe_transcription_entries set speaker_id = ? where speaker_id = ?",
        [new_name, old_name],
    )

    # Log the rename edit
    await db.execute_write(
        "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
        " values (null, null, ?, ?, datetime('now', 'subsec'))",
        [
            "rename_speaker",
            json.dumps({"old_name": old_name, "new_name": new_name}),
        ],
    )

    return Response.json(EditResponse(ok=True).model_dump())
