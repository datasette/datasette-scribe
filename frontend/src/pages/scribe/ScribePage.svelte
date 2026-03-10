<script lang="ts">
  import createClient from "openapi-fetch";
  import type { paths } from "../../../api.d.ts";
  import DatabaseSelector from "../../components/DatabaseSelector.svelte";
  import TranscriptionList from "./TranscriptionList.svelte";
  import { loadPageData } from "../../page_data/load";
  import type { ScribePageData } from "../../page_data/ScribePageData.types";
  import { appState } from "../../store.svelte";

  const client = createClient<paths>({ baseUrl: "/" });
  const pageData = loadPageData<ScribePageData>();

  let collections = $state([...(pageData.collections ?? [])]);
  let uncollected = $state([...(pageData.uncollected_transcriptions ?? [])]);

  // New collection form
  let showNewForm = $state(false);
  let newName = $state("");
  let newDescription = $state("");
  let creating = $state(false);
  let error: string | null = $state(null);

  async function createCollection() {
    if (!newName.trim()) return;
    creating = true;
    error = null;
    const { error: apiError } = await client.POST(
      "/-/api/scribe/collections/create",
      { body: { database: appState.selectedDatabase!, name: newName.trim(), description: newDescription } as any },
    );
    creating = false;
    if (apiError) {
      error = (apiError as any).error ?? "Failed to create collection";
      return;
    }
    // Reload the page to get the new collection
    window.location.reload();
  }
</script>

<main>
  <h1>Scribe</h1>
  <DatabaseSelector />
  <div class="actions">
    <a href="/{appState.selectedDatabase}/-/scribe/new" class="new-btn">New transcription</a>
    <button class="new-btn" onclick={() => { showNewForm = !showNewForm; }}>
      {showNewForm ? "Cancel" : "New collection"}
    </button>
  </div>

  {#if showNewForm}
    <div class="new-collection-form">
      <input
        type="text"
        bind:value={newName}
        placeholder="Collection name"
        class="form-input"
        onkeydown={(e) => { if (e.key === "Enter") createCollection(); }}
      />
      <input
        type="text"
        bind:value={newDescription}
        placeholder="Description (optional)"
        class="form-input"
      />
      <button class="btn-primary" onclick={createCollection} disabled={creating || !newName.trim()}>
        {creating ? "Creating..." : "Create"}
      </button>
      {#if error}
        <p class="error">{error}</p>
      {/if}
    </div>
  {/if}

  {#each collections as collection}
    <section class="collection-section">
      <h2>
        <a href="/{appState.selectedDatabase}/-/scribe/collections/{collection.id}" class="collection-link">
          {collection.name}
        </a>
        <span class="collection-count">{collection.transcriptions?.length ?? 0}</span>
      </h2>
      {#if collection.description}
        <p class="collection-desc">{collection.description}</p>
      {/if}
      <TranscriptionList transcriptions={collection.transcriptions ?? []} />
    </section>
  {/each}

  <section class="collection-section">
    <h2>Uncollected <span class="collection-count">{uncollected.length}</span></h2>
    <TranscriptionList transcriptions={uncollected} />
  </section>
</main>

<style>
  .actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
  }
  .new-btn {
    display: inline-block;
    padding: 0.4rem 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    text-decoration: none;
    color: inherit;
    background: white;
    cursor: pointer;
    font-size: inherit;
  }
  .new-btn:hover {
    background: #f5f5f5;
  }
  .new-collection-form {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.75rem;
    align-items: center;
  }
  .form-input {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  .btn-primary {
    padding: 0.4rem 1rem;
    border: 1px solid #4a90d9;
    border-radius: 4px;
    background: #4a90d9;
    color: white;
    cursor: pointer;
  }
  .btn-primary:hover {
    background: #3a7bc8;
  }
  .btn-primary:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .error {
    color: #c00;
    font-size: 0.85rem;
    width: 100%;
    margin: 0;
  }
  .collection-section {
    margin-top: 1.5rem;
  }
  .collection-section h2 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1.1rem;
    margin: 0;
    border-bottom: 2px solid #eee;
    padding-bottom: 0.3rem;
  }
  .collection-link {
    color: inherit;
    text-decoration: none;
  }
  .collection-link:hover {
    text-decoration: underline;
  }
  .collection-count {
    font-size: 0.8rem;
    color: #999;
    font-weight: normal;
  }
  .collection-desc {
    color: #666;
    font-size: 0.85rem;
    margin: 0.25rem 0 0;
  }
</style>
