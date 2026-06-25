export type UUID = string;

export type DocumentStatus = "active" | "archived" | "deleted";
export type ProcessingStatus = "queued" | "extracting" | "chunking" | "embedding" | "indexed" | "failed";
export type CrawlJobStatus = "queued" | "running" | "succeeded" | "failed";
export type CredibilityLevel = "official" | "academic" | "institutional" | "unknown";

export interface DocumentRead {
  id: UUID;
  title: string;
  summary?: string | null;
  source_organisation?: string | null;
  source_url?: string | null;
  policy_area?: string | null;
  country_or_region?: string | null;
  published_year?: number | null;
  tags: string[];
  credibility_level: CredibilityLevel | string;
  processing_status: ProcessingStatus | string;
  status: DocumentStatus;
  uploaded_at: string;
}

export interface DocumentChunkRead {
  chunk_id: UUID;
  document_id: UUID;
  chunk_index: number;
  page_start?: number | null;
  page_end?: number | null;
  section_title?: string | null;
  text_preview: string;
}

export interface ChatFilters {
  policy_area?: string | null;
  country_or_region?: string | null;
  source_organisation?: string | null;
  tags: string[];
  published_year_from?: number | null;
  published_year_to?: number | null;
}

export interface ChatRequest {
  question: string;
  document_ids: UUID[];
  filters: ChatFilters;
  top_k: number;
}

export interface Citation {
  document_id: UUID;
  title: string;
  chunk_id?: UUID | null;
  source_url?: string | null;
  page?: number | null;
  quote?: string | null;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
}

export interface DocumentProcessingStatus {
  document_id: UUID;
  status: ProcessingStatus;
  progress_percent: number;
  message?: string | null;
  error?: string | null;
  updated_at: string;
}

export interface TrustedSourceRead {
  id: UUID;
  name: string;
  start_url: string;
  allowed_domains: string[];
  policy_area?: string | null;
  enabled: boolean;
  created_at: string;
}

export interface CrawlJobRead {
  id: UUID;
  trusted_source_id: UUID;
  status: CrawlJobStatus;
  message?: string | null;
  created_at: string;
}
