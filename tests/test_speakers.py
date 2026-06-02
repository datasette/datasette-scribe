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
