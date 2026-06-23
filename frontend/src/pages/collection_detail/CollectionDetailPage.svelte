<script lang="ts">
  import createClient from "openapi-fetch";
  import type { paths } from "../../../api.d.ts";
  import DatabaseSelector from "../../components/DatabaseSelector.svelte";
  import { loadPageData } from "../../page_data/load";
  import type {
    CollectionDetailPageData,
    CollectionSpeakerStat,
    TranscriptionSummary,
  } from "../../page_data/CollectionDetailPageData.types";
  import { appState } from "../../store.svelte";

  const client = createClient<paths>({ baseUrl: "/" });
  const pageData = loadPageData<CollectionDetailPageData>();

  let collection = $state({ ...pageData.collection });
  let transcriptions: TranscriptionSummary[] = $state([...(pageData.transcriptions ?? [])]);
  let available: TranscriptionSummary[] = $state([...(pageData.available_transcriptions ?? [])]);
  const speakers: CollectionSpeakerStat[] = pageData.speakers ?? [];

  // Sharing: the collection's ACL governs all member transcripts. Render the
  // Share button + dialog only when the actor may manage the collection.
  const share = pageData.share;
  const canManageShare = !!(share && share.available && share.can_manage);
  let shareOpen = $state(false);

  // Moving a transcript in/out of a collection copies its speakers — confirm.
  let pendingMove: { kind: "add" | "remove"; tid: number } | null = $state(null);
  let toast: string | null = $state(null);

  // Editing state
  let editingName = $state(false);
  let editName = $state(collection.name);
  let editDescription = $state(collection.description ?? "");
  let editingDescription = $state(false);
  let saving = $state(false);
  let error: string | null = $state(null);

  // Add transcription
  let selectedTranscriptionId: string = $state("");

  async function saveName() {
    if (!editName.trim() || editName.trim() === collection.name) {
      editingName = false;
      return;
    }
    saving = true;
    error = null;
    const { error: apiError } = await client.POST(
      "/-/api/scribe/collections/{collection_id}/update",
      {
        params: { path: { collection_id: String(collection.id) } },
        body: {
          database: appState.selectedDatabase!,
          name: editName.trim(),
          description: collection.description ?? "",
        } as any,
      },
    );
    saving = false;
    if (apiError) {
      error = (apiError as any).error ?? "Failed to update";
      return;
    }
    collection = { ...collection, name: editName.trim() };
    editingName = false;
  }

  async function saveDescription() {
    saving = true;
    error = null;
    const { error: apiError } = await client.POST(
      "/-/api/scribe/collections/{collection_id}/update",
      {
        params: { path: { collection_id: String(collection.id) } },
        body: {
          database: appState.selectedDatabase!,
          name: collection.name,
          description: editDescription,
        } as any,
      },
    );
    saving = false;
    if (apiError) {
      error = (apiError as any).error ?? "Failed to update";
      return;
    }
    collection = { ...collection, description: editDescription };
    editingDescription = false;
  }

  function requestAdd() {
    if (!selectedTranscriptionId) return;
    pendingMove = { kind: "add", tid: Number(selectedTranscriptionId) };
  }

  function requestRemove(tid: number) {
    pendingMove = { kind: "remove", tid };
  }

  function cancelMove() {
    pendingMove = null;
  }

  async function confirmMove() {
    if (!pendingMove) return;
    const { kind, tid } = pendingMove;
    pendingMove = null;
    error = null;
    const path =
      kind === "add"
        ? "/-/api/scribe/collections/{collection_id}/add-transcription"
        : "/-/api/scribe/collections/{collection_id}/remove-transcription";
    const { data, error: apiError } = await client.POST(path, {
      params: { path: { collection_id: String(collection.id) } },
      body: {
        database: appState.selectedDatabase!,
        transcription_id: tid,
      } as any,
    });
    if (apiError || !data?.ok) {
      error = (apiError as any)?.error ?? `Failed to ${kind} transcription`;
      return;
    }
    const n = data.copied_speakers ?? 0;
    toast = `Done. ${n} ${n === 1 ? "speaker" : "speakers"} carried over.`;
    if (kind === "add") {
      const added = available.find((t) => t.id === tid);
      if (added) {
        transcriptions = [...transcriptions, added];
        available = available.filter((t) => t.id !== tid);
      }
      selectedTranscriptionId = "";
    } else {
      const removed = transcriptions.find((t) => t.id === tid);
      if (removed) {
        available = [...available, removed];
        transcriptions = transcriptions.filter((t) => t.id !== tid);
      }
    }
  }

  async function deleteCollection() {
    if (!confirm(`Delete collection "${collection.name}"? Transcriptions will become uncollected.`)) return;
    error = null;
    const { error: apiError } = await client.POST(
      "/-/api/scribe/collections/{collection_id}/delete",
      {
        params: { path: { collection_id: String(collection.id) } },
        body: {
          database: appState.selectedDatabase!,
          name: collection.name,
          description: "",
        } as any,
      },
    );
    if (apiError) {
      error = (apiError as any).error ?? "Failed to delete";
      return;
    }
    window.location.href = `/${appState.selectedDatabase}/-/scribe`;
  }

  function transcriptionLabel(t: TranscriptionSummary): string {
    if (t.input_type === "file") return t.filename ?? `#${t.id}`;
    return t.url ?? `#${t.id}`;
  }
