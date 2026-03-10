from typing import Annotated

from datasette import Response
from datasette_plugin_router import Body

from ..page_data import (
    CollectionTranscriptionRequest,
    CreateCollectionRequest,
    EditResponse,
    UpdateCollectionRequest,
)
from ..router import router, check_permission, ensure_schema


@router.POST("/-/api/scribe/collections/create$", output=EditResponse)
@check_permission()
async def api_create_collection(
    datasette, request, body: Annotated[CreateCollectionRequest, Body()]
):
    await ensure_schema(datasette, body.database)
    db = datasette.get_database(body.database)

    try:
        await db.execute_write(
            "insert into datasette_scribe_collections (name, description) values (?, ?)",
            [body.name.strip(), body.description],
        )
    except Exception:
        return Response.json(
            EditResponse(ok=False, error="A collection with that name already exists").model_dump(),
            status=400,
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

    row = (await db.execute("select id from datasette_scribe_collections where id = ?", [cid])).first()
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
            EditResponse(ok=False, error="A collection with that name already exists").model_dump(),
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

    row = (await db.execute("select id from datasette_scribe_collections where id = ?", [cid])).first()
    if row is None:
        return Response.json(
            EditResponse(ok=False, error="Collection not found").model_dump(),
            status=404,
        )

    await db.execute_write("delete from datasette_scribe_collections where id = ?", [cid])
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

    row = (await db.execute("select id from datasette_scribe_collections where id = ?", [cid])).first()
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
