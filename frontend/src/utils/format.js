export function formatSize(bytes = 0) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(value) {
  if (!value) return "Not processed";
  return new Date(value).toLocaleString();
}

export function asText(value) {
  if (Array.isArray(value)) return value.join(" ");
  return value || "";
}
