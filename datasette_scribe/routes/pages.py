from pydantic import BaseModel

from datasette import Response

from ..page_data import (
    ActorInfo,
    CollectionDetailPageData,
    CollectionSpeakerStat,
    CollectionSummary,
    CollectionWithTranscriptions,
    NewTranscriptionPageData,
    ScribePageData,
    ShareInfo,
    TranscriptionDetailPageData,
    TranscriptionEdit,
    TranscriptionEntry,
    TranscriptionSpeaker,
    TranscriptionSummary,
)
from ..permissions import (
    SCRIBE_COLLECTION_RESOURCE_TYPE,
    _scope_resource,
    can_edit,
    can_manage,
    can_manage_collection,
    ensure_view,
    filter_visible_ids,
)
from ..router import router, check_permission, ensure_schema

try:
    from datasette_acl_share import share_capabilities as _share_capabilities
except ImportError:  # pragma: no cover - datasette-acl-share not installed
    _share_capabilities = None


async def render_page(
    datasette, request, *, page_title: str, entrypoint: str, page_data: BaseModel
) -> Response:
    return Response.html(
        await datasette.render_template(
            "scribe_base.html",
            {
                "page_title": page_title,
                "entrypoint": entrypoint,
                "page_data": page_data.model_dump(),
            },
            request=request,
        )
    )


TRANSCRIPTION_SELECT = (
    "select t.id, t.url, t.input_type, t.filename, t.model, t.granularity, t.submitted_at,"
    " t.completed_at, t.error, t.created_by, ct.collection_id as collection_id,"
    " (select count(*) from datasette_scribe_transcription_entries e where e.transcription_id = t.id) as entries_count,"
    " (select max(e.end) from datasette_scribe_transcription_entries e where e.transcription_id = t.id) as duration,"
    " (select count(distinct e.speaker_id) from datasette_scribe_transcription_entries e where e.transcription_id = t.id and e.speaker_id is not null) as speakers_count"
    " from datasette_scribe_transcriptions t"
    " left join datasette_scribe_collection_transcriptions ct on ct.transcription_id = t.id"
)


async def _visible_summaries(datasette, request, database, rows):
    """Build TranscriptionSummary list, dropping rows the actor cannot view.

    Private by default: only transcriptions the actor owns or has been shared
    (acl grants), plus orphan transcriptions when the actor has global access.
    """
    visible = await filter_visible_ids(datasette, request.actor, database, rows)
    return [TranscriptionSummary(**dict(r)) for r in rows if r["id"] in visible]


async def _build_share_info(datasette, request, database, tid):
    """Sharing context for the transcription detail page.

    Returns None when datasette-acl-share is not installed (no share dialog).
    Otherwise reports the acl resource identity, the enabled dialog sections
    (from acl-share's capability probe), and whether this actor may manage
    sharing — which gates the Share button.
    """
    if _share_capabilities is None:
        return None
    caps = _share_capabilities(datasette)
    features = ",".join(key for key, enabled in caps.items() if enabled)
    # Point the dialog at the transcript's scope: a collected transcript opens
    # its collection's ACL (sharing it shares the whole collection); a standalone
    # one opens its own. can_manage resolves the same scope.
    resource, _ = await _scope_resource(datasette, database, tid)
    manage = await can_manage(datasette, request.actor, database, tid)
    return ShareInfo(
        resource_type=resource.name,
        parent=database,
        child=resource.child,
        features=features,
        can_manage=manage,
        available=True,
    )


async def _build_collection_share_info(datasette, request, database, cid):
    """Sharing context for the collection detail page (parallel to
    :func:`_build_share_info`). Targets the scribe-collection resource."""
    if _share_capabilities is None:
        return None
    caps = _share_capabilities(datasette)
    features = ",".join(key for key, enabled in caps.items() if enabled)
    manage = await can_manage_collection(datasette, request.actor, database, cid)
    return ShareInfo(
        resource_type=SCRIBE_COLLECTION_RESOURCE_TYPE,
        parent=database,
        child=str(cid),
        features=features,
        can_manage=manage,
        available=True,
    )


