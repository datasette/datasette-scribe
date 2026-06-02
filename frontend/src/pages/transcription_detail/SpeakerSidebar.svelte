<script lang="ts">
  import type {
    TranscriptionSpeaker,
    TranscriptionEdit,
    TranscriptionEntry,
  } from "../../page_data/TranscriptionDetailPageData.types";
  import { formatTime, formatTimestamp } from "./transcription-utils";

  let {
    speakers,
    speakerColorMap,
    filterSpeaker,
    showOriginal,
    edits,
    entries,
    database,
    onToggleFilter,
    onToggleShowOriginal,
    onCreateSpeaker,
    onRenameSpeaker,
    onUpdateSpeaker,
    onUploadPhoto,
    onCombineSpeakers,
    onDeleteSpeaker,
  }: {
    speakers: TranscriptionSpeaker[];
    speakerColorMap: Record<number, string>;
    filterSpeaker: number | null;
    showOriginal: boolean;
    edits: TranscriptionEdit[];
    entries: TranscriptionEntry[];
    database: string;
    onToggleFilter: (id: number) => void;
    onToggleShowOriginal: () => void;
    onCreateSpeaker: (name: string) => void;
    onRenameSpeaker: (speaker: TranscriptionSpeaker, newName: string) => void;
    onUpdateSpeaker: (
      speaker: TranscriptionSpeaker,
      fields: { name?: string; description?: string },
    ) => Promise<boolean>;
    onUploadPhoto: (
      speaker: TranscriptionSpeaker,
      fileData: string,
    ) => Promise<boolean>;
    onCombineSpeakers: (fromId: number, toId: number) => void;
    onDeleteSpeaker: (id: number) => void;
  } = $props();

  // Internal state
  let newSpeakerName = $state("");
  let renamingSpeakerId: number | null = $state(null);
  let renameText = $state("");
  let openMenuSpeakerId: number | null = $state(null);
  let combiningFromSpeaker: number | null = $state(null);
  let historyOpen = $state(false);

  // Profile editor state
  let editingProfileId: number | null = $state(null);
  let editDescription = $state("");
  let profileError: string | null = $state(null);
  let savingProfile = $state(false);
  // Bumped after a photo upload to bust the <img> cache for re-uploads.
  let photoBust = $state(0);

  function toggleSpeakerMenu(id: number) {
    openMenuSpeakerId = openMenuSpeakerId === id ? null : id;
    combiningFromSpeaker = null;
  }

  function closeSpeakerMenu() {
    openMenuSpeakerId = null;
    combiningFromSpeaker = null;
  }

  function startRenamingSpeaker(speaker: TranscriptionSpeaker) {
    renamingSpeakerId = speaker.id;
    renameText = speaker.name;
  }

  function cancelRenaming() {
    renamingSpeakerId = null;
    renameText = "";
  }

  function saveRename(speaker: TranscriptionSpeaker) {
    const newName = renameText.trim();
    if (!newName || newName === speaker.name) {
      cancelRenaming();
      return;
    }
    onRenameSpeaker(speaker, newName);
    cancelRenaming();
  }

  function handleCreate() {
    if (!newSpeakerName.trim()) return;
    onCreateSpeaker(newSpeakerName.trim());
    newSpeakerName = "";
  }

  function speakerEntryCount(id: number): number {
    return entries.filter((e) => e.speaker_id === id).length;
  }

  // --- Profile editor ---
  function startEditingProfile(speaker: TranscriptionSpeaker) {
    editingProfileId = speaker.id;
    editDescription = speaker.description ?? "";
    profileError = null;
  }

  function cancelProfile() {
    editingProfileId = null;
    editDescription = "";
    profileError = null;
  }

  async function saveProfile(speaker: TranscriptionSpeaker) {
    savingProfile = true;
    profileError = null;
    const ok = await onUpdateSpeaker(speaker, { description: editDescription });
    savingProfile = false;
    if (ok) {
      cancelProfile();
    } else {
      profileError = "Failed to save";
    }
  }

  async function fileToBase64(file: File): Promise<string> {
    const buf = new Uint8Array(await file.arrayBuffer());
    let s = "";
    for (const b of buf) s += String.fromCharCode(b);
    return btoa(s);
  }

  async function onPhotoSelected(e: Event, speaker: TranscriptionSpeaker) {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = ""; // allow re-selecting the same file
    if (!file) return;
    profileError = null;
    const okType = file.type === "image/png" || file.type === "image/jpeg";
    const okSize = file.size <= 1_048_576;
    if (!okType) {
      profileError = "Photo must be PNG or JPEG";
      return;
    }
    if (!okSize) {
      profileError = "Photo exceeds 1 MB";
      return;
    }
    savingProfile = true;
    const fileData = await fileToBase64(file);
    const ok = await onUploadPhoto(speaker, fileData);
    savingProfile = false;
    if (ok) {
      photoBust++;
    } else {
      profileError = "Upload failed";
    }
  }

  function photoUrl(speaker: TranscriptionSpeaker): string {
    const bust = photoBust > 0 ? `?v=${photoBust}` : "";
    return `/${database}/-/api/scribe/speakers/${speaker.id}/photo${bust}`;
  }

  function formatEditDescription(edit: TranscriptionEdit): string {
    try {
      const d = JSON.parse(edit.detail);
      switch (edit.operation) {
        case "edit_text": {
          const entry = entries.find((e) => e.id === edit.entry_id);
          const timeStr = entry ? ` at ${formatTime(entry.start)}` : "";
          return `Changed text of entry${timeStr}`;
        }
        case "reassign_speaker":
          return "Reassigned a speaker on an entry";
        case "create_speaker":
          return `Created speaker "${d.name}"`;
        case "combine_speakers":
          return `Combined two speakers (${d.affected_entries} entries)`;
        case "delete_speaker":
          return `Deleted a speaker (${d.affected_entries} entries unassigned)`;
        case "rename_speaker":
          return `Renamed speaker "${d.old_name}" to "${d.new_name}"`;
        default:
          return edit.operation;
      }
    } catch {
      return edit.operation;
    }
  }
