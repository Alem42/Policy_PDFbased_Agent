const API_PREFIX = "/api/v1";

function apiPath(path) {
  return `${API_PREFIX}${path}`;
}

async function request(path, options = {}) {
  const token = localStorage.getItem("authToken");
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(apiPath(path), { ...options, headers });
  if (response.ok) {
    if (response.status === 204) return null;
    return response.json();
  }

  let message = `Request failed with status ${response.status}`;
  try {
    const body = await response.json();
    if (Array.isArray(body.detail)) {
      message = body.detail
        .map((item) => item.msg || item.message || JSON.stringify(item))
        .join("; ");
    } else if (typeof body.detail === "object" && body.detail !== null) {
      message = body.detail.message || JSON.stringify(body.detail);
    } else {
      message = body.detail || message;
    }
  } catch {
    // Keep the HTTP fallback message.
  }
  throw new Error(message);
}

function normaliseDocument(document) {
  const policyAreas = document.policy_areas || (document.policy_area ? [document.policy_area] : []);
  const keywords = document.keywords || document.tags || [];
  const name = document.name || document.original_filename || document.title || document.id;
  return {
    ...document,
    id: document.id,
    name,
    original_filename: document.original_filename || name,
    title: document.title || name,
    status: document.processing_status || document.status || "uploaded",
    country_region: document.country_region || document.country_or_region || null,
    source_type: document.source_type || document.credibility_level || null,
    policy_areas: policyAreas,
    keywords,
    year: document.year || document.published_year || null,
    size: document.size || 0,
    modified_at: document.modified_at || Date.parse(document.uploaded_at || "") / 1000 || 0,
    page_count: document.page_count || 0,
    chunk_count: document.chunk_count || 0,
    approved: document.approved ?? true,
    access_level: document.access_level || "public",
    metadata_json: document.metadata_json || {},
  };
}

function normaliseChunk(chunk) {
  return {
    ...chunk,
    id: chunk.id,
    text: chunk.text || chunk.text_preview || "",
  };
}

export function saveAuth(auth) {
  localStorage.setItem("authToken", auth.token);
  localStorage.setItem("authUser", JSON.stringify(auth.user));
}

export function clearAuth() {
  localStorage.removeItem("authToken");
  localStorage.removeItem("authUser");
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("authUser") || "null");
  } catch {
    return null;
  }
}

export function login(username, password) {
  return request("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export function register(username, password, role) {
  return request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, role }),
  });
}

export function getCurrentUser() {
  return request("/auth/me");
}

export async function getDocuments() {
  const documents = await request("/documents");
  return { documents: documents.map(normaliseDocument) };
}

export function rescanDocuments() {
  return request("/admin/documents/rescan", {
    method: "POST",
  });
}

export async function getDocumentDetail(documentId) {
  return normaliseDocument(await request(`/documents/${encodeURIComponent(documentId)}`));
}

export async function getDocumentChunks(documentId) {
  const chunks = await request(`/documents/${encodeURIComponent(documentId)}/chunks`);
  return { document_id: documentId, chunks: chunks.map(normaliseChunk) };
}

export function getDocumentFileUrl(documentId) {
  return apiPath(`/documents/${encodeURIComponent(documentId)}/file`);
}

export async function openDocumentFile(documentId) {
  const token = localStorage.getItem("authToken");
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(getDocumentFileUrl(documentId), { headers });
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
  const blob = await response.blob();
  window.open(URL.createObjectURL(blob), "_blank", "noopener,noreferrer");
}

export async function uploadDocuments(files) {
  const uploaded = [];
  for (const file of files) {
    const formData = new FormData();
    formData.append("file", file);
    uploaded.push(
      await request("/admin/documents", {
        method: "POST",
        body: formData,
      }),
    );
  }
  return uploaded;
}

export function deleteDocument(documentId) {
  return request(`/admin/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE",
  });
}

export function updateDocument(documentId, updates) {
  return request(`/admin/documents/${encodeURIComponent(documentId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
}

export function getDocumentPages(documentId) {
  return request(`/documents/${encodeURIComponent(documentId)}/pages`);
}

export function askQuestion(question, documentIds, responseMode = "researcher") {
  return request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      document_ids: documentIds,
      response_mode: responseMode,
    }),
  });
}

export function getSettings() {
  return request("/settings");
}

export function saveSettings(settings) {
  return request("/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
}

export function getProcessingStatus(documentId) {
  return request(`/admin/documents/${encodeURIComponent(documentId)}/processing-status`);
}