</script>

<main>
  <a href="/{appState.selectedDatabase}/-/scribe" class="back-link">&larr; All transcriptions</a>
  <div class="header">
    <div class="header-left">
      {#if editingName}
        <div class="edit-row">
          <input
            type="text"
            class="edit-input"
            bind:value={editName}
            onkeydown={(e) => {
              if (e.key === "Enter") saveName();
              if (e.key === "Escape") { editingName = false; editName = collection.name; }
            }}
          />
          <button class="btn-small btn-primary" onclick={saveName} disabled={saving}>Save</button>
          <button class="btn-small" onclick={() => { editingName = false; editName = collection.name; }}>Cancel</button>
        </div>
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <h1 class="editable" onclick={() => { editingName = true; editName = collection.name; }} title="Click to rename">
          {collection.name}
        </h1>
      {/if}

      {#if editingDescription}
        <div class="edit-row">
          <input
            type="text"
            class="edit-input"
            bind:value={editDescription}
            placeholder="Description"
            onkeydown={(e) => {
              if (e.key === "Enter") saveDescription();
              if (e.key === "Escape") { editingDescription = false; editDescription = collection.description ?? ""; }
            }}
          />
          <button class="btn-small btn-primary" onclick={saveDescription} disabled={saving}>Save</button>
          <button class="btn-small" onclick={() => { editingDescription = false; editDescription = collection.description ?? ""; }}>Cancel</button>
        </div>
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <p class="description editable" onclick={() => { editingDescription = true; editDescription = collection.description ?? ""; }} title="Click to edit description">
          {collection.description || "No description — click to add"}
        </p>
      {/if}
    </div>
    <div class="header-right">
      <DatabaseSelector />
      {#if canManageShare}
        <button class="btn-share" onclick={() => (shareOpen = true)}>Share collection</button>
      {/if}
      <button class="btn-danger" onclick={deleteCollection}>Delete collection</button>
    </div>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if speakers.length > 0}
    <div class="speakers-section">
      <h2>Speakers <span class="count">{speakers.length}</span></h2>
      <div class="speaker-chips">
        {#each speakers as s}
          <span class="speaker-chip">
            <span class="speaker-chip-name">{s.name}</span>
            <span class="speaker-chip-stat" title="{s.entry_count} entries across {s.transcription_count} transcription{s.transcription_count === 1 ? '' : 's'}">{s.entry_count}</span>
          </span>
        {/each}
      </div>
    </div>
  {/if}

  <h2>Transcriptions <span class="count">{transcriptions.length}</span></h2>

  {#if transcriptions.length > 0}
    <table class="transcription-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Source</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {#each transcriptions as t}
          <tr>
            <td>
              <a href="/{appState.selectedDatabase}/-/scribe/transcription/{t.id}">#{t.id}</a>
            </td>
            <td class="url-cell">{transcriptionLabel(t)}</td>
            <td>
              {#if t.error}
                <span class="status-error">Error</span>
              {:else if t.completed_at}
                <span class="status-done">Done</span>
              {:else}
                <span class="status-pending">Pending</span>
              {/if}
            </td>
            <td>
              <button class="btn-small btn-remove" onclick={() => requestRemove(t.id)}>Remove</button>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  {:else}
    <p class="empty">No transcriptions in this collection.</p>
  {/if}

  {#if available.length > 0}
    <div class="add-section">
      <h3>Add transcription</h3>
      <div class="add-row">
        <select bind:value={selectedTranscriptionId} class="add-select">
          <option value="">Select a transcription...</option>
          {#each available as t}
            <option value={String(t.id)}>#{t.id} — {transcriptionLabel(t)}</option>
          {/each}
        </select>
        <button class="btn-small btn-primary" onclick={requestAdd} disabled={!selectedTranscriptionId}>Add</button>
      </div>
    </div>
  {/if}
</main>

{#if shareOpen && share}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="modal-backdrop" onclick={() => (shareOpen = false)}>
    <div class="share-modal" role="dialog" aria-label="Share collection" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <datasette-acl-share-dialog
        resource-type={share.resource_type}
        parent={share.parent}
        child={share.child}
        resource-label={collection.name}
        features={share.features}
      ></datasette-acl-share-dialog>
      <div class="modal-footer">
        <button class="btn-small" onclick={() => (shareOpen = false)}>Done</button>
      </div>
    </div>
  </div>
{/if}

{#if pendingMove}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="modal-backdrop" onclick={cancelMove}>
    <div class="confirm-modal" role="dialog" aria-label="Confirm move" tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h3>{pendingMove.kind === "add" ? "Add to collection?" : "Remove from collection?"}</h3>
      <p>
        The transcript's speakers come along — duplicate names in the
        destination get a numbered suffix, so you can merge them later. Sharing
        changes to the destination's settings.
      </p>
      <div class="confirm-actions">
        <button class="btn-primary-lg" onclick={confirmMove}>Continue</button>
        <button class="btn-small" onclick={cancelMove}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

{#if toast}
  <div class="toast">{toast}</div>
{/if}

<style>
  main {
    max-width: 900px;
    margin: 0 auto;
    padding: 1rem;
  }
  .back-link {
    font-size: 0.85rem;
    color: #555;
    text-decoration: none;
  }
  .back-link:hover {
    text-decoration: underline;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    margin-top: 0.5rem;
  }
  .header-left {
    flex: 1;
  }
  .header-right {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    align-items: flex-end;
  }
  h1 {
    margin: 0;
  }
  .editable {
    cursor: pointer;
  }
  .editable:hover {
    text-decoration: underline;
    text-decoration-style: dashed;
    text-underline-offset: 3px;
  }
  .description {
    color: #666;
    font-size: 0.9rem;
    margin: 0.25rem 0 0;
  }
  .edit-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  .edit-input {
    padding: 0.4rem 0.5rem;
    border: 1px solid #4a90d9;
    border-radius: 4px;
    font-size: 0.9rem;
    flex: 1;
    min-width: 200px;
  }
  h2 {
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
    font-size: 1.1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  .count {
    font-size: 0.8rem;
    color: #999;
    font-weight: normal;
  }
  .transcription-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
  }
  .transcription-table th,
  .transcription-table td {
    text-align: left;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid #eee;
  }
  .transcription-table th {
    font-weight: 600;
    border-bottom: 2px solid #ccc;
  }
  .url-cell {
    max-width: 400px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status-done { color: #060; }
  .status-error { color: #c00; }
  .status-pending { color: #888; }
  .btn-small {
    font-size: 0.75rem;
    padding: 0.15rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    cursor: pointer;
  }
  .btn-small:hover { background: #f5f5f5; }
  .btn-small:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn-primary {
    background: #4a90d9;
    color: white;
    border-color: #4a90d9;
  }
  .btn-primary:hover { background: #3a7bc8; }
  .btn-remove {
    color: #c00;
    border-color: #ecc;
  }
  .btn-remove:hover { background: #fef0f0; }
  .btn-danger {
    padding: 0.35rem 0.75rem;
    border: 1px solid #c00;
    border-radius: 4px;
    background: white;
    color: #c00;
    cursor: pointer;
    font-size: 0.85rem;
  }
  .btn-danger:hover { background: #fef0f0; }
  .add-section {
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid #eee;
  }
  .add-section h3 {
    font-size: 0.95rem;
    margin: 0 0 0.5rem;
  }
  .add-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  .add-select {
    padding: 0.35rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.85rem;
    max-width: 400px;
  }
  .speakers-section {
    margin-top: 1.25rem;
  }
  .speaker-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }
  .speaker-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.2rem 0.6rem;
    background: #f0f4f8;
    border: 1px solid #dce3ea;
    border-radius: 999px;
    font-size: 0.8rem;
  }
  .speaker-chip-name {
    font-weight: 600;
    color: #333;
  }
  .speaker-chip-stat {
    color: #888;
    font-size: 0.75rem;
    cursor: help;
  }
  .empty {
    color: #666;
    font-size: 0.9rem;
  }
  .error {
    color: #c00;
    font-size: 0.85rem;
  }
  .btn-share {
    padding: 0.35rem 0.75rem;
    border: 1px solid #6c63ff;
    border-radius: 4px;
    background: white;
    color: #6c63ff;
    cursor: pointer;
    font-size: 0.85rem;
    white-space: nowrap;
  }
  .btn-share:hover {
    background: #f3f2ff;
  }
  .modal-backdrop {
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
  .modal-footer {
    display: flex;
    justify-content: flex-end;
    margin-top: 1rem;
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