</script>

<aside class="sidebar">
  <h2 class="sidebar-title">Speakers</h2>
  <div class="speaker-list">
    {#each speakers as speaker}
      <div class="speaker-row">
        {#if speaker.has_photo}
          <img class="speaker-photo" src={photoUrl(speaker)} alt={speaker.name} />
        {:else}
          <span class="legend-dot" style="background: {speakerColorMap[speaker.id] ?? '#999'}"></span>
        {/if}
        {#if renamingSpeakerId === speaker.id}
          <input
            type="text"
            class="rename-input"
            bind:value={renameText}
            onkeydown={(e) => {
              if (e.key === "Enter") saveRename(speaker);
              if (e.key === "Escape") cancelRenaming();
            }}
          />
          <div class="speaker-actions">
            <button class="btn-small btn-primary" onclick={() => saveRename(speaker)}>Save</button>
            <button class="btn-small" onclick={cancelRenaming}>Cancel</button>
          </div>
        {:else}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <!-- svelte-ignore a11y_no_static_element_interactions -->
          <span class="speaker-name" class:speaker-name-active={filterSpeaker === speaker.id} onclick={() => onToggleFilter(speaker.id)} title="Click to filter">{speaker.name}</span>
          <span class="speaker-count">{speakerEntryCount(speaker.id)}</span>
          {#if speaker.is_configured}
            <span class="speaker-badge">custom</span>
          {/if}
          <div class="speaker-menu-wrapper">
            <button class="btn-dots" onclick={() => toggleSpeakerMenu(speaker.id)} title="More actions">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>
            </button>
            {#if openMenuSpeakerId === speaker.id}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <!-- svelte-ignore a11y_no_static_element_interactions -->
              <div class="speaker-menu-backdrop" onclick={closeSpeakerMenu}></div>
              <div class="speaker-menu">
                <button class="menu-item" onclick={() => { closeSpeakerMenu(); startEditingProfile(speaker); }}>Edit profile</button>
                <button class="menu-item" onclick={() => { closeSpeakerMenu(); startRenamingSpeaker(speaker); }}>Rename</button>
                {#if combiningFromSpeaker === speaker.id}
                  <div class="menu-submenu">
                    <span class="menu-label">Merge into:</span>
                    {#each speakers.filter((s) => s.id !== speaker.id) as other}
                      <button class="menu-item" onclick={() => { closeSpeakerMenu(); onCombineSpeakers(speaker.id, other.id); }}>{other.name}</button>
                    {/each}
                  </div>
                {:else}
                  <button class="menu-item" onclick={() => { combiningFromSpeaker = speaker.id; }}>Merge into...</button>
                {/if}
                <button class="menu-item menu-item-danger" onclick={() => { closeSpeakerMenu(); onDeleteSpeaker(speaker.id); }}>Delete</button>
              </div>
            {/if}
          </div>
        {/if}
      </div>
      {#if editingProfileId === speaker.id}
        <div class="profile-editor">
          <textarea
            class="profile-description"
            bind:value={editDescription}
            placeholder="Description"
            rows="2"
          ></textarea>
          <label class="photo-label">
            {speaker.has_photo ? "Replace photo" : "Upload photo"} (PNG/JPEG, ≤ 1 MB)
            <input type="file" accept="image/png,image/jpeg" onchange={(e) => onPhotoSelected(e, speaker)} disabled={savingProfile} />
          </label>
          {#if profileError}
            <span class="profile-error">{profileError}</span>
          {/if}
          <div class="speaker-actions">
            <button class="btn-small btn-primary" onclick={() => saveProfile(speaker)} disabled={savingProfile}>
              {savingProfile ? "Saving..." : "Save"}
            </button>
            <button class="btn-small" onclick={cancelProfile} disabled={savingProfile}>Cancel</button>
          </div>
        </div>
      {/if}
    {/each}
  </div>
  <div class="new-speaker-row">
    <input
      type="text"
      bind:value={newSpeakerName}
      placeholder="New speaker..."
      class="new-speaker-input"
      onkeydown={(e) => { if (e.key === "Enter") handleCreate(); }}
    />
    <button class="btn-small" onclick={handleCreate} disabled={!newSpeakerName.trim()}>
      Add
    </button>
  </div>

  <!-- Toolbar in sidebar -->
  <div class="sidebar-toolbar">
    <label class="toggle-label">
      <input type="checkbox" checked={showOriginal} onchange={onToggleShowOriginal} />
      Show original
    </label>
  </div>

  <!-- Edit history in sidebar -->
  <div class="sidebar-section">
    <button class="sidebar-section-toggle" onclick={() => (historyOpen = !historyOpen)}>
      {historyOpen ? "▾" : "▸"} Edit history ({edits.length})
    </button>
    {#if historyOpen}
      <div class="edit-history">
        {#if edits.length === 0}
          <p class="empty">No edits yet.</p>
        {:else}
          {#each edits as edit}
            <div class="edit-row">
              <span class="edit-desc">{formatEditDescription(edit)}</span>
              <span class="edit-time">{formatTimestamp(edit.created_at)}</span>
            </div>
          {/each}
        {/if}
      </div>
    {/if}
  </div>
</aside>

<style>
  .sidebar {
    width: 220px;
    flex-shrink: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-size: 0.85rem;
  }

  .sidebar-title {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #888;
    margin: 0;
  }

  .speaker-list {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .speaker-row {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.4rem;
    border-radius: 6px;
    flex-wrap: wrap;
  }
  .speaker-row:hover {
    background: #f5f5f5;
  }

  .legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .speaker-photo {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
    background: #eee;
  }

  .speaker-name {
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 8rem;
  }
  .speaker-name:hover {
    text-decoration: underline;
  }
  .speaker-name-active {
    background: #e8f4fd;
    border-radius: 3px;
    padding: 0 0.2rem;
  }

  .rename-input {
    font-size: 0.8rem;
    padding: 0.15rem 0.3rem;
    border: 1px solid #4a90d9;
    border-radius: 4px;
    width: 100%;
    min-width: 0;
    flex: 1;
  }

  .speaker-actions {
    display: flex;
    gap: 0.25rem;
  }

  .speaker-count {
    color: #aaa;
    font-size: 0.75rem;
    margin-left: auto;
  }

  .speaker-badge {
    font-size: 0.65rem;
    background: #e8f4fd;
    color: #2980b9;
    padding: 0.05rem 0.3rem;
    border-radius: 3px;
  }

  .speaker-menu-wrapper {
    position: relative;
    margin-left: auto;
    flex-shrink: 0;
  }

  .btn-dots {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: #999;
    cursor: pointer;
    padding: 0;
  }
  .btn-dots:hover {
    background: #e8e8e8;
    color: #555;
  }

  .speaker-menu-backdrop {
    position: fixed;
    inset: 0;
    z-index: 9;
  }

  .speaker-menu {
    position: absolute;
    right: 0;
    top: 100%;
    z-index: 10;
    background: white;
    border: 1px solid #ddd;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
    min-width: 140px;
    padding: 0.25rem 0;
  }

  .menu-item {
    display: block;
    width: 100%;
    text-align: left;
    padding: 0.35rem 0.75rem;
    border: none;
    background: none;
    cursor: pointer;
    font-size: 0.8rem;
    color: #333;
  }
  .menu-item:hover {
    background: #f0f0f0;
  }

  .menu-item-danger {
    color: #c00;
  }
  .menu-item-danger:hover {
    background: #fef0f0;
  }

  .menu-submenu {
    border-top: 1px solid #eee;
    padding-top: 0.2rem;
  }

  .menu-label {
    display: block;
    padding: 0.2rem 0.75rem;
    font-size: 0.7rem;
    color: #999;
    font-weight: 600;
  }

  .profile-editor {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    padding: 0.4rem 0.5rem 0.6rem;
    margin: 0 0.4rem 0.4rem;
    background: #f7f9fc;
    border: 1px solid #e3e9f0;
    border-radius: 6px;
  }

  .profile-description {
    width: 100%;
    box-sizing: border-box;
    font-size: 0.8rem;
    padding: 0.3rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    resize: vertical;
    font-family: inherit;
  }

  .photo-label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    font-size: 0.72rem;
    color: #666;
  }

  .profile-error {
    color: #c00;
    font-size: 0.72rem;
  }

  .new-speaker-row {
    display: flex;
    gap: 0.35rem;
    padding-top: 0.5rem;
    border-top: 1px solid #eee;
  }

  .new-speaker-input {
    flex: 1;
    padding: 0.25rem 0.4rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 0.8rem;
    min-width: 0;
  }

  .sidebar-toolbar {
    padding-top: 0.5rem;
    border-top: 1px solid #eee;
  }

  .toggle-label {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    cursor: pointer;
    color: #555;
    font-size: 0.8rem;
  }

  .sidebar-section {
    border-top: 1px solid #eee;
    padding-top: 0.5rem;
  }

  .sidebar-section-toggle {
    display: block;
    width: 100%;
    text-align: left;
    padding: 0;
    background: none;
    border: none;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
    color: #555;
  }
  .sidebar-section-toggle:hover {
    color: #333;
  }

  .edit-history {
    margin-top: 0.4rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    max-height: 200px;
    overflow-y: auto;
  }

  .edit-row {
    display: flex;
    flex-direction: column;
    font-size: 0.75rem;
    padding: 0.2rem 0;
    border-bottom: 1px solid #f0f0f0;
  }
  .edit-row:last-child {
    border-bottom: none;
  }

  .edit-time {
    color: #aaa;
    font-size: 0.7rem;
  }

  .edit-desc {
    color: #555;
  }

  .empty {
    color: #666;
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
