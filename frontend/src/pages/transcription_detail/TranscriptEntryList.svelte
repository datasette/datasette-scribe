<script lang="ts">
  import type { TranscriptionEntry } from "../../page_data/TranscriptionDetailPageData.types";
  import { formatTime, colorFor, isEntryEdited } from "./transcription-utils";

  let {
    entries,
    displayedEntries,
    filterSpeaker,
    allSpeakerNames,
    speakerColorMap,
    activeIndex,
    showOriginal,
    onClearFilter,
    onEntryClick,
    onSaveEntry,
    onSpeakerSelectChange,
  }: {
    entries: TranscriptionEntry[];
    displayedEntries: TranscriptionEntry[];
    filterSpeaker: string | null;
    allSpeakerNames: string[];
    speakerColorMap: Record<string, string>;
    activeIndex: number;
    showOriginal: boolean;
    onClearFilter: () => void;
    onEntryClick: (entry: TranscriptionEntry) => void;
    onSaveEntry: (entryId: number, newText: string) => Promise<boolean>;
    onSpeakerSelectChange: (e: Event, entry: TranscriptionEntry) => void;
  } = $props();

  // Internal state
  let editingEntryId: number | null = $state(null);
  let editText = $state("");
  let savingEntry = $state(false);
  let entryEls: HTMLElement[] = $state([]);

  // Auto-scroll active entry into view
  $effect(() => {
    if (activeIndex >= 0 && entryEls[activeIndex]) {
      entryEls[activeIndex]!.scrollIntoView({
        block: "nearest",
        behavior: "smooth",
      });
    }
  });

  function startEditing(entry: TranscriptionEntry) {
    editingEntryId = entry.id;
    editText = entry.text;
  }

  function cancelEditing() {
    editingEntryId = null;
    editText = "";
  }

  async function saveEntryText(entry: TranscriptionEntry) {
    if (editText === entry.text) {
      cancelEditing();
      return;
    }
    savingEntry = true;
    await onSaveEntry(entry.id, editText);
    savingEntry = false;
    cancelEditing();
  }
</script>

