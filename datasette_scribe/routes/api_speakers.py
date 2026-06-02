import base64
import json
from typing import Annotated

from datasette import Forbidden, Response
from datasette_plugin_router import Body

from ..page_data import (
    CombineSpeakersRequest,
    CreateSpeakerRequest,
    DeleteSpeakerRequest,
    EditResponse,
    RenameSpeakerRequest,
    SpeakerPhotoRequest,
    UpdateSpeakerRequest,
)
from ..permissions import ensure_edit, ensure_view
from ..router import router, check_permission, ensure_schema
from ._scope import scope_columns, scope_of_transcript

_MAX_PHOTO_BYTES = 1_048_576  # 1 MiB


def _sniff_image(raw: bytes) -> str | None:
    """Return the content type for PNG/JPEG magic bytes, else None."""
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return None


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


async def _speaker_scope_gate(datasette, request, database, sid, *, ensure):
    """Gate a speaker op behind ``ensure`` (ensure_edit / ensure_view) on its scope.

    A speaker is editable/viewable iff the actor may edit/view its scope.
    Resolve the speaker's scope to a representative transcript and defer to the
    transcription-level check — T04 routes that through the scope resource, so a
    collection-scoped speaker is gated by the collection's ACL. An empty
    collection has no representative transcript to gate on, so it is forbidden.
    """
    db = datasette.get_database(database)
    row = (
        await db.execute(
            "select collection_id, transcription_id from datasette_scribe_speakers where id = ?",
            [sid],
        )
    ).first()
    if row is None:
        raise Forbidden("speaker")
    if row["transcription_id"] is not None:
        tid = row["transcription_id"]
    else:
        m = (
            await db.execute(
                "select transcription_id from datasette_scribe_collection_transcriptions"
                " where collection_id = ? limit 1",
                [row["collection_id"]],
            )
        ).first()
        if m is None:
            raise Forbidden("speaker")
        tid = m["transcription_id"]
    owner = (
        await db.execute(
            "select created_by from datasette_scribe_transcriptions where id = ?", [tid]
        )
    ).first()
    await ensure(
        datasette, request.actor, database, tid, owner["created_by"] if owner else None
    )


async def _ensure_speaker_edit(datasette, request, database, sid):
    await _speaker_scope_gate(datasette, request, database, sid, ensure=ensure_edit)


