import pytest

from ._helpers import (
    DB,
    add_entry_get_id,
    add_to_collection,
    assign,
    client_post,
    create_speaker_in_collection,
    create_speaker_in_transcript,
    new_collection,
    new_transcription,
    scribe_db,
    seg,
    store_segments,
)


@pytest.mark.asyncio
async def test_extraction_creates_scoped_speakers(tmp_path):
    ds, db = await scribe_db(tmp_path)
    tid = await new_transcription(db)
    segs = [
        seg(0, 1, "Speaker 1", "hi"),
        seg(1, 2, "Speaker 2", "yo"),
        seg(2, 3, "Speaker 1", "again"),
    ]
    await store_segments(db, tid, segs)

    speakers = (
        await db.execute(
            "select id, transcription_id, collection_id, name from datasette_scribe_speakers"
        )
    ).rows
    assert {s["name"] for s in speakers} == {"Speaker 1", "Speaker 2"}
    assert all(
        s["transcription_id"] == tid and s["collection_id"] is None for s in speakers
    )
    # entries link by id; the two "Speaker 1" segments share one id
    erows = (
        await db.execute(
            "select speaker_id, original_speaker_id from datasette_scribe_transcription_entries"
            " order by start"
        )
    ).rows
    s1 = next(s["id"] for s in speakers if s["name"] == "Speaker 1")
    assert erows[0]["speaker_id"] == s1 and erows[2]["speaker_id"] == s1
    assert erows[0]["original_speaker_id"] == "Speaker 1"  # raw label preserved


@pytest.mark.asyncio
async def test_create_speaker_scoped_unique_per_scope(tmp_path):
    ds, db = await scribe_db(tmp_path)
    # two collections, each can hold an "Alice"
    c1 = await new_collection(db, "C1")
    c2 = await new_collection(db, "C2")
    t1 = await new_transcription(db)
    t2 = await new_transcription(db)
    await add_to_collection(db, c1, t1)
    await add_to_collection(db, c2, t2)

    r1 = await client_post(
        ds,
        f"/-/api/scribe/transcription/{t1}/speakers/create",
        {"database": DB, "name": "Alice"},
    )
    r2 = await client_post(
        ds,
        f"/-/api/scribe/transcription/{t2}/speakers/create",
        {"database": DB, "name": "Alice"},
    )
    assert r1.json()["ok"] and r2.json()["ok"]  # same name, different scopes: OK
    # duplicate in same scope rejected
    dup = await client_post(
        ds,
        f"/-/api/scribe/transcription/{t1}/speakers/create",
        {"database": DB, "name": "Alice"},
    )
    assert dup.status_code == 400
    rows = (
        await db.execute(
            "select collection_id, name from datasette_scribe_speakers where name='Alice'"
        )
    ).rows
    assert sorted(r["collection_id"] for r in rows) == sorted([c1, c2])


@pytest.mark.asyncio
async def test_combine_within_collection_merges_all_members(tmp_path):
    ds, db = await scribe_db(tmp_path)
    c = await new_collection(db, "C")
    t1 = await new_transcription(db)
    t2 = await new_transcription(db)
    await add_to_collection(db, c, t1)
    await add_to_collection(db, c, t2)
    a = await create_speaker_in_collection(db, c, "A")
    b = await create_speaker_in_collection(db, c, "B")
    await assign(db, t1, a)
    await assign(db, t2, a)
    await assign(db, t2, b)

    r = await client_post(
        ds,
        f"/-/api/scribe/transcription/{t1}/speakers/combine",
        {"database": DB, "from_speaker_id": a, "to_speaker_id": b},
    )
    assert r.json()["ok"]
    # all A entries (both transcripts) now point at B; A is gone
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speakers where id=?", [a]
        )
    ).first()["c"] == 0
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries where speaker_id=?",
            [a],
        )
    ).first()["c"] == 0


@pytest.mark.asyncio
async def test_delete_speaker_nulls_entries_and_drops_photo(tmp_path):
    ds, db = await scribe_db(tmp_path)
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "X")
    await assign(db, t, s)
    await db.execute_write(
        "insert into datasette_scribe_speaker_photos (speaker_id, data, content_type)"
        " values (?, ?, 'image/png')",
        [s, b"\x89PNG\r\n\x1a\n"],
    )
    r = await client_post(
        ds,
        f"/-/api/scribe/transcription/{t}/speakers/delete",
        {"database": DB, "speaker_id": s},
    )
    assert r.json()["ok"]
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries where speaker_id=?",
            [s],
        )
    ).first()["c"] == 0
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speaker_photos where speaker_id=?",
            [s],
        )
    ).first()["c"] == 0  # cascade
