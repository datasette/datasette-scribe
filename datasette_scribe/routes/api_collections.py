from typing import Annotated

from datasette import Response
from datasette_plugin_router import Body

from ..page_data import (
    CollectionTranscriptionRequest,
    CreateCollectionRequest,
    EditResponse,
    UpdateCollectionRequest,
)
from ..permissions import seed_collection_owner_grant
from ..router import router, check_permission, ensure_schema


def _actor_id(request):
    return request.actor.get("id") if request.actor else None


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

    try:
        await db.execute_write(
            "insert into datasette_scribe_collection_transcriptions (collection_id, transcription_id) values (?, ?)",
            [cid, body.transcription_id],
        )
    except Exception:
        return Response.json(
            EditResponse(
                ok=False, error="Transcription is already in a collection"
            ).model_dump(),
            status=400,
        )

    return Response.json(EditResponse(ok=True).model_dump())


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
    db = datasette.get_database(body.database)
    cid = int(collection_id)

    await db.execute_write(
        "delete from datasette_scribe_collection_transcriptions where collection_id = ? and transcription_id = ?",
        [cid, body.transcription_id],
    )

    return Response.json(EditResponse(ok=True).model_dump())
