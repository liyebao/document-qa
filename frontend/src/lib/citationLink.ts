import { documentFileUrl } from "../api/documents";
import type { Citation } from "../api/types";

export function citationPage(sourceLocation: string): number | null {
  const match = sourceLocation.match(/第\s*(\d+)(?:\s*[–-]\s*\d+)?\s*页/);
  return match ? Number(match[1]) : null;
}

export function citationFileUrl(citation: Citation): string | null {
  if (!citation.document_id) {
    return null;
  }
  return documentFileUrl(citation.document_id, citationPage(citation.source_location));
}
