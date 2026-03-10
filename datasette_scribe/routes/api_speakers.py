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
from ..router import router, check_permission, ensure_schema


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

    try:
        await db.execute_write(
            "insert into datasette_scribe_speakers (name, is_original) values (?, 0)",
            [body.name],
        )
    except Exception:
        return Response.json(
            EditResponse(ok=False, error="Speaker already exists").model_dump(),
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

    count_row = (
        await db.execute(
            "select count(*) as cnt from datasette_scribe_transcription_entries"
            " where transcription_id = ? and speaker_id = ?",
            [tid, body.from_speaker],
        )
    ).first()
    affected = count_row["cnt"] if count_row else 0

    await db.execute_write(
        "update datasette_scribe_transcription_entries set speaker_id = ?"
        " where transcription_id = ? and speaker_id = ?",
        [body.to_speaker, tid, body.from_speaker],
    )

    # Clean up from global speakers table if no entries remain globally
    global_count_row = (
        await db.execute(
            "select count(*) as cnt from datasette_scribe_transcription_entries where speaker_id = ?",
            [body.from_speaker],
        )
    ).first()
    if global_count_row and global_count_row["cnt"] == 0:
        await db.execute_write(
            "delete from datasette_scribe_speakers where name = ?",
            [body.from_speaker],
        )

    await db.execute_write(
        "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
        " values (?, null, ?, ?, datetime('now', 'subsec'))",
        [
            tid,
            "combine_speakers",
            json.dumps(
                {
                    "from": body.from_speaker,
                    "to": body.to_speaker,
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

    # Check if speaker is used in other transcriptions
    used_row = (
        await db.execute(
            "select exists("
            " select 1 from datasette_scribe_transcription_entries"
            " where speaker_id = ? and transcription_id != ?"
            ") as used_elsewhere",
            [body.speaker_name, tid],
        )
    ).first()
    if used_row and used_row["used_elsewhere"]:
        return Response.json(
            EditResponse(
                ok=False,
                error="Speaker is used in other transcriptions. Use unassign instead.",
            ).model_dump(),
            status=400,
        )

    count_row = (
        await db.execute(
            "select count(*) as cnt from datasette_scribe_transcription_entries"
            " where transcription_id = ? and speaker_id = ?",
            [tid, body.speaker_name],
        )
    ).first()
    affected = count_row["cnt"] if count_row else 0

    await db.execute_write(
        "update datasette_scribe_transcription_entries set speaker_id = null"
        " where transcription_id = ? and speaker_id = ?",
        [tid, body.speaker_name],
    )
    await db.execute_write(
        "delete from datasette_scribe_speakers where name = ?",
        [body.speaker_name],
    )

    await db.execute_write(
        "insert into datasette_scribe_transcription_edits (transcription_id, entry_id, operation, detail, created_at)"
        " values (?, null, ?, ?, datetime('now', 'subsec'))",
        [
            tid,
            "delete_speaker",
            json.dumps(
                {
                    "name": body.speaker_name,
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
    row = (await db.execute("select name from datasette_scribe_speakers where id = ?", [sid])).first()
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
        await db.execute("select id from datasette_scribe_speakers where name = ?", [new_name])
    ).first()
    if existing:
        return Response.json(
            EditResponse(
                ok=False, error="A speaker with that name already exists"
            ).model_dump(),
            status=400,
        )

    # Update the speaker name
    await db.execute_write("update datasette_scribe_speakers set name = ? where id = ?", [new_name, sid])

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
