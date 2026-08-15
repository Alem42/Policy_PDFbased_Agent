const API_PREFIX = "/api/v1";

function apiPath(path) {
  return `${API_PREFIX}${path}`;
}

async function errorMessageFrom(response) {
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
  return message;
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
  throw new Error(await errorMessageFrom(response));
}

function normaliseDocument(document) {
  const metadata = document.metadata || {};
  const source = document.source || {};
  const policyAreas =
    document.policy_areas ??
    metadata.policy_areas ??
    (document.policy_area ? [document.policy_area] : []);
  const keywords = document.keywords ?? metadata.keywords ?? document.tags ?? [];
  const originalFilename =
    document.original_filename ?? source.original_filename ?? document.name ?? null;
  const title = document.title ?? metadata.title ?? originalFilename ?? document.id;
  const name = originalFilename ?? title;

  return {
    ...document,
    id: document.id,
    name,
    original_filename: originalFilename ?? name,
    title,
    summary: document.summary ?? metadata.summary ?? null,
    status: document.processing_status ?? document.status ?? "uploaded",
    country_region:
      document.country_region ?? metadata.country_region ?? document.country_or_region ?? null,
    source_type:
      document.source_type ?? metadata.source_type ?? source.source_type ?? document.credibility_level ?? null,
    source_organisation:
      document.source_organisation ?? metadata.source_organisation ?? source.source_organisation ?? null,
    source_url: document.source_url ?? source.source_url ?? null,
    language: document.language ?? metadata.language ?? null,
    policy_areas: policyAreas,
    keywords,
    stakeholders: document.stakeholders ?? metadata.stakeholders ?? [],
    implementation_risks:
      document.implementation_risks ?? metadata.implementation_risks ?? [],
    year: document.year ?? metadata.year ?? document.published_year ?? null,
    publication_date: document.publication_date ?? metadata.publication_date ?? null,
    mime_type: document.mime_type ?? source.mime_type ?? null,
    size: document.size ?? document.file_size ?? source.file_size ?? 0,
    modified_at:
      document.modified_at ?? (Date.parse(document.uploaded_at || "") / 1000 || 0),
    page_count: document.page_count ?? 0,
    chunk_count: document.chunk_count ?? 0,
    approved: document.approved ?? true,
    access_level: document.access_level ?? source.access_level ?? "public",
    metadata_json: document.metadata_json ?? metadata.metadata ?? {},
  };
}

