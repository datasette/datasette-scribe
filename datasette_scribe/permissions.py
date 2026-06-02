"""Per-transcription sharing for datasette-scribe, backed by datasette-acl.

A transcription is **private by default to the actor who created it**: on
creation through the web UI we seed a Manager grant for ``request.actor`` on a
:class:`ScribeTranscriptionResource` (resource type ``scribe-transcription``,
``parent`` = database name, ``child`` = transcription id). The owner can then
share *view* / *edit* / *manage* with other actors or groups through the
``<datasette-acl-share-dialog>`` (its JSON API writes acl grants).

acl is a **soft dependency**. When it is not installed the grant helpers no-op
and every permission check falls back to the global ``datasette_scribe_scribe``
permission, i.e. scribe behaves exactly as it did before sharing existed.

Orphan transcriptions — those with no owner grant, i.e. ``created_by IS NULL``
(pre-existing rows, ``datasette-scribe add`` / ``import-json`` CLI creates, and
anonymous web creates) — are not owned by anyone, so they fall back to the
global ``datasette_scribe_scribe`` permission for view/edit. This keeps existing
data and CLI workflows visible (decision: "fall back to global access").

Permission decisions therefore compose two sources and live here rather than in
a ``permission_resources_sql`` hook: the hook SQL runs against the *internal*
database and cannot see transcription rows (which live in user databases), and
single-resource ``datasette.allowed()`` checks never consult ``resources_sql``
anyway — so a small Python helper that ANDs/ORs acl's answer with the orphan
fallback is both correct and simpler.
"""

from datasette import Forbidden
from datasette.permissions import Resource

from .router import SCRIBE_ACCESS_NAME

# Resource type discriminator stored in acl_resources.resource_type, and the
# Resource.name acl keys its generic permission_resources_sql on.
SCRIBE_TRANSCRIPTION_RESOURCE_TYPE = "scribe-transcription"

# Resource-scoped action names, resolved by datasette-acl against grants on
# ScribeTranscriptionResource.
ACTION_VIEW = "scribe-view"
ACTION_EDIT = "scribe-edit"
ACTION_MANAGE = "scribe-manage"

# Friendly role names (must match the AclRole names in scribe_acl_roles).
ROLE_OWNER = "Manager"


# acl is optional. Import its helpers defensively; every public function below
# degrades to the global-permission behaviour when these are None.
try:
    from datasette_acl.roles import AclRole
except ImportError:  # pragma: no cover - acl not installed
    AclRole = None

try:
    from datasette_acl.grants import grant as _acl_grant
except ImportError:  # pragma: no cover - acl not installed
    _acl_grant = None

# acl's global admin permission name (grants blanket manage rights).
ACL_ADMIN_PERMISSION = "datasette-acl"

# Action bundle for the owner ("Manager" role). seed_owner_grant writes these
# actions explicitly rather than passing role="Manager" so it does NOT depend on
# acl's role registry being populated. The registry is built at startup from the
# datasette_acl_roles hook, but that hook only attaches reliably when the host
# imports datasette.app before datasette_scribe (true under `datasette serve`,
# not under the scribe CLI entry point). Granting by action keeps ownership
# seeding correct regardless of import order; the registry is only needed by the
# share dialog, which runs exclusively under `datasette serve`.
OWNER_ACTIONS = [ACTION_VIEW, ACTION_EDIT, ACTION_MANAGE]


class ScribeTranscriptionsParent(Resource):
    """Parent level for :class:`ScribeTranscriptionResource`.

    The parent identifier is the database name a transcription lives in. This
    class only exists to give the child resource a ``parent_class`` (Datasette
    requires the two-level hierarchy be expressed this way); scribe never grants
    on it directly today.
    """

    name = "scribe-transcriptions-parent"
    parent_class = None

    @classmethod
    async def resources_sql(cls, datasette, actor=None) -> str:
        # Not used: scribe filters listings in Python rather than via
        # allowed_resources (transcriptions are not enumerable from the
        # internal database). Return an empty universe so the abstractmethod is
        # satisfied and any accidental call is harmless.
        return "SELECT NULL AS parent, NULL AS child WHERE 0"


