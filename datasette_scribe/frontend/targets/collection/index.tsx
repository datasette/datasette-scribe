import { createContext, h, render } from "preact";
import { useSignal, useSignalEffect } from "@preact/signals";
import {
  Api,
  CollectionItem,
  CollectionResult,
  CollectionSearchResultItem,
  apiReducer,
  State,
  Action,
  transcriptUrl,
} from "../../api";
import {
  SlBreadcrumb,
  SlBreadcrumbItem,
  SlIcon,
  SlInput,
  SlSpinner,
} from "../../components/shoelace";
import { useContext, useReducer } from "preact/hooks";
import { formatDuration } from "../../utils";

function SearchResultsTable(props: { results: CollectionSearchResultItem[] }) {
  const { database } = useContext(AppState);

  return (
    <table>
      <thead>
        <tr>
          <th>Video</th>
          <th>Speaker</th>
          <th>Timestamp</th>
          <th>Match</th>
        </tr>
      </thead>
      <tbody>
        {props.results.map((d) => (
          <tr>
            <td>
              <a href={transcriptUrl(database, d.transcript_id)}>
                {d.video_title}
              </a>
            </td>
            <td>{d.speaker}</td>
            <td>{formatDuration(d.started_at)}</td>
            <td>
              <span
                dangerouslySetInnerHTML={{ __html: d.highlighted_contents }}
              ></span>
            </td>
            <td>
              <a
                style="whitespace: nowrap;"
                href={`${d.video_url}&t=${Math.floor(d.started_at)}`}
              >
                Youtube link
              </a>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
function SearchSection() {
  const { collection, database } = useContext(AppState);

  const query = useSignal(
    new URL(window.location.href).searchParams.get("q") || ""
  );
  const results = useSignal<null | CollectionSearchResultItem[]>(null);
  const [x, dispatch] = useReducer<
    State<CollectionSearchResultItem[], string>,
    Action<CollectionSearchResultItem[], string>
  >(apiReducer, { loading: false, data: [] });

  useSignalEffect(() => {
    if (!query.value.trim().length) return;

    function search(query: string) {
      Api.collectionSearch({
        database,
        collection_id: collection.key,
        query: query,
      })
        .then((data) => {
          results.value = data.results;
          dispatch({ type: "success", data: data.results });
          const u = new URL(window.location.href);
          u.searchParams.delete("q");
          u.searchParams.append("q", query);
          history.replaceState({}, "", u);
        })
        .catch((error) => {
          dispatch({ type: "failure", error: "TODO" });
        });
    }
    const id = setTimeout(search, 250, query.value);
    dispatch({ type: "init" });
    return () => {
      clearTimeout(id);
    };
  });
  let content;
  if (x.loading) {
    content = <SlSpinner size="large" />;
  } else if (x.error) {
    content = <div>err</div>;
  } else {
    content = (
      <div>
        {query.value && !x.data.length && <div>No results :(</div>}
        <SearchResultsTable results={x.data} />
      </div>
    );
  }

  return (
    <div>
      <div style="max-width: 640px; margin: 0 auto;">
        <SlInput
          placeholder={`Search all transcripts in ${collection.name}...`}
          value={query.value}
          onSlInput={(e) => (query.value = e.target.value)}
        >
          <SlIcon name="search" slot="prefix"></SlIcon>
        </SlInput>
      </div>
      {content}
    </div>
  );
}

interface AState {
  database: string;
  collection: CollectionItem;
  //transcripts:
}

const AppState = createContext<AState>(null);

async function main() {
  const { database, collection_id } = JSON.parse(
    document.querySelector("#DATASETTE_SCRIBE_COLLECTION")!.textContent
  ) as { database: string; collection_id: string };

  render(<div>Loading...</div>, document.querySelector("#root")!);

  const { collection, transcripts } = await Api.collection(
    database,
    collection_id
  );
  render(
    <AppState.Provider value={{ database, collection }}>
      <div>
        <SlBreadcrumb>
          <SlBreadcrumbItem
            href={`/-/datasette-scribe?db=${encodeURIComponent(database)}`}
          >
            <SlIcon slot="prefix" name="vector-pen" />
            Scribe
          </SlBreadcrumbItem>
          <SlBreadcrumbItem>collections</SlBreadcrumbItem>
          <SlBreadcrumbItem>{collection.name}</SlBreadcrumbItem>
        </SlBreadcrumb>

        <h1>{collection.name}</h1>
        <p>{collection.description}</p>

        <h2>Search</h2>
        <SearchSection />
        <div>
          <h2>Transcripts</h2>
          {transcripts.map((t) => (
            <div>{t.title}</div>
          ))}
        </div>
      </div>
    </AppState.Provider>,
    document.querySelector("#root")!
  );
}

document.addEventListener("DOMContentLoaded", main);