<div class="content">
  {#if filterSpeaker}
    <div class="filter-bar">
      Showing entries for <strong>{filterSpeaker}</strong>
      <button class="btn-small" onclick={onClearFilter}>Show all</button>
    </div>
  {/if}
  <div class="entries">
    {#each displayedEntries as entry, i}
      {@const isContinuation = i > 0 && displayedEntries[i - 1]!.speaker_id === entry.speaker_id}
      {@const prevEntry = i > 0 ? displayedEntries[i - 1] : null}
      {@const hasGap = filterSpeaker && prevEntry && entries.indexOf(entry) - entries.indexOf(prevEntry) > 1}
      {#if hasGap}
        <div class="ellipsis-row">&hellip;</div>
      {/if}
      <div
        class="entry"
        class:active={i === activeIndex}
        class:continuation={isContinuation}
        bind:this={entryEls[i]}
        style="--speaker-color: {colorFor(entry, speakerColorMap)}"
      >
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <span class="entry-time" class:entry-time-sub={isContinuation} onclick={() => onEntryClick(entry)}>{formatTime(entry.start)}</span>
        <div class="entry-speaker-col">
          <select
            class="entry-speaker-select"
            class:entry-speaker-hidden={isContinuation}
            value={entry.speaker_id ?? ""}
            onchange={(e) => onSpeakerSelectChange(e, entry)}
          >
            <option value="">No speaker</option>
            {#each allSpeakerNames as name}
              <option value={name}>{name}</option>
            {/each}
            <option value="__new__">New speaker...</option>
          </select>
        </div>
        <div class="entry-content">
          {#if editingEntryId === entry.id}
            <textarea
              class="edit-textarea"
              bind:value={editText}
              onkeydown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) saveEntryText(entry);
                if (e.key === "Escape") cancelEditing();
              }}
            ></textarea>
            <div class="edit-actions">
              <button class="btn-small btn-primary" onclick={() => saveEntryText(entry)} disabled={savingEntry}>
                {savingEntry ? "Saving..." : "Save"}
              </button>
              <button class="btn-small" onclick={cancelEditing}>Cancel</button>
            </div>
          {:else}
            <!-- svelte-ignore a11y_click_events_have_key_events -->
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <div class="entry-text" onclick={() => onEntryClick(entry)}>
              {entry.text}
              {#if isEntryEdited(entry)}
                <span class="edited-badge" title="Edited">edited</span>
              {/if}
            </div>
            <button class="edit-btn" onclick={() => startEditing(entry)} title="Edit text">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </button>
            {#if showOriginal && isEntryEdited(entry)}
              <div class="original-text">
                {#if entry.original_text != null && entry.text !== entry.original_text}
                  <div class="original-line"><span class="original-label">Original text:</span> {entry.original_text}</div>
                {/if}
                {#if entry.original_speaker_id !== undefined && entry.speaker_id !== entry.original_speaker_id}
                  <div class="original-line"><span class="original-label">Original speaker:</span> {entry.original_speaker_id ?? "none"}</div>
                {/if}
              </div>
            {/if}
          {/if}
        </div>
      </div>
    {/each}
  </div>
</div>

<style>
  .ellipsis-row {
    text-align: center;
    color: #aaa;
    font-size: 1.2rem;
    letter-spacing: 0.2em;
    padding: 0.2rem 0;
  }

  .filter-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    background: #e8f4fd;
    border-radius: 4px;
    font-size: 0.85rem;
    color: #333;
    margin-bottom: 0.5rem;
    flex-shrink: 0;
  }

  .content {
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    scroll-behavior: smooth;
  }

  .entries {
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  .entry {
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    padding: 0.35rem 0.75rem;
    border-left: 3px solid var(--speaker-color);
    border-radius: 4px;
    transition:
      background 0.15s,
      border-color 0.15s;
  }
  .entry:not(.continuation) {
    margin-top: 0.6rem;
  }
  .entry:first-child {
    margin-top: 0;
  }
  .entry:hover {
    background: #f5f5f5;
  }
  .entry.active {
    background: color-mix(in srgb, var(--speaker-color) 12%, white);
    border-left-width: 4px;
  }

  .entry-time {
    font-size: 0.85rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: #333;
    cursor: pointer;
    min-width: 3rem;
    flex-shrink: 0;
  }
  .entry-time:hover {
    color: #000;
  }
  .entry-time-sub {
    font-weight: 400;
    color: #bbb;
  }
  .entry-time-sub:hover {
    color: #666;
  }

  .entry-speaker-col {
    width: 7rem;
    flex-shrink: 0;
  }

  .entry-speaker-select {
    font-size: 0.85rem;
    font-weight: 600;
    font-style: italic;
    color: var(--speaker-color);
    border: 1px solid transparent;
    background: transparent;
    padding: 0.1rem 0.2rem;
    border-radius: 3px;
    cursor: pointer;
    max-width: 100%;
  }
  .entry-speaker-select:hover,
  .entry-speaker-select:focus {
    border-color: #ccc;
    background: white;
  }

  .entry-speaker-hidden {
    visibility: hidden;
    pointer-events: none;
  }
  .entry:hover .entry-speaker-hidden {
    visibility: visible;
    pointer-events: auto;
  }

  .entry-content {
    flex: 1;
    position: relative;
    min-width: 0;
  }

  .entry-text {
    line-height: 1.5;
    font-size: 0.95rem;
    cursor: pointer;
  }

  .edited-badge {
    font-size: 0.65rem;
    color: #999;
    font-style: italic;
    margin-left: 0.3rem;
    vertical-align: super;
  }

  .edit-btn {
    position: absolute;
    top: 0;
    right: 0;
    background: none;
    border: none;
    color: #bbb;
    cursor: pointer;
    padding: 0.2rem;
    border-radius: 3px;
    opacity: 0;
    transition: opacity 0.15s;
  }
  .entry:hover .edit-btn {
    opacity: 1;
  }
  .edit-btn:hover {
    color: #555;
    background: #eee;
  }

  .edit-textarea {
    width: 100%;
    min-height: 3rem;
    padding: 0.4rem;
    font-size: 0.95rem;
    line-height: 1.5;
    border: 1px solid #4a90d9;
    border-radius: 4px;
    resize: vertical;
    font-family: inherit;
  }

  .edit-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 0.3rem;
  }

  .original-text {
    margin-top: 0.3rem;
    padding: 0.3rem 0.5rem;
    background: #f9f9f9;
    border-radius: 4px;
    border-left: 2px solid #ddd;
  }

  .original-line {
    font-size: 0.8rem;
    color: #999;
    line-height: 1.4;
  }

  .original-label {
    font-weight: 600;
    color: #888;
  }

  .btn-small {
    font-size: 0.75rem;
    padding: 0.15rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    cursor: pointer;
  }
  .btn-small:hover {
    background: #f5f5f5;
  }
  .btn-small:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-primary {
    background: #4a90d9;
    color: white;
    border-color: #4a90d9;
  }
  .btn-primary:hover {
    background: #3a7bc8;
  }
</style>
