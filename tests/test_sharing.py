"""Tests for per-transcription sharing (datasette-acl backed).

Covers the private-by-default model in datasette_scribe/permissions.py:
- an owner sees their transcription; other actors do not
- a view grant makes it visible (but not editable) to another actor
- orphan transcriptions (created_by IS NULL) fall back to the global
  datasette_scribe_scribe permission
- the listing page filters to visible transcriptions end to end
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
            # alice and bob can use scribe at all; anonymous cannot.
            "permissions": {permissions.SCRIBE_ACCESS_NAME: {"id": ["alice", "bob"]}},
        },
    )
    await ds.invoke_startup()
    await ensure_schema(ds, DB)
    return ds


async def _insert_transcription(ds, *, created_by):
    db = ds.get_database(DB)
    result = await db.execute_write(
        "insert into datasette_scribe_transcriptions"
        " (input_type, model, granularity, submitted_at, created_by)"
        " values ('url', 'm', 'segment', datetime('now'), ?)",
        [created_by],
    )
    return result.lastrowid


@pytest.mark.asyncio
async def test_owner_private_by_default(tmp_path):
    ds = await _make_datasette(tmp_path)
    tid = await _insert_transcription(ds, created_by="alice")
    await permissions.seed_owner_grant(ds, DB, tid, "alice")

    alice = {"id": "alice"}
    bob = {"id": "bob"}

    # Owner can view, edit, and manage.
    assert await permissions.can_view(ds, alice, DB, tid, "alice")
    assert await permissions.can_edit(ds, alice, DB, tid, "alice")
    assert await permissions.can_manage(ds, alice, DB, tid)

    # A different actor (even with global access) cannot — it's owned.
    assert not await permissions.can_view(ds, bob, DB, tid, "alice")
    assert not await permissions.can_edit(ds, bob, DB, tid, "alice")
    assert not await permissions.can_manage(ds, bob, DB, tid)

    # Anonymous cannot.
    assert not await permissions.can_view(ds, None, DB, tid, "alice")


@pytest.mark.asyncio
async def test_view_grant_shares_read_only(tmp_path):
    from datasette_acl.grants import grant, Principal

    ds = await _make_datasette(tmp_path)
    tid = await _insert_transcription(ds, created_by="alice")
    await permissions.seed_owner_grant(ds, DB, tid, "alice")

    bob = {"id": "bob"}
    # Grant by explicit action (Viewer = scribe-view) rather than role name, so
    # the test does not depend on acl's role registry being populated (which is
    # subject to plugin import order — see permissions.OWNER_ACTIONS). The share
    # dialog grants by role under `datasette serve`, where the registry is built.
    await grant(
        ds,
        permissions.SCRIBE_TRANSCRIPTION_RESOURCE_TYPE,
        DB,
        str(tid),
        principal=Principal.actor("bob"),
        actions=[permissions.ACTION_VIEW],
        by_actor="alice",
    )

    # Bob can now view but not edit or manage.
    assert await permissions.can_view(ds, bob, DB, tid, "alice")
    assert not await permissions.can_edit(ds, bob, DB, tid, "alice")
    assert not await permissions.can_manage(ds, bob, DB, tid)


@pytest.mark.asyncio
async def test_orphan_falls_back_to_global(tmp_path):
    ds = await _make_datasette(tmp_path)
    tid = await _insert_transcription(ds, created_by=None)
    # No owner grant for orphan transcriptions.

    alice = {"id": "alice"}  # has global access
    carol = {"id": "carol"}  # no global access

    # Global-access actors can view/edit the orphan.
    assert await permissions.can_view(ds, alice, DB, tid, None)
    assert await permissions.can_edit(ds, alice, DB, tid, None)

    # Actors without global access cannot.
    assert not await permissions.can_view(ds, carol, DB, tid, None)
    assert not await permissions.can_view(ds, None, DB, tid, None)


@pytest.mark.asyncio
async def test_listing_page_filters_visible(tmp_path):
    ds = await _make_datasette(tmp_path)
    alice_tid = await _insert_transcription(ds, created_by="alice")
    await permissions.seed_owner_grant(ds, DB, alice_tid, "alice")
    bob_tid = await _insert_transcription(ds, created_by="bob")
    await permissions.seed_owner_grant(ds, DB, bob_tid, "bob")
    orphan_tid = await _insert_transcription(ds, created_by=None)

    response = await ds.client.get(f"/{DB}/-/scribe", cookies=_cookies(ds, "alice"))
    assert response.status_code == 200
    match = re.search(
        r'<script type="application/json" id="pageData">(.*?)</script>',
        response.text,
        re.DOTALL,
    )
    assert match is not None
    page_data = json.loads(match.group(1))
    listed = {t["id"] for t in page_data["uncollected_transcriptions"]}

    # Alice sees her own transcription and the orphan (global fallback), but
    # not bob's owned transcription.
    assert alice_tid in listed
    assert orphan_tid in listed
    assert bob_tid not in listed
