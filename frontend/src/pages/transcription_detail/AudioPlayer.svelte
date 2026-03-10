<script lang="ts">
  import type { TranscriptionEntry } from "../../page_data/TranscriptionDetailPageData.types";
  import { formatTime, colorFor } from "./transcription-utils";

  let {
    playing,
    currentTime,
    duration,
    entries,
    speakerColorMap,
    filterSpeaker,
    onTogglePlay,
    onSeek,
  }: {
    playing: boolean;
    currentTime: number;
    duration: number;
    entries: TranscriptionEntry[];
    speakerColorMap: Record<string, string>;
    filterSpeaker: string | null;
    onTogglePlay: () => void;
    onSeek: (time: number) => void;
  } = $props();

  function segmentColor(entry: TranscriptionEntry): string {
    if (!filterSpeaker) return colorFor(entry, speakerColorMap);
    if (entry.speaker_id === filterSpeaker) return colorFor(entry, speakerColorMap);
    if (!entry.speaker_id) return "#ccc";
    return "#999";
  }

  let timelineEl: HTMLDivElement;
  let dragging = $state(false);

  function seekFromPointer(e: MouseEvent) {
    if (!duration || !timelineEl) return;
    const rect = timelineEl.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    onSeek(pct * duration);
  }

  function entryAtPointer(e: MouseEvent): TranscriptionEntry | undefined {
    if (!duration || !timelineEl) return;
    const rect = timelineEl.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    const time = pct * duration;
    return entries.find((entry) => time >= entry.start && time < entry.end);
  }

  function onTimelineDown(e: MouseEvent) {
    if (!duration) return;
    e.preventDefault();
    dragging = true;
    const startX = e.clientX;
    let didDrag = false;
    const clickedEntry = entryAtPointer(e);

    // Immediately seek to pointer position
    seekFromPointer(e);

    function onMove(e: MouseEvent) {
      if (!didDrag && Math.abs(e.clientX - startX) > 3) {
        didDrag = true;
      }
      if (didDrag) {
        seekFromPointer(e);
      }
    }
    function onUp() {
      dragging = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      // If it was a click (no drag) on a segment, jump to segment start
      if (!didDrag && clickedEntry) {
        onSeek(clickedEntry.start);
      }
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }
</script>

<div class="player">
  <button class="play-btn" onclick={onTogglePlay} aria-label={playing ? "Pause" : "Play"}>
    {#if playing}
      <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
        <rect x="6" y="4" width="4" height="16" rx="1" />
        <rect x="14" y="4" width="4" height="16" rx="1" />
      </svg>
    {:else}
      <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
        <polygon points="6,4 20,12 6,20" />
      </svg>
    {/if}
  </button>

  <span class="time-display">{formatTime(currentTime)}</span>

  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="timeline" class:dragging bind:this={timelineEl} onmousedown={onTimelineDown}>
    <div class="timeline-bg">
      {#if duration > 0}
        {#each entries as entry}
          <div
            class="timeline-segment"
            style="left: {(entry.start / duration) * 100}%; width: {((entry.end - entry.start) / duration) * 100}%; background: {segmentColor(entry)};"
            title="{entry.speaker_id ?? 'Speaker'}: {formatTime(entry.start)} - {formatTime(entry.end)}"
          ></div>
        {/each}
      {/if}
    </div>
    {#if duration > 0}
      <div
        class="playhead"
        style="left: {(currentTime / duration) * 100}%"
      ></div>
    {/if}
  </div>

  <span class="time-display">{formatTime(duration)}</span>
</div>

<style>
  .player {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: #f5f5f5;
    border-top: 1px solid #ddd;
    padding: 0.75rem 1rem;
  }

  .play-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    border: none;
    background: #333;
    color: #fff;
    cursor: pointer;
    flex-shrink: 0;
    transition: background 0.15s;
  }
  .play-btn:hover {
    background: #555;
  }

  .time-display {
    font-size: 0.8rem;
    font-variant-numeric: tabular-nums;
    color: #555;
    min-width: 3.2em;
    flex-shrink: 0;
  }

  .timeline {
    flex: 1;
    height: 28px;
    position: relative;
    cursor: grab;
    border-radius: 6px;
    overflow: visible;
  }
  .timeline.dragging {
    cursor: grabbing;
  }

  .timeline-bg {
    position: absolute;
    inset: 0;
    background: #ddd;
    border-radius: 6px;
    overflow: hidden;
  }

  .timeline-segment {
    position: absolute;
    top: 0;
    height: 100%;
    opacity: 0.85;
    transition: opacity 0.1s;
  }
  .timeline-segment:hover {
    opacity: 1;
  }

  .playhead {
    position: absolute;
    top: -4px;
    width: 3px;
    height: calc(100% + 8px);
    background: #111;
    border-radius: 2px;
    transform: translateX(-1px);
    pointer-events: none;
    z-index: 2;
  }
</style>
