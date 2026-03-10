<script lang="ts">
  import createClient from "openapi-fetch";
  import type { paths } from "../../../api.d.ts";
  import DatabaseSelector from "../../components/DatabaseSelector.svelte";
  import { loadPageData } from "../../page_data/load";
  import type {
    TranscriptionDetailPageData,
    TranscriptionEntry,
    TranscriptionSpeaker,
    TranscriptionEdit,
    CollectionSummary,
  } from "../../page_data/TranscriptionDetailPageData.types";
  import { appState } from "../../store.svelte";
  import { SPEAKER_COLORS, formatTimestamp, parseUTC } from "./transcription-utils";
  import AudioPlayer from "./AudioPlayer.svelte";
  import SpeakerSidebar from "./SpeakerSidebar.svelte";
  import TranscriptEntryList from "./TranscriptEntryList.svelte";

  const client = createClient<paths>({ baseUrl: "/" });

  const pageData = loadPageData<TranscriptionDetailPageData>();
  const t = pageData.transcription;
  const audioUrl = pageData.audio_url;
  let collection: CollectionSummary | null | undefined = $state(pageData.collection);
  const allCollections = pageData.all_collections ?? [];
  let entries: TranscriptionEntry[] = $state([...(pageData.entries ?? [])]);
  let speakers: TranscriptionSpeaker[] = $state([
    ...(pageData.speakers ?? []),
  ]);
  let allSpeakers: TranscriptionSpeaker[] = $state([
    ...(pageData.all_speakers ?? []),
  ]);
  let edits: TranscriptionEdit[] = $state([...(pageData.edits ?? [])]);

  // Derive speaker color map from current speakers list
  let speakerColorMap = $derived.by(() => {
    const ids = [
      ...new Set(entries.map((e) => e.speaker_id ?? "unknown")),
    ];
    const map: Record<string, string> = {};
    ids.forEach((id, i) => {
      map[id] = SPEAKER_COLORS[i % SPEAKER_COLORS.length]!;
    });
    return map;
  });

  let allSpeakerNames = $derived(allSpeakers.map((s) => s.name));

  // Audio player state
  let audioEl = $state<HTMLAudioElement | null>(null);
  let currentTime = $state(0);
  let duration = $state(0);
  let playing = $state(false);

  // Speaker filter
  let filterSpeaker: string | null = $state(null);

  let displayedEntries = $derived(
    filterSpeaker
      ? entries.filter((e) => e.speaker_id === filterSpeaker)
      : entries,
  );

  let activeIndex = $derived(
    displayedEntries.findIndex((e) => currentTime >= e.start && currentTime < e.end),
  );

  // Show original toggle
  let showOriginal = $state(false);

  // Global space-to-play/pause
  function onGlobalKeydown(e: KeyboardEvent) {
    if (e.key !== " ") return;
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    e.preventDefault();
    togglePlay();
  }

  function togglePlay() {
    if (!audioEl) return;
    if (playing) {
      audioEl.pause();
    } else {
      audioEl.play();
    }
  }

  function seekTo(time: number) {
    if (!audioEl) return;
    audioEl.currentTime = time;
  }

  function onEntryClick(entry: TranscriptionEntry) {
    seekTo(entry.start);
    if (!playing) {
      audioEl?.play();
    }
  }

  // Entry text saving
  async function saveEntryText(entryId: number, newText: string): Promise<boolean> {
    const entry = entries.find((e) => e.id === entryId);
    if (!entry) return false;
    const { data } = await client.POST(
      "/-/api/scribe/entry/{entry_id}/edit",
      {
        params: { path: { entry_id: String(entryId) } },
        body: { database: appState.selectedDatabase!, text: newText },
      },
    );
    if (data?.ok) {
      const idx = entries.findIndex((e) => e.id === entryId);
      if (idx >= 0) entries[idx] = { ...entries[idx]!, text: newText };
      edits = [
        {
          id: Date.now(),
          operation: "edit_text",
          detail: JSON.stringify({ old: entry.text, new: newText }),
          created_at: new Date().toISOString(),
          entry_id: entryId,
        },
        ...edits,
      ];
      return true;
    }
    return false;
  }

  // Speaker reassignment
  async function reassignSpeaker(entry: TranscriptionEntry, newSpeaker: string) {
    if (newSpeaker === (entry.speaker_id ?? "")) return;
    const { data } = await client.POST(
      "/-/api/scribe/entry/{entry_id}/edit",
      {
        params: { path: { entry_id: String(entry.id) } },
        body: {
          database: appState.selectedDatabase!,
          speaker_id: newSpeaker,
        },
      },
    );
    if (data?.ok) {
      const oldSpeaker = entry.speaker_id;
      const idx = entries.findIndex((e) => e.id === entry.id);
      if (idx >= 0)
        entries[idx] = { ...entries[idx]!, speaker_id: newSpeaker };
      edits = [
        {
          id: Date.now(),
          operation: "reassign_speaker",
          detail: JSON.stringify({ old: oldSpeaker, new: newSpeaker }),
          created_at: new Date().toISOString(),
          entry_id: entry.id,
        },
        ...edits,
      ];
    }
  }

  // Speaker management
  async function createSpeaker(name: string) {
    const { data } = await client.POST(
      "/-/api/scribe/transcription/{transcription_id}/speakers/create",
      {
        params: { path: { transcription_id: String(t.id) } },
        body: {
          database: appState.selectedDatabase!,
          name,
        },
      },
    );
    if (data?.ok) {
      const newSpeaker = {
        id: Date.now(),
        name,
        is_original: false,
        used_in_other_transcriptions: false,
      };
      speakers = [...speakers, newSpeaker];
      allSpeakers = [...allSpeakers, newSpeaker];
      edits = [
        {
          id: Date.now(),
          operation: "create_speaker",
          detail: JSON.stringify({ name }),
          created_at: new Date().toISOString(),
        },
        ...edits,
      ];
    }
  }

  async function renameSpeaker(speaker: TranscriptionSpeaker, newName: string) {
    const { data } = await client.POST(
      "/-/api/scribe/speakers/{speaker_id}/rename",
      {
        params: { path: { speaker_id: String(speaker.id) } },
        body: {
          database: appState.selectedDatabase!,
          new_name: newName,
        },
      },
    );
    if (data?.ok) {
      const oldName = speaker.name;
      entries = entries.map((e) =>
        e.speaker_id === oldName ? { ...e, speaker_id: newName } : e,
      );
      speakers = speakers.map((s) =>
        s.id === speaker.id ? { ...s, name: newName } : s,
      );
      allSpeakers = allSpeakers.map((s) =>
        s.id === speaker.id ? { ...s, name: newName } : s,
      );
      edits = [
        {
          id: Date.now(),
          operation: "rename_speaker",
          detail: JSON.stringify({ old_name: oldName, new_name: newName }),
          created_at: new Date().toISOString(),
        },
        ...edits,
      ];
    }
  }

  async function combineSpeakers(fromSpeaker: string, toSpeaker: string) {
    const { data } = await client.POST(
      "/-/api/scribe/transcription/{transcription_id}/speakers/combine",
      {
        params: { path: { transcription_id: String(t.id) } },
        body: {
          database: appState.selectedDatabase!,
          from_speaker: fromSpeaker,
          to_speaker: toSpeaker,
        },
      },
    );
    if (data?.ok) {
      let affected = 0;
      entries = entries.map((e) => {
        if (e.speaker_id === fromSpeaker) {
          affected++;
          return { ...e, speaker_id: toSpeaker };
        }
        return e;
      });
      speakers = speakers.filter((s) => s.name !== fromSpeaker);
      edits = [
        {
          id: Date.now(),
          operation: "combine_speakers",
          detail: JSON.stringify({
            from: fromSpeaker,
            to: toSpeaker,
            affected_entries: affected,
          }),
          created_at: new Date().toISOString(),
        },
        ...edits,
      ];
    }
  }

  async function deleteSpeaker(speakerName: string) {
    const { data } = await client.POST(
      "/-/api/scribe/transcription/{transcription_id}/speakers/delete",
      {
        params: { path: { transcription_id: String(t.id) } },
        body: {
          database: appState.selectedDatabase!,
          speaker_name: speakerName,
        },
      },
    );
    if (data?.ok) {
      let affected = 0;
      entries = entries.map((e) => {
        if (e.speaker_id === speakerName) {
          affected++;
          return { ...e, speaker_id: null };
        }
        return e;
      });
      speakers = speakers.filter((s) => s.name !== speakerName);
      edits = [
        {
          id: Date.now(),
          operation: "delete_speaker",
          detail: JSON.stringify({
            name: speakerName,
            affected_entries: affected,
          }),
          created_at: new Date().toISOString(),
        },
        ...edits,
      ];
    }
  }

  async function unassignSpeaker(speakerName: string) {
    let affected = 0;
    for (const entry of entries) {
      if (entry.speaker_id === speakerName) {
        const { data } = await client.POST(
          "/-/api/scribe/entry/{entry_id}/edit",
          {
            params: { path: { entry_id: String(entry.id) } },
            body: {
              database: appState.selectedDatabase!,
              speaker_id: "",
            },
          },
        );
        if (data?.ok) affected++;
      }
    }
    if (affected > 0) {
      entries = entries.map((e) =>
        e.speaker_id === speakerName ? { ...e, speaker_id: null } : e,
      );
      speakers = speakers.filter((s) => s.name !== speakerName);
      edits = [
        {
          id: Date.now(),
          operation: "unassign_speaker",
          detail: JSON.stringify({
            name: speakerName,
            affected_entries: affected,
          }),
          created_at: new Date().toISOString(),
        },
        ...edits,
      ];
    }
  }

  async function onSpeakerSelectChange(e: Event, entry: TranscriptionEntry) {
    const target = e.currentTarget as HTMLSelectElement;
    if (target.value === "__new__") {
      target.value = entry.speaker_id ?? "";
      const name = prompt("New speaker name:");
      if (!name?.trim()) return;
      const trimmed = name.trim();
      if (!allSpeakerNames.includes(trimmed)) {
        const { data } = await client.POST(
          "/-/api/scribe/transcription/{transcription_id}/speakers/create",
          {
            params: { path: { transcription_id: String(t.id) } },
            body: { database: appState.selectedDatabase!, name: trimmed },
          },
        );
        if (data?.ok) {
          const newSpeaker = { id: Date.now(), name: trimmed, is_original: false, used_in_other_transcriptions: false };
          speakers = [...speakers, newSpeaker];
          allSpeakers = [...allSpeakers, newSpeaker];
          edits = [
            { id: Date.now(), operation: "create_speaker", detail: JSON.stringify({ name: trimmed }), created_at: new Date().toISOString() },
            ...edits,
          ];
        } else {
          return;
        }
      }
      reassignSpeaker(entry, trimmed);
    } else {
      reassignSpeaker(entry, target.value);
    }
  }

  function toggleFilterSpeaker(name: string) {
    filterSpeaker = filterSpeaker === name ? null : name;
  }

  function formatProcessingDuration(startIso: string, endIso: string): string {
    try {
      const ms = parseUTC(endIso).getTime() - parseUTC(startIso).getTime();
      const totalSeconds = Math.round(ms / 1000);
      if (totalSeconds < 60) return `${totalSeconds}s`;
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      return `${minutes}m ${seconds}s`;
    } catch {
      return "";
    }
  }

  // Collection assignment
  let movingCollection = $state(false);

  async function onCollectionChange(e: Event) {
    const target = e.currentTarget as HTMLSelectElement;
    const newValue = target.value;
    movingCollection = true;

    if (collection) {
      const { error: removeErr } = await client.POST(
        "/-/api/scribe/collections/{collection_id}/remove-transcription",
        {
          params: { path: { collection_id: String(collection.id) } },
          body: {
            database: appState.selectedDatabase!,
            transcription_id: t.id,
          } as any,
        },
      );
      if (removeErr) {
        movingCollection = false;
        return;
      }
    }

    if (newValue) {
      const newId = Number(newValue);
      const { error: addErr } = await client.POST(
        "/-/api/scribe/collections/{collection_id}/add-transcription",
        {
          params: { path: { collection_id: String(newId) } },
          body: {
            database: appState.selectedDatabase!,
            transcription_id: t.id,
          } as any,
        },
      );
      if (addErr) {
        movingCollection = false;
        return;
      }
      collection = allCollections.find((c) => c.id === newId) ?? null;
    } else {
      collection = null;
    }

    movingCollection = false;
  }

  // Copy transcript text
  let copyLabel = $state("Copy");

  async function copyTranscript() {
    const text = displayedEntries
      .map((e) => {
        const speaker = e.speaker_id ? `${e.speaker_id}: ` : "";
        return `${speaker}${e.text}`;
      })
      .join("\n");
    await navigator.clipboard.writeText(text);
    copyLabel = "Copied!";
    setTimeout(() => (copyLabel = "Copy"), 2000);
  }