@router.GET("/(?P<database>[^/]+)/-/scribe$")
@check_permission()
async def scribe_page(datasette, request, database: str):
    await ensure_schema(datasette, database)
    db = datasette.get_database(database)

    # Get all collections
    collection_rows = await db.execute(
        "select id, name, description, created_at from datasette_scribe_collections order by name"
    )
    collections = []
    for crow in collection_rows.rows:
        cid = crow["id"]
        t_rows = await db.execute(
            TRANSCRIPTION_SELECT + " where ct.collection_id = ? order by t.id desc",
            [cid],
        )
        transcriptions = await _visible_summaries(
            datasette, request, database, t_rows.rows
        )
        collections.append(
            CollectionWithTranscriptions(
                id=crow["id"],
                name=crow["name"],
                description=crow["description"],
                created_at=crow["created_at"],
                transcriptions=transcriptions,
            )
        )

    # Get uncollected transcriptions
    uncollected_rows = await db.execute(
        TRANSCRIPTION_SELECT + " where ct.collection_id is null order by t.id desc"
    )
    uncollected = await _visible_summaries(
        datasette, request, database, uncollected_rows.rows
    )

    return await render_page(
        datasette,
        request,
        page_title="Scribe",
        entrypoint="src/pages/scribe/index.ts",
        page_data=ScribePageData(
            database_name=database,
            collections=collections,
            uncollected_transcriptions=uncollected,
        ),
    )


@router.GET("/(?P<database>[^/]+)/-/scribe/transcription/(?P<transcription_id>[^/]+)$")
@check_permission()
async def transcription_detail_page(
    datasette, request, database: str, transcription_id: str
):
    await ensure_schema(datasette, database)
    db = datasette.get_database(database)
    tid = int(transcription_id)

    row = (
        await db.execute(
            "select t.id, t.url, t.input_type, t.filename, t.model, t.granularity, t.submitted_at,"
            " t.completed_at, t.error, t.created_by,"
            " (select count(*) from datasette_scribe_transcription_entries e where e.transcription_id = t.id) as entries_count"
            " from datasette_scribe_transcriptions t where t.id = ?",
            [tid],
        )
    ).first()
    if row is None:
        return Response.text("Transcription not found", status=404)

    created_by = row["created_by"]
    await ensure_view(datasette, request.actor, database, tid, created_by)

    transcription = TranscriptionSummary(**dict(row))

    if transcription.input_type == "file":
        audio_url = f"/{database}/-/api/scribe/transcription/{tid}/audio"
    else:
        audio_url = transcription.url

    entry_rows = await db.execute(
        "select id, start, end, speaker_id, text, original_speaker_id, original_text"
        " from datasette_scribe_transcription_entries where transcription_id = ?"
        " order by start",
        [tid],
    )
    entries = [TranscriptionEntry(**dict(r)) for r in entry_rows.rows]

    # Check if transcription belongs to a collection — its scope.
    collection_row = (
        await db.execute(
            "select c.id, c.name, c.description, c.created_at"
            " from datasette_scribe_collections c"
            " join datasette_scribe_collection_transcriptions ct on ct.collection_id = c.id"
            " where ct.transcription_id = ?",
            [tid],
        )
    ).first()
    collection = CollectionSummary(**dict(collection_row)) if collection_row else None

    # all_speakers: every speaker in this transcript's scope (the collection
    # roster, or the transcript's own speakers when standalone).
    if collection:
        scope_col, scope_ref = "collection_id", collection.id
    else:
        scope_col, scope_ref = "transcription_id", tid
    all_speaker_rows = await db.execute(
        "select s.id, s.name, s.description, s.is_configured,"
        " exists(select 1 from datasette_scribe_speaker_photos p where p.speaker_id = s.id) as has_photo"
        f" from datasette_scribe_speakers s where s.{scope_col} = ? order by s.name",
        [scope_ref],
    )
    all_speakers = [
        TranscriptionSpeaker(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            is_configured=bool(r["is_configured"]),
            has_photo=bool(r["has_photo"]),
        )
        for r in all_speaker_rows.rows
    ]

    # speakers: those actually used in this transcript, joined by id.
    used_rows = await db.execute(
        "select s.id, s.name, s.description, s.is_configured,"
        " exists(select 1 from datasette_scribe_speaker_photos p where p.speaker_id = s.id) as has_photo,"
        " count(e.id) as entry_count"
        " from datasette_scribe_speakers s"
        " join datasette_scribe_transcription_entries e"
        "   on e.speaker_id = s.id and e.transcription_id = ?"
        " group by s.id order by entry_count desc",
        [tid],
    )
    speakers = [
        TranscriptionSpeaker(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            is_configured=bool(r["is_configured"]),
            has_photo=bool(r["has_photo"]),
        )
        for r in used_rows.rows
    ]

    edit_rows = await db.execute(
        "select id, operation, detail, created_at, entry_id from datasette_scribe_transcription_edits"
        " where transcription_id = ? order by id desc",
        [tid],
    )
    edits = [TranscriptionEdit(**dict(r)) for r in edit_rows.rows]

    # All collections for the move-to-collection dropdown
    all_collection_rows = await db.execute(
        "select id, name, description, created_at from datasette_scribe_collections order by name"
    )
    all_collections = [CollectionSummary(**dict(r)) for r in all_collection_rows.rows]

    actor = (
        ActorInfo(id=request.actor["id"], name=request.actor.get("name"))
        if request.actor and request.actor.get("id")
        else None
    )
    editable = await can_edit(datasette, request.actor, database, tid, created_by)
    share = await _build_share_info(datasette, request, database, tid)

    return await render_page(
        datasette,
        request,
        page_title=f"Transcription #{tid}",
        entrypoint="src/pages/transcription_detail/index.ts",
        page_data=TranscriptionDetailPageData(
            database_name=database,
            transcription=transcription,
            audio_url=audio_url,
            entries=entries,
            speakers=speakers,
            all_speakers=all_speakers,
            edits=edits,
            collection=collection,
            all_collections=all_collections,
            actor=actor,
            can_edit=editable,
            share=share,
        ),
    )


