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
    usage text
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

create table if not exists datasette_scribe_speakers (
    id integer primary key,
    name text not null unique,
    is_original integer not null default 1
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
    created_at text not null default (datetime('now', 'subsec'))
);

create table if not exists datasette_scribe_collection_transcriptions (
    collection_id integer not null references datasette_scribe_collections(id) on delete cascade,
    transcription_id integer not null unique references datasette_scribe_transcriptions(id) on delete cascade,
    added_at text not null default (datetime('now', 'subsec')),
    primary key (collection_id, transcription_id)
);
