import { apiRequest } from "../../lib/api";
import { CrawlJobRead, TrustedSourceRead, UUID } from "../../lib/types";

export interface TrustedSourceCreatePayload {
  name: string;
  start_url: string;
  allowed_domains: string[];
  policy_area?: string;
  enabled: boolean;
}

export interface CrawlJobCreatePayload {
  trusted_source_id: UUID;
  dry_run: boolean;
  max_pages: number;
}

export function listTrustedSources() {
  return apiRequest<TrustedSourceRead[]>("/trusted-sources");
}

export function createTrustedSource(payload: TrustedSourceCreatePayload) {
  return apiRequest<TrustedSourceRead>("/trusted-sources", {
    method: "POST",
    body: payload
  });
}

export function createCrawlJob(payload: CrawlJobCreatePayload) {
  return apiRequest<CrawlJobRead>("/crawl-jobs", {
    method: "POST",
    body: payload
  });
}

export function getCrawlJob(jobId: UUID) {
  return apiRequest<CrawlJobRead>(`/crawl-jobs/${jobId}`);
}
