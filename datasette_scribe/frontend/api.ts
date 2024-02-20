async function api(path: string, params?: { method: string; data: any }) {
  const { method, data } = params ?? {};
  // TODO base_url
  return fetch(`${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: data ? JSON.stringify(data) : undefined,
  }).then((response) => response.json());
}

export interface ApiJobsResult {
  completed_jobs: {
    id: string;
    transcript_id: string;
    url: string;
    submitted_at: string;
    completed_at: string;
    title: string;
    duration: number;
    entries_info: string;
  }[];
  inprogress_jobs: {}[];
}

export interface Entry {
  started_at: number;
  ended_at: number;
  speaker: string;
  contents: string;
}
export interface TranscriptMeta {
  duration: number;
  id: string;
  job_id: string;
  title: string;
  url: string;
}
export interface TranscriptResult {
  entries: Entry[];
  transcript: TranscriptMeta;
}

export class Api {
  static async jobs(db: string): Promise<ApiJobsResult> {
    return api(`/-/datasette-scribe/api/jobs/${db}`);
  }

  static async submitJobs(database: string, urls: string[]) {
    return api("/-/datasette-scribe/api/submit", {
      method: "POST",
      data: JSON.stringify({
        database,
        urls,
      }),
    });
  }

  static async transcript(
    database: string,
    transcript_id: string
  ): Promise<TranscriptResult> {
    return api(
      `/-/datasette-scribe/api/transcripts/${database}/${transcript_id}`
    );
  }

  static async databases(): Promise<string[]> {
    return api(`/-/databases.json`).then((data) => data.map((d) => d.name));
  }
}

// TODO base_url
export function transcriptRawUrl(db: string, transcript_id: string) {
  return `/${db}/datasette_scribe_transcription_entries?transcript_id=${transcript_id}`;
}
export function transcriptUrl(db: string, transcript_id: string) {
  return `/-/datasette-scribe/transcripts/${db}/${transcript_id}`;
}