async def _ensure_speaker_view(datasette, request, database, sid):
    await _speaker_scope_gate(datasette, request, database, sid, ensure=ensure_view)


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
        result = await db.execute_write(
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

    return Response.json(EditResponse(ok=True, id=result.lastrowid).model_dump())


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

    row = (
        await db.execute(
            "select collection_id, transcription_id, name from datasette_scribe_speakers"
            " where id = ?",
            [sid],
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

    # Uniqueness is per-scope: only clash with speakers in this speaker's scope.
    col = "collection_id" if row["collection_id"] is not None else "transcription_id"
    ref = (
        row["collection_id"]
        if row["collection_id"] is not None
        else row["transcription_id"]
    )
    clash = (
        await db.execute(
            f"select 1 from datasette_scribe_speakers where {col} = ? and name = ? and id != ?",
            [ref, new_name, sid],
        )
    ).first()
    if clash:
        return Response.json(
            EditResponse(
                ok=False, error="A speaker with that name already exists in this scope"
            ).model_dump(),
            status=400,
        )

    # With id-keyed entries, rename is just an update on the speaker row — entries
    # already reference it by id and need no rewrite. original_speaker_id is the
    # transcript-local raw label and is never touched.
    await db.execute_write(
        "update datasette_scribe_speakers set name = ?, is_configured = 1,"
        " configured_at = coalesce(configured_at, datetime('now', 'subsec')) where id = ?",
        [new_name, sid],
    )

    await db.execute_write(
        "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
        " values (null, null, ?, ?, datetime('now', 'subsec'))",
        [
            "rename_speaker",
            json.dumps({"old_name": old_name, "new_name": new_name}),
        ],
    )

    return Response.json(EditResponse(ok=True).model_dump())


@router.POST(
    "/-/api/scribe/speakers/(?P<speaker_id>\\d+)/update$",
    output=EditResponse,
)
@check_permission()
async def api_update_speaker(
    datasette,
    request,
    speaker_id: str,
    body: Annotated[UpdateSpeakerRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    sid = int(speaker_id)
    await _ensure_speaker_edit(datasette, request, body.database, sid)

    row = (
        await db.execute(
            "select collection_id, transcription_id, name from datasette_scribe_speakers"
            " where id = ?",
            [sid],
        )
    ).first()
    if row is None:
        return Response.json(
            EditResponse(ok=False, error="Speaker not found").model_dump(), status=404
        )

    sets = [
        "is_configured = 1",
        "configured_at = coalesce(configured_at, datetime('now', 'subsec'))",
    ]
    params: list = []
    if body.name is not None:
        name = body.name.strip()
        if not name:
            return Response.json(
                EditResponse(ok=False, error="Name cannot be empty").model_dump(),
                status=400,
            )
        col = (
            "collection_id" if row["collection_id"] is not None else "transcription_id"
        )
        ref = (
            row["collection_id"]
            if row["collection_id"] is not None
            else row["transcription_id"]
        )
        clash = (
            await db.execute(
                f"select 1 from datasette_scribe_speakers where {col} = ? and name = ? and id != ?",
                [ref, name, sid],
            )
        ).first()
        if clash:
            return Response.json(
                EditResponse(
                    ok=False,
                    error="A speaker with that name already exists in this scope",
                ).model_dump(),
                status=400,
            )
        sets.append("name = ?")
        params.append(name)
    if body.description is not None:
        sets.append("description = ?")
        params.append(body.description)

    params.append(sid)
    await db.execute_write(
        f"update datasette_scribe_speakers set {', '.join(sets)} where id = ?", params
    )
    return Response.json(EditResponse(ok=True).model_dump())


@router.POST(
    "/-/api/scribe/speakers/(?P<speaker_id>\\d+)/photo$",
    output=EditResponse,
)
@check_permission()
async def api_set_speaker_photo(
    datasette,
    request,
    speaker_id: str,
    body: Annotated[SpeakerPhotoRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    sid = int(speaker_id)
    await _ensure_speaker_edit(datasette, request, body.database, sid)
    try:
        raw = base64.b64decode(body.file_data, validate=True)
    except Exception:
        return Response.json(
            EditResponse(ok=False, error="Invalid base64").model_dump(), status=400
        )
    if len(raw) > _MAX_PHOTO_BYTES:
        return Response.json(
            EditResponse(ok=False, error="Photo exceeds 1 MB limit").model_dump(),
            status=400,
        )
    content_type = _sniff_image(raw)
    if content_type is None:
        return Response.json(
            EditResponse(ok=False, error="Photo must be PNG or JPEG").model_dump(),
            status=400,
        )
    await db.execute_write(
        "insert into datasette_scribe_speaker_photos (speaker_id, data, content_type)"
        " values (?, ?, ?) on conflict(speaker_id) do update set"
        " data = excluded.data, content_type = excluded.content_type",
        [sid, raw, content_type],
    )
    return Response.json(EditResponse(ok=True).model_dump())


@router.GET("/(?P<database>[^/]+)/-/api/scribe/speakers/(?P<speaker_id>\\d+)/photo$")
@check_permission()
async def api_get_speaker_photo(datasette, request, database: str, speaker_id: str):
    await ensure_schema(datasette, database)
    db = datasette.get_database(database)
    sid = int(speaker_id)
    await _ensure_speaker_view(datasette, request, database, sid)
    row = (
        await db.execute(
            "select data, content_type from datasette_scribe_speaker_photos where speaker_id = ?",
            [sid],
        )
    ).first()
    if row is None:
        return Response.text("No photo", status=404)
    return Response(body=row["data"], content_type=row["content_type"])
