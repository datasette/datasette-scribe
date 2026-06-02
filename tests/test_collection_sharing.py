"""Tests for scope-based (collection) sharing — T04.

A collected transcript is governed by its collection's ACL; a standalone
transcript keeps the per-transcription ACL (test_sharing.py). Fixtures mirror
test_sharing.py.
"""

import json
import re

import pytest
from datasette.app import Datasette

from datasette_scribe import permissions
from datasette_scribe.router import ensure_schema

DB = "data"


def _cookies(ds, actor_id):
    return {"ds_actor": ds.sign({"a": {"id": actor_id}}, "actor")}


async def _make_datasette(tmp_path):
    db_path = tmp_path / f"{DB}.db"
    db_path.write_bytes(b"")
    ds = Datasette(
        [str(db_path)],
        config={
            "permissions": {permissions.SCRIBE_ACCESS_NAME: {"id": ["alice", "bob"]}}
        },
    )
    await ds.invoke_startup()
    await ensure_schema(ds, DB)
    return ds


async def _insert_collection(ds, name, *, created_by=None):
    db = ds.get_database(DB)
    r = await db.execute_write(
        "insert into datasette_scribe_collections (name, created_by) values (?, ?)",
        [name, created_by],
    )
    return r.lastrowid


async def _insert_transcription(ds, *, created_by):
    db = ds.get_database(DB)
    r = await db.execute_write(
        "insert into datasette_scribe_transcriptions"
        " (input_type, model, granularity, submitted_at, created_by)"
        " values ('url', 'm', 'segment', datetime('now'), ?)",
        [created_by],
    )
    return r.lastrowid


async def _add_to_collection(ds, cid, tid):
    db = ds.get_database(DB)
    await db.execute_write(
        "insert into datasette_scribe_collection_transcriptions"
        " (collection_id, transcription_id) values (?, ?)",
        [cid, tid],
    )


@pytest.mark.asyncio
async def test_collection_actions_resolve(tmp_path):
    ds = await _make_datasette(tmp_path)
    cid = await _insert_collection(ds, "C")
    from datasette_acl.grants import grant
    from datasette_scribe import permissions as P

    await grant(
        ds,
        P.SCRIBE_COLLECTION_RESOURCE_TYPE,
        DB,
        str(cid),
        actor_id="bob",
        actions=[P.ACTION_COLLECTION_VIEW],
        by_actor="alice",
    )
    assert await ds.allowed(
        action=P.ACTION_COLLECTION_VIEW,
        resource=P.ScribeCollectionResource(DB, cid),
        actor={"id": "bob"},
    )
    assert not await ds.allowed(
        action=P.ACTION_COLLECTION_EDIT,
        resource=P.ScribeCollectionResource(DB, cid),
        actor={"id": "bob"},
    )


@pytest.mark.asyncio
async def test_collection_view_grant_makes_members_visible(tmp_path):
    ds = await _make_datasette(tmp_path)
    cid = await _insert_collection(ds, "C")
    t1 = await _insert_transcription(ds, created_by="alice")
    t2 = await _insert_transcription(ds, created_by="alice")
    await _add_to_collection(ds, cid, t1)
    await _add_to_collection(ds, cid, t2)
    await permissions.seed_collection_owner_grant(ds, DB, cid, "alice")

    from datasette_acl.grants import grant

    await grant(
        ds,
        permissions.SCRIBE_COLLECTION_RESOURCE_TYPE,
        DB,
        str(cid),
        actor_id="bob",
        actions=[permissions.ACTION_COLLECTION_VIEW],
        by_actor="alice",
    )

    # bob sees BOTH members via the single collection grant
    assert await permissions.can_view(ds, {"id": "bob"}, DB, t1, "alice")
    assert await permissions.can_view(ds, {"id": "bob"}, DB, t2, "alice")
    assert not await permissions.can_edit(ds, {"id": "bob"}, DB, t1, "alice")


@pytest.mark.asyncio
async def test_standalone_unaffected(tmp_path):
    ds = await _make_datasette(tmp_path)
    t = await _insert_transcription(ds, created_by="alice")
    await permissions.seed_owner_grant(ds, DB, t, "alice")
    assert await permissions.can_view(ds, {"id": "alice"}, DB, t, "alice")
    assert not await permissions.can_view(ds, {"id": "bob"}, DB, t, "alice")


@pytest.mark.asyncio
async def test_creator_owns_collection(tmp_path):
    ds = await _make_datasette(tmp_path)
    resp = await ds.client.post(
        "/-/api/scribe/collections/create",
        json={"database": DB, "name": "C"},
        cookies=_cookies(ds, "alice"),
    )
    assert resp.json()["ok"]
    cid = (
        await ds.get_database(DB).execute(
            "select id, created_by from datasette_scribe_collections where name='C'"
        )
    ).first()
    assert cid["created_by"] == "alice"
    assert await permissions.can_manage_collection(ds, {"id": "alice"}, DB, cid["id"])
    assert not await permissions.can_manage_collection(ds, {"id": "bob"}, DB, cid["id"])
