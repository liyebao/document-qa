import { request } from "./client";
import type {
  ConnectionTestResult,
  ModelProviderConfig,
  ModelProviderSettings,
  ProviderModels,
} from "./types";

export function fetchProviderSettings(): Promise<ModelProviderSettings> {
  return request<ModelProviderSettings>("/settings/model-providers");
}

/** 查询本地服务商实际已下载的模型；云端服务商会返回 reachable=false。 */
export function fetchProviderModels(providerKey: string): Promise<ProviderModels> {
  return request<ProviderModels>(`/settings/model-providers/${providerKey}/models`);
}

export interface SaveProviderPayload {
  provider_key: string;
  api_key?: string;
  embedding_model?: string;
  chat_model?: string;
  rerank_model?: string;
  role?: "embedding" | "chat" | "both";
}

export function saveProvider(payload: SaveProviderPayload): Promise<ModelProviderConfig> {
  return request<ModelProviderConfig>("/settings/model-providers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function testProvider(
  configId: string,
  role?: "embedding" | "chat",
): Promise<ConnectionTestResult> {
  return request<ConnectionTestResult>(`/settings/model-providers/${configId}/test`, {
    method: "POST",
    body: JSON.stringify({ role: role ?? null }),
  });
}

export function deleteProvider(configId: string): Promise<void> {
  return request<void>(`/settings/model-providers/${configId}`, { method: "DELETE" });
}

export function setProviderRole(
  configId: string,
  role: "embedding" | "chat",
): Promise<ModelProviderSettings> {
  return request<ModelProviderSettings>(`/settings/model-providers/${configId}/role`, {
    method: "POST",
    body: JSON.stringify({ role }),
  });
}
