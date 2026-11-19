import { API_BASE, ApiError, request } from "./client";
import type { ConversationDetail, MessageExchange } from "./types";

export function getConversation(id: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${id}`);
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/conversations/${id}`, { method: "DELETE" });
}

export interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone: (payload: MessageExchange) => void;
  onError: (message: string) => void;
}

function parseEvent(raw: string): { event: string; data: string } | null {
  let event = "message";
  const data: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data.push(line.slice(5).trimStart());
    }
  }
  return data.length > 0 ? { event, data: data.join("\n") } : null;
}

export async function sendMessageStream(
  conversationId: string,
  content: string,
  documentIds: string[] | undefined,
  handlers: StreamHandlers,
  options: { signal?: AbortSignal } = {},
): Promise<void> {
  const payload: { content: string; document_ids?: string[] } = { content };
  if (documentIds && documentIds.length > 0) {
    payload.document_ids = documentIds;
  }

  const response = await fetch(
    `${API_BASE}/conversations/${conversationId}/messages/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "include",
      signal: options.signal,
    },
  );

  if (!response.ok || !response.body) {
    let message = `请求失败（${response.status}）`;
    try {
      const body = (await response.json()) as { error?: { message?: string } };
      if (body.error?.message) {
        message = body.error.message;
      }
    } catch {
      // 非 JSON 错误响应保留默认提示
    }
    throw new ApiError(response.status, "HTTP_ERROR", message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  // 只有收到 done 或 error 才算正常结束；连接被中途掐断时抛错，
  // 让界面清掉 pending 消息并重新拉取会话，而不是残留假消息。
  let finished = false;

  function consume(block: string) {
    const parsed = parseEvent(block);
    if (!parsed) {
      return;
    }
    try {
      if (parsed.event === "delta") {
        const data = JSON.parse(parsed.data) as { text?: string };
        if (data.text) {
          handlers.onDelta(data.text);
        }
      } else if (parsed.event === "done") {
        finished = true;
        handlers.onDone(JSON.parse(parsed.data) as MessageExchange);
      } else if (parsed.event === "error") {
        finished = true;
        const data = JSON.parse(parsed.data) as { message?: string };
        handlers.onError(data.message ?? "回答失败，请稍后重试");
      }
    } catch {
      // 忽略无法解析的单个事件，不影响后续增量
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let index = buffer.indexOf("\n\n");
      while (index >= 0) {
        consume(buffer.slice(0, index));
        buffer = buffer.slice(index + 2);
        index = buffer.indexOf("\n\n");
      }
    }
    if (buffer.trim()) {
      consume(buffer);
    }
  } finally {
    reader.releaseLock();
  }

  if (!finished) {
    throw new ApiError(0, "STREAM_INTERRUPTED", "连接中断，请重试");
  }
}
