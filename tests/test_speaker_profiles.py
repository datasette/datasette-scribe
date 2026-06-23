import base64

import pytest

from ._helpers import (
    DB,
    _cookies,
    client_post,
    create_speaker_in_transcript,
    new_transcription,
    scribe_db,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32


def b64(x):
    return base64.b64encode(x).decode()


@pytest.mark.asyncio
async def test_update_sets_description_and_marks_configured(tmp_path):
    ds, db = await scribe_db(tmp_path)
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "Speaker 1")
    await db.execute_write(
        "update datasette_scribe_speakers set is_configured=0 where id=?", [s]
    )
    r = await client_post(
        ds,
        f"/-/api/scribe/speakers/{s}/update",
        {"database": DB, "name": "Alice", "description": "Host"},
    )
    assert r.json()["ok"]
    row = (
        await db.execute(
            "select name, description, is_configured, configured_at"
            " from datasette_scribe_speakers where id=?",
            [s],
        )
    ).first()
    assert row["name"] == "Alice" and row["description"] == "Host"
    assert row["is_configured"] == 1 and row["configured_at"] is not None


@pytest.mark.asyncio
async def test_photo_accepts_png_and_jpeg(tmp_path):
    ds, db = await scribe_db(tmp_path)
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "S")
    for img, ct in [(PNG, "image/png"), (JPEG, "image/jpeg")]:
        r = await client_post(
            ds,
            f"/-/api/scribe/speakers/{s}/photo",
            {"database": DB, "file_data": b64(img)},
        )
        assert r.json()["ok"]
        row = (
            await db.execute(
                "select content_type, length(data) n from datasette_scribe_speaker_photos"
                " where speaker_id=?",
                [s],
            )
        ).first()
        assert row["content_type"] == ct and row["n"] == len(img)  # upsert overwrites


@pytest.mark.asyncio
async def test_photo_rejects_non_image(tmp_path):
    ds, db = await scribe_db(tmp_path)
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "S")
    r = await client_post(
        ds, f"/-/api/scribe/speakers/{s}/photo", {"database": DB, "file_data": b64(GIF)}
    )
    assert r.status_code == 400 and "PNG or JPEG" in r.json()["error"]


@pytest.mark.asyncio
async def test_photo_rejects_oversize(tmp_path):
    ds, db = await scribe_db(tmp_path)
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "S")
    big = PNG + b"\x00" * 1_048_577
    r = await client_post(
        ds, f"/-/api/scribe/speakers/{s}/photo", {"database": DB, "file_data": b64(big)}
    )
    assert r.status_code == 400 and "1 MB" in r.json()["error"]


@pytest.mark.asyncio
async def test_photo_serve_roundtrip(tmp_path):
    ds, db = await scribe_db(tmp_path)
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "S")
    await client_post(
        ds, f"/-/api/scribe/speakers/{s}/photo", {"database": DB, "file_data": b64(PNG)}
    )
    resp = await ds.client.get(
        f"/{DB}/-/api/scribe/speakers/{s}/photo", cookies=_cookies(ds, "tester")
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == PNG


@pytest.mark.asyncio
async def test_photo_missing_404(tmp_path):
    ds, db = await scribe_db(tmp_path)
    t = await new_transcription(db)
    s = await create_speaker_in_transcript(db, t, "S")
    resp = await ds.client.get(
        f"/{DB}/-/api/scribe/speakers/{s}/photo", cookies=_cookies(ds, "tester")
    )
    assert resp.status_code == 404