class ScribeTranscriptionResource(Resource):
    """A single transcription, acl-backed (resource type ``scribe-transcription``).

    Two-level resource: ``parent`` is the database name, ``child`` is the
    transcription id (as a string). This is the model the ``scribe-view`` /
    ``scribe-edit`` / ``scribe-manage`` actions resolve against via
    datasette-acl's generic ``permission_resources_sql`` and grant helpers.

    Callers pass ``(database, transcription_id)`` positionally, which is also
    acl's ``build_resource(parent, child)`` convention.
    """

    name = SCRIBE_TRANSCRIPTION_RESOURCE_TYPE
    parent_class = ScribeTranscriptionsParent

    def __init__(self, parent=None, child=None):
        super().__init__(
            parent=str(parent) if parent is not None else None,
            child=str(child) if child is not None else None,
        )

    @classmethod
    async def resources_sql(cls, datasette, actor=None) -> str:
        # See ScribeTranscriptionsParent.resources_sql — intentionally empty.
        return "SELECT NULL AS parent, NULL AS child WHERE 0"


def scribe_acl_roles():
    """Friendly Viewer / Editor / Manager roles for ``scribe-transcription``.

    Consumed by datasette-acl's role registry. Returns ``[]`` when acl is not
    installed (``AclRole is None``) so the hook is a no-op. The owner gets the
    Manager role, which is ``manage=True`` so they may re-share.
    """
    if AclRole is None:
        return []
    return [
        AclRole(
            resource_type=SCRIBE_TRANSCRIPTION_RESOURCE_TYPE,
            name="Viewer",
            actions=[ACTION_VIEW],
            rank=1,
            description="Can view the transcription",
        ),
        AclRole(
            resource_type=SCRIBE_TRANSCRIPTION_RESOURCE_TYPE,
            name="Editor",
            actions=[ACTION_VIEW, ACTION_EDIT],
            rank=2,
            description="Can view and edit the transcription",
        ),
        AclRole(
            resource_type=SCRIBE_TRANSCRIPTION_RESOURCE_TYPE,
            name=ROLE_OWNER,
            actions=[ACTION_VIEW, ACTION_EDIT, ACTION_MANAGE],
            rank=3,
            manage=True,
            description="Can view, edit, and manage sharing",
        ),
    ]


# --- Collection-scoped sharing -------------------------------------------------
#
# A collected transcript is governed by its collection's ACL rather than a
# per-transcription grant. The collection is its own acl resource type so the
# share dialog and grants operate at the collection level; scope resolution
# (_scope_resource) decides which resource a transcription check routes to.

SCRIBE_COLLECTION_RESOURCE_TYPE = "scribe-collection"

ACTION_COLLECTION_VIEW = "scribe-collection-view"
ACTION_COLLECTION_EDIT = "scribe-collection-edit"
ACTION_COLLECTION_MANAGE = "scribe-collection-manage"
COLLECTION_OWNER_ACTIONS = [
    ACTION_COLLECTION_VIEW,
    ACTION_COLLECTION_EDIT,
    ACTION_COLLECTION_MANAGE,
]


class ScribeCollectionsParent(Resource):
    """Parent level for :class:`ScribeCollectionResource` (the database name)."""

    name = "scribe-collections-parent"
    parent_class = None

    @classmethod
    async def resources_sql(cls, datasette, actor=None) -> str:
        return "SELECT NULL AS parent, NULL AS child WHERE 0"


class ScribeCollectionResource(Resource):
    """A single collection, acl-backed (resource type ``scribe-collection``).

    Two-level resource: ``parent`` is the database name, ``child`` is the
    collection id (as a string). Mirrors :class:`ScribeTranscriptionResource`.
    """

    name = SCRIBE_COLLECTION_RESOURCE_TYPE
    parent_class = ScribeCollectionsParent

    def __init__(self, parent=None, child=None):
        super().__init__(
            parent=str(parent) if parent is not None else None,
            child=str(child) if child is not None else None,
        )

    @classmethod
    async def resources_sql(cls, datasette, actor=None) -> str:
        return "SELECT NULL AS parent, NULL AS child WHERE 0"


