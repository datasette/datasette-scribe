import { Ref, createContext, h, render } from "preact";
import { useContext, useEffect, useMemo, useRef, useState } from "preact/hooks";
import { formatDuration } from "../../utils";
import "./index.css";
import { YoutubeVideo } from "../../components/Youtube";
import { Signal, signal } from "@preact/signals";
import {
  Api,
  Entry,
  TranscriptMeta,
  TranscriptResult,
  transcriptRawUrl,
} from "../../api";
import * as Plot from "@observablehq/plot";

function usePlot(def: () => HTMLElement | SVGElement): Ref<HTMLDivElement> {
  const target = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!target.current) return;
    const plot = def();
    target.current.appendChild(plot);
    return () => target.current.removeChild(plot);
  }, []);
  return target;
}

function PlotSpeakerStats() {
  const { entries } = useContext(AppState);
  const target = usePlot(() => {
    const data = entries.map((d) => ({
      ...d,
      duration: d.ended_at - d.started_at,
    }));
    return Plot.plot({
      marginLeft: 100,
      grid: true,
      x: {
        tickFormat: formatDuration,
      },
      marks: [
        Plot.barX(
          data,
          Plot.groupY(
            { x: "sum" },
            { x: "duration", y: "speaker", tip: true, sort: { y: "-x" } }
          )
        ),

        Plot.ruleX([0]),
      ],
    });
  });

  return <div ref={target} />;
}

function PlotWaterfall() {
  const { entries } = useContext(AppState);
  const target = usePlot(() => {
    return Plot.plot({
      //width: 400,
      height: 800,
      marginLeft: 100,
      x: {
        tickFormat: (d) => formatDuration(d),
        axis: "top",
      },
      y: {
        grid: true,
      },
      marks: [
        Plot.barX(entries, {
          x1: "started_at",
          x2: "ended_at",
          y: "speaker",
          //height: 20,
          sort: { y: "x2" },
        }),
      ],
    });
  });
  return <div ref={target} />;
}

function TranscriptVideo(props: { url: string }) {
  const { seek } = useContext(AppState);
  const videoId = useMemo(
    () => new URL(props.url).searchParams.get("v"),
    [props.url]
  );
  function onStateChange(e, currentTime) {
    seek.value = currentTime;
  }
  return (
    <div>
      <YoutubeVideo id={videoId} onStateChange={onStateChange} seek={seek} />
    </div>
  );
}

function Entries() {
  const { entries, seek } = useContext(AppState);
  return (
    <div className="entries">
      {entries.map((entry, i, a) => (
        <div className="entry">
          <div
            className="entry-started"
            onClick={() => {
              seek.value = entry.started_at;
            }}
          >
            {formatDuration(entry.started_at)}
          </div>
          <div className="entry-speaker">
            {a[i - 1]?.speaker === entry.speaker ? "" : entry.speaker}
          </div>
          <div
            className="entry-contents"
            style={{
              color:
                seek.value >= entry.started_at && seek.value <= entry.ended_at
                  ? "red"
                  : "blue",
            }}
          >
            {entry.contents}
          </div>
        </div>
      ))}
    </div>
  );
}
function Transcript() {
  const { database, transcript } = useContext(AppState);
  return (
    <div>
      <h1>{transcript.title}</h1>
      <p>
        {transcript.url}
        {formatDuration(transcript.duration)}

        <a href={transcriptRawUrl(database, transcript.id)}>
          View transcript data
        </a>
      </p>
      <div style="display: flex; justify-content: space-between;">
        <div>
          <PlotSpeakerStats />
          <PlotWaterfall />
        </div>
        <div>
          <div>
            <TranscriptVideo url={transcript.url} />
          </div>
          <Entries />
        </div>
      </div>
    </div>
  );
}

interface State {
  seek: Signal<number>;
  entries: Entry[];
  transcript: TranscriptMeta;
  database: string;
}
const AppState = createContext<State>(null);

async function main() {
  const { database, transcript_id } = JSON.parse(
    document.querySelector("#DATASETTE_SCRIBE_TRANSCRIPT")!.textContent
  ) as { database: string; transcript_id: string };

  render(<div>Loading...</div>, document.querySelector("#root")!);

  const { entries, transcript } = await Api.transcript(database, transcript_id);
  render(
    <AppState.Provider
      value={{ database, entries, transcript, seek: signal(0) }}
    >
      <Transcript />
    </AppState.Provider>,
    document.querySelector("#root")!
  );
}

document.addEventListener("DOMContentLoaded", main);
