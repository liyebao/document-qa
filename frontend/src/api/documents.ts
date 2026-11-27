import { API_BASE, request } from "./client";
import type { DocumentItem, DocumentPreview } from "./types";

export function documentFileUrl(documentId: string, page?: number | null): string {
  const url = `${API_BASE}/documents/${documentId}/file`;
  return page ? `${url}#page=${page}` : url;
}

/** 按原文件重新排版成的 HTML，供 Office 等浏览器不能直接渲染的格式预览。 */
export function documentRenderUrl(documentId: string): string {
  return `${API_BASE}/documents/${documentId}/render`;
}

export function listDocuments(collectionId: string): Promise<DocumentItem[]> {
  return request<DocumentItem[]>(`/collections/${collectionId}/documents`);
}

export function uploadDocument(collectionId: string, file: File): Promise<DocumentItem> {
  const form = new FormData();
  form.append("file", file);
  return request<DocumentItem>(`/collections/${collectionId}/documents`, {
    method: "POST",
    body: form,
  });
}

/** 解析后的片段序列，用于抽屉内预览非 PDF 文件并定位引用。 */
export function getDocumentPreview(documentId: string): Promise<DocumentPreview> {
  return request<DocumentPreview>(`/documents/${documentId}/preview`);
}

export function createTextDocument(
  collectionId: string,
  title: string,
  content: string,
): Promise<DocumentItem> {
  return request<DocumentItem>(`/collections/${collectionId}/documents/text`, {
    method: "POST",
    body: JSON.stringify({ title, content }),
  });
}

export function importUrlDocument(
  collectionId: string,
  url: string,
): Promise<DocumentItem> {
  return request<DocumentItem>(`/collections/${collectionId}/documents/url`, {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export function replaceDocument(documentId: string, file: File): Promise<DocumentItem> {
  const form = new FormData();
  form.append("file", file);
  return request<DocumentItem>(`/documents/${documentId}/replace`, {
    method: "POST",
    body: form,
  });
}

export function retryDocument(documentId: string): Promise<DocumentItem> {
  return request<DocumentItem>(`/documents/${documentId}/retry`, {
    method: "POST",
  });
}

export function setDocumentEnabled(
  documentId: string,
  enabled: boolean,
): Promise<DocumentItem> {
  return request<DocumentItem>(`/documents/${documentId}`, {
    method: "PATCH",
    body: JSON.stringify({ is_enabled: enabled }),
  });
}

export function deleteDocument(documentId: string): Promise<void> {
  return request<void>(`/documents/${documentId}`, { method: "DELETE" });
}
