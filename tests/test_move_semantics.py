import pytest

from datasette_scribe import permissions

from ._helpers import (
    DB,
    add_to_collection,
    assign,
    client_post,
    create_speaker_in_collection,
    create_speaker_in_transcript,
    new_collection,
    new_transcription,
    scribe_db,
)
from .test_collection_sharing import (
    _add_to_collection,
    _cookies,
    _insert_collection,
    _insert_transcription,
    _make_datasette,
)


@pytest.mark.asyncio
async def test_move_into_collection_unlinks_and_cleans(tmp_path):
    ds, db = await scribe_db(tmp_path)
    # standalone transcript with its own speakers + assignments + a photo
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "Speaker 1")
    await assign(db, t, s)
    await db.execute_write(
        "insert into datasette_scribe_speaker_photos (speaker_id, data, content_type)"
        " values (?, ?, 'image/png')",
        [s, b"\x89PNG\r\n\x1a\n"],
    )
    c = await new_collection(db, "C")

    r = await client_post(
        ds,
        f"/-/api/scribe/collections/{c}/add-transcription",
        {"database": DB, "transcription_id": t},
    )
    body = r.json()
    assert body["ok"] and body["unlinked_entries"] >= 1
    # assignments cleared
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries"
            " where transcription_id=? and speaker_id is not null",
            [t],
        )
    ).first()["c"] == 0
    # transcript-scoped speaker + its photo gone
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speakers where transcription_id=?",
            [t],
        )
    ).first()["c"] == 0
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speaker_photos where speaker_id=?",
            [s],
        )
    ).first()["c"] == 0
    # membership set
    assert (
        await db.execute(
            "select collection_id from datasette_scribe_collection_transcriptions where transcription_id=?",
            [t],
        )
    ).first()["collection_id"] == c


@pytest.mark.asyncio
async def test_sibling_speakers_survive_when_one_leaves(tmp_path):
    ds, db = await scribe_db(tmp_path)
    c = await new_collection(db, "C")
    t1 = await new_transcription(db)
    t2 = await new_transcription(db)
    await add_to_collection(db, c, t1)
    await add_to_collection(db, c, t2)
    shared = await create_speaker_in_collection(db, c, "Alice")
    await assign(db, t1, shared)
    await assign(db, t2, shared)

    # t1 leaves the collection
    r = await client_post(
        ds,
        f"/-/api/scribe/collections/{c}/remove-transcription",
        {"database": DB, "transcription_id": t1},
    )
    assert r.json()["ok"]
    # collection-scoped "Alice" still exists (t2 still uses her)
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speakers where id=?", [shared]
        )
    ).first()["c"] == 1
    # t1's assignment was unlinked; t2's preserved
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries"
            " where transcription_id=? and speaker_id=?",
            [t1, shared],
        )
    ).first()["c"] == 0
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries"
            " where transcription_id=? and speaker_id=?",
            [t2, shared],
        )
    ).first()["c"] >= 1


@pytest.mark.asyncio
async def test_leaving_collection_makes_actor_owner(tmp_path):
    ds = await _make_datasette(tmp_path)
    cid = await _insert_collection(ds, "C", created_by="alice")
    t = await _insert_transcription(ds, created_by="alice")
    await _add_to_collection(ds, cid, t)
    await permissions.seed_collection_owner_grant(ds, DB, cid, "alice")
    resp = await ds.client.post(
        f"/-/api/scribe/collections/{cid}/remove-transcription",
        json={"database": DB, "transcription_id": t},
        cookies=_cookies(ds, "alice"),
    )
    assert resp.json()["ok"]
    # now standalone: alice owns it via the seeded transcription grant
    assert await permissions.can_manage(ds, {"id": "alice"}, DB, t)
    assert not await permissions.can_view(ds, {"id": "bob"}, DB, t, "alice")


@pytest.mark.asyncio
async def test_move_a_to_b_unlinks(tmp_path):
    ds, db = await scribe_db(tmp_path)
    a = await new_collection(db, "A")
    b = await new_collection(db, "B")
    t = await new_transcription(db)
    await add_to_collection(db, a, t)
    sa = await create_speaker_in_collection(db, a, "X")
    await assign(db, t, sa)
    r = await client_post(
        ds,
        f"/-/api/scribe/transcription/{t}/move",
        {"database": DB, "collection_id": b},
    )
    body = r.json()
    assert body["ok"] and body["collection_id"] == b and body["unlinked_entries"] >= 1
    assert (
        await db.execute(
            "select collection_id from datasette_scribe_collection_transcriptions where transcription_id=?",
            [t],
        )
    ).first()["collection_id"] == b
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries"
            " where transcription_id=? and speaker_id is not null",
            [t],
        )
    ).first()["c"] == 0
    # A's collection-scoped speaker is untouched (other members could use it)
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speakers where id=?", [sa]
        )
    ).first()["c"] == 1


@pytest.mark.asyncio
async def test_add_requires_collection_manage(tmp_path):
    """An actor who controls the transcript but cannot manage the destination
    collection is rejected."""
    ds = await _make_datasette(tmp_path)
    cid = await _insert_collection(ds, "C", created_by="alice")
    await permissions.seed_collection_owner_grant(ds, DB, cid, "alice")
    # bob owns a standalone transcript but has no rights on alice's collection
    t = await _insert_transcription(ds, created_by="bob")
    await permissions.seed_owner_grant(ds, DB, t, "bob")
    resp = await ds.client.post(
        f"/-/api/scribe/collections/{cid}/add-transcription",
        json={"database": DB, "transcription_id": t},
        cookies=_cookies(ds, "bob"),
    )
    assert resp.status_code == 403
