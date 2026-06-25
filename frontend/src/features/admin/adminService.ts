import { apiRequest } from "../../lib/api";
import { DocumentProcessingStatus, DocumentRead, UUID } from "../../lib/types";

export interface MetadataUpdatePayload {
  title?: string;
  summary?: string;
  source_organisation?: string;
  source_url?: string;
  policy_area?: string;
  country_or_region?: string;
  published_year?: number;
  tags?: string[];
  credibility_level?: string;
}

export function uploadAdminDocument(formData: FormData) {
  return apiRequest<{ document_id: UUID; processing_status: string }>("/admin/documents", {
    method: "POST",
    headers: {},
    body: formData
  });
}

export function updateAdminDocument(documentId: UUID, payload: MetadataUpdatePayload) {
  return apiRequest<DocumentRead>(`/admin/documents/${documentId}`, {
    method: "PATCH",
    body: payload
  });
}

export function deleteAdminDocument(documentId: UUID) {
  return apiRequest<void>(`/admin/documents/${documentId}`, {
    method: "DELETE"
  });
}

export function getProcessingStatus(documentId: UUID) {
  return apiRequest<DocumentProcessingStatus>(`/admin/documents/${documentId}/processing-status`);
}
