import { h, render } from "preact";
import { useRef, useState } from "preact/hooks";
import { formatDuration } from "../../utils";
import "./index.css";
import {
  Signal,
  effect,
  signal,
  useSignal,
  useSignalEffect,
} from "@preact/signals";
import { Api, ApiJobsResult, transcriptUrl, transcriptRawUrl } from "../../api";
import {
  SlOption,
  SlSelect,
  SlDialog,
  SlInput,
  SlButton,
} from "../../components/shoelace";

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

function NewCollectionDialog(props: { open: Signal<boolean> }) {
  const { open } = props;
  const name = useSignal("");
  const description = useSignal("");
  const submitting = useSignal(false);

  function onSubmit() {
    submitting.value = true;
  }

  return (
    <SlDialog
      label="Create new Scribe Collection"
      open={open.value}
      onSlAfterHide={() => (open.value = false)}
    >
      <p>
        Collections are used to organized transcribed videos. A single video can
        be a part of multiple collections.
      </p>
      <div>
        <SlInput
          label="Name"
          type="text"
          value={name.value}
          onSlInput={(e) => (name.value = e.target.value)}
          disabled={submitting.value}
        />
        <br />
        <SlInput
          label="Description"
          type="text"
          value={description.value}
          onSlInput={(e) => (description.value = e.target.value)}
          disabled={submitting.value}
        />
        <br />
        <SlButton
          type="submit"
          variant="primary"
          onClick={onSubmit}
          loading={submitting.value}
        >
          Submit
        </SlButton>
      </div>
    </SlDialog>
  );
}
function Submit() {
  const open = useSignal(false);
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
      <NewCollectionDialog open={open} />
      <div style="width: 420px;">
        <SlSelect
          xlabel={"asdf"}
          value={["option-1", "option-2"]}
          multiple
          clearable
          onSlInput={(e) => console.log(e.target.value)}
        >
          <div slot="label">
            xxxx{" "}
            <button onClick={() => (open.value = true)}>
              Create new collection
            </button>
          </div>
          <SlOption value="option-1">Option 1</SlOption>
          <SlOption value="option-2">Option 2</SlOption>
          <SlOption value="option-3">Option 3</SlOption>
          <SlOption value="option-4">Option 4</SlOption>
          <SlOption value="option-5">Option 5</SlOption>
          <SlOption value="option-6">Option 6</SlOption>
        </SlSelect>
      </div>
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
