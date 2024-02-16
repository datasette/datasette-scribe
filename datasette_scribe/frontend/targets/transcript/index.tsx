import { createContext, h, render } from "preact";
import { useContext, useEffect, useRef, useState } from "preact/hooks";
import { formatDuration } from "../../utils";
import "./index.css";

interface Entry {
  started_at: number;
  ended_at: number;
  speaker: string;
  contents: string;
}
interface TranscriptData {
  entries: Entry[];
  transcript: {
    duration: number;
    id: string;
    job_id: string;
    title: string;
    url: string;
  };
}
function Transcript(props: { data: TranscriptData }) {
  return (
    <div>
      {props.data.entries.map((entry) => (
        <div className="entry">
          <div>{formatDuration(entry.started_at)}</div>
          <div>{entry.speaker}</div>
          <div>{entry.contents}</div>
        </div>
      ))}
    </div>
  );
}
async function main() {
  const CONFIG = JSON.parse(
    document.querySelector("#DATASETTE_SCRIBE_TRANSCRIPT")!.textContent
  );
  const { database, transcript_id } = CONFIG;

  render(<div>Loading...</div>, document.querySelector("#root")!);

  const data = await fetch(
    `/-/datasette-scribe/api/transcripts/${database}/${transcript_id}`
  ).then((r) => r.json());

  render(<Transcript data={data} />, document.querySelector("#root")!);
}

document.addEventListener("DOMContentLoaded", main);
