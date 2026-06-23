"""Scope helpers shared across speaker/transcript routes.

A speaker belongs to exactly one *scope*: a collection (when the transcript it
was extracted in has since been collected) or a standalone transcript. The scope
of a transcript is its collection if it belongs to one, otherwise the transcript
itself. These helpers resolve that and translate it into the speakers-table
column to filter/insert on.
"""


async def scope_of_transcript(db, tid: int) -> tuple[str, int]:
    """Return ('collection', collection_id) or ('transcription', tid)."""
    row = (
        await db.execute(
            "select collection_id from datasette_scribe_collection_transcriptions"
            " where transcription_id = ?",
            [tid],
        )
    ).first()
    if row:
        return ("collection", row["collection_id"])
    return ("transcription", tid)


def scope_columns(scope: tuple[str, int]) -> tuple[str, int]:
    """Map a scope tuple to (speakers_column, reference_id)."""
    kind, ref = scope
    col = "collection_id" if kind == "collection" else "transcription_id"
    return col, ref


async def unlink_and_rescope(datasette, database, tid, *, new_collection_id) -> int:
    """Move transcript ``tid`` to ``new_collection_id`` (None = standalone).

    The single primitive behind all three transitions (standalone↔collection,
    collection→collection). Unlinks every speaker assignment on the transcript,
    deletes its now-orphaned transcript-scoped speakers (and their photos),
    updates membership. ACL transition is the caller's job because policy
    differs by direction. Returns the number of entries that were unlinked.
    """
    db = datasette.get_database(database)

    affected = (
        await db.execute(
            "select count(*) c from datasette_scribe_transcription_entries"
            " where transcription_id = ? and speaker_id is not null",
            [tid],
        )
    ).first()["c"]

    # 1. unlink all assignments on this transcript
    await db.execute_write(
        "update datasette_scribe_transcription_entries set speaker_id = null"
        " where transcription_id = ?",
        [tid],
    )

    # 2. delete transcript-scoped speakers of THIS transcript (now unreferenced
    #    and unreachable — nothing else can point at a transcript-scoped
    #    speaker). Their photos go too (explicit, FK enforcement is off).
    #    Collection-scoped speakers are left intact for the remaining members.
    await db.execute_write(
        "delete from datasette_scribe_speaker_photos where speaker_id in"
        " (select id from datasette_scribe_speakers where transcription_id = ?)",
        [tid],
    )
    await db.execute_write(
        "delete from datasette_scribe_speakers where transcription_id = ?",
        [tid],
    )

    # 3. update membership
    await db.execute_write(
        "delete from datasette_scribe_collection_transcriptions where transcription_id = ?",
        [tid],
    )
    if new_collection_id is not None:
        await db.execute_write(
            "insert into datasette_scribe_collection_transcriptions"
            " (collection_id, transcription_id) values (?, ?)",
            [new_collection_id, tid],
        )

    return affected


async def store_segments(db, transcription_id: int, segments) -> None:
    """Insert entries + per-transcript scoped speakers for an extraction result.

    A freshly created transcript is always standalone, so speakers are scoped to
    the transcript. Raw model labels (e.g. "Speaker 1") become speaker rows that
    are unique per-transcript — no ``t{tid}_`` prefix needed — and duplicate
    labels within one transcript collapse to a single speaker via
    ``speaker_id_for``. Entries link to their speaker by integer id; the raw
    label is preserved verbatim in ``original_speaker_id``.
    """
    speaker_id_for: dict[str, int] = {}
    for segment in segments:
        raw = segment.speaker_id  # e.g. "Speaker 1" or None
        sid = None
        if raw:
            if raw not in speaker_id_for:
                r = await db.execute_write(
                    "insert into datasette_scribe_speakers"
                    " (transcription_id, name, is_configured) values (?, ?, 0)",
                    [transcription_id, raw],
                )
                speaker_id_for[raw] = r.lastrowid
            sid = speaker_id_for[raw]
        await db.execute_write(
            "insert into datasette_scribe_transcription_entries"
            " (transcription_id, start, end, speaker_id, text, original_text, original_speaker_id)"
            " values (?, ?, ?, ?, ?, ?, ?)",
            [
                transcription_id,
                segment.start,
                segment.end,
                sid,
                segment.text,
                segment.text,
                raw,
            ],
        )