def scribe_collection_acl_roles():
    """Viewer / Editor / Manager roles for ``scribe-collection``. ``[]`` w/o acl."""
    if AclRole is None:
        return []
    return [
        AclRole(
            resource_type=SCRIBE_COLLECTION_RESOURCE_TYPE,
            name="Viewer",
            actions=[ACTION_COLLECTION_VIEW],
            rank=1,
            description="Can view the collection",
        ),
        AclRole(
            resource_type=SCRIBE_COLLECTION_RESOURCE_TYPE,
            name="Editor",
            actions=[ACTION_COLLECTION_VIEW, ACTION_COLLECTION_EDIT],
            rank=2,
            description="Can view and edit the collection",
        ),
        AclRole(
            resource_type=SCRIBE_COLLECTION_RESOURCE_TYPE,
            name=ROLE_OWNER,
            actions=COLLECTION_OWNER_ACTIONS,
            rank=3,
            manage=True,
            description="Can view, edit, and manage sharing",
        ),
    ]


async def seed_owner_grant(datasette, database, transcription_id, created_by) -> None:
    """Grant ``created_by`` the Manager role on a freshly created transcription.

    No-op for anonymous creates (``created_by`` falsy — anonymous actors never
    own) and when acl is not installed. This is what makes a transcription
    "private by default to its creator": until the owner shares it, only the
    Manager grant exists.
    """
    if not created_by or _acl_grant is None:
        return
    await _acl_grant(
        datasette,
        SCRIBE_TRANSCRIPTION_RESOURCE_TYPE,
        str(database),
        str(transcription_id),
        actor_id=str(created_by),
        actions=OWNER_ACTIONS,
        by_actor=str(created_by),
    )


async def seed_collection_owner_grant(
    datasette, database, collection_id, created_by
) -> None:
    """Grant ``created_by`` the Manager role on a freshly created collection.

    Mirror of :func:`seed_owner_grant` for the collection resource. No-op for
    anonymous creates and when acl is not installed.
    """
    if not created_by or _acl_grant is None:
        return
    await _acl_grant(
        datasette,
        SCRIBE_COLLECTION_RESOURCE_TYPE,
        str(database),
        str(collection_id),
        actor_id=str(created_by),
        actions=COLLECTION_OWNER_ACTIONS,
        by_actor=str(created_by),
    )


async def _has_global_access(datasette, actor) -> bool:
    return await datasette.allowed(action=SCRIBE_ACCESS_NAME, actor=actor)


async def _scope_resource(datasette, database, transcription_id):
    """Return ``(resource, (view, edit, manage))`` governing this transcription.

    A collected transcript resolves to its :class:`ScribeCollectionResource` and
    the collection action triple; a standalone transcript resolves to its
    :class:`ScribeTranscriptionResource` and the transcription action triple
    (today's behaviour). The right resource is computed live from current
    membership, so a move re-points the check the instant membership changes.
    """
    db = datasette.get_database(database)
    row = (
        await db.execute(
            "select collection_id from datasette_scribe_collection_transcriptions"
            " where transcription_id = ?",
            [transcription_id],
        )
    ).first()
    if row:
        return ScribeCollectionResource(database, row["collection_id"]), (
            ACTION_COLLECTION_VIEW,
            ACTION_COLLECTION_EDIT,
            ACTION_COLLECTION_MANAGE,
        )
    return ScribeTranscriptionResource(database, transcription_id), (
        ACTION_VIEW,
        ACTION_EDIT,
        ACTION_MANAGE,
    )


async def _allowed(datasette, actor, action, resource) -> bool:
    """True if acl grants ``action`` to ``actor`` on ``resource``.

    Returns False (rather than erroring) when acl is not installed, because no
    grants can exist — callers then rely on the orphan/global fallback.
    """
    if _acl_grant is None:
        return False
    return await datasette.allowed(action=action, resource=resource, actor=actor)