function normaliseChunk(chunk) {
  return {
    ...chunk,
    id: chunk.id,
    text: chunk.text ?? chunk.text_preview ?? "",
    metadata_json: chunk.metadata_json ?? chunk.metadata ?? {},
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

export function register({ username, email, password, passwordConfirmation, role, inviteCode }) {
  const body = {
    username,
    email,
    password,
    password_confirmation: passwordConfirmation,
    role,
  };
  if (inviteCode) body.invite_code = inviteCode;
  return request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getCurrentUser() {
  return request("/auth/me");
}

export async function getDocuments() {
  const documents = await request("/documents");
  return { documents: documents.map(normaliseDocument) };
}

export async function searchDocuments(filters = {}, options = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "" && value !== "all") {
      params.set(key, String(value));
    }
  }
  const result = await request(`/documents/search?${params.toString()}`, options);
  return {
    ...result,
    items: result.items.map(normaliseDocument),
  };
}

export function rescanDocuments() {
  return request("/admin/documents/rescan", {
    method: "POST",
  });
}

// Re-embed existing chunks into the active embedding model's vector table.
// Cheaper than a rescan (no re-extract/re-chunk) and preserves other models'
// vectors — used after switching the embedding model.
export function reembedLibrary() {
  return request("/admin/documents/reembed", {
    method: "POST",
  });
}

// Reprocess a single document (re-extract, re-chunk, re-metadata, re-embed).
export function rescanFile(documentId) {
  return request(`/admin/documents/${encodeURIComponent(documentId)}/rescan`, {
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

export async function openDocumentFile(documentId, page = null) {
  const token = localStorage.getItem("authToken");
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(getDocumentFileUrl(documentId), { headers });
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`);
  const blob = await response.blob();
  const pageFragment = Number.isInteger(page) && page > 0 ? `#page=${page}` : "";
  window.open(`${URL.createObjectURL(blob)}${pageFragment}`, "_blank", "noopener,noreferrer");
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

export function importWebDocument(url, title = "") {
  return request("/admin/documents/import-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, ...(title.trim() ? { title: title.trim() } : {}) }),
  });
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

// Maximum number of prior conversation turns to send to the backend.
// Each turn = one user message + one assistant reply.
const MAX_HISTORY_TURNS = 5;

async function postForSSE(path, body, signal) {
  const token = localStorage.getItem("authToken");
  const response = await fetch(apiPath(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    throw new Error(await errorMessageFrom(response));
  }
  return response;
}

async function* readSSEFrames(response) {
  if (!response.body) {
    throw new Error("The server returned an empty stream.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by \n\n
      const parts = buffer.split("\n\n");
      buffer = parts.pop(); // keep any incomplete trailing fragment

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data: ")) continue;
        const payload = line.slice(6).trim();
        try {
          yield JSON.parse(payload);
        } catch { /* skip malformed frames */ }
      }
    }
  } finally {
    // Release the connection even when the consumer exits early (e.g. the
    // stream pauses on an ask_user interrupt and the generator is closed).
    reader.cancel().catch(() => {});
  }
}

/**
 * Streaming version of askQuestion, driven by the web-search agent.
 * Returns an async generator that yields SSE event objects:
 *   {type:"tool_call",tool:str} | {type:"tool_result",tool:str,evidence_sufficient}
 *   | {type:"token",value:str}
 *   | {type:"ask_user",session_id,mode:"confirm"|"choice"|"freeform",question,options:[str]|null}
 *   | {type:"confirm_import",session_id,url,title,question}
 *   | {type:"citations",data:[],evidence_sufficient,evidence_reason,response_mode,answer_mode,session_id}
 *   | {type:"answer_done",suggestions_pending:bool} | {type:"suggestions",items:[str]}
 *   | {type:"done"} | {type:"error",message:str}
 * An ask_user/confirm_import event ends the stream — call resumeChatStream()
 * with the user's answer to continue it.
 */
export async function* askQuestionStream(
  question,
  documentIds,
  responseMode = "researcher",
  answerMode = "analysis",
  history = [],
  sessionId = null,
  model = null,
  signal = null,
  agentMode = "react",
) {
  const body = {
    question,
    document_ids: documentIds,
    response_mode: responseMode,
    answer_mode: answerMode,
    agent_mode: agentMode,
    session_id: sessionId,
  };
  if (model) body.model = model;
  if (!sessionId) {
    body.history = history.slice(-(MAX_HISTORY_TURNS * 2)).map((msg) => ({
      role: msg.role,
      content: msg.content,
    }));
  }
  const response = await postForSSE("/chat/stream", body, signal);
  yield* readSSEFrames(response);
}

/**
 * Resumes a chat turn paused by an ask_user/confirm_import event.
 * `answer` is whatever that interrupt expects back: a string (one of the
 * event's `options`, or any free-typed text) for ask_user, a boolean for
 * confirm_import. Yields the same SSE event shapes as askQuestionStream().
 */
export async function* resumeChatStream(sessionId, answer, signal = null) {
  const response = await postForSSE("/chat/resume", { session_id: sessionId, answer }, signal);
  yield* readSSEFrames(response);
}

// Models selectable per-message, grouped by provider. Only providers with a
// configured API key are returned by the backend.
export function getChatModels() {
  return request("/chat/models");
}

// ── Chat history API ───────────────────────────────────────────────────────

export function getChatSessions() {
  return request("/chat/sessions");
}

export function getChatSession(sessionId) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}`);
}

export function deleteChatSession(sessionId) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}

export function renameChatSession(sessionId, title) {
  return request(`/chat/sessions/${encodeURIComponent(sessionId)}/title`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
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

// ── Embedding settings (admin) ─────────────────────────────────────────────
// Backend endpoints TBD; the Manage > Embedding page degrades gracefully to a
// local draft when these 404, so the interface can be wired later.

export function getEmbeddingSettings() {
  return request("/admin/embedding");
}

export function saveEmbeddingSettings(payload) {
  return request("/admin/embedding", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function testEmbeddingConnection(payload) {
  return request("/admin/embedding/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Reranking settings (admin) ─────────────────────────────────────────────

export function getRerankingSettings() {
  return request("/admin/reranking");
}

export function saveRerankingSettings(payload) {
  return request("/admin/reranking", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function testRerankingConnection(payload) {
  return request("/admin/reranking/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Model catalog (admin) ──────────────────────────────────────────────────
// Known provider/model/endpoint reference (no keys). Powers the pick-a-model
// dropdowns on the embedding/reranker pages.

export function getModelCatalog(capability) {
  const query = capability ? `?capability=${encodeURIComponent(capability)}` : "";
  return request(`/admin/catalog${query}`);
}

export function addCatalogEntry(payload) {
  return request("/admin/catalog", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function addCatalogProvider(payload) {
  return request("/admin/catalog/providers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Policy taxonomy (two-level categories) ──────────────────────────────────

// Returns { groups: [{ parent, children: [], source_ref }] }
// ── Follow-up suggestions ────────────────────────────────────────────────
export function getSuggestionSettings() {
  return request("/admin/suggestions");
}

export function saveSuggestionSettings(payload) {
  return request("/admin/suggestions", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// Best-effort click log for personalization; ignore failures.
export function logSuggestionClick(sessionId, question) {
  return request("/chat/suggestions/click", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId || null, question }),
  }).catch(() => {});
}

// ── Agent tool limits ────────────────────────────────────────────────────
export function getAgentToolLimits() {
  return request("/admin/agent-tool-limits");
}

export function saveAgentToolLimits(payload) {
  return request("/admin/agent-tool-limits", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Agent run observability (admin) ───────────────────────────────────────
export function getAgentRuns(limit = 50) {
  return request(`/admin/agent-runs?limit=${encodeURIComponent(limit)}`);
}

export function getAgentRun(runId) {
  return request(`/admin/agent-runs/${encodeURIComponent(runId)}`);
}

export function getAdminInvites() {
  return request("/admin/invites");
}

export function createAdminInvite(expiresInDays) {
  return request("/admin/invites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expires_in_days: expiresInDays }),
  });
}

export function revokeAdminInvite(inviteId) {
  return request(`/admin/invites/${inviteId}`, { method: "DELETE" });
}

export function getTaxonomy() {
  return request("/taxonomy");
}

// Admin-only: replace the whole taxonomy tree.
export function saveTaxonomy(groups) {
  return request("/admin/taxonomy", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ groups }),
  });
}
