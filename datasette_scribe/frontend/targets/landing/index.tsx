import { createContext, h, render } from "preact";
import { useContext, useEffect, useRef, useState } from "preact/hooks";
import { formatDuration } from "../../utils";
import "./index.css";

const Database = createContext("");

interface ApiJobsData {
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
function Transcriptions() {
  const database = useContext(Database);
  const [data, setData] = useState<null | ApiJobsData>(null);
  useEffect(() => {
    fetch(`/-/datasette-scribe/api/jobs/${database}`)
      .then((r) => r.json())
      .then((data) => setData(data));
  }, []);
  if (!data) return <div>Loading...</div>;
  const { completed_jobs, inprogress_jobs } = data;
  return (
    <div>
      <table>
        <thead>
          <tr>
            <th>Submitted at</th>
            <th>Title</th>
            <th>Youtube Link</th>
            <th>Duration</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {completed_jobs.map((d) => {
            const transcriptUrl = `/${database}/datasette_scribe_transcription_entries?transcript_id=${d.transcript_id}`;
            const { total_entries, total_speakers } = JSON.parse(
              d.entries_info
            ) as { total_entries: number; total_speakers: number };
            return (
              <tr>
                <td>{d.submitted_at}</td>
                <td>
                  <a
                    href={`/-/datasette-scribe/transcripts/${database}/${d.transcript_id}`}
                  >
                    {d.title}
                  </a>
                </td>
                <td>
                  <a
                    href="${d.url}"
                    class="outbound"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    link
                  </a>
                </td>
                <td>{formatDuration(d.duration)}</td>
                <td>
                  <a href={transcriptUrl}>Transcript</a> (
                  {`${total_speakers} speaker${
                    total_speakers === 1 ? "" : "s"
                  }`}
                  )
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Submit() {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const database = useContext(Database);

  function submit() {
    const urls = textarea.current.value.split("\n").filter((d) => d);
    fetch("/-/datasette-scribe/api/submit", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        database,
        urls,
      }),
    })
      .then((r) => r.json())
      .then(() => {
        textarea.current.value = "";
      });
  }
  return (
    <div>
      <h2>Submit a new Scribe Job</h2>

      <p>
        Paste Youtube video URLs below to have them transcribed.
        <br />
        Separate multiple URLs on separate lines.{" "}
      </p>

      <textarea ref={textarea} rows={8} cols={50}></textarea>
      <br />
      <button onClick={submit}>Submit</button>
    </div>
  );
}

function DatabaseToggle(props: {
  databases: string[];
  onChange: (db: string) => void;
}) {
  return (
    <div>
      {" "}
      Database:
      <select>
        <option>{props.databases.map((db) => db)}</option>
      </select>
    </div>
  );
}
function Landing(props: { databases: string[] }) {
  const [db, setDb] = useState(props.databases[0]);
  return (
    <Database.Provider value={db}>
      <DatabaseToggle databases={props.databases} onChange={(d) => setDb(d)} />

      <div>
        <h1>Datasette Scribe</h1>

        <Transcriptions />

        <Submit />
      </div>
    </Database.Provider>
  );
}
async function main() {
  const databases = await fetch("/-/databases.json")
    .then((r) => r.json())
    .then((data) => data.map((d) => d.name));
  render(<Landing databases={databases} />, document.querySelector("#root")!);
}

document.addEventListener("DOMContentLoaded", main);
