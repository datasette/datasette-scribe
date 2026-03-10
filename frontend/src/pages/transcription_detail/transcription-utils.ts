import type { TranscriptionEntry } from "../../page_data/TranscriptionDetailPageData.types";

export const SPEAKER_COLORS = [
  "#4a90d9",
  "#d94a6b",
  "#50b86c",
  "#d9a34a",
  "#9b59b6",
  "#e67e22",
  "#1abc9c",
  "#e74c3c",
];

export function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function colorFor(
  entry: TranscriptionEntry,
  speakerColorMap: Record<string, string>,
): string {
  return (
    speakerColorMap[entry.speaker_id ?? "unknown"] ?? SPEAKER_COLORS[0]!
  );
}

export function isEntryEdited(entry: TranscriptionEntry): boolean {
  return (
    (entry.original_text != null && entry.text !== entry.original_text) ||
    (entry.original_speaker_id !== undefined &&
      entry.speaker_id !== entry.original_speaker_id)
  );
}

export function parseUTC(iso: string): Date {
  // SQLite timestamps lack a Z suffix; ensure they're parsed as UTC
  return new Date(iso.endsWith("Z") ? iso : iso + "Z");
}

export function formatTimestamp(iso: string): string {
  try {
    return parseUTC(iso).toLocaleString();
  } catch {
    return iso;
  }
}