</script>

<svelte:window onkeydown={onGlobalKeydown} />

<div class="top-bar">
  <div class="top-bar-left">
    <h1>Transcription #{t.id}</h1>
    <a href="/{appState.selectedDatabase}/-/scribe" class="back-link">&larr; All transcriptions</a>
    {#if allCollections.length > 0}
      <span class="meta-item collection-meta">
        <strong>Collection:</strong>
        <select class="collection-select" value={collection?.id != null ? String(collection.id) : ""} onchange={onCollectionChange} disabled={movingCollection}>
          <option value="">None</option>
          {#each allCollections as c}
            <option value={String(c.id)}>{c.name}</option>
          {/each}
        </select>
        {#if collection}
          <a href="/{appState.selectedDatabase}/-/scribe/collections/{collection.id}" class="collection-link" title="View collection">View</a>
        {/if}
      </span>
    {:else if collection}
      <span class="meta-item"><strong>Collection:</strong> <a href="/{appState.selectedDatabase}/-/scribe/collections/{collection.id}">{collection.name}</a></span>
    {/if}
    <div class="meta">
      <span class="meta-item">
        <strong>Source:</strong>
        {#if t.input_type === "file"}
          {t.filename ?? "Uploaded file"}
        {:else}
          <a href={t.url} target="_blank" rel="noopener">{t.url}</a>
        {/if}
      </span>
      <span class="meta-item"><strong>Model:</strong> {t.model}</span>
      <span class="meta-item"><strong>Granularity:</strong> {t.granularity}</span>
      {#if t.error}
        <span class="meta-item status-error">Error: {t.error}</span>
      {:else if t.completed_at}
        <span class="meta-item status-done" title="{t.completed_at} UTC">Processed at {formatTimestamp(t.completed_at)}{#if t.submitted_at} ({formatProcessingDuration(t.submitted_at, t.completed_at)}){/if}</span>
      {:else}
        <span class="meta-item status-pending">Pending</span>
      {/if}
    </div>
  </div>
  <div class="top-bar-right">
    {#if entries.length > 0}
      <button class="btn-copy" onclick={copyTranscript}>{copyLabel}</button>
    {/if}
    <DatabaseSelector />
  </div>
</div>

<main>
  <!-- Hidden audio element -->
  <audio
    bind:this={audioEl}
    src={audioUrl}
    onloadedmetadata={() => {
      if (audioEl) duration = audioEl.duration;
    }}
    ontimeupdate={() => {
      if (audioEl) currentTime = audioEl.currentTime;
    }}
    onplay={() => (playing = true)}
    onpause={() => (playing = false)}
    onended={() => (playing = false)}
  ></audio>

  {#if entries.length > 0}
    <div class="layout">
      <SpeakerSidebar
        {speakers}
        {speakerColorMap}
        {filterSpeaker}
        {showOriginal}
        {edits}
        {entries}
        onToggleFilter={toggleFilterSpeaker}
        onToggleShowOriginal={() => (showOriginal = !showOriginal)}
        onCreateSpeaker={createSpeaker}
        onRenameSpeaker={renameSpeaker}
        onCombineSpeakers={combineSpeakers}
        onDeleteSpeaker={deleteSpeaker}
        onUnassignSpeaker={unassignSpeaker}
      />

      <TranscriptEntryList
        {entries}
        {displayedEntries}
        {filterSpeaker}
        {allSpeakerNames}
        {speakerColorMap}
        {activeIndex}
        {showOriginal}
        onClearFilter={() => (filterSpeaker = null)}
        onEntryClick={onEntryClick}
        onSaveEntry={saveEntryText}
        onSpeakerSelectChange={onSpeakerSelectChange}
      />
    </div>
  {:else}
    <p class="empty">No entries.</p>
  {/if}
</main>

{#if entries.length > 0}
  <AudioPlayer
    {playing}
    {currentTime}
    {duration}
    {entries}
    {speakerColorMap}
    {filterSpeaker}
    onTogglePlay={togglePlay}
    onSeek={seekTo}
  />
{/if}

<style>
  /* Datasette shell: make body a full-height flex layout */
  :global(body) {
    display: flex;
    flex-direction: column;
    height: 100vh;
    margin: 0;
    overflow: hidden;
  }
  :global(.not-footer) {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
  :global(.not-footer > header) {
    flex-shrink: 0;
  }
  :global(section.content) {
    flex: 1;
    overflow: hidden;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  :global(#app-root) {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  :global(body > footer) {
    flex-shrink: 0;
  }

  .top-bar {
    flex-shrink: 0;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding: 0.75rem 1rem;
    background: #fff;
    border-bottom: 1px solid #ddd;
  }

  .top-bar-left {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .back-link {
    font-size: 0.85rem;
    color: #555;
    text-decoration: none;
  }
  .back-link:hover {
    color: #333;
    text-decoration: underline;
  }

  .collection-meta {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }

  .collection-select {
    font-size: 0.85rem;
    padding: 0.1rem 0.3rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    cursor: pointer;
  }
  .collection-select:disabled {
    opacity: 0.6;
    cursor: wait;
  }

  .collection-link {
    font-size: 0.8rem;
    color: #4a90d9;
    text-decoration: none;
  }
  .collection-link:hover {
    text-decoration: underline;
  }

  h1 {
    margin: 0;
  }

  main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 1rem;
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem 1.5rem;
    font-size: 0.85rem;
    color: #555;
    margin-top: 0.25rem;
  }

  .status-done {
    color: #999;
  }
  .status-error {
    color: #c00;
  }
  .status-pending {
    color: #888;
  }

  .top-bar-right {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    flex-shrink: 0;
  }

  .btn-copy {
    font-size: 0.8rem;
    padding: 0.3rem 0.7rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    cursor: pointer;
    white-space: nowrap;
  }
  .btn-copy:hover {
    background: #f5f5f5;
  }

  .layout {
    display: flex;
    gap: 1.25rem;
    flex: 1;
    min-height: 0;
  }

  .empty {
    color: #666;
  }
</style>
