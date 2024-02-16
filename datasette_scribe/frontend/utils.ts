export function formatDuration(seconds: number): string {
  var hours = Math.floor(seconds / 3600);
  var minutes = Math.floor((seconds % 3600) / 60);
  var secs = Math.floor(seconds % 60);

  let result = "";
  if (hours) result += String(hours).padStart(2, "0") + ":";
  result += String(minutes).padStart(2, "0") + ":";
  result += String(secs).padStart(2, "0");

  return result;
}
