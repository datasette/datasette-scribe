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


async def _free_name(db, col: str, ref: int, base: str) -> str:
    """First name in scope (``col`` = ``ref``) not already taken, suffixing
    ``base``, ``base (2)``, ``base (3)`` … so a copy never collides with the
    scope's ``unique(scope, name)`` index."""
    name, n = base, 2
    while (
        await db.execute(
            f"select 1 from datasette_scribe_speakers where {col} = ? and name = ?",
            [ref, name],
        )
    ).first():
        name, n = f"{base} ({n})", n + 1
    return name


async def copy_and_rescope(datasette, database, tid, *, new_collection_id) -> int:
    """Move transcript ``tid`` to ``new_collection_id`` (None = standalone),
    carrying its speakers along.

    The single primitive behind all three transitions (standalone↔collection,
    collection→collection). For every speaker the transcript's entries reference,
    a fresh speaker is created in the destination scope — copying name (suffixed
    if that name is taken; we never auto-merge), description, configured state,
    and photo — and the entries are repointed to it, so the transcript keeps all
    its assignments. Source speakers that were *transcript*-scoped (exclusively
    this transcript's) are then deleted; *collection*-scoped source speakers are
    left intact for the sibling members that remain. Membership is rewritten.

    ACL transition is the caller's job because policy differs by direction.
    Returns the number of speakers carried over.
    """
    db = datasette.get_database(database)

    # Source scope, read before membership changes. A standalone source owns its
    # speakers exclusively (safe to delete after copying); a collection source
    # shares them with siblings (must not delete).
    src = (
        await db.execute(
            "select collection_id from datasette_scribe_collection_transcriptions"
            " where transcription_id = ?",
            [tid],
        )
    ).first()
    src_is_transcript = src is None

    dest_col = "collection_id" if new_collection_id is not None else "transcription_id"
    dest_ref = new_collection_id if new_collection_id is not None else tid

    # Speakers this transcript actually uses (one row per distinct speaker).
    referenced = (
        await db.execute(
            "select distinct s.id, s.name, s.description, s.is_configured,"
            " s.configured_at"
            " from datasette_scribe_transcription_entries e"
            " join datasette_scribe_speakers s on s.id = e.speaker_id"
            " where e.transcription_id = ? and e.speaker_id is not null",
            [tid],
        )
    ).rows

    for sp in referenced:
        name = await _free_name(db, dest_col, dest_ref, sp["name"])
        r = await db.execute_write(
            f"insert into datasette_scribe_speakers"
            f" ({dest_col}, name, description, is_configured, configured_at)"
            f" values (?, ?, ?, ?, ?)",
            [
                dest_ref,
                name,
                sp["description"],
                sp["is_configured"],
                sp["configured_at"],
            ],
        )
        dest_id = r.lastrowid
        # Carry the photo if the source speaker had one (FK enforcement is off,
        # so this is explicit). No-op when the source has no photo row.
        await db.execute_write(
            "insert into datasette_scribe_speaker_photos (speaker_id, data, content_type)"
            " select ?, data, content_type from datasette_scribe_speaker_photos"
            " where speaker_id = ?",
            [dest_id, sp["id"]],
        )
        # Repoint this transcript's entries onto the copy.
        await db.execute_write(
            "update datasette_scribe_transcription_entries set speaker_id = ?"
            " where transcription_id = ? and speaker_id = ?",
            [dest_id, tid, sp["id"]],
        )

    # Delete the source speakers only when they were transcript-scoped — those
    # are now orphaned and unreachable. Collection-scoped speakers belong to the
    # collection and may still serve sibling transcripts, so leave them be.
    if src_is_transcript:
        await db.execute_write(
            "delete from datasette_scribe_speaker_photos where speaker_id in"
            " (select id from datasette_scribe_speakers where transcription_id = ?)",
            [tid],
        )
        await db.execute_write(
            "delete from datasette_scribe_speakers where transcription_id = ?",
            [tid],
        )

    # Update membership.
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

    return len(referenced)


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
