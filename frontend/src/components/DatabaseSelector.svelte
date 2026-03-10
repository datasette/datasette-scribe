<script lang="ts">
  import { appState } from "../store.svelte";

  let loading = $state(true);
  let error: string | null = $state(null);

  async function fetchDatabases() {
    try {
      const res = await fetch("/.json");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      appState.databases = Object.values(data.databases);
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  function onchange(e: Event) {
    const name = (e.target as HTMLSelectElement).value;
    window.location.href = `/${encodeURIComponent(name)}/-/scribe`;
  }

  fetchDatabases();
</script>

<div class="database-selector">
  {#if loading}
    <span class="loading">Loading databases…</span>
  {:else if error}
    <span class="error">Error: {error}</span>
  {:else if appState.databases.length === 0}
    <span class="empty">No databases found</span>
  {:else}
    <label for="db-select">Database</label>
    <select id="db-select" value={appState.selectedDatabase} {onchange}>
      {#each appState.databases as db}
        <option value={db.name}>
          {db.name}
        </option>
      {/each}
    </select>
    {#if appState.selectedDatabase}
      {@const db = appState.databases.find((d) => d.name === appState.selectedDatabase)}
      {#if db}
        <span class="color-dot" style="background-color: #{db.color};"></span>
      {/if}
    {/if}
  {/if}
</div>

<style>
  .database-selector {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }
  label {
    font-weight: 600;
  }
  select {
    padding: 0.3rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  .color-dot {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 50%;
  }
  .loading,
  .error,
  .empty {
    font-size: 0.85rem;
    color: #666;
  }
  .error {
    color: #c00;
  }
</style>
