import { apiRequest } from "../../lib/api";
import { DocumentChunkRead, DocumentRead, UUID } from "../../lib/types";

export function listDocuments(query = "") {
  const search = query ? `?search=${encodeURIComponent(query)}` : "";
  return apiRequest<DocumentRead[]>(`/documents${search}`);
}

export function getDocument(documentId: UUID) {
  return apiRequest<DocumentRead>(`/documents/${documentId}`);
}

export function getDocumentChunks(documentId: UUID) {
  return apiRequest<DocumentChunkRead[]>(`/documents/${documentId}/chunks`);
}
