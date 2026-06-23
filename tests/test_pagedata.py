import json
import re

import pytest

from datasette_scribe.page_data import TranscriptionEntry, TranscriptionSpeaker

from ._helpers import (
    DB,
    _cookies,
    add_to_collection,
    create_speaker_in_collection,
    create_speaker_in_transcript,
    new_collection,
    new_transcription,
    scribe_db,
)


def test_speaker_model_fields():
    s = TranscriptionSpeaker(
        id=1, name="Alice", description="Host", is_configured=True, has_photo=True
    )
    assert s.model_dump() == {
        "id": 1,
        "name": "Alice",
        "description": "Host",
        "is_configured": True,
        "has_photo": True,
    }


def test_entry_speaker_id_is_int():
    e = TranscriptionEntry(id=1, start=0, end=1, speaker_id=7, text="hi")
    assert e.speaker_id == 7
    assert TranscriptionEntry(id=2, start=0, end=1, text="x").speaker_id is None


def _page_data(resp):
    match = re.search(
        r'<script type="application/json" id="pageData">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


@pytest.mark.asyncio
async def test_detail_page_lists_only_scope_speakers(tmp_path):
    ds, db = await scribe_db(tmp_path)
    c = await new_collection(db, "C")
    t1 = await new_transcription(db)
    await add_to_collection(db, c, t1)
    other = await new_transcription(db)  # standalone, different scope
    await create_speaker_in_collection(db, c, "InScope")
    await create_speaker_in_transcript(db, other, "OutOfScope")

    resp = await ds.client.get(
        f"/{DB}/-/scribe/transcription/{t1}", cookies=_cookies(ds, "tester")
    )
    assert resp.status_code == 200
    pd = _page_data(resp)
    names = {s["name"] for s in pd["all_speakers"]}
    assert "InScope" in names
    assert "OutOfScope" not in names
