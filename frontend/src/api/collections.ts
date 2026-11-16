import { request } from "./client";
import type {
  CollectionOut,
  CollectionReindexResult,
  CollectionSummary,
  ConversationSummary,
} from "./types";

export function listCollections(): Promise<CollectionSummary[]> {
  return request<CollectionSummary[]>("/collections");
}

export function createCollection(name: string): Promise<CollectionOut> {
  return request<CollectionOut>("/collections", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function getCollection(id: string): Promise<CollectionOut> {
  return request<CollectionOut>(`/collections/${id}`);
}

export function renameCollection(id: string, name: string): Promise<CollectionOut> {
  return request<CollectionOut>(`/collections/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function deleteCollection(id: string): Promise<void> {
  return request<void>(`/collections/${id}`, { method: "DELETE" });
}

export function reindexCollection(
  id: string,
  providerKey?: string,
): Promise<CollectionReindexResult> {
  return request<CollectionReindexResult>(`/collections/${id}/reindex`, {
    method: "POST",
    body: JSON.stringify({ provider_key: providerKey ?? null }),
    timeoutMs: 600000,
  });
}

export function listConversations(collectionId: string): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>(`/collections/${collectionId}/conversations`);
}

export function createConversation(
  collectionId: string,
  title?: string,
): Promise<ConversationSummary> {
  return request<ConversationSummary>(`/collections/${collectionId}/conversations`, {
    method: "POST",
    body: JSON.stringify({ title: title ?? null }),
  });
}
