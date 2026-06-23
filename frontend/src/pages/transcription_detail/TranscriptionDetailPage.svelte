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

  // Sharing: the <datasette-acl-share-dialog> custom element is registered by
  // datasette-acl-share's bundle (included via extra_js_urls on this page). We
  // only render the Share button + modal wrapper when the current actor may
  // manage sharing for this transcription.
  const share = pageData.share;
  const actor = pageData.actor;
  const canManageShare = !!(share && share.available && share.can_manage);
  const actorJson = actor
    ? JSON.stringify({ id: actor.id, kind: "user", name: actor.name ?? undefined })
    : "";
  let shareOpen = $state(false);
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

  // Stable color per speaker id (scope roster first, then any extras used by
  // entries). Keyed by integer speaker id.
  let speakerColorMap = $derived.by(() => {
    const ids = [
      ...new Set([
        ...allSpeakers.map((s) => s.id),
        ...entries
          .map((e) => e.speaker_id)
          .filter((id): id is number => id != null),
      ]),
    ];
    const map: Record<number, string> = {};
    ids.forEach((id, i) => {
      map[id] = SPEAKER_COLORS[i % SPEAKER_COLORS.length]!;
    });
    return map;
  });

  // id -> display name lookup (for copy/export rendering).
  let speakerNameById = $derived.by(() => {
    const map: Record<number, string> = {};
    for (const s of allSpeakers) map[s.id] = s.name;
    for (const s of speakers) map[s.id] = s.name;
    return map;
  });

  // Audio player state
  let audioEl = $state<HTMLAudioElement | null>(null);
  let currentTime = $state(0);
  let duration = $state(0);
  let playing = $state(false);
  let playbackRate = $state(1);

  // Keep the audio element's rate in sync with the selected multiplier.
  $effect(() => {
    if (audioEl) audioEl.playbackRate = playbackRate;
  });

  // Speaker filter (by speaker id)
  let filterSpeaker: number | null = $state(null);

  let displayedEntries = $derived(
    filterSpeaker != null
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

  // Speaker reassignment (by speaker id)
  async function reassignSpeaker(entry: TranscriptionEntry, newSpeakerId: number) {
    if (newSpeakerId === entry.speaker_id) return;
    const { data } = await client.POST(
      "/-/api/scribe/entry/{entry_id}/edit",
      {
        params: { path: { entry_id: String(entry.id) } },
        body: {
          database: appState.selectedDatabase!,
          speaker_id: newSpeakerId,
        },
      },
    );
    if (data?.ok) {
      const oldSpeaker = entry.speaker_id;
      const idx = entries.findIndex((e) => e.id === entry.id);
      if (idx >= 0)
        entries[idx] = { ...entries[idx]!, speaker_id: newSpeakerId };
      edits = [
        {
          id: Date.now(),
          operation: "reassign_speaker",
          detail: JSON.stringify({ old: oldSpeaker, new: newSpeakerId }),
          created_at: new Date().toISOString(),
          entry_id: entry.id,
        },
        ...edits,
      ];
    }
  }

  // Speaker management (all keyed by integer speaker id)
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
    if (data?.ok && data.id != null) {
      const newSpeaker: TranscriptionSpeaker = {
        id: data.id,
        name,
        description: "",
        is_configured: true,
        has_photo: false,
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
      // Entries reference speakers by id, so renaming touches no entries.
      speakers = speakers.map((s) =>
        s.id === speaker.id ? { ...s, name: newName, is_configured: true } : s,
      );
      allSpeakers = allSpeakers.map((s) =>
        s.id === speaker.id ? { ...s, name: newName, is_configured: true } : s,
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

  // Update name and/or description in one call (profile editor).
  async function updateSpeaker(
    speaker: TranscriptionSpeaker,
    fields: { name?: string; description?: string },
  ): Promise<boolean> {
    const { data } = await client.POST(
      "/-/api/scribe/speakers/{speaker_id}/update",
      {
        params: { path: { speaker_id: String(speaker.id) } },
        body: { database: appState.selectedDatabase!, ...fields },
      },
    );
    if (!data?.ok) return false;
    const patch = (s: TranscriptionSpeaker) =>
      s.id === speaker.id
        ? {
            ...s,
            name: fields.name ?? s.name,
            description: fields.description ?? s.description,
            is_configured: true,
          }
        : s;
    speakers = speakers.map(patch);
    allSpeakers = allSpeakers.map(patch);
    return true;
  }

  // Upload a photo for a speaker (base64). Flips has_photo true on success.
  async function uploadSpeakerPhoto(
    speaker: TranscriptionSpeaker,
    fileData: string,
  ): Promise<boolean> {
    const { data } = await client.POST(
      "/-/api/scribe/speakers/{speaker_id}/photo",
      {
        params: { path: { speaker_id: String(speaker.id) } },
        body: { database: appState.selectedDatabase!, file_data: fileData },
      },
    );
    if (!data?.ok) return false;
    const patch = (s: TranscriptionSpeaker) =>
      s.id === speaker.id ? { ...s, has_photo: true } : s;
    speakers = speakers.map(patch);
    allSpeakers = allSpeakers.map(patch);
    return true;
  }

  async function combineSpeakers(fromId: number, toId: number) {
    const { data } = await client.POST(
      "/-/api/scribe/transcription/{transcription_id}/speakers/combine",
      {
        params: { path: { transcription_id: String(t.id) } },
        body: {
          database: appState.selectedDatabase!,
          from_speaker_id: fromId,
          to_speaker_id: toId,
        },
      },
    );
    if (data?.ok) {
      let affected = 0;
      entries = entries.map((e) => {
        if (e.speaker_id === fromId) {
          affected++;
          return { ...e, speaker_id: toId };
        }
        return e;
      });
      speakers = speakers.filter((s) => s.id !== fromId);
      allSpeakers = allSpeakers.filter((s) => s.id !== fromId);
      if (filterSpeaker === fromId) filterSpeaker = null;
      edits = [
        {
          id: Date.now(),
          operation: "combine_speakers",
          detail: JSON.stringify({
            from: fromId,
            to: toId,
            affected_entries: affected,
          }),
          created_at: new Date().toISOString(),
        },
        ...edits,
      ];
    }
  }

  async function deleteSpeaker(speakerId: number) {
    const { data } = await client.POST(
      "/-/api/scribe/transcription/{transcription_id}/speakers/delete",
      {
        params: { path: { transcription_id: String(t.id) } },
        body: {
          database: appState.selectedDatabase!,
          speaker_id: speakerId,
        },
      },
    );
    if (data?.ok) {
      let affected = 0;
      entries = entries.map((e) => {
        if (e.speaker_id === speakerId) {
          affected++;
          return { ...e, speaker_id: null };
        }
        return e;
      });
      speakers = speakers.filter((s) => s.id !== speakerId);
      allSpeakers = allSpeakers.filter((s) => s.id !== speakerId);
      if (filterSpeaker === speakerId) filterSpeaker = null;
      edits = [
        {
          id: Date.now(),
          operation: "delete_speaker",
          detail: JSON.stringify({
            speaker_id: speakerId,
            affected_entries: affected,
          }),
          created_at: new Date().toISOString(),
        },
        ...edits,
      ];
    }
  }

  function onSpeakerSelectChange(e: Event, entry: TranscriptionEntry) {
    const target = e.currentTarget as HTMLSelectElement;
    // "No speaker" (empty value) cannot clear via the reassign endpoint; use
    // the sidebar delete/combine actions to manage assignments.
    if (!target.value) {
      target.value = entry.speaker_id != null ? String(entry.speaker_id) : "";
      return;
    }
    reassignSpeaker(entry, Number(target.value));
  }

  function toggleFilterSpeaker(id: number) {
    filterSpeaker = filterSpeaker === id ? null : id;
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

  // Collection assignment — moving copies speakers to the new scope, so confirm first.
  let movingCollection = $state(false);
  let moveConfirmOpen = $state(false);
  let pendingCollectionId: number | null = $state(null);
  let moveToast: string | null = $state(null);

  function requestCollectionChange(e: Event) {
    const target = e.currentTarget as HTMLSelectElement;
    pendingCollectionId = target.value ? Number(target.value) : null;
    // Revert the <select> to the current value until the move is confirmed.
    target.value = collection?.id != null ? String(collection.id) : "";
    moveConfirmOpen = true;
  }

  function cancelMove() {
    moveConfirmOpen = false;
    pendingCollectionId = null;
  }

  let pendingCollectionName = $derived(
    pendingCollectionId != null
      ? (allCollections.find((c) => c.id === pendingCollectionId)?.name ??
          "the collection")
      : null,
  );

  async function confirmMove() {
    moveConfirmOpen = false;
    movingCollection = true;
    const { data } = await client.POST(
      "/-/api/scribe/transcription/{transcription_id}/move",
      {
        params: { path: { transcription_id: String(t.id) } },
        body: {
          database: appState.selectedDatabase!,
          collection_id: pendingCollectionId,
        },
      },
    );
    movingCollection = false;
    if (data?.ok) {
      moveToast = `Moved. ${data.copied_speakers} ${
        data.copied_speakers === 1 ? "speaker" : "speakers"
      } carried over.`;
      // Reload so the sidebar reflects the new scope's speakers and the Share
      // button targets the new scope.
      setTimeout(() => window.location.reload(), 700);
    }
  }

  // Copy transcript text
  let copyLabel = $state("Copy");

  async function copyTranscript() {
    const text = displayedEntries
      .map((e) => {
        const name = e.speaker_id != null ? speakerNameById[e.speaker_id] : undefined;
        const speaker = name ? `${name}: ` : "";
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
        <select class="collection-select" value={collection?.id != null ? String(collection.id) : ""} onchange={requestCollectionChange} disabled={movingCollection}>
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
    {#if canManageShare}
      <button class="btn-share" onclick={() => (shareOpen = true)} title={collection ? "Sharing is managed at the collection level" : "Share this transcription"}>Share</button>
    {/if}
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
        database={appState.selectedDatabase!}
        onToggleFilter={toggleFilterSpeaker}
        onToggleShowOriginal={() => (showOriginal = !showOriginal)}
        onCreateSpeaker={createSpeaker}
        onRenameSpeaker={renameSpeaker}
        onUpdateSpeaker={updateSpeaker}
        onUploadPhoto={uploadSpeakerPhoto}
        onCombineSpeakers={combineSpeakers}
        onDeleteSpeaker={deleteSpeaker}
      />

      <TranscriptEntryList
        {entries}
        {displayedEntries}
        {filterSpeaker}
        {allSpeakers}
        {speakerNameById}
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
    {playbackRate}
    onTogglePlay={togglePlay}
    onSeek={seekTo}
    onSetPlaybackRate={(rate) => (playbackRate = rate)}
  />
{/if}

{#if shareOpen && share}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="share-backdrop" onclick={() => (shareOpen = false)}>
    <div
      class="share-modal"
      role="dialog"
      aria-label="Share transcription"
      tabindex="-1"
      onclick={(e) => e.stopPropagation()}
    >
      <datasette-acl-share-dialog
        resource-type={share.resource_type}
        parent={share.parent}
        child={share.child}
        resource-label={`Transcription #${t.id}`}
        actor-json={actorJson}
        features={share.features}
      ></datasette-acl-share-dialog>
      <div class="share-footer">
        <button class="btn-copy" onclick={() => (shareOpen = false)}>Done</button>
      </div>
    </div>
  </div>
{/if}

{#if moveConfirmOpen}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="share-backdrop" onclick={cancelMove}>
    <div class="confirm-modal" role="dialog" aria-label="Confirm move" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h3>
        {#if pendingCollectionId != null}
          Move to {pendingCollectionName}?
        {:else}
          Remove from collection?
        {/if}
      </h3>
      <p>
        Your speakers come along — duplicate names in the destination get a
        numbered suffix, so you can merge them later if you want. Sharing will
        also change to the destination's settings.
      </p>
      <div class="confirm-actions">
        <button class="btn-primary-lg" onclick={confirmMove}>Continue</button>
        <button class="btn-copy" onclick={cancelMove}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

{#if moveToast}
  <div class="toast">{moveToast}</div>
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

  .btn-copy,
  .btn-share {
    font-size: 0.8rem;
    padding: 0.3rem 0.7rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    cursor: pointer;
    white-space: nowrap;
  }
  .btn-copy:hover,
  .btn-share:hover {
    background: #f5f5f5;
  }

  .btn-share {
    border-color: #6c63ff;
    color: #6c63ff;
  }
  .btn-share:hover {
    background: #f3f2ff;
  }

  .share-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.35);
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding-top: 8vh;
    z-index: 1000;
  }

  .share-modal {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
    width: min(540px, 92vw);
    max-height: 80vh;
    overflow: auto;
    padding: 1.25rem;
  }

  .share-footer {
    display: flex;
    justify-content: flex-end;
    margin-top: 1rem;
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

  .confirm-modal {
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.25);
    width: min(420px, 92vw);
    padding: 1.25rem;
  }
  .confirm-modal h3 {
    margin: 0 0 0.5rem;
  }
  .confirm-modal p {
    margin: 0 0 1rem;
    color: #555;
    font-size: 0.9rem;
    line-height: 1.4;
  }
  .confirm-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }
  .btn-primary-lg {
    font-size: 0.85rem;
    padding: 0.35rem 0.9rem;
    border: 1px solid #4a90d9;
    border-radius: 4px;
    background: #4a90d9;
    color: white;
    cursor: pointer;
  }
  .btn-primary-lg:hover {
    background: #3a7bc8;
  }

  .toast {
    position: fixed;
    bottom: 1.5rem;
    left: 50%;
    transform: translateX(-50%);
    background: #323232;
    color: #fff;
    padding: 0.6rem 1rem;
    border-radius: 6px;
    font-size: 0.85rem;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    z-index: 1100;
  }
</style>