async def can_view(datasette, actor, database, transcription_id, created_by) -> bool:
    """Whether ``actor`` may view this transcription.

    Allowed if acl grants view on the transcription's *scope* (its collection
    when collected, else the transcription itself — owner or a share), OR the
    transcription is an orphan (``created_by`` is None) and the actor holds the
    global ``datasette_scribe_scribe`` permission. The orphan fallback is a
    property of the transcription row independent of scope: a collected orphan
    still falls back to global view/edit, matching CLI/legacy visibility.
    """
    resource, (av, _ae, _am) = await _scope_resource(
        datasette, database, transcription_id
    )
    if await _allowed(datasette, actor, av, resource):
        return True
    if created_by is None and await _has_global_access(datasette, actor):
        return True
    return False


async def can_edit(datasette, actor, database, transcription_id, created_by) -> bool:
    """Whether ``actor`` may edit this transcription (same shape as :func:`can_view`)."""
    resource, (_av, ae, _am) = await _scope_resource(
        datasette, database, transcription_id
    )
    if await _allowed(datasette, actor, ae, resource):
        return True
    if created_by is None and await _has_global_access(datasette, actor):
        return True
    return False


async def can_manage(datasette, actor, database, transcription_id) -> bool:
    """Whether ``actor`` may manage sharing for this transcription's scope.

    Allowed if acl grants the scope's manage action (collection-manage for a
    collected transcript, scribe-manage for a standalone one — the owner holds
    it via the seeded grant), OR the actor holds acl's global ``datasette-acl``
    admin permission. False when acl is not installed.
    """
    if _acl_grant is None:
        return False
    resource, (_av, _ae, am) = await _scope_resource(
        datasette, database, transcription_id
    )
    if await _allowed(datasette, actor, am, resource):
        return True
    return await datasette.allowed(action=ACL_ADMIN_PERMISSION, actor=actor)


async def can_manage_collection(datasette, actor, database, collection_id) -> bool:
    """Whether ``actor`` may manage sharing for a collection directly.

    Used by the collection share dialog (T07) and move semantics (T05). Checks
    the collection-manage action on :class:`ScribeCollectionResource` plus acl's
    global admin fallback. False when acl is not installed.
    """
    if _acl_grant is None:
        return False
    if await _allowed(
        datasette,
        actor,
        ACTION_COLLECTION_MANAGE,
        ScribeCollectionResource(database, collection_id),
    ):
        return True
    return await datasette.allowed(action=ACL_ADMIN_PERMISSION, actor=actor)


async def ensure_view(datasette, actor, database, transcription_id, created_by) -> None:
    if not await can_view(datasette, actor, database, transcription_id, created_by):
        raise Forbidden(ACTION_VIEW)


async def ensure_edit(datasette, actor, database, transcription_id, created_by) -> None:
    if not await can_edit(datasette, actor, database, transcription_id, created_by):
        raise Forbidden(ACTION_EDIT)


async def filter_visible_ids(datasette, actor, database, rows) -> set[int]:
    """Return the subset of transcription ids in ``rows`` that ``actor`` may view.

    ``rows`` is any iterable of mappings exposing ``id`` and ``created_by``, and
    optionally ``collection_id`` (when present and non-NULL the row is checked
    against its collection resource instead of the transcription resource — see
    :func:`_scope_resource`). Callers that join ``collection_transcriptions``
    expose ``collection_id``; those that don't get the standalone behaviour.
    Orphans (``created_by`` is None) fall back to a single global check.
    """
    global_access = await _has_global_access(datasette, actor)
    visible: set[int] = set()
    for row in rows:
        cid = row["collection_id"] if "collection_id" in row.keys() else None
        if row["created_by"] is None and global_access:
            visible.add(row["id"])
            continue
        if cid is not None:
            resource = ScribeCollectionResource(database, cid)
            action = ACTION_COLLECTION_VIEW
        else:
            resource = ScribeTranscriptionResource(database, row["id"])
            action = ACTION_VIEW
        if await _allowed(datasette, actor, action, resource):
            visible.add(row["id"])
    return visible
