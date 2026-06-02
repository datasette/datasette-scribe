import pytest
from datasette.app import Datasette
from datasette_scribe.router import ensure_schema

DB = "data"


async def _fresh(tmp_path):
    p = tmp_path / f"{DB}.db"
    p.write_bytes(b"")
    ds = Datasette(
        [str(p)],
        config={"permissions": {"datasette_scribe_scribe": {"id": ["alice"]}}},
    )
    await ds.invoke_startup()
    await ensure_schema(ds, DB)
    return ds


@pytest.mark.asyncio
async def test_v2_schema_shape(tmp_path):
    ds = await _fresh(tmp_path)
    db = ds.get_database(DB)
    cols = {
        r["name"]
        for r in (await db.execute("pragma table_info(datasette_scribe_speakers)")).rows
    }
    assert {
        "collection_id",
        "transcription_id",
        "description",
        "is_configured",
        "configured_at",
    } <= cols
    assert "is_original" not in cols
    assert (
        await db.execute(
            "select name from sqlite_master where name='datasette_scribe_speaker_photos'"
        )
    ).first() is not None
    ccols = {
        r["name"]
        for r in (
            await db.execute("pragma table_info(datasette_scribe_collections)")
        ).rows
    }
    assert "created_by" in ccols


@pytest.mark.asyncio
async def test_scope_check_constraint(tmp_path):
    db = (await _fresh(tmp_path)).get_database(DB)
    # neither scope column set -> rejected
    with pytest.raises(Exception):
        await db.execute_write(
            "insert into datasette_scribe_speakers (name) values ('x')"
        )
    # both set -> rejected
    with pytest.raises(Exception):
        await db.execute_write(
            "insert into datasette_scribe_speakers (name, collection_id, transcription_id)"
            " values ('x', 1, 1)"
        )


@pytest.mark.asyncio
async def test_unique_name_per_scope(tmp_path):
    db = (await _fresh(tmp_path)).get_database(DB)
    c = (
        await db.execute_write(
            "insert into datasette_scribe_collections (name) values ('C')"
        )
    ).lastrowid
    await db.execute_write(
        "insert into datasette_scribe_speakers (collection_id, name) values (?, 'Alice')",
        [c],
    )
    # same name, same collection -> rejected
    with pytest.raises(Exception):
        await db.execute_write(
            "insert into datasette_scribe_speakers (collection_id, name) values (?, 'Alice')",
            [c],
        )
    # same name, different scope (a transcription) -> allowed
    t = (
        await db.execute_write(
            "insert into datasette_scribe_transcriptions (input_type, model, granularity, submitted_at)"
            " values ('url','m','segment',datetime('now'))"
        )
    ).lastrowid
    await db.execute_write(
        "insert into datasette_scribe_speakers (transcription_id, name) values (?, 'Alice')",
        [t],
    )
    assert (
        await db.execute(
            "select count(*) c from datasette_scribe_speakers where name='Alice'"
        )
    ).first()["c"] == 2
