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
