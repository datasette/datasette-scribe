from typing import Annotated

from datasette import Forbidden, Response
from datasette_plugin_router import Body

from ..page_data import (
    CollectionTranscriptionRequest,
    CreateCollectionRequest,
    EditResponse,
    MoveResponse,
    MoveTranscriptionRequest,
    UpdateCollectionRequest,
)
from ..permissions import (
    can_manage_collection,
    ensure_edit,
    seed_collection_owner_grant,
    seed_owner_grant,
)
from ..router import router, check_permission, ensure_schema
from ._scope import unlink_and_rescope


def _actor_id(request):
    return request.actor.get("id") if request.actor else None


async def _ensure_transcript_edit(datasette, request, database, tid):
    db = datasette.get_database(database)
    owner = (
        await db.execute(
            "select created_by from datasette_scribe_transcriptions where id = ?", [tid]
        )
    ).first()
    await ensure_edit(
        datasette, request.actor, database, tid, owner["created_by"] if owner else None
    )


@router.POST("/-/api/scribe/collections/create$", output=EditResponse)
@check_permission()
async def api_create_collection(
    datasette, request, body: Annotated[CreateCollectionRequest, Body()]
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)

    created_by = _actor_id(request)
    try:
        result = await db.execute_write(
            "insert into datasette_scribe_collections (name, description, created_by) values (?, ?, ?)",
            [body.name.strip(), body.description, created_by],
        )
    except Exception:
        return Response.json(
            EditResponse(
                ok=False, error="A collection with that name already exists"
            ).model_dump(),
            status=400,
        )

    # Private by default: seed the creator as Manager (owner) of the collection,
    # so its members are governed by the creator's grant. No-op for anonymous
    # creates / when acl is absent.
    await seed_collection_owner_grant(
        datasette, body.database, result.lastrowid, created_by
    )

    return Response.json(EditResponse(ok=True).model_dump())


@router.POST(
    "/-/api/scribe/collections/(?P<collection_id>\\d+)/update$", output=EditResponse
)
@check_permission()
async def api_update_collection(
    datasette,
    request,
    collection_id: str,
    body: Annotated[UpdateCollectionRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    cid = int(collection_id)

    row = (
        await db.execute(
            "select id from datasette_scribe_collections where id = ?", [cid]
        )
    ).first()
    if row is None:
        return Response.json(
            EditResponse(ok=False, error="Collection not found").model_dump(),
            status=404,
        )

    try:
        await db.execute_write(
            "update datasette_scribe_collections set name = ?, description = ? where id = ?",
            [body.name.strip(), body.description, cid],
        )
    except Exception:
        return Response.json(
            EditResponse(
                ok=False, error="A collection with that name already exists"
            ).model_dump(),
            status=400,
        )

    return Response.json(EditResponse(ok=True).model_dump())


@router.POST(
    "/-/api/scribe/collections/(?P<collection_id>\\d+)/delete$", output=EditResponse
)
@check_permission()
async def api_delete_collection(
    datasette,
    request,
    collection_id: str,
    body: Annotated[CreateCollectionRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    cid = int(collection_id)

    row = (
        await db.execute(
            "select id from datasette_scribe_collections where id = ?", [cid]
        )
    ).first()
    if row is None:
        return Response.json(
            EditResponse(ok=False, error="Collection not found").model_dump(),
            status=404,
        )

    await db.execute_write(
        "delete from datasette_scribe_collections where id = ?", [cid]
    )
    return Response.json(EditResponse(ok=True).model_dump())


@router.POST(
    "/-/api/scribe/collections/(?P<collection_id>\\d+)/add-transcription$",
    output=EditResponse,
)
@check_permission()
async def api_add_transcription_to_collection(
    datasette,
    request,
    collection_id: str,
    body: Annotated[CollectionTranscriptionRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    cid = int(collection_id)

    row = (
        await db.execute(
            "select id from datasette_scribe_collections where id = ?", [cid]
        )
    ).first()
    if row is None:
        return Response.json(
            EditResponse(ok=False, error="Collection not found").model_dump(),
            status=404,
        )

    # The mover must control the transcript AND manage the destination
    # collection (adding can expand who sees the transcript).
    tid = body.transcription_id
    await _ensure_transcript_edit(datasette, request, body.database, tid)
    if not await can_manage_collection(datasette, request.actor, body.database, cid):
        raise Forbidden("collection-manage")

    affected = await unlink_and_rescope(
        datasette, body.database, tid, new_collection_id=cid
    )
    return Response.json(EditResponse(ok=True, unlinked_entries=affected).model_dump())


@router.POST(
    "/-/api/scribe/collections/(?P<collection_id>\\d+)/remove-transcription$",
    output=EditResponse,
)
@check_permission()
async def api_remove_transcription_from_collection(
    datasette,
    request,
    collection_id: str,
    body: Annotated[CollectionTranscriptionRequest, Body()],
):
    await ensure_schema(datasette, body.database)
    cid = int(collection_id)
    tid = body.transcription_id

    # Removing requires control of the transcript and management of the
    # collection it is leaving.
    await _ensure_transcript_edit(datasette, request, body.database, tid)
    if not await can_manage_collection(datasette, request.actor, body.database, cid):
        raise Forbidden("collection-manage")

    affected = await unlink_and_rescope(
        datasette, body.database, tid, new_collection_id=None
    )
    # Now standalone: seed an owner grant so the transcript is not left
    # ownerless (the collection's grants no longer apply once membership is gone).
    await seed_owner_grant(datasette, body.database, tid, _actor_id(request))
    return Response.json(EditResponse(ok=True, unlinked_entries=affected).model_dump())


@router.POST(
    "/-/api/scribe/transcription/(?P<transcription_id>\\d+)/move$",
    output=MoveResponse,
)
@check_permission()
async def api_move_transcription(
    datasette,
    request,
    transcription_id: str,
    body: Annotated[MoveTranscriptionRequest, Body()],
):
    """Move a transcript to a collection (or to standalone, collection_id=None).

    One call for the transcription detail dropdown: wraps unlink_and_rescope with
    the same permission checks as add/remove and returns unlinked_entries for the
    confirm summary plus the resulting collection_id.
    """
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)
    tid = int(transcription_id)

    await _ensure_transcript_edit(datasette, request, body.database, tid)

    # Manage the source scope (the collection it is currently in, if any) ...
    src = (
        await db.execute(
            "select collection_id from datasette_scribe_collection_transcriptions"
            " where transcription_id = ?",
            [tid],
        )
    ).first()
    if src is not None and not await can_manage_collection(
        datasette, request.actor, body.database, src["collection_id"]
    ):
        raise Forbidden("collection-manage")
    # ... and the destination collection, if any.
    if body.collection_id is not None:
        dest = (
            await db.execute(
                "select id from datasette_scribe_collections where id = ?",
                [body.collection_id],
            )
        ).first()
        if dest is None:
            return Response.json(
                MoveResponse(ok=False, error="Collection not found").model_dump(),
                status=404,
            )
        if not await can_manage_collection(
            datasette, request.actor, body.database, body.collection_id
        ):
            raise Forbidden("collection-manage")

    affected = await unlink_and_rescope(
        datasette, body.database, tid, new_collection_id=body.collection_id
    )
    if body.collection_id is None:
        await seed_owner_grant(datasette, body.database, tid, _actor_id(request))
    return Response.json(
        MoveResponse(
            ok=True, unlinked_entries=affected, collection_id=body.collection_id
        ).model_dump()
    )
