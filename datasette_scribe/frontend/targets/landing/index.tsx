import { h, render } from "preact";
import { useRef, useState } from "preact/hooks";
import { formatDuration } from "../../utils";
import "./index.css";
import { Signal, effect, signal, useSignalEffect } from "@preact/signals";
import { Api, ApiJobsResult, transcriptUrl, transcriptRawUrl } from "../../api";

let db: Signal<string>;

function Transcriptions() {
  const [data, setData] = useState<null | ApiJobsResult>(null);
  useSignalEffect(() => {
    Api.jobs(db.value).then((data) => setData(data));
  });
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
          {completed_jobs.length == 0 && <tr>No jobs!</tr>}
          {completed_jobs.map((d) => {
            const { total_entries, total_speakers } = JSON.parse(
              d.entries_info
            ) as { total_entries: number; total_speakers: number };
            return (
              <tr>
                <td>{d.submitted_at}</td>
                <td>
                  <a href={transcriptUrl(db.value, d.transcript_id)}>
                    {d.title}
                  </a>
                </td>
                <td>
                  <a
                    href={d.url}
                    class="outbound"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    link
                  </a>
                </td>
                <td>{formatDuration(d.duration)}</td>
                <td>
                  <a href={transcriptRawUrl(db.value, d.transcript_id)}>
                    Transcript
                  </a>{" "}
                  (
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

  function submit() {
    const urls = textarea.current.value.split("\n").filter((d) => d);
    Api.submitJobs(db.value, urls).then(() => {
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

function DatabaseToggle(props: { databases: string[] }) {
  return (
    <div>
      Database:
      <select
        onInput={(e: InputEvent) => {
          db.value = (e.target as HTMLSelectElement).value;
        }}
      >
        {props.databases.map((db) => (
          <option>{db}</option>
        ))}
      </select>
    </div>
  );
}
function Landing(props: { databases: string[] }) {
  return (
    <div>
      <DatabaseToggle databases={props.databases} />

      <div>
        <h1>Datasette Scribe</h1>
        <Transcriptions />
        <Submit />
      </div>
    </div>
  );
}
async function main() {
  const databases = await Api.databases();
  const initDb =
    new URL(window.location.href).searchParams.get("db") || databases[0];

  db = signal(initDb);

  effect(() => {
    const u = new URL(window.location.href);
    u.searchParams.delete("db");
    u.searchParams.append("db", db.value);
    history.replaceState({}, "Title", u);
  });
  render(<Landing databases={databases} />, document.querySelector("#root")!);
}

document.addEventListener("DOMContentLoaded", main);