@router.GET("/(?P<database>[^/]+)/-/scribe/new$")
@check_permission()
async def new_transcription_page(datasette, request, database: str):
    await ensure_schema(datasette, database)
    db = datasette.get_database(database)
    collection_rows = await db.execute(
        "select id, name, description, created_at from datasette_scribe_collections order by name"
    )
    collections = [CollectionSummary(**dict(r)) for r in collection_rows.rows]
    return await render_page(
        datasette,
        request,
        page_title="New transcription",
        entrypoint="src/pages/new_transcript/index.ts",
        page_data=NewTranscriptionPageData(
            database_name=database, collections=collections
        ),
    )


@router.GET("/(?P<database>[^/]+)/-/scribe/collections/(?P<collection_id>[^/]+)$")
@check_permission()
async def collection_detail_page(datasette, request, database: str, collection_id: str):
    await ensure_schema(datasette, database)
    db = datasette.get_database(database)
    cid = int(collection_id)

    row = (
        await db.execute(
            "select id, name, description, created_at from datasette_scribe_collections where id = ?",
            [cid],
        )
    ).first()
    if row is None:
        return Response.text("Collection not found", status=404)

    collection = CollectionSummary(**dict(row))

    # Transcriptions in this collection
    t_rows = await db.execute(
        TRANSCRIPTION_SELECT + " where ct.collection_id = ? order by t.id desc",
        [cid],
    )
    transcriptions = await _visible_summaries(datasette, request, database, t_rows.rows)

    # Available uncollected transcriptions
    avail_rows = await db.execute(
        TRANSCRIPTION_SELECT + " where ct.collection_id is null order by t.id desc"
    )
    available = await _visible_summaries(datasette, request, database, avail_rows.rows)

    # Speaker stats for this collection — keyed on speaker id.
    speaker_rows = await db.execute(
        "select s.id, s.name, s.description,"
        " exists(select 1 from datasette_scribe_speaker_photos p where p.speaker_id = s.id) as has_photo,"
        " count(e.id) as entry_count,"
        " count(distinct e.transcription_id) as transcription_count"
        " from datasette_scribe_speakers s"
        " left join datasette_scribe_transcription_entries e on e.speaker_id = s.id"
        " where s.collection_id = ? group by s.id order by entry_count desc",
        [cid],
    )
    speakers = [
        CollectionSpeakerStat(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            has_photo=bool(r["has_photo"]),
            entry_count=r["entry_count"],
            transcription_count=r["transcription_count"],
        )
        for r in speaker_rows.rows
    ]

    share = await _build_collection_share_info(datasette, request, database, cid)

    return await render_page(
        datasette,
        request,
        page_title=collection.name,
        entrypoint="src/pages/collection_detail/index.ts",
        page_data=CollectionDetailPageData(
            database_name=database,
            collection=collection,
            transcriptions=transcriptions,
            available_transcriptions=available,
            speakers=speakers,
            share=share,
        ),
    )
