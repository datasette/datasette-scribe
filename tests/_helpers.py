"""Shared test fixtures/helpers for the v2 scoped-speaker test suite.

Reused by test_speakers.py (T02), test_speaker_profiles.py (T03),
test_move_semantics.py (T05) and test_pagedata.py (T06).
"""

from types import SimpleNamespace

from datasette.app import Datasette

from datasette_scribe.router import SCRIBE_ACCESS_NAME, ensure_schema
from datasette_scribe.routes._scope import store_segments  # noqa: F401  (re-export)

DB = "data"
DEFAULT_ACTOR = "tester"


def _cookies(ds, actor_id):
    return {"ds_actor": ds.sign({"a": {"id": actor_id}}, "actor")}


async def scribe_db(tmp_path):
    """An acl-enabled Datasette with an empty scribe schema. Returns (ds, db)."""
    db_path = tmp_path / f"{DB}.db"
    db_path.write_bytes(b"")
    ds = Datasette(
        [str(db_path)],
        # Any authenticated actor may use scribe; anonymous cannot.
        config={"permissions": {SCRIBE_ACCESS_NAME: {"id": "*"}}},
    )
    await ds.invoke_startup()
    await ensure_schema(ds, DB)
    return ds, ds.get_database(DB)


async def client_post(ds, path, json_body, actor=DEFAULT_ACTOR):
    cookies = _cookies(ds, actor) if actor else {}
    return await ds.client.post(path, json=json_body, cookies=cookies)


def seg(start, end, speaker_id, text):
    """A minimal extraction-segment stand-in (start/end/speaker_id/text)."""
    return SimpleNamespace(start=start, end=end, speaker_id=speaker_id, text=text)


async def new_transcription(db):
    """Insert an orphan (created_by NULL) standalone transcription. Returns id."""
    r = await db.execute_write(
        "insert into datasette_scribe_transcriptions"
        " (input_type, model, granularity, submitted_at)"
        " values ('url', 'm', 'segment', datetime('now'))"
    )
    return r.lastrowid


async def new_collection(db, name):
    r = await db.execute_write(
        "insert into datasette_scribe_collections (name) values (?)", [name]
    )
    return r.lastrowid


async def add_to_collection(db, cid, tid):
    await db.execute_write(
        "insert into datasette_scribe_collection_transcriptions"
        " (collection_id, transcription_id) values (?, ?)",
        [cid, tid],
    )


async def create_speaker_in_collection(db, cid, name):
    r = await db.execute_write(
        "insert into datasette_scribe_speakers (collection_id, name, is_configured)"
        " values (?, ?, 1)",
        [cid, name],
    )
    return r.lastrowid


async def create_speaker_in_transcript(db, tid, name):
    r = await db.execute_write(
        "insert into datasette_scribe_speakers (transcription_id, name, is_configured)"
        " values (?, ?, 1)",
        [tid, name],
    )
    return r.lastrowid


async def assign(db, tid, sid):
    """Insert one entry into transcript `tid` assigned to speaker `sid`. Returns id."""
    r = await db.execute_write(
        "insert into datasette_scribe_transcription_entries"
        " (transcription_id, start, end, speaker_id, text) values (?, 0, 1, ?, 'x')",
        [tid, sid],
    )
    return r.lastrowid


async def add_entry_get_id(db, tid):
    """Insert one unassigned entry into transcript `tid`. Returns its id."""
    r = await db.execute_write(
        "insert into datasette_scribe_transcription_entries"
        " (transcription_id, start, end, speaker_id, text) values (?, 0, 1, null, 'x')",
        [tid],
    )
    return r.lastrowid
