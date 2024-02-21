create table if not exists datasette_scribe_submitted_jobs(
  --!

  id text primary key,

  --- Datasette actor ID of the user who submitted this job
  submitter_actor_id text,
  --- Timestamp of when job was submit
  submitted_at datetime,
  --- Timestamp of when job was marked 'complete' or 'failed'
  completed_at datetime,
  --- URL of video to download + scribe
  url text,
  -- 'pending' | 'completed', 'failed'
  status text
);
create index if not exists idx_datasette_scribe_submitted_jobs_status
  on datasette_scribe_submitted_jobs(status);

create table if not exists datasette_scribe_transcripts(
  id text primary key,
  job_id text references datasette_scribe_submitted_jobs(id),
  url text,
  title text,
  duration float,
  meta json
);

create table if not exists datasette_scribe_transcription_entries(
  transcript_id text references datasette_scribe_transcripts(id),
  speaker text,
  started_at float,
  ended_at float,
  contents text
);

create table if not exists datasette_scribe_collections(
  key text primary key,
  name text,
  description text
);


create table if not exists datasette_scribe_collection_members(
  collection_id text references datasette_scribe_collections(key),
  transcript_id text references datasette_scribe_transcripts(id),
  unique (collection_id, transcript_id)
);

create index if not exists idx_datasette_scribe_collection_members_collection_id
  on datasette_scribe_collection_members(collection_id);

create index if not exists idx_datasette_scribe_collection_members_transcript_id
  on datasette_scribe_collection_members(transcript_id);

create virtual table if not exists datasette_scribe_transcription_entries_fts using fts5(
  contents,
  transcript_id unindexed
);

CREATE TRIGGER if not exists ds_scribe_entry_after_insert AFTER INSERT ON datasette_scribe_transcription_entries BEGIN
  INSERT INTO datasette_scribe_transcription_entries_fts(rowid, contents, transcript_id)
    VALUES (new.rowid, new.contents, new.transcript_id);
END;
CREATE TRIGGER if not exists ds_scribe_entry_after_delete AFTER DELETE ON datasette_scribe_transcription_entries BEGIN
  DELETE FROM datasette_scribe_transcription_entries_fts WHERE rowid = old.rowid;
END;
CREATE TRIGGER if not exists ds_scribe_entry_after_update AFTER UPDATE ON datasette_scribe_transcription_entries BEGIN
  DELETE FROM datasette_scribe_transcription_entries_fts WHERE rowid = old.rowid;
  INSERT INTO datasette_scribe_transcription_entries_fts(rowid, contents, transcript_id)
    VALUES (new.rowid, new.contents, new.transcript_id);
END;
