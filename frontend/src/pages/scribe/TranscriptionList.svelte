<script lang="ts">
  import type { TranscriptionSummary } from "../../page_data/ScribePageData.types";
  import { appState } from "../../store.svelte";

  let { transcriptions = [] }: { transcriptions: TranscriptionSummary[] } = $props();

  function formatDuration(seconds: number): string {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const mm = String(m).padStart(2, '0');
    const ss = String(s).padStart(2, '0');
    if (h > 0) return `${h}:${mm}:${ss}`;
    return `${mm}:${ss}`;
  }
</script>

{#if transcriptions.length === 0}
  <p class="empty">No transcriptions yet.</p>
{:else}
  <table>
    <thead>
      <tr>
        <th>ID</th>
        <th>Source</th>
        <th>Model</th>
        <th>Submitted</th>
        <th>Duration</th>
        <th>Speakers</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {#each transcriptions as t}
        <tr class="clickable-row" onclick={() => window.location.href = `/${appState.selectedDatabase}/-/scribe/transcription/${t.id}`}>
          <td>{t.id}</td>
          <td class="url-cell">{t.input_type === "file" ? t.filename ?? "Uploaded file" : t.url}</td>
          <td class="nowrap">{t.model}</td>
          <td class="nowrap">{t.submitted_at}</td>
          <td class="nowrap">{t.duration != null ? formatDuration(t.duration) : '—'}</td>
          <td>{t.speakers_count || '—'}</td>
          <td>
            {#if t.error}
              <span class="status-error" title={t.error}>Error</span>
            {:else if t.completed_at}
              <span class="status-done">Done</span>
            {:else}
              <span class="status-pending">Pending</span>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 1rem;
    font-size: 0.9rem;
  }
  th,
  td {
    text-align: left;
    padding: 0.4rem 0.6rem;
    border-bottom: 1px solid #eee;
  }
  th {
    font-weight: 600;
    border-bottom: 2px solid #ccc;
  }
  .url-cell {
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status-done {
    color: #060;
  }
  .status-error {
    color: #c00;
    cursor: help;
  }
  .status-pending {
    color: #888;
  }
  .clickable-row {
    cursor: pointer;
  }
  .clickable-row:hover {
    background: #f5f5f5;
  }
  .nowrap {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 150px;
  }
  .empty {
    color: #666;
    font-size: 0.9rem;
  }
</style>
