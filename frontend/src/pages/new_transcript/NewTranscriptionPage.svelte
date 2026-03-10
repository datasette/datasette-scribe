<script lang="ts">
  import createClient from "openapi-fetch";
  import type { paths } from "../../../api.d.ts";
  import DatabaseSelector from "../../components/DatabaseSelector.svelte";
  import { loadPageData } from "../../page_data/load";
  import type { NewTranscriptionPageData } from "../../page_data/NewTranscriptionPageData.types";
  import { appState } from "../../store.svelte";

  const client = createClient<paths>({ baseUrl: "/" });
  const pageData = loadPageData<NewTranscriptionPageData>();
  const collections = pageData.collections ?? [];

  let mode: "url" | "file" = $state("url");
  let selectedCollectionId: string = $state("");
  let url = $state("");
  let selectedFile: File | null = $state(null);
  let dragging = $state(false);
  let submitting = $state(false);
  let error: string | null = $state(null);
  let success: string | null = $state(null);

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function handleFile(file: File) {
    if (!file.type.startsWith("audio/")) {
      error = "Please select an audio file";
      return;
    }
    selectedFile = file;
    error = null;
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    const file = e.dataTransfer?.files[0];
    if (file) handleFile(file);
  }

  function onDragOver(e: DragEvent) {
    e.preventDefault();
    dragging = true;
  }

  function onDragLeave(e: DragEvent) {
    e.preventDefault();
    dragging = false;
  }

  function onFileInput(e: Event) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (file) handleFile(file);
  }

  function readFileAsBase64(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result as string;
        // Strip the data:...;base64, prefix
        resolve(dataUrl.split(",")[1]!);
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  async function handleSubmit(e: Event) {
    e.preventDefault();
    error = null;
    success = null;
    submitting = true;
    try {
      let body: Record<string, string | number>;
      if (mode === "file" && selectedFile) {
        const base64 = await readFileAsBase64(selectedFile);
        body = {
          database: appState.selectedDatabase!,
          file_data: base64,
          filename: selectedFile.name,
          content_type: selectedFile.type || "audio/mpeg",
        };
      } else {
        body = {
          database: appState.selectedDatabase!,
          url,
        };
      }
      if (selectedCollectionId) {
        body.collection_id = Number(selectedCollectionId);
      }
      const { data, error: apiError } = await client.POST(
        "/-/api/scribe/new",
        { body: body as any },
      );
      if (apiError) {
        error = (apiError as any).error ?? "Unknown error";
        return;
      }
      window.location.href = `/${appState.selectedDatabase}/-/scribe/transcription/${data.id}`;
    } catch (e: any) {
      error = e.message;
    } finally {
      submitting = false;
    }
  }
</script>

<main>
  <h1>New transcription</h1>
  <DatabaseSelector />

  <div class="mode-toggle">
    <button
      class="mode-btn"
      class:active={mode === "url"}
      onclick={() => { mode = "url"; error = null; }}
    >URL</button>
    <button
      class="mode-btn"
      class:active={mode === "file"}
      onclick={() => { mode = "file"; error = null; }}
    >File upload</button>
  </div>

  <form onsubmit={handleSubmit}>
    {#if mode === "url"}
      <label for="audio-url">Audio URL (.mp3 or .wav)</label>
      <input
        id="audio-url"
        type="url"
        bind:value={url}
        placeholder="https://example.com/audio.mp3"
        required
      />
    {:else}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        class="drop-zone"
        class:dragging
        class:has-file={selectedFile !== null}
        ondrop={onDrop}
        ondragover={onDragOver}
        ondragleave={onDragLeave}
      >
        {#if selectedFile}
          <div class="file-info">
            <span class="file-name">{selectedFile.name}</span>
            <span class="file-size">{formatFileSize(selectedFile.size)}</span>
            <button type="button" class="clear-btn" onclick={() => { selectedFile = null; }}>Remove</button>
          </div>
        {:else}
          <p class="drop-text">Drag & drop an audio file here</p>
          <p class="drop-subtext">or</p>
          <label class="browse-btn">
            Browse files
            <input type="file" accept="audio/*" onchange={onFileInput} hidden />
          </label>
        {/if}
      </div>
    {/if}
    {#if collections.length > 0}
      <label for="collection-select">Collection (optional)</label>
      <select id="collection-select" bind:value={selectedCollectionId} class="collection-select">
        <option value="">No collection</option>
        {#each collections as c}
          <option value={String(c.id)}>{c.name}</option>
        {/each}
      </select>
    {/if}
    <button
      type="submit"
      disabled={submitting || (mode === "file" && !selectedFile) || (mode === "url" && !url)}
    >
      {submitting ? "Submitting…" : "Submit"}
    </button>
  </form>

  {#if error}
    <p class="error">{error}</p>
  {/if}
  {#if success}
    <p class="success">{success}</p>
  {/if}
</main>

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-top: 1rem;
    max-width: 500px;
  }
  label {
    font-weight: 600;
  }
  input[type="url"] {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  button[type="submit"] {
    align-self: flex-start;
    padding: 0.4rem 1rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    cursor: pointer;
  }
  button[type="submit"]:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .error {
    color: #c00;
  }
  .success {
    color: #060;
  }

  .mode-toggle {
    display: flex;
    gap: 0;
    margin-top: 1rem;
    max-width: 500px;
  }
  .mode-btn {
    flex: 1;
    padding: 0.4rem 1rem;
    border: 1px solid #ccc;
    background: #f5f5f5;
    cursor: pointer;
    font-size: 0.85rem;
    color: #555;
  }
  .mode-btn:first-child {
    border-radius: 4px 0 0 4px;
  }
  .mode-btn:last-child {
    border-radius: 0 4px 4px 0;
    border-left: none;
  }
  .mode-btn.active {
    background: #4a90d9;
    color: white;
    border-color: #4a90d9;
  }

  .drop-zone {
    border: 2px dashed #ccc;
    border-radius: 8px;
    padding: 2rem 1rem;
    text-align: center;
    transition: border-color 0.15s, background 0.15s;
  }
  .drop-zone.dragging {
    border-color: #4a90d9;
    background: #f0f7ff;
  }
  .drop-zone.has-file {
    border-color: #50b86c;
    background: #f0faf4;
  }
  .drop-text {
    margin: 0;
    color: #555;
    font-size: 0.95rem;
  }
  .drop-subtext {
    margin: 0.3rem 0;
    color: #999;
    font-size: 0.8rem;
  }
  .browse-btn {
    display: inline-block;
    padding: 0.3rem 0.8rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    cursor: pointer;
    font-size: 0.85rem;
    color: #333;
  }
  .browse-btn:hover {
    background: #f5f5f5;
  }

  .file-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    justify-content: center;
  }
  .file-name {
    font-weight: 600;
    color: #333;
  }
  .file-size {
    color: #888;
    font-size: 0.85rem;
  }
  .clear-btn {
    font-size: 0.8rem;
    padding: 0.15rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: white;
    cursor: pointer;
    color: #c00;
  }
  .clear-btn:hover {
    background: #fef0f0;
  }
  .collection-select {
    padding: 0.4rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
</style>
