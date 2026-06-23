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
async def test_move_into_collection_copies_speakers(tmp_path):
    ds, db = await scribe_db(tmp_path)
    # standalone transcript with its own speakers + assignments + a photo
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "Speaker 1")
    eid = await assign(db, t, s)
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
    assert body["ok"] and body["copied_speakers"] == 1
    # the entry is still assigned — to a freshly created collection-scoped speaker
    entry = (
        await db.execute(
            "select speaker_id from datasette_scribe_transcription_entries where id=?",
            [eid],
        )
    ).first()
    assert entry["speaker_id"] is not None
    copy = (
        await db.execute(
            "select id, name from datasette_scribe_speakers"
            " where collection_id=? and name='Speaker 1'",
            [c],
        )
    ).first()
    assert copy is not None and entry["speaker_id"] == copy["id"]
    # the photo was carried onto the copy
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speaker_photos where speaker_id=?",
            [copy["id"]],
        )
    ).first()["c"] == 1
    # the old transcript-scoped speaker + its photo are gone
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
    e1 = await assign(db, t1, shared)
    await assign(db, t2, shared)

    # t1 leaves the collection
    r = await client_post(
        ds,
        f"/-/api/scribe/collections/{c}/remove-transcription",
        {"database": DB, "transcription_id": t1},
    )
    assert r.json()["ok"]
    # collection-scoped "Alice" still exists (t2 still uses her, and collection
    # speakers are never deleted on move)
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speakers where id=?", [shared]
        )
    ).first()["c"] == 1
    # t1's entry is now assigned to a fresh transcript-scoped copy, not unlinked
    e1_speaker = (
        await db.execute(
            "select speaker_id from datasette_scribe_transcription_entries where id=?",
            [e1],
        )
    ).first()["speaker_id"]
    assert e1_speaker is not None and e1_speaker != shared
    copy = (
        await db.execute(
            "select transcription_id, name from datasette_scribe_speakers where id=?",
            [e1_speaker],
        )
    ).first()
    assert copy["transcription_id"] == t1 and copy["name"] == "Alice"
    # t2's assignment to the shared collection speaker is preserved
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
async def test_move_a_to_b_copies(tmp_path):
    ds, db = await scribe_db(tmp_path)
    a = await new_collection(db, "A")
    b = await new_collection(db, "B")
    t = await new_transcription(db)
    await add_to_collection(db, a, t)
    sa = await create_speaker_in_collection(db, a, "X")
    eid = await assign(db, t, sa)
    r = await client_post(
        ds,
        f"/-/api/scribe/transcription/{t}/move",
        {"database": DB, "collection_id": b},
    )
    body = r.json()
    assert body["ok"] and body["collection_id"] == b and body["copied_speakers"] == 1
    assert (
        await db.execute(
            "select collection_id from datasette_scribe_collection_transcriptions where transcription_id=?",
            [t],
        )
    ).first()["collection_id"] == b
    # the entry is still assigned — to a fresh B-scoped copy of "X"
    entry_speaker = (
        await db.execute(
            "select speaker_id from datasette_scribe_transcription_entries where id=?",
            [eid],
        )
    ).first()["speaker_id"]
    assert entry_speaker is not None
    bx = (
        await db.execute(
            "select id from datasette_scribe_speakers where collection_id=? and name='X'",
            [b],
        )
    ).first()
    assert bx is not None and entry_speaker == bx["id"]
    # A's collection-scoped speaker is untouched (other members could use it)
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speakers where id=?", [sa]
        )
    ).first()["c"] == 1


@pytest.mark.asyncio
async def test_move_keeps_speakers_separate_on_name_clash(tmp_path):
    """A copied speaker never auto-merges into a same-named destination speaker;
    it gets a numbered suffix instead (merging is a later, deliberate action)."""
    ds, db = await scribe_db(tmp_path)
    c = await new_collection(db, "C")
    existing = await create_speaker_in_collection(db, c, "Alice")
    # standalone transcript whose speaker is also named "Alice"
    t = await new_transcription(db)
    mine = await create_speaker_in_transcript(db, t, "Alice")
    eid = await assign(db, t, mine)

    r = await client_post(
        ds,
        f"/-/api/scribe/collections/{c}/add-transcription",
        {"database": DB, "transcription_id": t},
    )
    assert r.json()["ok"]
    # two distinct "Alice" rows now live in the collection
    rows = (
        await db.execute(
            "select id, name from datasette_scribe_speakers where collection_id=?"
            " order by id",
            [c],
        )
    ).rows
    assert [row["name"] for row in rows] == ["Alice", "Alice (2)"]
    # the moved entry points at the suffixed copy, not the pre-existing speaker
    entry_speaker = (
        await db.execute(
            "select speaker_id from datasette_scribe_transcription_entries where id=?",
            [eid],
        )
    ).first()["speaker_id"]
    assert entry_speaker == rows[1]["id"] and entry_speaker != existing


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
