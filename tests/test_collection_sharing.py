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
