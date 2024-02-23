async function api(path: string, params?: { method: string; data: any }) {
  const { method, data } = params ?? {};
  // TODO base_url
  console.debug(`${method ?? "GET"} ${path}`);
  return fetch(`${path}`, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: data ? JSON.stringify(data) : undefined,
  }).then((response) => {
    if (!response.ok)
      return response.json().then((d) => {
        throw Error(d.message);
      });
    return response.json();
  });
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
    collections: { collection_id: string; name: string }[];
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
  collections: { collection_id: string; name: string }[];
}
export interface TranscriptResult {
  entries: Entry[];
  transcript: TranscriptMeta;
}

export interface CollectionItem {
  key: string;
  name: string;
  description: string;
}
export interface CollectionResult {
  collection: CollectionItem;

  transcripts: {
    id: string;
    title: string;
  }[];
}

export interface Collection {
  key: string;
  name: string;
}

export interface CollectionSearchResultItem {
  transcript_id: string;
  video_title: string;
  video_url: string;
  speaker: string;
  started_at: number;
  contents: string;
  highlighted_contents: string;
}
export interface CollectionSearchResult {
  results: CollectionSearchResultItem[];
}

export class Api {
  static async jobs(db: string): Promise<ApiJobsResult> {
    return api(`/-/datasette-scribe/api/jobs/${db}`);
  }

  static async submitJobs(database: string, urls: string[]) {
    return api("/-/datasette-scribe/api/submit", {
      method: "POST",
      data: {
        database,
        urls,
      },
    });
  }
  static async collectionNew(
    database: string,
    name: string,
    description: string
  ) {
    return api("/-/datasette-scribe/api/collection/new", {
      method: "POST",
      data: {
        database,
        name,
        description,
      },
    });
  }
  static async collectionAddVideo(params: {
    database: string;
    transcript_id: string;
    collection_id: string;
  }) {
    return api("/-/datasette-scribe/api/collection/add_video", {
      method: "POST",
      data: {
        ...params,
      },
    });
  }
  static async collectionRemoveVideo(params: {
    database: string;
    transcript_id: string;
    collection_id: string;
  }) {
    return api("/-/datasette-scribe/api/collection/remove_video", {
      method: "POST",
      data: {
        ...params,
      },
    });
  }
  static async collectionSearch(params: {
    database: string;
    collection_id: string;
    query: string;
  }): Promise<CollectionSearchResult> {
    return api("/-/datasette-scribe/api/collection/search", {
      method: "POST",
      data: {
        ...params,
      },
    });
  }

  static async collections(database: string): Promise<Collection[]> {
    return api(`/-/datasette-scribe/api/collections/${database}`);
  }

  static async transcript(
    database: string,
    transcript_id: string
  ): Promise<TranscriptResult> {
    return api(
      `/-/datasette-scribe/api/transcripts/${database}/${transcript_id}`
    );
  }
  static async collection(
    database: string,
    collection_id: string
  ): Promise<CollectionResult> {
    return api(
      `/-/datasette-scribe/api/collection/${database}/${collection_id}`
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

export interface State<T, E> {
  loading: boolean;
  data?: T;
  error?: E;
}
export type Action<T, E> =
  | { type: "init" }
  | { type: "success"; data: T }
  | { type: "failure"; error: E };

export function apiReducer<
  T,
  E,
  TState extends State<T, E>,
  TAction extends Action<T, E>
>(state: TState, action: TAction): TState {
  switch (action.type) {
    case "init":
      return {
        ...state,
        loading: true,
      };
    case "failure":
      return { ...state, loading: false, error: action.error };
    case "success":
      return {
        ...state,
        loading: false,
        data: action.data,
      };
  }
}
