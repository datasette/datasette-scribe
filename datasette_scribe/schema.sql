create table if not exists datasette_scribe_transcriptions (
    id integer primary key,
    url text,
    input_type text not null default 'url',
    filename text,
    model text not null,
    granularity text not null,
    submitted_at text not null,
    completed_at text,
    error text,
    usage text,
    -- actor["id"] of the creator, set on authenticated web creates. NULL for
    -- anonymous web creates and CLI (add / import-json) creates. Ownership +
    -- private-by-default sharing key off this (see permissions.py): a non-NULL
    -- created_by gets a seeded acl Manager grant; NULL transcriptions fall back
    -- to the global datasette_scribe_scribe permission.
    created_by text
);

-- TODO: Remove audio_blobs table when S3 storage is implemented
create table if not exists datasette_scribe_audio_blobs (
    id integer primary key,
    transcription_id integer not null unique references datasette_scribe_transcriptions(id),
    data blob not null,
    content_type text not null
);

create table if not exists datasette_scribe_transcription_entries (
    id integer primary key,
    transcription_id integer not null references datasette_scribe_transcriptions(id),
    start real not null,
    end real not null,
    speaker_id text,
    text text not null,
    original_text text,
    original_speaker_id text
);

create table if not exists datasette_scribe_transcription_edits (
    id integer primary key,
    transcription_id integer references datasette_scribe_transcriptions(id),
    entry_id integer references datasette_scribe_transcription_entries(id),
    operation text not null,
    detail text not null,
    created_at text not null
);

create table if not exists datasette_scribe_collections (
    id integer primary key,
    name text not null unique,
    description text not null default '',
    created_at text not null default (datetime('now', 'subsec')),
    created_by text
);

create table if not exists datasette_scribe_collection_transcriptions (
    collection_id integer not null references datasette_scribe_collections(id) on delete cascade,
    transcription_id integer not null unique references datasette_scribe_transcriptions(id) on delete cascade,
    added_at text not null default (datetime('now', 'subsec')),
    primary key (collection_id, transcription_id)
);

create table if not exists datasette_scribe_speakers (
    id integer primary key,
    collection_id    integer references datasette_scribe_collections(id) on delete cascade,
    transcription_id integer references datasette_scribe_transcriptions(id) on delete cascade,
    name text not null,
    description text not null default '',
    is_configured integer not null default 0,   -- replaces is_original
    configured_at text,
    check ((collection_id is null) <> (transcription_id is null))
);
create unique index if not exists scribe_speaker_collection_name
    on datasette_scribe_speakers(collection_id, name) where collection_id is not null;
create unique index if not exists scribe_speaker_transcription_name
    on datasette_scribe_speakers(transcription_id, name) where transcription_id is not null;

create table if not exists datasette_scribe_speaker_photos (
    speaker_id integer primary key references datasette_scribe_speakers(id) on delete cascade,
    data blob not null,
    content_type text not null
);
