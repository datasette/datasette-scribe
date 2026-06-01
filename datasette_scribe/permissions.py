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


async def _has_global_access(datasette, actor) -> bool:
    return await datasette.allowed(action=SCRIBE_ACCESS_NAME, actor=actor)


async def _allowed_resource(
    datasette, actor, action, database, transcription_id
) -> bool:
    """True if acl grants ``action`` to ``actor`` on this transcription.

    Returns False (rather than erroring) when acl is not installed, because no
    grants can exist — callers then rely on the orphan/global fallback.
    """
    if _acl_grant is None:
        return False
    return await datasette.allowed(
        action=action,
        resource=ScribeTranscriptionResource(database, transcription_id),
        actor=actor,
    )


async def can_view(datasette, actor, database, transcription_id, created_by) -> bool:
    """Whether ``actor`` may view this transcription.

    Allowed if acl grants ``scribe-view`` (owner or a share), OR the
    transcription is an orphan (``created_by`` is None) and the actor holds the
    global ``datasette_scribe_scribe`` permission.
    """
    if await _allowed_resource(
        datasette, actor, ACTION_VIEW, database, transcription_id
    ):
        return True
    if created_by is None and await _has_global_access(datasette, actor):
        return True
    return False


async def can_edit(datasette, actor, database, transcription_id, created_by) -> bool:
    """Whether ``actor`` may edit this transcription (same shape as :func:`can_view`)."""
    if await _allowed_resource(
        datasette, actor, ACTION_EDIT, database, transcription_id
    ):
        return True
    if created_by is None and await _has_global_access(datasette, actor):
        return True
    return False


async def can_manage(datasette, actor, database, transcription_id) -> bool:
    """Whether ``actor`` may manage sharing for this transcription.

    Allowed if acl grants the ``scribe-manage`` action on this resource (the
    owner holds it via the seeded owner grant), OR the actor holds acl's global
    ``datasette-acl`` admin permission. Returns False when acl is not installed
    (no sharing without acl). This mirrors acl's own share-API manage gate but
    checks the manage action directly, so it does not depend on the role
    registry being populated (see OWNER_ACTIONS).
    """
    if _acl_grant is None:
        return False
    if await _allowed_resource(
        datasette, actor, ACTION_MANAGE, database, transcription_id
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

    ``rows`` is any iterable of mappings exposing ``id`` and ``created_by``.
    Computes global access once, then applies :func:`can_view` per row. Orphans
    are resolved by the single global check; owned rows each get one acl lookup
    (fine for the dozens-of-transcriptions listings scribe renders today).
    """
    global_access = await _has_global_access(datasette, actor)
    visible: set[int] = set()
    for row in rows:
        created_by = row["created_by"]
        if created_by is None:
            if global_access:
                visible.add(row["id"])
            continue
        if await _allowed_resource(datasette, actor, ACTION_VIEW, database, row["id"]):
            visible.add(row["id"])
    return visible
